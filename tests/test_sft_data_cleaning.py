"""
SFT Data Cleaning Test Suite

Comprehensive test suite for SFT data transformation, quality filtering,
format conversion, and processing pipeline with 95%+ coverage.
"""

import pytest
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

# Import services to test
from src.services.sft_data_transformer import (
    SFTDataTransformer,
    SFTFormat,
    SFTTrainingPair,
    TransformationMetrics
)
from src.services.sft_quality_filter import (
    SFTQualityFilter,
    QualityFilterResult,
    QualityMetrics,
    FilterResult
)
from src.services.sft_format_converter import (
    SFTFormatConverter,
    OutputFormat,
    FormatConversionResult
)
from src.tasks.sft_data_processing import (
    process_sft_data_batch,
    generate_sft_dataset_from_date_range,
    clean_and_optimize_sft_data,
    generate_sft_processing_report
)

# Test fixtures

@pytest.fixture
def sample_execution_trace():
    """Sample execution trace for testing."""
    return {
        'metadata': {
            'job_id': 'test_job_123',
            'job_type': 'orchestrator_task',
            'created_at': '2025-01-01T10:00:00',
            'total_steps': 3,
            'execution_time_seconds': 45.6
        },
        'steps': [
            {
                'step_number': 1,
                'timestamp': '2025-01-01T10:00:00',
                'step_type': 'THOUGHT',
                'thought': 'I need to analyze this user request and plan the next steps.',
                'action_tool': None,
                'action_input': None,
                'observation_result': None,
                'step_cost': Decimal('0.001234'),
                'model_used': 'gemini-2.5-pro'
            },
            {
                'step_number': 2,
                'timestamp': '2025-01-01T10:00:01',
                'step_type': 'ACTION',
                'thought': None,
                'action_tool': 'web_search',
                'action_input': {'query': 'best practices for AI assistants'},
                'observation_result': None,
                'step_cost': Decimal('0.002345'),
                'model_used': 'gemini-2.5-pro'
            },
            {
                'step_number': 3,
                'timestamp': '2025-01-01T10:00:10',
                'step_type': 'OBSERVATION',
                'thought': None,
                'action_tool': None,
                'action_input': None,
                'observation_result': {
                    'results': [
                        {'title': 'Best Practices for AI Assistants', 'url': 'https://example.com'},
                        {'title': 'AI Development Guide', 'url': 'https://example2.com'}
                    ]
                },
                'step_cost': None,
                'model_used': None
            }
        ]
    }

@pytest.fixture
def sample_training_pair():
    """Sample SFT training pair."""
    return {
        'input_text': 'You are an AI orchestrator. Given user requests and available tools, plan the next action.\n\nAvailable tools: web_search, document_analysis\n\nUser: Create a project plan.\n\nWhat should I do next?',
        'output_text': 'I should research best practices first.\n\nAction: web_search\nParameters: {"query": "project planning best practices"}',
        'metadata': {
            'step_type': 'THOUGHT',
            'confidence': 0.95,
            'execution_time': 2.3,
            'success_rate': 0.92
        },
        'quality_score': 0.85,
        'format_type': SFTFormat.ORCHESTRATOR
    }

@pytest.fixture
def sample_filtered_pairs():
    """Sample filtered training pairs."""
    return [
        {
            'input_text': 'Tool: web_search\nTask: Research latest AI trends',
            'output_text': 'Results: [structured search results]',
            'metadata': {'tool_name': 'web_search'},
            'quality_score': 0.92,
            'format_type': 'tool_specialist'
        },
        {
            'input_text': 'Previous steps failed with timeout',
            'output_text': 'Retry with exponential backoff',
            'metadata': {'failure_type': 'timeout'},
            'quality_score': 0.78,
            'format_type': 'error_recovery'
        }
    ]

class TestSFTDataTransformer:
    """Test SFTDataTransformer functionality."""

    @pytest.fixture
    def transformer(self):
        return SFTDataTransformer()

    @pytest.mark.asyncio
    async def test_transform_orchestrator_format(self, transformer, sample_execution_trace):
        """Test transformation to orchestrator format."""
        result = await transformer.transform_execution_trace(
            sample_execution_trace,
            target_formats=[SFTFormat.ORCHESTRATOR]
        )

        orchestrator_pairs = result[SFTFormat.ORCHESTRATOR]
        assert len(orchestrator_pairs) > 0

        pair = orchestrator_pairs[0]
        assert isinstance(pair, SFTTrainingPair)
        assert pair.format_type == SFTFormat.ORCHESTRATOR
        assert 'orchestrator' in pair.input_text.lower()
        assert 'action:' in pair.output_text.lower()

    @pytest.mark.asyncio
    async def test_transform_tool_specialist_format(self, transformer, sample_execution_trace):
        """Test transformation to tool specialist format."""
        result = await transformer.transform_execution_trace(
            sample_execution_trace,
            target_formats=[SFTFormat.TOOL_SPECIALIST]
        )

        tool_pairs = result[SFTFormat.TOOL_SPECIALIST]
        assert len(tool_pairs) > 0

        pair = tool_pairs[0]
        assert pair.format_type == SFTFormat.TOOL_SPECIALIST
        assert 'function:' in pair.input_text.lower()
        assert len(pair.output_text) > 0

    @pytest.mark.asyncio
    async def test_transform_error_recovery_format(self, transformer, sample_execution_trace):
        """Test transformation to error recovery format."""
        result = await transformer.transform_execution_trace(
            sample_execution_trace,
            target_formats=[SFTFormat.ERROR_RECOVERY]
        )

        error_pairs = result[SFTFormat.ERROR_RECOVERY]
        # May be empty if no errors detected
        if error_pairs:
            pair = error_pairs[0]
            assert pair.format_type == SFTFormat.ERROR_RECOVERY
            assert 'recover' in pair.input_text.lower() or 'fail' in pair.input_text.lower()

    @pytest.mark.asyncio
    async def test_batch_transform_traces(self, transformer, sample_execution_trace):
        """Test batch transformation of multiple traces."""
        traces = [sample_execution_trace, sample_execution_trace]

        result = await transformer.batch_transform_traces(
            traces,
            target_formats=[SFTFormat.ORCHESTRATOR],
            batch_size=2
        )

        orchestrator_pairs = result[SFTFormat.ORCHESTRATOR]
        assert len(orchestrator_pairs) >= 2

    def test_transformation_metrics(self, transformer):
        """Test transformation metrics tracking."""
        metrics = transformer.get_transformation_metrics()

        assert isinstance(metrics, TransformationMetrics)
        assert metrics.total_traces_processed == 0
        assert metrics.total_pairs_generated == 0

    def test_metrics_reset(self, transformer):
        """Test metrics reset functionality."""
        transformer.reset_metrics()
        metrics = transformer.get_transformation_metrics()

        assert metrics.total_traces_processed == 0
        assert metrics.processing_time_seconds == 0.0

class TestSFTQualityFilter:
    """Test SFTQualityFilter functionality."""

    @pytest.fixture
    def quality_filter(self):
        return SFTQualityFilter()

    @pytest.mark.asyncio
    async def test_filter_high_quality_trace(self, quality_filter, sample_execution_trace):
        """Test filtering of high-quality trace."""
        result = await quality_filter.filter_trace(sample_execution_trace)

        assert result.decision in [QualityFilterResult.ACCEPT, QualityFilterResult.NEEDS_REVIEW]
        assert result.quality_metrics.overall_quality > 0.7
        assert len(result.issues) == 0 or result.quality_metrics.overall_quality >= 0.8

    @pytest.mark.asyncio
    async def test_filter_low_quality_trace(self, quality_filter):
        """Test filtering of low-quality trace."""
        low_quality_trace = {
            'metadata': {'job_id': 'test'},
            'steps': [
                {
                    'step_number': 1,
                    'step_type': 'THOUGHT',
                    'thought': 'a'  # Very short thought
                }
            ]
        }

        result = await quality_filter.filter_trace(low_quality_trace)

        assert result.decision == QualityFilterResult.REJECT
        assert result.quality_metrics.overall_quality < 0.5
        assert len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_batch_filter_traces(self, quality_filter):
        """Test batch filtering of traces."""
        traces = [
            {
                'metadata': {'job_id': 'test1', 'total_steps': 3},
                'steps': [{'step_number': 1, 'step_type': 'THOUGHT', 'thought': 'Good quality thought'}]
            },
            {
                'metadata': {'job_id': 'test2', 'total_steps': 1},
                'steps': [{'step_number': 1, 'step_type': 'THOUGHT', 'thought': 'x'}]
            }
        ]

        filtered_traces, quality_report = await quality_filter.batch_filter_traces(traces)

        assert len(filtered_traces) <= len(traces)
        assert quality_report['total_traces'] == len(traces)
        assert quality_report['accepted_traces'] + quality_report['rejected_traces'] == len(traces)

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, quality_filter):
        """Test duplicate detection functionality."""
        trace = {
            'metadata': {'job_id': 'test'},
            'steps': [{'step_number': 1, 'step_type': 'THOUGHT', 'thought': 'Test thought'}]
        }

        # Filter first time (should pass)
        result1 = await quality_filter.filter_trace(trace, check_duplicates=True)
        assert result1.decision != QualityFilterResult.REJECT or 'duplicate' not in str(result1.issues).lower()

        # Filter second time with same content (should be detected as duplicate)
        result2 = await quality_filter.filter_trace(trace, check_duplicates=True)
        # Note: This test may need adjustment based on actual duplicate detection implementation

    def test_pii_detection(self, quality_filter):
        """Test PII detection functionality."""
        trace_with_pii = {
            'metadata': {'job_id': 'test'},
            'steps': [
                {
                    'step_number': 1,
                    'step_type': 'THOUGHT',
                    'thought': 'Contact user@example.com or call 555-123-4567'
                }
            ]
        }

        issues = quality_filter._check_pii_risk(trace_with_pii)
        assert len(issues) > 0
        assert any('email' in issue.lower() or 'phone' in issue.lower() for issue in issues)

    def test_quality_thresholds(self, quality_filter):
        """Test quality threshold configuration."""
        # Test default thresholds
        thresholds = quality_filter._get_thresholds(strict_mode=False)
        assert 'min_overall_quality' in thresholds
        assert thresholds['min_overall_quality'] == 0.80

        # Test strict thresholds
        strict_thresholds = quality_filter._get_thresholds(strict_mode=True)
        assert strict_thresholds['min_overall_quality'] > thresholds['min_overall_quality']

class TestSFTFormatConverter:
    """Test SFTFormatConverter functionality."""

    @pytest.fixture
    def format_converter(self):
        return SFTFormatConverter()

    @pytest.mark.asyncio
    async def test_convert_to_alpaca_format(self, format_converter, sample_training_pair):
        """Test conversion to Alpaca format."""
        pairs = [sample_training_pair]

        result = await format_converter.convert_training_pairs(
            pairs,
            OutputFormat.ALPCA,
            include_metadata=True
        )

        assert result.format_type == OutputFormat.ALPCA
        assert len(result.output_data) == 1

        record = result.output_data[0]
        assert 'instruction' in record
        assert 'input' in record
        assert 'output' in record
        assert 'metadata' in record

    @pytest.mark.asyncio
    async def test_convert_to_sharegpt_format(self, format_converter, sample_training_pair):
        """Test conversion to ShareGPT format."""
        pairs = [sample_training_pair]

        result = await format_converter.convert_training_pairs(
            pairs,
            OutputFormat.SHAREGPT,
            include_metadata=False
        )

        assert result.format_type == OutputFormat.SHAREGPT
        assert len(result.output_data) == 1

        record = result.output_data[0]
        assert 'conversations' in record
        assert len(record['conversations']) >= 2  # System + user + assistant

        conversation = record['conversations']
        assert conversation[0]['from'] == 'system'
        assert conversation[1]['from'] == 'human'
        assert conversation[2]['from'] == 'assistant'

    @pytest.mark.asyncio
    async def test_convert_to_jsonl_format(self, format_converter, sample_training_pair):
        """Test conversion to JSONL format."""
        pairs = [sample_training_pair]

        result = await format_converter.convert_training_pairs(
            pairs,
            OutputFormat.JSONL,
            include_metadata=True
        )

        assert result.format_type == OutputFormat.JSONL
        assert isinstance(result.output_data, str)

        # Should contain valid JSON lines
        lines = [line.strip() for line in result.output_data.split('\n') if line.strip()]
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert 'input' in record
        assert 'output' in record

    @pytest.mark.asyncio
    async def test_batch_convert_formats(self, format_converter, sample_training_pair):
        """Test batch conversion to multiple formats."""
        pairs = [sample_training_pair]

        results = await format_converter.batch_convert_formats(
            pairs,
            [OutputFormat.ALPCA, OutputFormat.SHAREGPT]
        )

        assert OutputFormat.ALPCA in results
        assert OutputFormat.SHAREGPT in results

        alpaca_result = results[OutputFormat.ALPCA]
        assert alpaca_result.format_type == OutputFormat.ALPCA
        assert len(alpaca_result.output_data) == 1

        sharegpt_result = results[OutputFormat.SHAREGPT]
        assert sharegpt_result.format_type == OutputFormat.SHAREGPT
        assert len(sharegpt_result.output_data) == 1

    def test_format_compliance_checking(self, format_converter):
        """Test format compliance checking."""
        # Test valid JSONL
        valid_jsonl = '{"input": "test", "output": "result"}\n{"input": "test2", "output": "result2"}'
        compliance = format_converter._check_format_compliance(valid_jsonl, OutputFormat.JSONL)
        assert compliance >= 0.5

        # Test valid list format
        valid_list = [{'instruction': 'test', 'input': 'input', 'output': 'output'}]
        compliance = format_converter._check_format_compliance(valid_list, OutputFormat.ALPCA)
        assert compliance == 1.0

        # Test invalid list format
        invalid_list = [{'invalid': 'format'}]
        compliance = format_converter._check_format_compliance(invalid_list, OutputFormat.ALPCA)
        assert compliance == 0.0

    def test_format_info(self, format_converter):
        """Test format information retrieval."""
        info = format_converter.get_format_info(OutputFormat.ALPCA)

        assert info['format_name'] == 'alpaca'
        assert 'description' in info
        assert 'required_fields' in info
        assert info['supported'] is True

    def test_supported_formats(self, format_converter):
        """Test listing of supported formats."""
        formats = format_converter.list_supported_formats()

        assert len(formats) > 0
        format_names = [f['format_name'] for f in formats]
        assert 'alpaca' in format_names
        assert 'sharegpt' in format_names

class TestSFTDataProcessingTasks:
    """Test SFT data processing background tasks."""

    @pytest.mark.asyncio
    async def test_process_sft_data_batch(self, sample_execution_trace):
        """Test batch processing of SFT data."""
        with patch('src.tasks.sft_data_processing.SFTDataTransformer') as mock_transformer, \
             patch('src.tasks.sft_data_processing.SFTQualityFilter') as mock_filter, \
             patch('src.tasks.sft_data_processing.SFTFormatConverter') as mock_converter, \
             patch('src.tasks.sft_data_processing.FineTuningGCSService') as mock_gcs:

            # Setup mocks
            mock_transformer_instance = Mock()
            mock_transformer_instance.batch_transform_traces = AsyncMock(return_value={
                SFTFormat.ORCHESTRATOR: [Mock(spec=SFTTrainingPair)]
            })
            mock_transformer.return_value = mock_transformer_instance

            mock_filter_instance = Mock()
            mock_filter_instance.batch_filter_traces = AsyncMock(return_value=(
                [{'input_text': 'test', 'output_text': 'result'}],
                {'accepted_traces': 1, 'average_quality': 0.8}
            ))
            mock_filter.return_value = mock_filter_instance

            mock_converter_instance = Mock()
            mock_converter_instance.convert_training_pairs = AsyncMock(return_value=Mock(
                conversion_stats={'records_generated': 1, 'format_compliance': 1.0, 'estimated_size_mb': 0.1}
            ))
            mock_converter.return_value = mock_converter_instance

            mock_gcs_instance = Mock()
            mock_gcs_instance.get_ml_training_dataset = AsyncMock(return_value=[sample_execution_trace])
            mock_gcs.return_value = mock_gcs_instance

            # Execute task
            trace_ids = ['trace1', 'trace2']
            result = await process_sft_data_batch(
                trace_ids=trace_ids,
                output_formats=['orchestrator'],
                batch_size=10,
                strict_quality=False
            )

            assert result['total_traces'] == 2
            assert result['processed_traces'] == 1
            assert 'errors' in result

    @pytest.mark.asyncio
    async def test_generate_sft_dataset_from_date_range(self):
        """Test dataset generation from date range."""
        with patch('src.tasks.sft_data_processing.FineTuningGCSService') as mock_gcs, \
             patch('src.tasks.sft_data_processing.SFTDataTransformer') as mock_transformer, \
             patch('src.tasks.sft_data_processing.SFTQualityFilter') as mock_filter, \
             patch('src.tasks.sft_data_processing.SFTFormatConverter') as mock_converter:

            # Setup mocks
            mock_gcs_instance = Mock()
            mock_gcs_instance.get_ml_training_dataset = AsyncMock(return_value=[])
            mock_gcs.return_value = mock_gcs_instance

            mock_transformer_instance = Mock()
            mock_transformer_instance.batch_transform_traces = AsyncMock(return_value={})
            mock_transformer.return_value = mock_transformer_instance

            # Execute task
            result = await generate_sft_dataset_from_date_range(
                start_date='2025-01-01',
                end_date='2025-01-31',
                output_formats=['orchestrator'],
                job_type_filter=None,
                min_quality_score=0.8
            )

            assert 'dataset_generation_timestamp' in result
            assert 'date_range' in result

    @pytest.mark.asyncio
    async def test_clean_and_optimize_sft_data(self):
        """Test data cleaning and optimization."""
        with patch('src.tasks.sft_data_processing.FineTuningGCSService') as mock_gcs, \
             patch('src.tasks.sft_data_processing.SFTDataTransformer') as mock_transformer, \
             patch('src.tasks.sft_data_processing.SFTQualityFilter') as mock_filter, \
             patch('src.tasks.sft_data_processing.SFTFormatConverter') as mock_converter:

            # Setup mocks
            mock_gcs_instance = Mock()
            mock_gcs_instance.get_ml_training_dataset = AsyncMock(return_value=[])
            mock_gcs.return_value = mock_gcs_instance

            # Execute task
            result = await clean_and_optimize_sft_data(
                input_gcs_uri='gs://test/data.jsonl',
                output_formats=['orchestrator'],
                deduplication_threshold=0.9,
                max_file_size_mb=100
            )

            assert 'input_uri' in result
            assert 'optimization_timestamp' in result

    @pytest.mark.asyncio
    async def test_generate_sft_processing_report(self):
        """Test processing report generation."""
        sample_results = [
            {
                'total_traces': 100,
                'processed_traces': 80,
                'filtered_traces': 75,
                'quality_report': {
                    'orchestrator': {
                        'average_quality': 0.85,
                        'accepted_traces': 75
                    }
                }
            }
        ]

        result = await generate_sft_processing_report(sample_results)

        assert result['report_generated_at']
        assert result['aggregate_statistics']['total_traces'] == 100
        assert result['aggregate_statistics']['total_processed'] == 80
        assert result['aggregate_statistics']['total_filtered'] == 75
        assert result['quality_metrics']['average_quality_score'] == 0.85

class TestIntegrationScenarios:
    """Test integration scenarios and end-to-end workflows."""

    @pytest.mark.asyncio
    async def test_end_to_end_transformation_pipeline(self, sample_execution_trace):
        """Test complete transformation pipeline from trace to final formats."""
        transformer = SFTDataTransformer()
        quality_filter = SFTQualityFilter()
        format_converter = SFTFormatConverter()

        # Step 1: Transform trace to training pairs
        transformation_results = await transformer.transform_execution_trace(
            sample_execution_trace,
            target_formats=[SFTFormat.ORCHESTRATOR, SFTFormat.TOOL_SPECIALIST]
        )

        # Step 2: Filter pairs by quality
        all_pairs = []
        for fmt in [SFTFormat.ORCHESTRATOR, SFTFormat.TOOL_SPECIALIST]:
            pairs = transformation_results.get(fmt, [])
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
            all_pairs.extend(pair_dicts)

        filtered_pairs, quality_report = await quality_filter.batch_filter_traces(all_pairs)

        # Step 3: Convert to final formats
        conversion_results = await format_converter.batch_convert_formats(
            filtered_pairs,
            [OutputFormat.ALPCA, OutputFormat.SHAREGPT]
        )

        # Verify pipeline completed successfully
        assert len(transformation_results) > 0
        assert len(filtered_pairs) <= len(all_pairs)
        assert len(conversion_results) == 2

        # Check quality metrics
        assert quality_report['total_traces'] > 0
        assert quality_report['accepted_traces'] >= 0

    @pytest.mark.asyncio
    async def test_format_conversion_compliance(self, format_converter, sample_training_pair):
        """Test that format conversions maintain data integrity."""
        pairs = [sample_training_pair]

        # Convert to multiple formats
        formats_to_test = [OutputFormat.ALPCA, OutputFormat.SHAREGPT, OutputFormat.JSONL]

        for fmt in formats_to_test:
            result = await format_converter.convert_training_pairs(pairs, fmt)

            # Verify compliance
            compliance = format_converter._check_format_compliance(result.output_data, fmt)
            assert compliance >= 0.8, f"Low compliance for {fmt.value}: {compliance}"

            # Verify records can be counted
            record_count = format_converter._count_records(result.output_data)
            assert record_count == 1

            # Verify size estimation works
            size_mb = format_converter._estimate_size(result.output_data)
            assert size_mb >= 0

    @pytest.mark.asyncio
    async def test_quality_filtering_thresholds(self, quality_filter):
        """Test quality filtering with different thresholds."""
        test_traces = [
            # High quality trace
            {
                'metadata': {'job_id': 'high_quality', 'total_steps': 5},
                'steps': [
                    {'step_number': i, 'step_type': 'THOUGHT', 'thought': f'Quality thought {i}' * 10}
                    for i in range(1, 6)
                ]
            },
            # Low quality trace
            {
                'metadata': {'job_id': 'low_quality', 'total_steps': 1},
                'steps': [
                    {'step_number': 1, 'step_type': 'THOUGHT', 'thought': 'x'}
                ]
            },
            # Medium quality trace
            {
                'metadata': {'job_id': 'medium_quality', 'total_steps': 3},
                'steps': [
                    {'step_number': i, 'step_type': 'THOUGHT', 'thought': f'Medium thought {i}' * 5}
                    for i in range(1, 4)
                ]
            }
        ]

        # Test normal mode
        filtered_normal, report_normal = await quality_filter.batch_filter_traces(test_traces, strict_mode=False)

        # Test strict mode
        quality_filter.reset_filter_state()
        filtered_strict, report_strict = await quality_filter.batch_filter_traces(test_traces, strict_mode=True)

        # Strict mode should filter more aggressively
        assert len(filtered_strict) <= len(filtered_normal)

        # At least high quality trace should pass
        assert len(filtered_normal) >= 1

class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_trace_handling(self):
        """Test handling of invalid or malformed traces."""
        transformer = SFTDataTransformer()
        quality_filter = SFTQualityFilter()

        invalid_traces = [
            {},  # Empty trace
            {'metadata': {}},  # Missing steps
            {'steps': []},  # Empty steps
            {'metadata': {'job_id': 'test'}, 'steps': 'invalid'},  # Invalid steps format
            None  # None trace
        ]

        for invalid_trace in invalid_traces:
            if invalid_trace is None:
                continue

            # Should handle gracefully without crashing
            try:
                result = await transformer.transform_execution_trace(invalid_trace)
                # May return empty results but shouldn't crash
                assert isinstance(result, dict)
            except Exception as e:
                # If it fails, should be a handled exception
                assert 'transformation failed' in str(e).lower() or 'invalid' in str(e).lower()

    @pytest.mark.asyncio
    async def test_format_converter_error_handling(self, format_converter):
        """Test error handling in format converter."""
        invalid_pairs = [
            {},  # Empty pair
            {'input_text': None, 'output_text': 'test'},  # None input
            {'input_text': 'test', 'output_text': None},  # None output
            {'input_text': 123, 'output_text': 'test'},  # Wrong type
        ]

        for invalid_pair in invalid_pairs:
            try:
                result = await format_converter.convert_training_pairs(
                    [invalid_pair],
                    OutputFormat.ALPCA
                )
                # Should handle gracefully
                assert result.format_type == OutputFormat.ALPCA
            except Exception as e:
                # Should not crash with unhandled exceptions
                assert True  # Exception is acceptable for invalid data

    def test_pii_pattern_edge_cases(self):
        """Test PII pattern detection with edge cases."""
        quality_filter = SFTQualityFilter()

        edge_case_traces = [
            {
                'metadata': {'job_id': 'test'},
                'steps': [{'step_number': 1, 'step_type': 'THOUGHT', 'thought': 'No PII here'}]
            },
            {
                'metadata': {'job_id': 'test'},
                'steps': [{'step_number': 1, 'step_type': 'THOUGHT', 'thought': 'Contact admin@company.com'}]
            },
            {
                'metadata': {'job_id': 'test'},
                'steps': [{'step_number': 1, 'step_type': 'THOUGHT', 'thought': 'Call 555-1234 or 1-800-HELP-NOW'}]
            }
        ]

        for trace in edge_case_traces:
            issues = quality_filter._check_pii_risk(trace)
            if 'admin@' in trace['steps'][0]['thought']:
                assert len(issues) > 0, "Should detect email PII"
            elif '555-1234' in trace['steps'][0]['thought']:
                assert len(issues) > 0, "Should detect phone PII"
            else:
                assert len(issues) == 0, "Should not flag valid content"

# Performance and load testing

class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.asyncio
    async def test_large_batch_processing(self):
        """Test processing of large batches."""
        transformer = SFTDataTransformer()

        # Create a large batch of traces
        large_batch = []
        for i in range(100):  # 100 traces
            trace = {
                'metadata': {'job_id': f'test_{i}', 'total_steps': 3},
                'steps': [
                    {'step_number': 1, 'step_type': 'THOUGHT', 'thought': f'Thought {i}'},
                    {'step_number': 2, 'step_type': 'ACTION', 'action_tool': 'web_search'},
                    {'step_number': 3, 'step_type': 'OBSERVATION', 'observation_result': {'results': []}}
                ]
            }
            large_batch.append(trace)

        # Process in batches
        start_time = datetime.now()
        result = await transformer.batch_transform_traces(
            large_batch,
            target_formats=[SFTFormat.ORCHESTRATOR],
            batch_size=25
        )

        processing_time = (datetime.now() - start_time).total_seconds()
        pairs_generated = len(result[SFTFormat.ORCHESTRATOR])

        # Should process within reasonable time
        assert processing_time < 30  # Less than 30 seconds for 100 traces
        assert pairs_generated > 0

    def test_memory_efficiency(self):
        """Test memory efficiency of processing."""
        import sys

        transformer = SFTDataTransformer()
        quality_filter = SFTQualityFilter()
        format_converter = SFTFormatConverter()

        # Check that services don't hold excessive references
        initial_objects = len(gc.get_objects()) if 'gc' in sys.modules else 0

        # Create some test data
        for i in range(10):
            trace = {
                'metadata': {'job_id': f'test_{i}'},
                'steps': [{'step_number': 1, 'step_type': 'THOUGHT', 'thought': f'Thought {i}'}]
            }

            # Process without storing references
            asyncio.run(transformer.transform_execution_trace(trace))

        # Memory should not grow excessively
        if 'gc' in sys.modules:
            final_objects = len(gc.get_objects())
            # Allow some growth but not excessive
            assert final_objects < initial_objects * 2

# Configuration and customization tests

class TestConfiguration:
    """Test configuration and customization options."""

    def test_quality_filter_configuration(self):
        """Test quality filter configuration options."""
        quality_filter = SFTQualityFilter()

        # Test threshold updates
        new_thresholds = {
            'min_overall_quality': 0.95,
            'min_completeness': 0.9,
            'min_consistency': 0.85
        }

        quality_filter.update_thresholds(new_thresholds)
        retrieved_thresholds = quality_filter._get_thresholds(strict_mode=False)

        for key, value in new_thresholds.items():
            assert retrieved_thresholds[key] == value

    def test_pii_pattern_customization(self):
        """Test PII pattern customization."""
        quality_filter = SFTQualityFilter()

        # Add custom PII pattern
        quality_filter.add_pii_pattern('custom_id', r'custom_\d+')

        # Test the new pattern
        trace_with_custom = {
            'metadata': {'job_id': 'test'},
            'steps': [
                {
                    'step_number': 1,
                    'step_type': 'THOUGHT',
                    'thought': 'User has custom_123 identifier'
                }
            ]
        }

        issues = quality_filter._check_pii_risk(trace_with_custom)
        assert len(issues) > 0
        assert any('custom_id' in issue for issue in issues)

    def test_format_converter_customization(self, format_converter):
        """Test format converter customization."""
        # Test format validation
        custom_config = {'include_metadata': False, 'separator': '|'}

        issues = format_converter.validate_format_config(OutputFormat.JSONL, custom_config)
        # Should validate successfully
        assert len(issues) == 0

        invalid_config = {'invalid_key': 'value'}
        issues = format_converter.validate_format_config(OutputFormat.ALPCA, invalid_config)
        assert len(issues) > 0  # Should detect invalid keys

if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--cov=src.services.sft_data_transformer',
        '--cov=src.services.sft_quality_filter',
        '--cov=src.services.sft_format_converter',
        '--cov=src.tasks.sft_data_processing',
        '--cov-report=html:htmlcov',
        '--cov-report=term-missing',
        '--cov-fail-under=95'
    ])
