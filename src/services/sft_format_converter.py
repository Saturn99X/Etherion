"""
SFT Format Converter Service

This module provides conversion capabilities for multiple SFT (Supervised Fine-Tuning)
formats including Alpaca-style, ShareGPT-style, and custom orchestrator formats.
"""

import logging
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class OutputFormat(str, Enum):
    """Supported output formats for SFT data."""
    ALPCA = "alpaca"  # instruction/input/output format
    SHAREGPT = "sharegpt"  # conversation format
    CUSTOM_ORCHESTRATOR = "custom_orchestrator"  # Custom format for orchestration
    JSONL = "jsonl"  # Generic JSONL format
    CONVERSATION = "conversation"  # General conversation format

@dataclass
class FormatConversionResult:
    """Result of format conversion."""
    output_data: Union[str, Dict[str, Any], List[Dict[str, Any]]]
    format_type: OutputFormat
    metadata: Dict[str, Any]
    conversion_stats: Dict[str, Any]

class SFTFormatConverter:
    """
    Converts SFT training pairs to multiple output formats.

    This service handles the conversion of training pairs into various
    SFT formats required by different training frameworks and models.
    """

    def __init__(self):
        """Initialize the format converter."""
        self.supported_formats = [fmt.value for fmt in OutputFormat]

        # Format-specific configurations
        self.format_configs = {
            OutputFormat.ALPCA: {
                'instruction_key': 'instruction',
                'input_key': 'input',
                'output_key': 'output',
                'include_metadata': True
            },
            OutputFormat.SHAREGPT: {
                'conversation_key': 'conversations',
                'system_message': 'You are a helpful AI assistant.',
                'include_metadata': False
            },
            OutputFormat.CUSTOM_ORCHESTRATOR: {
                'context_key': 'context',
                'instruction_key': 'instruction',
                'output_key': 'output',
                'metadata_key': 'metadata'
            },
            OutputFormat.JSONL: {
                'record_format': 'dict',
                'separator': '\n'
            },
            OutputFormat.CONVERSATION: {
                'message_format': 'role_content',
                'include_timestamps': False
            }
        }

    async def convert_training_pairs(
        self,
        training_pairs: List[Dict[str, Any]],
        output_format: OutputFormat,
        include_metadata: bool = True,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> FormatConversionResult:
        """
        Convert training pairs to the specified output format.

        Args:
            training_pairs: List of SFTTrainingPair objects converted to dicts
            output_format: Target output format
            include_metadata: Whether to include metadata in output
            custom_config: Custom configuration for the format

        Returns:
            FormatConversionResult: Converted data and metadata
        """
        try:
            if output_format not in OutputFormat:
                raise ValueError(f"Unsupported output format: {output_format}")

            # Merge custom config with default
            config = self.format_configs[output_format].copy()
            if custom_config:
                config.update(custom_config)

            # Convert based on format
            if output_format == OutputFormat.ALPCA:
                output_data = await self._convert_to_alpaca_format(training_pairs, config, include_metadata)
            elif output_format == OutputFormat.SHAREGPT:
                output_data = await self._convert_to_sharegpt_format(training_pairs, config, include_metadata)
            elif output_format == OutputFormat.CUSTOM_ORCHESTRATOR:
                output_data = await self._convert_to_custom_orchestrator_format(training_pairs, config, include_metadata)
            elif output_format == OutputFormat.JSONL:
                output_data = await self._convert_to_jsonl_format(training_pairs, config, include_metadata)
            elif output_format == OutputFormat.CONVERSATION:
                output_data = await self._convert_to_conversation_format(training_pairs, config, include_metadata)
            else:
                raise ValueError(f"Conversion not implemented for format: {output_format}")

            # Generate conversion metadata
            metadata = {
                'conversion_timestamp': datetime.utcnow().isoformat(),
                'input_pairs_count': len(training_pairs),
                'output_format': output_format.value,
                'format_version': '1.0'
            }

            conversion_stats = {
                'records_generated': self._count_records(output_data),
                'format_compliance': self._check_format_compliance(output_data, output_format),
                'estimated_size_mb': self._estimate_size(output_data)
            }

            logger.info(f"Converted {len(training_pairs)} pairs to {output_format.value} format")
            return FormatConversionResult(
                output_data=output_data,
                format_type=output_format,
                metadata=metadata,
                conversion_stats=conversion_stats
            )

        except Exception as e:
            logger.error(f"Failed to convert training pairs to {output_format.value}: {e}")
            raise

    async def batch_convert_formats(
        self,
        training_pairs: List[Dict[str, Any]],
        output_formats: List[OutputFormat],
        include_metadata: bool = True
    ) -> Dict[OutputFormat, FormatConversionResult]:
        """
        Convert training pairs to multiple formats in batch.

        Args:
            training_pairs: List of training pairs to convert
            output_formats: List of target formats
            include_metadata: Whether to include metadata

        Returns:
            Dict[OutputFormat, FormatConversionResult]: Results by format
        """
        results = {}

        for fmt in output_formats:
            try:
                result = await self.convert_training_pairs(training_pairs, fmt, include_metadata)
                results[fmt] = result
                logger.info(f"Successfully converted to {fmt.value}: {result.conversion_stats['records_generated']} records")
            except Exception as e:
                logger.error(f"Failed to convert to {fmt.value}: {e}")
                results[fmt] = None

        return results

    async def _convert_to_alpaca_format(
        self,
        training_pairs: List[Dict[str, Any]],
        config: Dict[str, Any],
        include_metadata: bool
    ) -> List[Dict[str, Any]]:
        """
        Convert to Alpaca-style format.

        Format: {"instruction": "...", "input": "...", "output": "..."}
        """
        alpaca_records = []

        for pair in training_pairs:
            # Build instruction based on pair type
            instruction = self._build_alpaca_instruction(pair)

            # Build input context
            input_text = self._build_alpaca_input(pair)

            # Build output
            output_text = pair.get('output_text', '')

            record = {
                config['instruction_key']: instruction,
                config['input_key']: input_text,
                config['output_key']: output_text
            }

            # Add metadata if requested
            if include_metadata and pair.get('metadata'):
                record['metadata'] = pair['metadata']

            alpaca_records.append(record)

        return alpaca_records

    async def _convert_to_sharegpt_format(
        self,
        training_pairs: List[Dict[str, Any]],
        config: Dict[str, Any],
        include_metadata: bool
    ) -> List[Dict[str, Any]]:
        """
        Convert to ShareGPT-style conversation format.

        Format: {"conversations": [{"from": "user", "value": "..."}, {"from": "assistant", "value": "..."}]}
        """
        sharegpt_records = []

        for pair in training_pairs:
            conversations = []

            # Add system message
            if config.get('system_message'):
                conversations.append({
                    "from": "system",
                    "value": config['system_message']
                })

            # Add user input
            user_input = self._build_sharegpt_user_input(pair)
            conversations.append({
                "from": "human",
                "value": user_input
            })

            # Add assistant output
            assistant_output = pair.get('output_text', '')
            conversations.append({
                "from": "assistant",
                "value": assistant_output
            })

            record = {
                config['conversation_key']: conversations
            }

            # Add metadata if requested
            if include_metadata and pair.get('metadata'):
                record['metadata'] = pair['metadata']

            sharegpt_records.append(record)

        return sharegpt_records

    async def _convert_to_custom_orchestrator_format(
        self,
        training_pairs: List[Dict[str, Any]],
        config: Dict[str, Any],
        include_metadata: bool
    ) -> List[Dict[str, Any]]:
        """
        Convert to custom orchestrator format.

        This format is optimized for training AI orchestrators with
        context awareness and tool integration.
        """
        orchestrator_records = []

        for pair in training_pairs:
            # Build context from previous steps
            context = self._build_orchestrator_context(pair)

            # Build instruction for orchestration
            instruction = self._build_orchestrator_instruction(pair)

            # Build output with tool calls
            output = self._build_orchestrator_output(pair)

            record = {
                config['context_key']: context,
                config['instruction_key']: instruction,
                config['output_key']: output
            }

            # Add comprehensive metadata
            if include_metadata:
                metadata = pair.get('metadata', {})
                metadata.update({
                    'format_type': pair.get('format_type', 'unknown'),
                    'quality_score': pair.get('quality_score', 0.0),
                    'context_length': len(context),
                    'instruction_length': len(instruction),
                    'output_length': len(output)
                })
                record[config['metadata_key']] = metadata

            orchestrator_records.append(record)

        return orchestrator_records

    async def _convert_to_jsonl_format(
        self,
        training_pairs: List[Dict[str, Any]],
        config: Dict[str, Any],
        include_metadata: bool
    ) -> str:
        """
        Convert to JSONL format.

        Each line is a JSON object representing a training pair.
        """
        jsonl_lines = []

        for pair in training_pairs:
            # Create a clean record for JSONL
            record = {
                'input': pair.get('input_text', ''),
                'output': pair.get('output_text', ''),
                'pair_type': pair.get('format_type', 'unknown')
            }

            # Add metadata if requested
            if include_metadata and pair.get('metadata'):
                record['metadata'] = pair['metadata']

            # Convert to JSON line
            json_line = json.dumps(record, ensure_ascii=False)
            jsonl_lines.append(json_line)

        return config['separator'].join(jsonl_lines)

    async def _convert_to_conversation_format(
        self,
        training_pairs: List[Dict[str, Any]],
        config: Dict[str, Any],
        include_metadata: bool
    ) -> List[Dict[str, Any]]:
        """
        Convert to general conversation format.

        Format: {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
        """
        conversation_records = []

        for pair in training_pairs:
            messages = []

            # Add user message
            user_content = pair.get('input_text', '')
            messages.append({
                "role": "user",
                "content": user_content
            })

            # Add assistant message
            assistant_content = pair.get('output_text', '')
            messages.append({
                "role": "assistant",
                "content": assistant_content
            })

            record = {"messages": messages}

            # Add metadata if requested
            if include_metadata and pair.get('metadata'):
                record['metadata'] = pair['metadata']

            conversation_records.append(record)

        return conversation_records

    def _build_alpaca_instruction(self, pair: Dict[str, Any]) -> str:
        """Build instruction for Alpaca format."""
        format_type = pair.get('format_type', 'unknown')

        if format_type == 'orchestrator':
            return "You are an AI orchestrator. Given the user request and available tools, plan the next action step by step."
        elif format_type == 'tool_specialist':
            return "You are a tool specialist. Given the function name and parameters, provide the correct output format and result."
        elif format_type == 'error_recovery':
            return "You are an error recovery specialist. Given the failure context, provide a recovery strategy."
        else:
            return "You are a helpful AI assistant. Respond to the user's request."

    def _build_alpaca_input(self, pair: Dict[str, Any]) -> str:
        """Build input context for Alpaca format."""
        input_text = pair.get('input_text', '')

        # Add format-specific context
        format_type = pair.get('format_type', 'unknown')
        metadata = pair.get('metadata', {})

        if format_type == 'orchestrator':
            available_tools = metadata.get('available_tools', [])
            if available_tools:
                input_text = f"Available tools: {', '.join(available_tools)}\n\n{input_text}"
        elif format_type == 'tool_specialist':
            tool_name = metadata.get('tool_name', 'unknown')
            input_text = f"Tool: {tool_name}\n\n{input_text}"

        return input_text

    def _build_sharegpt_user_input(self, pair: Dict[str, Any]) -> str:
        """Build user input for ShareGPT format."""
        input_text = pair.get('input_text', '')

        # Add context about the AI's role
        format_type = pair.get('format_type', 'unknown')
        metadata = pair.get('metadata', {})

        if format_type == 'orchestrator':
            available_tools = metadata.get('available_tools', [])
            if available_tools:
                input_text = f"I need help with a task. Available tools: {', '.join(available_tools)}\n\n{input_text}"
        elif format_type == 'tool_specialist':
            tool_name = metadata.get('tool_name', 'unknown')
            input_text = f"I need to use the {tool_name} tool. {input_text}"
        elif format_type == 'error_recovery':
            input_text = f"I'm having trouble with a task. {input_text}"

        return input_text

    def _build_orchestrator_context(self, pair: Dict[str, Any]) -> str:
        """Build context for orchestrator format."""
        input_text = pair.get('input_text', '')
        metadata = pair.get('metadata', {})

        # Add available tools to context
        available_tools = metadata.get('available_tools', [])
        if available_tools:
            context = f"Available tools: {', '.join(available_tools)}\n\n"
        else:
            context = ""

        context += f"Current task: {input_text}"
        return context

    def _build_orchestrator_instruction(self, pair: Dict[str, Any]) -> str:
        """Build instruction for orchestrator format."""
        format_type = pair.get('format_type', 'unknown')

        if format_type == 'orchestrator':
            return "Plan the next action step by step, considering available tools and current context. If using a tool, specify the exact parameters needed."
        elif format_type == 'tool_specialist':
            return "Execute the tool call with the correct parameters and return the result in the expected format."
        elif format_type == 'error_recovery':
            return "Analyze the failure and provide a recovery strategy with specific actions to take."
        else:
            return "Respond to the user's request in a helpful and accurate manner."

    def _build_orchestrator_output(self, pair: Dict[str, Any]) -> str:
        """Build output for orchestrator format."""
        output_text = pair.get('output_text', '')

        # Enhance output with tool call information if applicable
        metadata = pair.get('metadata', {})
        format_type = pair.get('format_type', 'unknown')

        if format_type == 'tool_specialist' and metadata.get('tool_name'):
            tool_name = metadata['tool_name']
            # Try to extract tool call from output
            if 'Action:' in output_text and tool_name in output_text:
                return output_text
            else:
                return f"Action: {tool_name}\n{output_text}"

        return output_text

    def _count_records(self, output_data: Union[str, Dict[str, Any], List[Dict[str, Any]]]) -> int:
        """Count the number of records in the output data."""
        if isinstance(output_data, str):
            # JSONL format - count lines
            return len([line for line in output_data.split('\n') if line.strip()])
        elif isinstance(output_data, list):
            return len(output_data)
        elif isinstance(output_data, dict):
            return 1
        else:
            return 0

    def _check_format_compliance(self, output_data: Union[str, Dict[str, Any], List[Dict[str, Any]]], output_format: OutputFormat) -> float:
        """Check compliance with the target format."""
        try:
            if output_format == OutputFormat.JSONL:
                # Check if it's valid JSONL
                if isinstance(output_data, str):
                    lines = [line.strip() for line in output_data.split('\n') if line.strip()]
                    valid_json_lines = 0
                    for line in lines:
                        try:
                            json.loads(line)
                            valid_json_lines += 1
                        except json.JSONDecodeError:
                            continue
                    return valid_json_lines / len(lines) if lines else 0.0
                else:
                    return 0.0

            elif isinstance(output_data, list):
                # Check if all records have required fields
                required_fields = self._get_required_fields(output_format)
                if not required_fields:
                    return 1.0

                compliant_records = 0
                for record in output_data:
                    if all(field in record for field in required_fields):
                        compliant_records += 1

                return compliant_records / len(output_data) if output_data else 0.0

            else:
                return 1.0 if output_data else 0.0

        except Exception as e:
            logger.warning(f"Error checking format compliance: {e}")
            return 0.0

    def _get_required_fields(self, output_format: OutputFormat) -> List[str]:
        """Get required fields for the output format."""
        field_mappings = {
            OutputFormat.ALPCA: ['instruction', 'input', 'output'],
            OutputFormat.SHAREGPT: ['conversations'],
            OutputFormat.CUSTOM_ORCHESTRATOR: ['context', 'instruction', 'output'],
            OutputFormat.CONVERSATION: ['messages']
        }
        return field_mappings.get(output_format, [])

    def _estimate_size(self, output_data: Union[str, Dict[str, Any], List[Dict[str, Any]]]) -> float:
        """Estimate the size of output data in MB."""
        try:
            if isinstance(output_data, str):
                size_bytes = len(output_data.encode('utf-8'))
            elif isinstance(output_data, dict):
                size_bytes = len(json.dumps(output_data).encode('utf-8'))
            elif isinstance(output_data, list):
                size_bytes = len(json.dumps(output_data).encode('utf-8'))
            else:
                size_bytes = 0

            return round(size_bytes / (1024 * 1024), 3)
        except Exception as e:
            logger.warning(f"Error estimating size: {e}")
            return 0.0

    def get_format_info(self, output_format: OutputFormat) -> Dict[str, Any]:
        """Get information about a specific output format."""
        return {
            'format_name': output_format.value,
            'description': self._get_format_description(output_format),
            'required_fields': self._get_required_fields(output_format),
            'config_options': self.format_configs[output_format],
            'supported': True
        }

    def _get_format_description(self, output_format: OutputFormat) -> str:
        """Get description of the output format."""
        descriptions = {
            OutputFormat.ALPCA: "Alpaca-style format with instruction/input/output structure",
            OutputFormat.SHAREGPT: "ShareGPT-style conversation format with human/assistant turns",
            OutputFormat.CUSTOM_ORCHESTRATOR: "Custom orchestrator format optimized for AI orchestration tasks",
            OutputFormat.JSONL: "JSON Lines format for streaming and large datasets",
            OutputFormat.CONVERSATION: "General conversation format with role-based messages"
        }
        return descriptions.get(output_format, "Unknown format")

    def list_supported_formats(self) -> List[Dict[str, Any]]:
        """List all supported output formats."""
        return [self.get_format_info(fmt) for fmt in OutputFormat]

    def validate_format_config(self, output_format: OutputFormat, config: Dict[str, Any]) -> List[str]:
        """Validate configuration for a specific format."""
        issues = []

        # Check required fields are not overridden inappropriately
        required_fields = self._get_required_fields(output_format)
        for field in required_fields:
            if field in config and config[field] != self.format_configs[output_format].get(field):
                issues.append(f"Cannot override required field '{field}'")

        # Check for invalid keys
        valid_keys = set(self.format_configs[output_format].keys())
        for key in config.keys():
            if key not in valid_keys:
                issues.append(f"Unknown configuration key '{key}'")

        return issues

    async def create_custom_format(
        self,
        format_name: str,
        field_mapping: Dict[str, str],
        description: str = ""
    ) -> OutputFormat:
        """
        Create a custom output format.

        Args:
            format_name: Name for the custom format
            field_mapping: Mapping of internal fields to output fields
            description: Description of the format

        Returns:
            OutputFormat: The custom format enum value
        """
        # Note: In a real implementation, you might want to dynamically
        # create enum values or use a different approach for extensibility
        logger.info(f"Created custom format '{format_name}' with fields: {field_mapping}")
        return OutputFormat.CUSTOM_ORCHESTRATOR  # Placeholder
