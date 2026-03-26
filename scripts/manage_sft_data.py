#!/usr/bin/env python3
"""
SFT Data Management CLI

Command-line interface for managing SFT (Supervised Fine-Tuning) data processing,
including trace transformation, quality filtering, format conversion, and dataset generation.
"""

import asyncio
import json
import argparse
import sys
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.services.sft_data_transformer import SFTDataTransformer, SFTFormat
from src.services.sft_quality_filter import SFTQualityFilter
from src.services.sft_format_converter import SFTFormatConverter, OutputFormat
from src.services.fine_tuning_gcs import FineTuningGCSService
from src.tasks.sft_data_processing import (
    process_sft_data_batch,
    generate_sft_dataset_from_date_range,
    clean_and_optimize_sft_data,
    generate_sft_processing_report
)

class SFTDataManager:
    """CLI manager for SFT data operations."""

    def __init__(self):
        self.transformer = SFTDataTransformer()
        self.quality_filter = SFTQualityFilter()
        self.format_converter = SFTFormatConverter()
        self.gcs_service = FineTuningGCSService()

    async def transform_traces(self, args):
        """Transform execution traces to SFT format."""
        print(f"Transforming traces to SFT format: {args.trace_ids}")

        try:
            # Get traces from GCS
            traces = await self.gcs_service.get_ml_training_dataset(
                trace_ids=args.trace_ids,
                limit=len(args.trace_ids) if args.trace_ids else None
            )

            if not traces:
                print("No traces found to transform")
                return 1

            print(f"Found {len(traces)} traces to transform")

            # Transform to training pairs
            target_formats = [SFTFormat(fmt) for fmt in args.output_formats]
            transformation_results = await self.transformer.batch_transform_traces(
                traces, target_formats, batch_size=args.batch_size
            )

            # Convert to output formats
            for fmt in target_formats:
                pairs = transformation_results.get(fmt, [])
                if pairs:
                    conversion_result = await self.format_converter.convert_training_pairs(
                        pairs, OutputFormat(fmt.value), include_metadata=args.include_metadata
                    )

                    # Save to file
                    output_file = args.output_dir / f"transformed_{fmt.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
                    await self._save_conversion_result(conversion_result, output_file)

                    print(f"Saved {len(pairs)} {fmt.value} pairs to {output_file}")

            print("Transformation completed successfully")
            return 0

        except Exception as e:
            print(f"Transformation failed: {e}")
            return 1

    async def filter_traces(self, args):
        """Filter traces by quality criteria."""
        print(f"Filtering traces from: {args.input_file}")

        try:
            # Load traces from file
            traces = await self._load_traces_from_file(args.input_file)

            if not traces:
                print("No traces found to filter")
                return 1

            print(f"Loaded {len(traces)} traces for filtering")

            # Apply quality filtering
            filtered_traces, quality_report = await self.quality_filter.batch_filter_traces(
                traces,
                batch_size=args.batch_size,
                strict_mode=args.strict_mode
            )

            # Save filtered results
            output_file = args.output_dir / f"filtered_traces_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump({
                    'filtered_traces': filtered_traces,
                    'quality_report': quality_report,
                    'filtered_at': datetime.now().isoformat()
                }, f, indent=2)

            print(f"Filtered {len(filtered_traces)}/{len(traces)} traces")
            print(f"Results saved to {output_file}")

            # Print quality summary
            accepted = quality_report.get('accepted_traces', 0)
            rejected = quality_report.get('rejected_traces', 0)
            avg_quality = quality_report.get('average_quality', 0)

            print(f"Quality Summary: {accepted} accepted, {rejected} rejected, {avg_quality".2f"} avg quality")

            return 0

        except Exception as e:
            print(f"Filtering failed: {e}")
            return 1

    async def convert_format(self, args):
        """Convert SFT data between formats."""
        print(f"Converting format: {args.input_file} -> {args.output_format}")

        try:
            # Load training pairs
            training_pairs = await self._load_training_pairs_from_file(args.input_file)

            if not training_pairs:
                print("No training pairs found to convert")
                return 1

            print(f"Loaded {len(training_pairs)} training pairs")

            # Convert format
            conversion_result = await self.format_converter.convert_training_pairs(
                training_pairs,
                OutputFormat(args.output_format),
                include_metadata=args.include_metadata
            )

            # Save converted data
            output_file = args.output_dir / f"converted_{args.output_format}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            await self._save_conversion_result(conversion_result, output_file)

            print(f"Converted {conversion_result.conversion_stats['records_generated']} records")
            print(f"Compliance: {conversion_result.conversion_stats['format_compliance']".2%"}")
            print(f"Saved to {output_file}")

            return 0

        except Exception as e:
            print(f"Format conversion failed: {e}")
            return 1

    async def generate_dataset(self, args):
        """Generate SFT dataset from date range."""
        print(f"Generating dataset from {args.start_date} to {args.end_date}")

        try:
            # Generate dataset
            result = await generate_sft_dataset_from_date_range(
                args.start_date,
                args.end_date,
                args.output_formats,
                job_type_filter=args.job_type,
                min_quality_score=args.min_quality
            )

            # Save generation report
            output_file = args.output_dir / f"dataset_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)

            print(f"Dataset generation completed")
            print(f"Report saved to {output_file}")

            # Print summary
            datasets = result.get('datasets_generated', {})
            for fmt, info in datasets.items():
                print(f"- {fmt}: {info['records_count']} records -> {info['gcs_uri']}")

            return 0

        except Exception as e:
            print(f"Dataset generation failed: {e}")
            return 1

    async def clean_data(self, args):
        """Clean and optimize SFT data."""
        print(f"Cleaning data: {args.input_uri}")

        try:
            # Clean and optimize
            result = await clean_and_optimize_sft_data(
                args.input_uri,
                args.output_formats,
                deduplication_threshold=args.deduplication_threshold,
                max_file_size_mb=args.max_file_size
            )

            # Save cleaning report
            output_file = args.output_dir / f"cleaning_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)

            print(f"Data cleaning completed")
            print(f"Report saved to {output_file}")

            # Print summary
            original = result.get('original_records', 0)
            filtered = result.get('filtered_records', 0)
            deduplicated = result.get('deduplicated_records', 0)

            print(f"Records: {original} -> {filtered} -> {deduplicated}")

            return 0

        except Exception as e:
            print(f"Data cleaning failed: {e}")
            return 1

    async def generate_report(self, args):
        """Generate processing report."""
        print(f"Generating report from: {args.result_files}")

        try:
            # Load result files
            results = []
            for file_path in args.result_files:
                with open(file_path) as f:
                    results.append(json.load(f))

            # Generate comprehensive report
            report = await generate_sft_processing_report(results)

            # Save report
            output_file = args.output_dir / f"sft_processing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)

            print(f"Report generated and saved to {output_file}")

            # Print summary
            stats = report.get('aggregate_statistics', {})
            quality = report.get('quality_metrics', {})

            print(f"Total traces processed: {stats.get('total_processed', 0)}")
            print(f"Acceptance rate: {stats.get('acceptance_rate', 0)".2%"}")
            print(f"Average quality: {quality.get('average_quality_score', 0)".2f"}")

            if report.get('recommendations'):
                print("\nRecommendations:")
                for rec in report['recommendations']:
                    print(f"- {rec}")

            return 0

        except Exception as e:
            print(f"Report generation failed: {e}")
            return 1

    async def validate_data(self, args):
        """Validate SFT data quality and format."""
        print(f"Validating data: {args.input_file}")

        try:
            # Load and validate data
            validation_result = await self._validate_sft_data(args.input_file)

            # Save validation report
            output_file = args.output_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(validation_result, f, indent=2)

            print(f"Validation completed")
            print(f"Report saved to {output_file}")

            # Print summary
            if validation_result.get('is_valid'):
                print("✅ Data is valid")
            else:
                print("❌ Data validation failed")

            print(f"Records: {validation_result.get('total_records', 0)}")
            print(f"Quality score: {validation_result.get('average_quality', 0)".2f"}")

            return 0

        except Exception as e:
            print(f"Validation failed: {e}")
            return 1

    async def _load_traces_from_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Load traces from JSON/JSONL file."""
        traces = []

        with open(file_path) as f:
            if file_path.suffix == '.jsonl':
                for line in f:
                    if line.strip():
                        traces.append(json.loads(line))
            else:
                data = json.load(f)
                if isinstance(data, list):
                    traces = data
                else:
                    traces = [data]

        return traces

    async def _load_training_pairs_from_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Load training pairs from file."""
        training_pairs = []

        with open(file_path) as f:
            if file_path.suffix == '.jsonl':
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if 'input' in data and 'output' in data:
                            training_pairs.append(data)
            else:
                data = json.load(f)
                if isinstance(data, list):
                    training_pairs = data
                else:
                    training_pairs = [data]

        return training_pairs

    async def _save_conversion_result(self, conversion_result, output_file: Path):
        """Save conversion result to file."""
        os.makedirs(output_file.parent, exist_ok=True)

        with open(output_file, 'w') as f:
            if isinstance(conversion_result.output_data, str):
                # JSONL format
                f.write(conversion_result.output_data)
            else:
                # List/dict format
                if isinstance(conversion_result.output_data, list):
                    if output_file.suffix == '.jsonl':
                        for record in conversion_result.output_data:
                            f.write(json.dumps(record, ensure_ascii=False) + '\n')
                    else:
                        json.dump(conversion_result.output_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(conversion_result.output_data, f, indent=2, ensure_ascii=False)

    async def _validate_sft_data(self, file_path: Path) -> Dict[str, Any]:
        """Validate SFT data quality and format."""
        # Load data
        training_pairs = await self._load_training_pairs_from_file(file_path)

        # Basic validation
        validation_result = {
            'total_records': len(training_pairs),
            'valid_records': 0,
            'invalid_records': 0,
            'quality_scores': [],
            'format_issues': [],
            'is_valid': True,
            'average_quality': 0.0
        }

        for i, pair in enumerate(training_pairs):
            issues = []

            # Check required fields
            if 'input' not in pair:
                issues.append("Missing 'input' field")
            if 'output' not in pair:
                issues.append("Missing 'output' field")

            # Check field types and lengths
            if not isinstance(pair.get('input', ''), str):
                issues.append("Input must be string")
            if not isinstance(pair.get('output', ''), str):
                issues.append("Output must be string")

            if len(pair.get('input', '')) < 10:
                issues.append("Input too short")
            if len(pair.get('output', '')) < 5:
                issues.append("Output too short")

            if issues:
                validation_result['invalid_records'] += 1
                validation_result['format_issues'].extend([f"Record {i}: {issue}" for issue in issues])
            else:
                validation_result['valid_records'] += 1

                # Calculate basic quality score
                quality_score = self._calculate_basic_quality_score(pair)
                validation_result['quality_scores'].append(quality_score)

        # Calculate average quality
        if validation_result['quality_scores']:
            validation_result['average_quality'] = (
                sum(validation_result['quality_scores']) / len(validation_result['quality_scores'])
            )

        # Overall validation
        if validation_result['invalid_records'] > validation_result['valid_records'] * 0.1:
            validation_result['is_valid'] = False

        return validation_result

    def _calculate_basic_quality_score(self, pair: Dict[str, Any]) -> float:
        """Calculate basic quality score for a training pair."""
        score = 0.0

        # Length score (30%)
        input_len = len(pair.get('input', ''))
        output_len = len(pair.get('output', ''))

        if 50 <= input_len <= 1000:
            score += 0.3
        elif input_len > 0:
            score += 0.15

        if 20 <= output_len <= 500:
            score += 0.3
        elif output_len > 0:
            score += 0.15

        # Content diversity (20%)
        input_words = set(pair.get('input', '').lower().split())
        output_words = set(pair.get('output', '').lower().split())

        if len(input_words) > 10 and len(output_words) > 5:
            score += 0.2

        # Structure (20%)
        if '\n' in pair.get('input', '') or '\n' in pair.get('output', ''):
            score += 0.2

        return min(score, 1.0)

def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="SFT Data Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Transform traces to SFT format
  python manage_sft_data.py transform --trace-ids trace1 trace2 --output-formats orchestrator tool_specialist

  # Filter traces by quality
  python manage_sft_data.py filter --input-file traces.jsonl --strict-mode

  # Convert between formats
  python manage_sft_data.py convert --input-file data.jsonl --output-format alpaca

  # Generate dataset from date range
  python manage_sft_data.py generate-dataset --start-date 2025-01-01 --end-date 2025-01-31 --output-formats alpaca sharegpt

  # Clean and optimize data
  python manage_sft_data.py clean --input-uri gs://bucket/data.jsonl --output-formats alpaca

  # Generate processing report
  python manage_sft_data.py report --result-files result1.json result2.json

  # Validate data quality
  python manage_sft_data.py validate --input-file data.jsonl
        """
    )

    # Common arguments
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('output'),
        help='Output directory for results'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Transform command
    transform_parser = subparsers.add_parser('transform', help='Transform traces to SFT format')
    transform_parser.add_argument('--trace-ids', nargs='+', help='Trace IDs to transform')
    transform_parser.add_argument('--output-formats', nargs='+', default=['orchestrator'],
                                  choices=[fmt.value for fmt in SFTFormat],
                                  help='Output formats to generate')
    transform_parser.add_argument('--batch-size', type=int, default=10,
                                  help='Batch size for processing')
    transform_parser.add_argument('--include-metadata', action='store_true',
                                  help='Include metadata in output')

    # Filter command
    filter_parser = subparsers.add_parser('filter', help='Filter traces by quality')
    filter_parser.add_argument('--input-file', type=Path, required=True,
                               help='Input file containing traces')
    filter_parser.add_argument('--batch-size', type=int, default=50,
                               help='Batch size for processing')
    filter_parser.add_argument('--strict-mode', action='store_true',
                               help='Use strict quality filtering')

    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert SFT data format')
    convert_parser.add_argument('--input-file', type=Path, required=True,
                                help='Input file containing training pairs')
    convert_parser.add_argument('--output-format', required=True,
                                choices=[fmt.value for fmt in OutputFormat],
                                help='Target output format')
    convert_parser.add_argument('--include-metadata', action='store_true',
                                help='Include metadata in output')

    # Generate dataset command
    dataset_parser = subparsers.add_parser('generate-dataset', help='Generate dataset from date range')
    dataset_parser.add_argument('--start-date', required=True,
                                help='Start date (YYYY-MM-DD)')
    dataset_parser.add_argument('--end-date', required=True,
                                help='End date (YYYY-MM-DD)')
    dataset_parser.add_argument('--output-formats', nargs='+', required=True,
                                choices=[fmt.value for fmt in SFTFormat],
                                help='Output formats to generate')
    dataset_parser.add_argument('--job-type', help='Filter by job type')
    dataset_parser.add_argument('--min-quality', type=float, default=0.8,
                                help='Minimum quality score')

    # Clean command
    clean_parser = subparsers.add_parser('clean', help='Clean and optimize SFT data')
    clean_parser.add_argument('--input-uri', required=True,
                              help='GCS URI of input data')
    clean_parser.add_argument('--output-formats', nargs='+', required=True,
                              choices=[fmt.value for fmt in SFTFormat],
                              help='Output formats to generate')
    clean_parser.add_argument('--deduplication-threshold', type=float, default=0.9,
                              help='Deduplication similarity threshold')
    clean_parser.add_argument('--max-file-size', type=int, default=100,
                              help='Max file size in MB')

    # Report command
    report_parser = subparsers.add_parser('report', help='Generate processing report')
    report_parser.add_argument('--result-files', nargs='+', type=Path, required=True,
                               help='Result files to analyze')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate SFT data')
    validate_parser.add_argument('--input-file', type=Path, required=True,
                                 help='Input file to validate')

    return parser

async def main():
    """Main CLI entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Create output directory
    args.output_dir.mkdir(exist_ok=True)

    # Initialize manager
    manager = SFTDataManager()

    # Execute command
    try:
        if args.command == 'transform':
            return await manager.transform_traces(args)
        elif args.command == 'filter':
            return await manager.filter_traces(args)
        elif args.command == 'convert':
            return await manager.convert_format(args)
        elif args.command == 'generate-dataset':
            return await manager.generate_dataset(args)
        elif args.command == 'clean':
            return await manager.clean_data(args)
        elif args.command == 'report':
            return await manager.generate_report(args)
        elif args.command == 'validate':
            return await manager.validate_data(args)
        else:
            print(f"Unknown command: {args.command}")
            return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
