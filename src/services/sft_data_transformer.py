"""
SFT Data Transformer Service

This module transforms execution traces into clean, structured SFT (Supervised Fine-Tuning)
datasets ready for AI model training. Supports multiple output formats including
Alpaca-style, ShareGPT-style, and custom orchestrator formats.
"""

import logging
import json
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class SFTFormat(str, Enum):
    """Supported SFT output formats."""
    ORCHESTRATOR = "orchestrator"
    TOOL_SPECIALIST = "tool_specialist"
    ERROR_RECOVERY = "error_recovery"
    CONVERSATION_CHAIN = "conversation_chain"

@dataclass
class SFTTrainingPair:
    """Represents a single training pair for SFT."""
    input_text: str
    output_text: str
    metadata: Dict[str, Any]
    quality_score: float
    format_type: SFTFormat

@dataclass
class TransformationMetrics:
    """Metrics for transformation operations."""
    total_traces_processed: int = 0
    total_pairs_generated: int = 0
    successful_transformations: int = 0
    failed_transformations: int = 0
    average_quality_score: float = 0.0
    processing_time_seconds: float = 0.0

class SFTDataTransformer:
    """
    Transforms execution traces into SFT training datasets.

    This service converts raw execution traces into structured training pairs
    suitable for supervised fine-tuning of AI models, supporting multiple
    output formats for different training objectives.
    """

    def __init__(self):
        """Initialize the SFT data transformer."""
        self.metrics = TransformationMetrics()
        self.start_time = datetime.utcnow()

        # Quality scoring weights
        self.quality_weights = {
            'step_completion': 0.3,
            'thought_quality': 0.25,
            'action_success': 0.25,
            'context_consistency': 0.2
        }

    async def transform_execution_trace(
        self,
        trace: Dict[str, Any],
        target_formats: Optional[List[SFTFormat]] = None,
        include_context: bool = True
    ) -> Dict[SFTFormat, List[SFTTrainingPair]]:
        """
        Transform a single execution trace into multiple SFT formats.

        Args:
            trace: Anonymized execution trace
            target_formats: List of formats to generate (default: all)
            include_context: Whether to include conversation context

        Returns:
            Dict[SFTFormat, List[SFTTrainingPair]]: Training pairs by format
        """
        try:
            if target_formats is None:
                target_formats = [SFTFormat.ORCHESTRATOR, SFTFormat.TOOL_SPECIALIST, SFTFormat.ERROR_RECOVERY]

            results = {}

            for fmt in target_formats:
                try:
                    pairs = await self._transform_to_format(trace, fmt, include_context)
                    results[fmt] = pairs
                    self.metrics.total_pairs_generated += len(pairs)
                    self.metrics.successful_transformations += 1

                    logger.info(f"Generated {len(pairs)} {fmt.value} training pairs")

                except Exception as e:
                    logger.error(f"Failed to transform trace to {fmt.value} format: {e}")
                    self.metrics.failed_transformations += 1
                    results[fmt] = []

            self.metrics.total_traces_processed += 1
            return results

        except Exception as e:
            logger.error(f"Failed to transform execution trace: {e}")
            raise

    async def _transform_to_format(
        self,
        trace: Dict[str, Any],
        format_type: SFTFormat,
        include_context: bool
    ) -> List[SFTTrainingPair]:
        """
        Transform trace to a specific SFT format.

        Args:
            trace: Execution trace to transform
            format_type: Target format
            include_context: Include conversation context

        Returns:
            List[SFTTrainingPair]: Training pairs in target format
        """
        if format_type == SFTFormat.ORCHESTRATOR:
            return await self._transform_to_orchestrator_format(trace, include_context)
        elif format_type == SFTFormat.TOOL_SPECIALIST:
            return await self._transform_to_tool_specialist_format(trace, include_context)
        elif format_type == SFTFormat.ERROR_RECOVERY:
            return await self._transform_to_error_recovery_format(trace, include_context)
        elif format_type == SFTFormat.CONVERSATION_CHAIN:
            return await self._transform_to_conversation_chain_format(trace, include_context)
        else:
            raise ValueError(f"Unsupported format: {format_type}")

    async def _transform_to_orchestrator_format(
        self,
        trace: Dict[str, Any],
        include_context: bool
    ) -> List[SFTTrainingPair]:
        """
        Transform to orchestrator training format (Alpaca-style).

        Creates input/output pairs for teaching AI to orchestrate tasks
        and reason through multi-step processes.
        """
        pairs = []
        steps = trace.get('steps', [])
        metadata = trace.get('metadata', {})

        for i, step in enumerate(steps):
            # Skip non-thought steps (actions and observations)
            if step.get('step_type') != 'THOUGHT':
                continue

            # Build input context
            context_steps = steps[:i] if include_context else []
            input_text = self._build_orchestrator_input(context_steps, step, metadata)

            # Build output (next action)
            next_step = steps[i + 1] if i + 1 < len(steps) else None
            output_text = self._build_orchestrator_output(step, next_step)

            # Calculate quality score
            quality_score = self._calculate_step_quality(step, context_steps)

            # Create training pair
            pair_metadata = {
                'step_number': step.get('step_number'),
                'step_type': step.get('step_type'),
                'context_steps_count': len(context_steps),
                'job_type': metadata.get('job_type'),
                'execution_time': metadata.get('execution_time_seconds'),
                'success_rate': quality_score,
                'model_used': step.get('model_used'),
                'step_cost': step.get('step_cost')
            }

            pair = SFTTrainingPair(
                input_text=input_text,
                output_text=output_text,
                metadata=pair_metadata,
                quality_score=quality_score,
                format_type=SFTFormat.ORCHESTRATOR
            )

            pairs.append(pair)

        return pairs

    async def _transform_to_tool_specialist_format(
        self,
        trace: Dict[str, Any],
        include_context: bool
    ) -> List[SFTTrainingPair]:
        """
        Transform to tool specialist training format.

        Creates input/output pairs focused on tool usage patterns
        and parameter optimization.
        """
        pairs = []
        steps = trace.get('steps', [])
        metadata = trace.get('metadata', {})

        for step in steps:
            # Only process action steps
            if step.get('step_type') != 'ACTION':
                continue

            tool_name = step.get('action_tool')
            if not tool_name:
                continue

            # Build input context
            input_text = self._build_tool_input(step, metadata)

            # Build output (tool execution result)
            observation_result = self._extract_observation_result(steps, step)
            output_text = self._build_tool_output(step, observation_result)

            # Calculate quality score based on tool success
            quality_score = self._calculate_tool_quality(step, observation_result)

            # Create training pair
            pair_metadata = {
                'tool_name': tool_name,
                'step_number': step.get('step_number'),
                'execution_success': quality_score > 0.7,
                'model_used': step.get('model_used'),
                'step_cost': step.get('step_cost'),
                'observation_available': observation_result is not None
            }

            pair = SFTTrainingPair(
                input_text=input_text,
                output_text=output_text,
                metadata=pair_metadata,
                quality_score=quality_score,
                format_type=SFTFormat.TOOL_SPECIALIST
            )

            pairs.append(pair)

        return pairs

    async def _transform_to_error_recovery_format(
        self,
        trace: Dict[str, Any],
        include_context: bool
    ) -> List[SFTTrainingPair]:
        """
        Transform to error recovery training format.

        Creates input/output pairs for handling failures and
        implementing recovery strategies.
        """
        pairs = []
        steps = trace.get('steps', [])
        metadata = trace.get('metadata', {})

        # Find failed steps or patterns
        failed_steps = self._identify_failed_steps(steps)

        for failed_step in failed_steps:
            # Build error context
            context_steps = [s for s in steps if s.get('step_number') < failed_step.get('step_number', 0)]
            input_text = self._build_error_context(failed_step, context_steps, metadata)

            # Build recovery strategy
            recovery_steps = [s for s in steps if s.get('step_number') > failed_step.get('step_number', 0)]
            output_text = self._build_recovery_strategy(failed_step, recovery_steps)

            # Calculate quality score
            quality_score = self._calculate_recovery_quality(failed_step, recovery_steps)

            # Create training pair
            pair_metadata = {
                'failed_step_number': failed_step.get('step_number'),
                'failure_type': self._identify_failure_type(failed_step),
                'recovery_steps_count': len(recovery_steps),
                'context_steps_count': len(context_steps),
                'overall_success': quality_score > 0.6
            }

            pair = SFTTrainingPair(
                input_text=input_text,
                output_text=output_text,
                metadata=pair_metadata,
                quality_score=quality_score,
                format_type=SFTFormat.ERROR_RECOVERY
            )

            pairs.append(pair)

        return pairs

    async def _transform_to_conversation_chain_format(
        self,
        trace: Dict[str, Any],
        include_context: bool
    ) -> List[SFTTrainingPair]:
        """
        Transform to conversation chain format (ShareGPT-style).

        Creates conversational training pairs that maintain context
        across multiple steps.
        """
        pairs = []
        steps = trace.get('steps', [])
        metadata = trace.get('metadata', {})

        # Group steps into conversation turns
        conversation_turns = self._group_conversation_turns(steps)

        for turn in conversation_turns:
            input_text = self._build_conversation_input(turn, metadata)
            output_text = self._build_conversation_output(turn)

            # Calculate quality score for the conversation turn
            quality_score = self._calculate_conversation_quality(turn)

            pair_metadata = {
                'turn_number': turn.get('turn_number', 0),
                'steps_in_turn': len(turn.get('steps', [])),
                'conversation_type': turn.get('type', 'unknown'),
                'turn_success': quality_score > 0.7
            }

            pair = SFTTrainingPair(
                input_text=input_text,
                output_text=output_text,
                metadata=pair_metadata,
                quality_score=quality_score,
                format_type=SFTFormat.CONVERSATION_CHAIN
            )

            pairs.append(pair)

        return pairs

    def _build_orchestrator_input(
        self,
        context_steps: List[Dict[str, Any]],
        current_step: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> str:
        """Build input text for orchestrator training."""
        # Start with system instruction
        input_text = "You are an AI orchestrator. Given user requests and available tools, plan the next action.\n\n"

        # Add available tools (from context or common tools)
        available_tools = self._extract_available_tools(context_steps)
        if available_tools:
            input_text += f"Available tools: {', '.join(available_tools)}\n\n"

        # Add conversation context
        if context_steps:
            input_text += "Previous conversation:\n"
            for step in context_steps[-3:]:  # Last 3 steps for context
                if step.get('step_type') == 'THOUGHT':
                    input_text += f"Thought: {step.get('thought', '')}\n"
                elif step.get('step_type') == 'ACTION' and step.get('action_tool'):
                    input_text += f"Action: {step['action_tool']}\n"

        # Add current user request (from current step thought)
        current_thought = current_step.get('thought', '')
        if current_thought:
            input_text += f"\nCurrent request: {current_thought}\n"

        input_text += "\nWhat should I do next?"
        return input_text

    def _build_orchestrator_output(
        self,
        current_step: Dict[str, Any],
        next_step: Optional[Dict[str, Any]]
    ) -> str:
        """Build output text for orchestrator training."""
        if not next_step:
            return "I have completed the task successfully."

        output_text = ""

        # Add reasoning continuation if available
        if current_step.get('thought'):
            output_text += f"{current_step['thought']}\n\n"

        # Add next action
        if next_step.get('step_type') == 'ACTION' and next_step.get('action_tool'):
            action_input = next_step.get('action_input', {})
            if isinstance(action_input, dict):
                params_str = ", ".join([f"{k}: {v}" for k, v in action_input.items()])
                output_text += f"Action: {next_step['action_tool']}\nParameters: {{{params_str}}}"
            else:
                output_text += f"Action: {next_step['action_tool']}"

        return output_text

    def _build_tool_input(self, step: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Build input text for tool specialist training."""
        tool_name = step.get('action_tool', 'unknown')
        action_input = step.get('action_input', {})

        input_text = f"Function: {tool_name}\n"

        if isinstance(action_input, dict):
            if action_input:
                params_str = "\n".join([f"{k}: {v}" for k, v in action_input.items()])
                input_text += f"Arguments:\n{params_str}"
        else:
            input_text += f"Arguments: {action_input}"

        return input_text

    def _build_tool_output(self, step: Dict[str, Any], observation_result: Optional[Dict[str, Any]]) -> str:
        """Build output text for tool specialist training."""
        if not observation_result:
            return "[No result returned]"

        # Format observation result as structured output
        if isinstance(observation_result, dict):
            # Try to create a clean, structured output
            if 'results' in observation_result:
                results = observation_result['results']
                if isinstance(results, list) and results:
                    if isinstance(results[0], dict):
                        # Structured results
                        formatted_results = []
                        for result in results[:5]:  # Limit to first 5 results
                            formatted_results.append(f"- {result}")
                        return "\n".join(formatted_results)
                    else:
                        # Simple list results
                        return "\n".join([f"- {r}" for r in results[:5]])

            # Generic dictionary formatting
            lines = []
            for key, value in observation_result.items():
                if isinstance(value, (list, dict)):
                    lines.append(f"{key}: [structured data]")
                else:
                    lines.append(f"{key}: {value}")
            return "\n".join(lines)
        else:
            return str(observation_result)

    def _extract_observation_result(self, steps: List[Dict[str, Any]], current_step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract observation result for the current step."""
        current_step_num = current_step.get('step_number', 0)

        # Find the next observation step
        for step in steps:
            if (step.get('step_number', 0) == current_step_num + 1 and
                step.get('step_type') == 'OBSERVATION'):
                observation_data = step.get('observation_result')
                if observation_data:
                    try:
                        if isinstance(observation_data, str):
                            return json.loads(observation_data)
                        return observation_data
                    except (json.JSONDecodeError, TypeError):
                        return {'raw_result': str(observation_data)}

        return None

    def _identify_failed_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify steps that represent failures or errors."""
        failed_steps = []

        for step in steps:
            # Check for explicit failure indicators
            if step.get('step_type') == 'THOUGHT':
                thought = step.get('thought', '').lower()
                failure_keywords = ['error', 'failed', 'failure', 'exception', 'timeout', 'retry']
                if any(keyword in thought for keyword in failure_keywords):
                    failed_steps.append(step)

            # Check for action steps without corresponding observations
            elif step.get('step_type') == 'ACTION':
                step_num = step.get('step_number', 0)
                has_observation = any(
                    s.get('step_number', 0) == step_num + 1 and s.get('step_type') == 'OBSERVATION'
                    for s in steps
                )
                if not has_observation:
                    failed_steps.append(step)

        return failed_steps

    def _build_error_context(
        self,
        failed_step: Dict[str, Any],
        context_steps: List[Dict[str, Any]],
        metadata: Dict[str, Any]
    ) -> str:
        """Build error context for error recovery training."""
        input_text = "Previous steps failed. I need to recover and continue.\n\n"

        # Add context about what went wrong
        if failed_step.get('step_type') == 'THOUGHT':
            thought = failed_step.get('thought', '')
            input_text += f"Failed thought: {thought}\n\n"
        elif failed_step.get('step_type') == 'ACTION':
            tool = failed_step.get('action_tool', 'unknown')
            input_text += f"Failed action: {tool}\n\n"

        # Add previous context
        if context_steps:
            input_text += "Previous successful steps:\n"
            for step in context_steps[-2:]:  # Last 2 successful steps
                if step.get('step_type') == 'THOUGHT':
                    input_text += f"- Thought: {step.get('thought', '')}\n"
                elif step.get('step_type') == 'ACTION' and step.get('action_tool'):
                    input_text += f"- Action: {step['action_tool']}\n"

        input_text += "\nHow should I recover from this failure?"
        return input_text

    def _build_recovery_strategy(
        self,
        failed_step: Dict[str, Any],
        recovery_steps: List[Dict[str, Any]]
    ) -> str:
        """Build recovery strategy output."""
        if not recovery_steps:
            return "I should retry the failed step with a different approach."

        # Analyze recovery steps to understand the strategy
        recovery_actions = [s for s in recovery_steps if s.get('step_type') == 'ACTION']
        recovery_thoughts = [s for s in recovery_steps if s.get('step_type') == 'THOUGHT']

        output_text = "Recovery strategy:\n\n"

        if recovery_thoughts:
            # Use the first recovery thought as the main strategy
            strategy = recovery_thoughts[0].get('thought', '')
            output_text += f"{strategy}\n\n"

        if recovery_actions:
            # Describe the recovery actions
            for action in recovery_actions[:2]:  # Limit to first 2 recovery actions
                tool = action.get('action_tool', 'unknown')
                action_input = action.get('action_input', {})
                if isinstance(action_input, dict):
                    params_str = ", ".join([f"{k}: {v}" for k, v in action_input.items()])
                    output_text += f"Action: {tool}\nParameters: {{{params_str}}}\n\n"
                else:
                    output_text += f"Action: {tool}\n\n"

        return output_text

    def _calculate_step_quality(self, step: Dict[str, Any], context_steps: List[Dict[str, Any]]) -> float:
        """Calculate quality score for a step."""
        score = 0.0

        # Step completion score (30%)
        if step.get('thought'):
            score += self.quality_weights['step_completion'] * 1.0

        # Thought quality score (25%)
        thought = step.get('thought', '')
        if thought and len(thought) > 20:
            score += self.quality_weights['thought_quality'] * 0.8
        elif thought:
            score += self.quality_weights['thought_quality'] * 0.5

        # Context consistency score (20%)
        if context_steps:
            # Check if thought relates to previous context
            context_keywords = self._extract_keywords_from_steps(context_steps)
            step_keywords = self._extract_keywords(thought)
            overlap = len(set(context_keywords) & set(step_keywords))
            if overlap > 0:
                score += self.quality_weights['context_consistency'] * min(overlap / 3, 1.0)

        # Success indication (25%) - based on whether next step exists and succeeds
        step_num = step.get('step_number', 0)
        next_step = next((s for s in context_steps if s.get('step_number', 0) > step_num), None)
        if next_step:
            score += self.quality_weights['action_success'] * 0.8

        return min(score, 1.0)

    def _calculate_tool_quality(self, step: Dict[str, Any], observation_result: Optional[Dict[str, Any]]) -> float:
        """Calculate quality score for tool usage."""
        score = 0.0

        # Tool execution success (40%)
        if observation_result:
            score += 0.4

        # Tool result quality (30%)
        if observation_result and isinstance(observation_result, dict):
            if 'results' in observation_result and observation_result['results']:
                score += 0.3
            elif len(observation_result) > 1:
                score += 0.2

        # Parameter completeness (20%)
        action_input = step.get('action_input', {})
        if isinstance(action_input, dict) and action_input:
            score += 0.2

        # Cost efficiency (10%)
        step_cost = step.get('step_cost', 0)
        if step_cost and step_cost < 0.01:  # Low cost threshold
            score += 0.1

        return min(score, 1.0)

    def _calculate_recovery_quality(self, failed_step: Dict[str, Any], recovery_steps: List[Dict[str, Any]]) -> float:
        """Calculate quality score for error recovery."""
        score = 0.0

        # Recovery attempt (30%)
        if recovery_steps:
            score += 0.3

        # Recovery success (40%)
        successful_recoveries = len([s for s in recovery_steps if s.get('step_type') == 'ACTION'])
        if successful_recoveries > 0:
            score += 0.4

        # Recovery strategy sophistication (20%)
        recovery_thoughts = [s for s in recovery_steps if s.get('step_type') == 'THOUGHT']
        if recovery_thoughts:
            thought = recovery_thoughts[0].get('thought', '')
            strategy_keywords = ['retry', 'alternative', 'different', 'backup', 'fallback']
            if any(keyword in thought.lower() for keyword in strategy_keywords):
                score += 0.2

        # Context awareness (10%)
        if len(recovery_steps) > 1:
            score += 0.1

        return min(score, 1.0)

    def _calculate_conversation_quality(self, turn: Dict[str, Any]) -> float:
        """Calculate quality score for conversation turn."""
        score = 0.0
        steps = turn.get('steps', [])

        # Turn completeness (40%)
        if len(steps) > 1:
            score += 0.4

        # Response coherence (30%)
        thoughts = [s for s in steps if s.get('step_type') == 'THOUGHT']
        if thoughts and thoughts[0].get('thought'):
            score += 0.3

        # Action relevance (20%)
        actions = [s for s in steps if s.get('step_type') == 'ACTION']
        if actions:
            score += 0.2

        # Turn success (10%)
        if turn.get('success', False):
            score += 0.1

        return min(score, 1.0)

    def _extract_available_tools(self, context_steps: List[Dict[str, Any]]) -> List[str]:
        """Extract available tools from context steps."""
        tools = set()
        for step in context_steps:
            if step.get('step_type') == 'ACTION' and step.get('action_tool'):
                tools.add(step['action_tool'])
        return list(tools)

    def _extract_keywords_from_steps(self, steps: List[Dict[str, Any]]) -> List[str]:
        """Extract keywords from multiple steps."""
        all_keywords = []
        for step in steps:
            if step.get('thought'):
                all_keywords.extend(self._extract_keywords(step['thought']))
            if step.get('action_tool'):
                all_keywords.append(step['action_tool'])
        return list(set(all_keywords))

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        if not text:
            return []

        # Simple keyword extraction - split by common delimiters
        words = text.lower().replace('.', '').replace(',', '').replace('(', '').replace(')', '').split()
        keywords = [word for word in words if len(word) > 3]  # Filter short words
        return keywords[:10]  # Limit to top 10 keywords

    def _identify_failure_type(self, failed_step: Dict[str, Any]) -> str:
        """Identify the type of failure."""
        if failed_step.get('step_type') == 'THOUGHT':
            thought = failed_step.get('thought', '').lower()
            if 'timeout' in thought:
                return 'timeout'
            elif 'error' in thought or 'exception' in thought:
                return 'execution_error'
            else:
                return 'planning_failure'
        else:
            return 'action_failure'

    def _group_conversation_turns(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group steps into conversation turns."""
        if not steps:
            return []

        turns = []
        current_turn = {
            'turn_number': 1,
            'type': 'initial',
            'steps': [],
            'success': False
        }

        for step in steps:
            current_turn['steps'].append(step)

            # End turn on observation or after action without observation
            if (step.get('step_type') == 'OBSERVATION' or
                (step.get('step_type') == 'ACTION' and
                 not any(s.get('step_number', 0) == step.get('step_number', 0) + 1
                        for s in steps))):
                turns.append(current_turn)
                current_turn = {
                    'turn_number': len(turns) + 1,
                    'type': 'continuation',
                    'steps': [],
                    'success': len(turns) > 0
                }

        # Add the last turn if it has steps
        if current_turn['steps']:
            turns.append(current_turn)

        return turns

    def _build_conversation_input(self, turn: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Build conversation input for conversation chain format."""
        steps = turn.get('steps', [])

        input_text = "Continue the conversation as an AI assistant.\n\n"

        if steps:
            # Add previous steps as conversation history
            for i, step in enumerate(steps[:-1]):
                if step.get('step_type') == 'THOUGHT':
                    input_text += f"Assistant: {step.get('thought', '')}\n"
                elif step.get('step_type') == 'ACTION':
                    tool = step.get('action_tool', 'unknown')
                    input_text += f"Assistant: I'll use the {tool} tool.\n"

            # Add the current step as user input
            current_step = steps[-1]
            if current_step.get('step_type') == 'THOUGHT':
                input_text += f"User: {current_step.get('thought', '')}\n"

        input_text += "\nAssistant:"
        return input_text

    def _build_conversation_output(self, turn: Dict[str, Any]) -> str:
        """Build conversation output for conversation chain format."""
        steps = turn.get('steps', [])

        if not steps:
            return "I understand. How can I help you?"

        # Find the last thought or action as the response
        for step in reversed(steps):
            if step.get('step_type') == 'THOUGHT' and step.get('thought'):
                return step['thought']
            elif step.get('step_type') == 'ACTION' and step.get('action_tool'):
                action_input = step.get('action_input', {})
                if isinstance(action_input, dict):
                    params_str = ", ".join([f"{k}: {v}" for k, v in action_input.items()])
                    return f"I'll use the {step['action_tool']} tool with parameters: {params_str}"
                else:
                    return f"I'll use the {step['action_tool']} tool."

        return "I understand your request."

    def get_transformation_metrics(self) -> TransformationMetrics:
        """Get current transformation metrics."""
        elapsed_time = (datetime.utcnow() - self.start_time).total_seconds()
        self.metrics.processing_time_seconds = elapsed_time

        if self.metrics.total_traces_processed > 0:
            self.metrics.average_quality_score = (
                sum(pair.quality_score for pair in self._get_all_pairs()) /
                len(self._get_all_pairs())
            )

        return self.metrics

    def _get_all_pairs(self) -> List[SFTTrainingPair]:
        """Get all generated training pairs (for metrics)."""
        # This is a simplified implementation
        # In a real system, you'd track all pairs generated
        return []

    def reset_metrics(self) -> None:
        """Reset transformation metrics."""
        self.metrics = TransformationMetrics()
        self.start_time = datetime.utcnow()

    async def batch_transform_traces(
        self,
        traces: List[Dict[str, Any]],
        target_formats: Optional[List[SFTFormat]] = None,
        batch_size: int = 10
    ) -> Dict[SFTFormat, List[SFTTrainingPair]]:
        """
        Transform multiple traces in batches.

        Args:
            traces: List of execution traces to transform
            target_formats: Target SFT formats
            batch_size: Batch size for processing

        Returns:
            Dict[SFTFormat, List[SFTTrainingPair]]: All training pairs by format
        """
        all_results = {fmt: [] for fmt in (target_formats or [SFTFormat.ORCHESTRATOR])}

        for i in range(0, len(traces), batch_size):
            batch = traces[i:i + batch_size]

            for trace in batch:
                try:
                    batch_results = await self.transform_execution_trace(
                        trace, target_formats, include_context=True
                    )

                    for fmt, pairs in batch_results.items():
                        all_results[fmt].extend(pairs)

                except Exception as e:
                    logger.error(f"Failed to transform trace in batch: {e}")
                    continue

        logger.info(f"Batch transformation completed: {sum(len(pairs) for pairs in all_results.values())} total pairs")
        return all_results
