"""
SFT Quality Filter Service

This module provides quality validation and filtering capabilities for SFT datasets,
ensuring high-quality training data by removing duplicates, incomplete traces,
and low-confidence executions.
"""

import logging
import hashlib
import json
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class QualityFilterResult(str, Enum):
    """Result of quality filtering."""
    ACCEPT = "accept"
    REJECT = "reject"
    NEEDS_REVIEW = "needs_review"

@dataclass
class QualityMetrics:
    """Quality metrics for a trace or dataset."""
    completeness_score: float = 0.0
    consistency_score: float = 0.0
    clarity_score: float = 0.0
    overall_quality: float = 0.0
    duplicate_score: float = 0.0
    pii_risk_score: float = 0.0

@dataclass
class FilterResult:
    """Result of filtering a single trace."""
    decision: QualityFilterResult
    quality_metrics: QualityMetrics
    issues: List[str]
    recommendations: List[str]

class SFTQualityFilter:
    """
    Quality filter for SFT training datasets.

    This service validates execution traces for quality, removes duplicates,
    filters out low-quality data, and ensures compliance with training requirements.
    """

    def __init__(self):
        """Initialize the quality filter."""
        self.duplicate_hashes: Set[str] = set()
        self.trace_count = 0

        # Quality thresholds (configurable)
        self.quality_thresholds = {
            'min_completeness': 0.85,
            'min_consistency': 0.75,
            'min_clarity': 0.70,
            'min_overall_quality': 0.80,
            'max_pii_risk': 0.05,
            'max_duplicate_similarity': 0.90
        }

        # PII patterns to check for
        self.pii_patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            'api_key': r'\b[A-Za-z0-9]{20,}\b',
            'url': r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))*)?',
            'ip_address': r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
        }

    async def filter_trace(
        self,
        trace: Dict[str, Any],
        check_duplicates: bool = True,
        strict_mode: bool = False
    ) -> FilterResult:
        """
        Filter a single execution trace based on quality criteria.

        Args:
            trace: Execution trace to filter
            check_duplicates: Whether to check for duplicates
            strict_mode: Use stricter quality thresholds

        Returns:
            FilterResult: Filtering decision and quality metrics
        """
        try:
            self.trace_count += 1

            # Calculate quality metrics
            quality_metrics = await self._calculate_quality_metrics(trace)

            # Check for duplicates if enabled
            if check_duplicates:
                duplicate_score = self._calculate_duplicate_score(trace)
                quality_metrics.duplicate_score = duplicate_score

                if duplicate_score > self.quality_thresholds['max_duplicate_similarity']:
                    return FilterResult(
                        decision=QualityFilterResult.REJECT,
                        quality_metrics=quality_metrics,
                        issues=[f"Duplicate trace detected (similarity: {duplicate_score".2f"})"],
                        recommendations=["Remove duplicate trace", "Consider data deduplication"]
                    )

            # Check PII risk
            pii_issues = self._check_pii_risk(trace)
            if pii_issues:
                quality_metrics.pii_risk_score = 1.0
                return FilterResult(
                    decision=QualityFilterResult.REJECT,
                    quality_metrics=quality_metrics,
                    issues=pii_issues,
                    recommendations=["Remove PII from trace", "Re-run anonymization"]
                )

            # Evaluate quality thresholds
            thresholds = self._get_thresholds(strict_mode)
            issues, recommendations = self._evaluate_quality_thresholds(quality_metrics, thresholds)

            # Make filtering decision
            decision = self._make_filtering_decision(quality_metrics, thresholds, issues)

            logger.info(f"Filtered trace {self.trace_count}: {decision.value} (quality: {quality_metrics.overall_quality".2f"})")

            return FilterResult(
                decision=decision,
                quality_metrics=quality_metrics,
                issues=issues,
                recommendations=recommendations
            )

        except Exception as e:
            logger.error(f"Failed to filter trace: {e}")
            return FilterResult(
                decision=QualityFilterResult.NEEDS_REVIEW,
                quality_metrics=QualityMetrics(),
                issues=[f"Filtering error: {str(e)}"],
                recommendations=["Manual review required"]
            )

    async def batch_filter_traces(
        self,
        traces: List[Dict[str, Any]],
        batch_size: int = 50,
        strict_mode: bool = False
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Filter multiple traces in batches.

        Args:
            traces: List of traces to filter
            batch_size: Batch size for processing
            strict_mode: Use stricter quality thresholds

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: (filtered_traces, quality_report)
        """
        filtered_traces = []
        quality_report = {
            'total_traces': len(traces),
            'accepted_traces': 0,
            'rejected_traces': 0,
            'needs_review': 0,
            'quality_distribution': [],
            'common_issues': {},
            'average_quality': 0.0
        }

        total_quality_scores = []

        for i in range(0, len(traces), batch_size):
            batch = traces[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(traces)-1)//batch_size + 1}")

            for trace in batch:
                try:
                    result = await self.filter_trace(trace, check_duplicates=True, strict_mode=strict_mode)

                    if result.decision == QualityFilterResult.ACCEPT:
                        filtered_traces.append(trace)
                        quality_report['accepted_traces'] += 1
                    elif result.decision == QualityFilterResult.REJECT:
                        quality_report['rejected_traces'] += 1
                    else:
                        quality_report['needs_review'] += 1

                    # Track quality metrics
                    total_quality_scores.append(result.quality_metrics.overall_quality)

                    # Track common issues
                    for issue in result.issues:
                        quality_report['common_issues'][issue] = quality_report['common_issues'].get(issue, 0) + 1

                    # Track quality distribution
                    quality_report['quality_distribution'].append({
                        'quality_score': result.quality_metrics.overall_quality,
                        'decision': result.decision.value
                    })

                except Exception as e:
                    logger.error(f"Error processing trace in batch: {e}")
                    quality_report['rejected_traces'] += 1
                    continue

        # Calculate average quality
        if total_quality_scores:
            quality_report['average_quality'] = sum(total_quality_scores) / len(total_quality_scores)

        # Sort quality distribution
        quality_report['quality_distribution'] = sorted(
            quality_report['quality_distribution'],
            key=lambda x: x['quality_score'],
            reverse=True
        )

        logger.info(f"Batch filtering completed: {quality_report['accepted_traces']}/{quality_report['total_traces']} traces accepted")
        return filtered_traces, quality_report

    async def _calculate_quality_metrics(self, trace: Dict[str, Any]) -> QualityMetrics:
        """Calculate comprehensive quality metrics for a trace."""
        steps = trace.get('steps', [])
        metadata = trace.get('metadata', {})

        # Completeness score (30%)
        completeness_score = self._calculate_completeness_score(steps, metadata)

        # Consistency score (25%)
        consistency_score = self._calculate_consistency_score(steps)

        # Clarity score (25%)
        clarity_score = self._calculate_clarity_score(steps)

        # Overall quality (weighted average)
        overall_quality = (
            completeness_score * 0.3 +
            consistency_score * 0.25 +
            clarity_score * 0.25
        )

        return QualityMetrics(
            completeness_score=completeness_score,
            consistency_score=consistency_score,
            clarity_score=clarity_score,
            overall_quality=overall_quality,
            pii_risk_score=0.0  # Will be calculated separately
        )

    def _calculate_completeness_score(self, steps: List[Dict[str, Any]], metadata: Dict[str, Any]) -> float:
        """Calculate completeness score based on step coverage and metadata."""
        score = 0.0

        # Check metadata completeness (20%)
        required_metadata = ['job_id', 'created_at', 'total_steps']
        present_metadata = sum(1 for field in required_metadata if metadata.get(field))
        score += 0.2 * (present_metadata / len(required_metadata))

        # Check step completeness (50%)
        if not steps:
            return score

        total_steps = len(steps)
        complete_steps = 0

        for step in steps:
            # Count complete fields for each step
            step_fields = ['step_number', 'timestamp', 'step_type']
            present_fields = sum(1 for field in step_fields if step.get(field) is not None)

            # Check for content based on step type
            step_type = step.get('step_type')
            if step_type == 'THOUGHT' and step.get('thought'):
                present_fields += 1
            elif step_type == 'ACTION' and step.get('action_tool'):
                present_fields += 1
            elif step_type == 'OBSERVATION' and step.get('observation_result'):
                present_fields += 1

            if present_fields >= len(step_fields) + 1:
                complete_steps += 1

        score += 0.5 * (complete_steps / total_steps)

        # Check execution flow (30%)
        expected_steps = metadata.get('total_steps', total_steps)
        if expected_steps > 0:
            coverage_ratio = total_steps / expected_steps
            score += 0.3 * min(coverage_ratio, 1.0)

        return min(score, 1.0)

    def _calculate_consistency_score(self, steps: List[Dict[str, Any]]) -> float:
        """Calculate consistency score based on step relationships."""
        if not steps:
            return 0.0

        score = 0.0
        consistent_steps = 0

        # Check step numbering consistency (40%)
        step_numbers = sorted([s.get('step_number', 0) for s in steps])
        expected_numbers = list(range(1, len(steps) + 1))

        if step_numbers == expected_numbers:
            score += 0.4
            consistent_steps += 1

        # Check step type transitions (30%)
        valid_transitions = {
            'THOUGHT': ['ACTION', 'OBSERVATION'],
            'ACTION': ['OBSERVATION', 'THOUGHT'],
            'OBSERVATION': ['THOUGHT', 'ACTION']
        }

        valid_transitions_count = 0
        for i in range(len(steps) - 1):
            current_type = steps[i].get('step_type')
            next_type = steps[i + 1].get('step_type')

            if current_type in valid_transitions and next_type in valid_transitions[current_type]:
                valid_transitions_count += 1

        if len(steps) > 1:
            transition_score = valid_transitions_count / (len(steps) - 1)
            score += 0.3 * transition_score

        # Check timestamp consistency (30%)
        timestamps = [s.get('timestamp') for s in steps if s.get('timestamp')]
        if len(timestamps) > 1:
            # Check if timestamps are in chronological order
            chronological = all(
                timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1)
            )
            if chronological:
                score += 0.3

        return score

    def _calculate_clarity_score(self, steps: List[Dict[str, Any]]) -> float:
        """Calculate clarity score based on content quality."""
        if not steps:
            return 0.0

        score = 0.0
        clear_steps = 0

        for step in steps:
            step_score = 0.0

            # Thought clarity (40%)
            if step.get('step_type') == 'THOUGHT':
                thought = step.get('thought', '')
                if thought:
                    # Check length (not too short, not too long)
                    word_count = len(thought.split())
                    if 5 <= word_count <= 100:
                        step_score += 0.4
                    elif word_count > 0:
                        step_score += 0.2  # Some content is better than none

            # Action clarity (30%)
            if step.get('step_type') == 'ACTION':
                action_tool = step.get('action_tool')
                action_input = step.get('action_input')

                if action_tool:
                    step_score += 0.2
                    if action_input:
                        step_score += 0.1

            # Observation clarity (30%)
            if step.get('step_type') == 'OBSERVATION':
                observation = step.get('observation_result')
                if observation:
                    try:
                        obs_data = json.loads(observation) if isinstance(observation, str) else observation
                        if isinstance(obs_data, dict) and len(obs_data) > 0:
                            step_score += 0.3
                        elif isinstance(obs_data, list) and len(obs_data) > 0:
                            step_score += 0.3
                        elif obs_data:
                            step_score += 0.15
                    except (json.JSONDecodeError, TypeError):
                        if observation and len(str(observation)) > 10:
                            step_score += 0.15

            if step_score >= 0.3:  # Minimum threshold for clarity
                clear_steps += 1

        # Overall clarity score
        clarity_ratio = clear_steps / len(steps)
        score = clarity_ratio

        return score

    def _calculate_duplicate_score(self, trace: Dict[str, Any]) -> float:
        """Calculate similarity score with existing traces."""
        # Create a hash of the trace structure and content
        trace_hash = self._generate_trace_hash(trace)

        if trace_hash in self.duplicate_hashes:
            return 1.0  # Exact duplicate

        # Check similarity with existing traces (simplified)
        # In a real implementation, you might use more sophisticated similarity measures
        return 0.0

    def _generate_trace_hash(self, trace: Dict[str, Any]) -> str:
        """Generate a hash for duplicate detection."""
        # Create a normalized representation for comparison
        normalized = {
            'step_count': len(trace.get('steps', [])),
            'step_types': [s.get('step_type') for s in trace.get('steps', [])],
            'tools_used': sorted([s.get('action_tool') for s in trace.get('steps', [])
                                if s.get('action_tool')]),
            'metadata_keys': sorted(trace.get('metadata', {}).keys())
        }

        # Create hash of normalized structure
        hash_input = json.dumps(normalized, sort_keys=True)
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def _check_pii_risk(self, trace: Dict[str, Any]) -> List[str]:
        """Check for potential PII in the trace."""
        issues = []
        trace_text = json.dumps(trace)

        for pattern_name, pattern in self.pii_patterns.items():
            import re
            matches = re.findall(pattern, trace_text)
            if matches:
                issues.append(f"Potential {pattern_name} found: {matches[:3]}...")

        return issues

    def _get_thresholds(self, strict_mode: bool) -> Dict[str, float]:
        """Get quality thresholds based on mode."""
        if strict_mode:
            return {
                'min_completeness': 0.95,
                'min_consistency': 0.90,
                'min_clarity': 0.85,
                'min_overall_quality': 0.90,
                'max_pii_risk': 0.01,
                'max_duplicate_similarity': 0.85
            }
        else:
            return self.quality_thresholds.copy()

    def _evaluate_quality_thresholds(
        self,
        metrics: QualityMetrics,
        thresholds: Dict[str, float]
    ) -> Tuple[List[str], List[str]]:
        """Evaluate quality against thresholds."""
        issues = []
        recommendations = []

        if metrics.completeness_score < thresholds['min_completeness']:
            issues.append(f"Low completeness: {metrics.completeness_score".2f"}")
            recommendations.append("Add missing steps or metadata to improve completeness")

        if metrics.consistency_score < thresholds['min_consistency']:
            issues.append(f"Low consistency: {metrics.consistency_score".2f"}")
            recommendations.append("Review step transitions and ordering for consistency")

        if metrics.clarity_score < thresholds['min_clarity']:
            issues.append(f"Low clarity: {metrics.clarity_score".2f"}")
            recommendations.append("Improve step descriptions and add more detailed thoughts")

        if metrics.overall_quality < thresholds['min_overall_quality']:
            issues.append(f"Low overall quality: {metrics.overall_quality".2f"}")
            recommendations.append("Review and improve trace quality across all metrics")

        return issues, recommendations

    def _make_filtering_decision(
        self,
        metrics: QualityMetrics,
        thresholds: Dict[str, float],
        issues: List[str]
    ) -> QualityFilterResult:
        """Make the final filtering decision."""
        # Reject if PII risk is too high
        if metrics.pii_risk_score > thresholds['max_pii_risk']:
            return QualityFilterResult.REJECT

        # Reject if overall quality is too low
        if metrics.overall_quality < thresholds['min_overall_quality']:
            return QualityFilterResult.REJECT

        # Accept if no major issues and quality is good
        if not issues:
            return QualityFilterResult.ACCEPT

        # Needs review if there are issues but quality is borderline
        if metrics.overall_quality >= thresholds['min_overall_quality'] * 0.9:
            return QualityFilterResult.NEEDS_REVIEW

        # Reject otherwise
        return QualityFilterResult.REJECT

    def get_filter_statistics(self) -> Dict[str, Any]:
        """Get filtering statistics."""
        return {
            'total_traces_processed': self.trace_count,
            'unique_traces': len(self.duplicate_hashes),
            'quality_thresholds': self.quality_thresholds,
            'pii_patterns_count': len(self.pii_patterns)
        }

    def update_thresholds(self, new_thresholds: Dict[str, float]) -> None:
        """Update quality thresholds."""
        self.quality_thresholds.update(new_thresholds)
        logger.info(f"Updated quality thresholds: {new_thresholds}")

    def add_pii_pattern(self, pattern_name: str, pattern: str) -> None:
        """Add a new PII pattern to check for."""
        self.pii_patterns[pattern_name] = pattern
        logger.info(f"Added PII pattern: {pattern_name}")

    def reset_filter_state(self) -> None:
        """Reset the filter state (clear duplicates, etc.)."""
        self.duplicate_hashes.clear()
        self.trace_count = 0
        logger.info("Reset filter state")
