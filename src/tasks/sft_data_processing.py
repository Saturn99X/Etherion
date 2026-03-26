"""
SFT Data Processing Tasks

This module contains Celery tasks for batch processing of execution traces
into SFT training datasets with quality filtering and format conversion.
"""

import logging
import json
import tempfile
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from src.core.celery import celery_app
from src.services.sft_data_transformer import SFTDataTransformer, SFTFormat
from src.services.sft_quality_filter import SFTQualityFilter, QualityFilterResult
from src.services.sft_format_converter import SFTFormatConverter, OutputFormat
from src.services.fine_tuning_gcs import FineTuningGCSService

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
async def process_sft_data_batch(
    self,
    trace_ids: List[str],
    output_formats: List[str],
    batch_size: int = 50,
    strict_quality: bool = False
) -> Dict[str, Any]:
    """
    Process a batch of traces into SFT training datasets.

    Args:
        trace_ids: List of trace IDs to process
        output_formats: List of output formats to generate
        batch_size: Size of processing batches
        strict_quality: Use strict quality filtering

    Returns:
        Dict[str, Any]: Processing results and statistics
    """
    try:
        logger.info(f"Starting SFT data processing for {len(trace_ids)} traces")

        # Initialize services
        transformer = SFTDataTransformer()
        quality_filter = SFTQualityFilter()
        format_converter = SFTFormatConverter()
        gcs_service = FineTuningGCSService()

        # Convert format strings to enums
        target_formats = [SFTFormat(fmt) for fmt in output_formats]

        # Processing results
        results = {
            'total_traces': len(trace_ids),
            'processed_traces': 0,
            'filtered_traces': 0,
            'quality_report': {},
            'format_results': {},
            'errors': [],
            'processing_time': 0.0,
            'output_files': {}
        }

        start_time = datetime.utcnow()

        # Process traces in batches
        for i in range(0, len(trace_ids), batch_size):
            batch_ids = trace_ids[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {len(batch_ids)} traces")

            try:
                # Retrieve traces from GCS by explicit IDs
                batch_traces = await gcs_service.get_traces_by_ids(batch_ids)

                if not batch_traces:
                    logger.warning(f"No traces found for batch: {batch_ids}")
                    continue

                # Transform traces to training pairs
                transformation_results = await transformer.batch_transform_traces(
                    batch_traces,
                    target_formats
                )

                # Filter training pairs by quality
                filtered_pairs = {}
                quality_report = {}

                for fmt in target_formats:
                    pairs = transformation_results.get(fmt, [])

                    # Apply quality filtering
                    quality_filter.reset_filter_state()
                    filtered_batch, batch_quality_report = await quality_filter.batch_filter_traces(
                        [{'input_text': p.input_text, 'output_text': p.output_text, 'metadata': p.metadata}
                         for p in pairs],
                        strict_mode=strict_quality
                    )

                    filtered_pairs[fmt] = filtered_batch
                    quality_report[fmt.value] = batch_quality_report

                # Convert to output formats
                format_results = {}
                for fmt in target_formats:
                    pairs = filtered_pairs.get(fmt, [])

                    # Convert to output format
                    conversion_result = await format_converter.convert_training_pairs(
                        pairs,
                        OutputFormat(fmt.value),
                        include_metadata=True
                    )

                    format_results[fmt.value] = {
                        'records_generated': conversion_result.conversion_stats['records_generated'],
                        'format_compliance': conversion_result.conversion_stats['format_compliance'],
                        'estimated_size_mb': conversion_result.conversion_stats['estimated_size_mb']
                    }

                # Store results in temporary files and upload to GCS
                for fmt in target_formats:
                    pairs = filtered_pairs.get(fmt, [])

                    if pairs:
                        # Convert to desired format
                        conversion_result = await format_converter.convert_training_pairs(
                            pairs,
                            OutputFormat(fmt.value),
                            include_metadata=True
                        )

                        # Save to temporary file
                        temp_file = await _save_conversion_result_to_temp_file(conversion_result)

                        try:
                            # Upload to GCS with appropriate naming
                            batch_timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                            gcs_key = f"sft_datasets/{fmt.value}/batch_{batch_timestamp}_{i//batch_size + 1}.jsonl"

                            # Upload to fine-tuning bucket as training-ready JSONL
                            gcs_uri = await _upload_dataset_jsonl(temp_file, gcs_key, fmt.value)

                            results['output_files'][f"{fmt.value}_batch_{i//batch_size + 1}"] = {
                                'gcs_uri': gcs_uri,
                                'records_count': len(pairs),
                                'size_mb': conversion_result.conversion_stats['estimated_size_mb']
                            }

                        finally:
                            # Clean up temp file
                            os.unlink(temp_file)

                # Update results
                results['processed_traces'] += len(batch_traces)
                results['quality_report'].update(quality_report)
                results['format_results'].update(format_results)

            except Exception as e:
                logger.error(f"Error processing batch {i//batch_size + 1}: {e}")
                results['errors'].append({
                    'batch_index': i//batch_size + 1,
                    'error': str(e),
                    'trace_count': len(batch_ids)
                })

                # Retry logic for transient failures
                if self.request.retries < self.max_retries:
                    logger.info(f"Retrying batch {i//batch_size + 1} (attempt {self.request.retries + 1})")
                    raise self.retry(countdown=60 * (2 ** self.request.retries))

        # Calculate processing time
        results['processing_time'] = (datetime.utcnow() - start_time).total_seconds()

        # Generate final report
        total_filtered = sum(
            report.get('accepted_traces', 0)
            for report in results['quality_report'].values()
        )
        results['filtered_traces'] = total_filtered

        logger.info(f"SFT data processing completed: {results['processed_traces']} traces, {total_filtered} filtered pairs")

        return results

    except Exception as e:
        logger.error(f"SFT data processing failed: {e}")
        raise

@celery_app.task(bind=True, max_retries=3)
async def generate_sft_dataset_from_date_range(
    self,
    start_date: str,
    end_date: str,
    output_formats: List[str],
    job_type_filter: Optional[str] = None,
    min_quality_score: float = 0.8
) -> Dict[str, Any]:
    """
    Generate SFT dataset from traces within a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        output_formats: List of output formats to generate
        job_type_filter: Optional job type filter
        min_quality_score: Minimum quality score for inclusion

    Returns:
        Dict[str, Any]: Dataset generation results
    """
    try:
        logger.info(f"Generating SFT dataset from {start_date} to {end_date}")

        # Initialize services
        gcs_service = FineTuningGCSService()
        transformer = SFTDataTransformer()
        quality_filter = SFTQualityFilter()
        format_converter = SFTFormatConverter()

        # Convert format strings to enums
        target_formats = [SFTFormat(fmt) for fmt in output_formats]

        # Retrieve traces from date range
        traces = await gcs_service.get_ml_training_dataset(
            date_range=(start_date, end_date)
        )

        if job_type_filter:
            traces = [t for t in traces if t.get('metadata', {}).get('job_type') == job_type_filter]

        logger.info(f"Retrieved {len(traces)} traces for dataset generation")

        # Transform to training pairs
        transformation_results = await transformer.batch_transform_traces(traces, target_formats)

        # Filter by quality
        all_pairs = {}
        for fmt in target_formats:
            pairs = transformation_results.get(fmt, [])

            # Convert to dict format for filtering
            pair_dicts = [
                {
                    'input_text': p.input_text,
                    'output_text': p.output_text,
                    'metadata': p.metadata,
                    'quality_score': p.quality_score,
                    'format_type': p.format_type.value
                }
                for p in pairs
            ]

            # Apply quality filtering
            quality_filter.reset_filter_state()
            filtered_pairs, quality_report = await quality_filter.batch_filter_traces(
                pair_dicts,
                strict_mode=min_quality_score > 0.85
            )

            # Filter by minimum quality score
            high_quality_pairs = [
                p for p in filtered_pairs
                if p.get('quality_score', 0) >= min_quality_score
            ]

            all_pairs[fmt] = high_quality_pairs

        # Generate datasets for each format
        dataset_results = {}
        for fmt in target_formats:
            pairs = all_pairs.get(fmt, [])

            if not pairs:
                continue

            # Convert to output format
            conversion_result = await format_converter.convert_training_pairs(
                pairs,
                OutputFormat(fmt.value),
                include_metadata=True
            )

            # Save to GCS with dataset naming
            dataset_timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            dataset_name = f"sft_dataset_{start_date}_to_{end_date}_{fmt.value}_{dataset_timestamp}"

            # Save as JSONL file
            temp_file = await _save_conversion_result_to_temp_file(conversion_result)

            try:
                gcs_key = f"datasets/{dataset_name}.jsonl"
                gcs_uri = await _upload_dataset_jsonl(temp_file, gcs_key, fmt.value)

                dataset_results[fmt.value] = {
                    'dataset_name': dataset_name,
                    'gcs_uri': gcs_uri,
                    'records_count': len(pairs),
                    'size_mb': conversion_result.conversion_stats['estimated_size_mb'],
                    'quality_report': quality_report.get(fmt.value, {}),
                    'date_range': (start_date, end_date)
                }

            finally:
                os.unlink(temp_file)

        # Generate summary report
        summary = {
            'dataset_generation_timestamp': datetime.utcnow().isoformat(),
            'date_range': (start_date, end_date),
            'total_input_traces': len(traces),
            'datasets_generated': dataset_results,
            'quality_thresholds': {
                'min_quality_score': min_quality_score,
                'job_type_filter': job_type_filter
            }
        }

        logger.info(f"Dataset generation completed: {len(dataset_results)} formats generated")
        return summary

    except Exception as e:
        logger.error(f"Dataset generation failed: {e}")
        raise

@celery_app.task(bind=True, max_retries=3)
async def clean_and_optimize_sft_data(
    self,
    input_gcs_uri: str,
    output_formats: List[str],
    deduplication_threshold: float = 0.9,
    max_file_size_mb: int = 100
) -> Dict[str, Any]:
    """
    Clean and optimize existing SFT data.

    Args:
        input_gcs_uri: GCS URI of input dataset
        output_formats: List of output formats to generate
        deduplication_threshold: Similarity threshold for duplicate removal
        max_file_size_mb: Maximum file size for output files

    Returns:
        Dict[str, Any]: Cleaning and optimization results
    """
    try:
        logger.info(f"Starting SFT data cleaning and optimization for {input_gcs_uri}")

        # Initialize services
        gcs_service = FineTuningGCSService()
        transformer = SFTDataTransformer()
        quality_filter = SFTQualityFilter()
        format_converter = SFTFormatConverter()

        # Download and parse input data
        input_data = await _download_from_gcs(input_gcs_uri)

        # Parse training pairs from input
        training_pairs = await _parse_training_pairs(input_data, input_gcs_uri)

        # Apply quality filtering with deduplication
        quality_filter.reset_filter_state()
        filtered_pairs, quality_report = await quality_filter.batch_filter_traces(
            training_pairs,
            strict_mode=True
        )

        # Remove duplicates based on similarity
        deduplicated_pairs = await _remove_duplicates(
            filtered_pairs,
            similarity_threshold=deduplication_threshold
        )

        # Convert to requested formats
        target_formats = [SFTFormat(fmt) for fmt in output_formats]
        format_results = {}

        for fmt in target_formats:
            pairs = deduplicated_pairs

            # Convert to output format
            conversion_result = await format_converter.convert_training_pairs(
                pairs,
                OutputFormat(fmt.value),
                include_metadata=True
            )

            # Split large files if needed
            output_files = await _split_and_upload_large_files(
                conversion_result,
                max_file_size_mb
            )

            format_results[fmt.value] = {
                'output_files': output_files,
                'records_count': len(pairs),
                'size_mb': conversion_result.conversion_stats['estimated_size_mb'],
                'files_generated': len(output_files)
            }

        # Generate optimization report
        optimization_report = {
            'input_uri': input_gcs_uri,
            'original_records': len(training_pairs),
            'filtered_records': len(filtered_pairs),
            'deduplicated_records': len(deduplicated_pairs),
            'format_results': format_results,
            'quality_report': quality_report,
            'optimization_timestamp': datetime.utcnow().isoformat(),
            'deduplication_threshold': deduplication_threshold,
            'max_file_size_mb': max_file_size_mb
        }

        logger.info(f"Data optimization completed: {len(deduplicated_pairs)} records from {len(training_pairs)} original")
        return optimization_report

    except Exception as e:
        logger.error(f"Data optimization failed: {e}")
        raise

@celery_app.task
async def generate_sft_processing_report(
    processing_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate comprehensive report from SFT processing results.

    Args:
        processing_results: List of processing result dictionaries

    Returns:
        Dict[str, Any]: Comprehensive processing report
    """
    try:
        logger.info("Generating SFT processing report")

        total_traces = sum(r.get('total_traces', 0) for r in processing_results)
        total_processed = sum(r.get('processed_traces', 0) for r in processing_results)
        total_filtered = sum(r.get('filtered_traces', 0) for r in processing_results)

        # Aggregate quality reports
        all_quality_reports = []
        for result in processing_results:
            quality_reports = result.get('quality_report', {})
            all_quality_reports.extend(quality_reports.values())

        # Calculate average quality metrics
        avg_quality = 0.0
        avg_completeness = 0.0
        avg_consistency = 0.0
        if all_quality_reports:
            total_reports = len(all_quality_reports)
            avg_quality = sum(r.get('average_quality', 0) for r in all_quality_reports) / total_reports

            # Aggregate completeness and consistency
            completeness_scores = []
            consistency_scores = []
            for report in all_quality_reports:
                if 'quality_distribution' in report:
                    for item in report['quality_distribution']:
                        completeness_scores.append(item.get('quality_score', 0))

            avg_completeness = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0
            avg_consistency = avg_completeness  # Simplified for this example

        # Count output files
        total_output_files = sum(
            len(result.get('output_files', {}))
            for result in processing_results
        )

        # Generate recommendations
        recommendations = []

        if total_filtered / total_processed < 0.8:
            recommendations.append("Consider lowering quality thresholds to increase dataset size")

        if avg_quality < 0.75:
            recommendations.append("Dataset quality is below recommended threshold - review filtering criteria")

        if total_output_files > 50:
            recommendations.append("Large number of output files - consider increasing batch sizes or file size limits")

        report = {
            'report_generated_at': datetime.utcnow().isoformat(),
            'total_processing_runs': len(processing_results),
            'aggregate_statistics': {
                'total_traces': total_traces,
                'total_processed': total_processed,
                'total_filtered': total_filtered,
                'acceptance_rate': total_filtered / total_processed if total_processed > 0 else 0,
                'total_output_files': total_output_files
            },
            'quality_metrics': {
                'average_quality_score': avg_quality,
                'average_completeness': avg_completeness,
                'average_consistency': avg_consistency
            },
            'recommendations': recommendations,
            'individual_results': processing_results
        }

        logger.info(f"Generated SFT processing report: {total_processed} traces processed, {avg_quality:.2f} avg quality")
        return report

    except Exception as e:
        logger.error(f"Failed to generate processing report: {e}")
        return {
            'success': False,
            'error': str(e),
            'report_generated_at': datetime.utcnow().isoformat()
        }

# Helper functions

async def _save_conversion_result_to_temp_file(conversion_result) -> str:
    """Save conversion result to temporary file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        if isinstance(conversion_result.output_data, str):
            # JSONL format
            f.write(conversion_result.output_data)
        else:
            # List/dict format - convert to JSONL
            if isinstance(conversion_result.output_data, list):
                for record in conversion_result.output_data:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
            else:
                f.write(json.dumps(conversion_result.output_data, ensure_ascii=False) + '\n')

        return f.name

async def _upload_dataset_jsonl(temp_file_path: str, gcs_key: str, format_name: str) -> str:
    """Upload training-ready JSONL dataset to fine-tuning bucket."""
    gcs_service = FineTuningGCSService()
    metadata = {
        'data_type': 'sft_dataset',
        'format': 'jsonl',
        'schema': format_name,
        'uploaded_at': datetime.utcnow().isoformat()
    }
    return await gcs_service.upload_dataset_jsonl(temp_file_path, gcs_key, metadata)

async def _download_from_gcs(gcs_uri: str) -> str:
    """Download data from GCS."""
    # This would use the GCS service to download
    # For now, return placeholder
    return ""

async def _parse_training_pairs(input_data: str, source_uri: str) -> List[Dict[str, Any]]:
    """Parse training pairs from input data."""
    # This would parse the input format and extract training pairs
    # For now, return placeholder
    return []

async def _remove_duplicates(
    training_pairs: List[Dict[str, Any]],
    similarity_threshold: float = 0.9
) -> List[Dict[str, Any]]:
    """Remove duplicate training pairs based on similarity."""
    # This would implement deduplication logic
    # For now, return input as-is
    return training_pairs

async def _split_and_upload_large_files(
    conversion_result,
    max_file_size_mb: int
) -> List[str]:
    """Split large files and upload to GCS."""
    # This would split large datasets into multiple files
    # For now, return placeholder
    return []
