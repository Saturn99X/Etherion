"""
Fine-Tuning Anonymizer Service

This module provides anonymization capabilities for execution traces to ensure
PII and sensitive data is removed while preserving execution patterns for ML training.
"""

import logging
import hashlib
import json
import re
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

class FineTuningAnonymizer:
    """
    Anonymizes execution traces for fine-tuning purposes.

    This class removes PII and tenant-specific data while preserving
    execution patterns, tool usage, and reasoning for ML training.
    """

    def __init__(self):
        """Initialize the anonymizer with PII patterns and replacement strategies."""
        # Common PII patterns that should be removed/anonymized
        self.pii_patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            'url': r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))*)?',
            'ip_address': r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            'api_key': r'\b[A-Za-z0-9]{20,}\b',  # Generic API key pattern
            'secret_token': r'\b[A-Za-z0-9+/=]{20,}\b',  # Base64-like tokens
        }

        # Fields that should be completely removed (contain PII)
        self.fields_to_remove = {
            'user_id', 'tenant_id', 'tenant_name', 'user_email', 'user_name',
            'project_id', 'project_name', 'session_id', 'api_key', 'secret',
            'token', 'credentials', 'auth_header', 'webhook_url', 'callback_url'
        }

        # Fields that should be anonymized (keep structure but replace values)
        self.fields_to_anonymize = {
            'input_data', 'output_data', 'thought', 'action_input', 'observation_result',
            'raw_data', 'job_metadata'
        }

        # Tool names that might contain sensitive information
        self.sensitive_tool_patterns = {
            'email', 'api', 'webhook', 'database', 'storage', 'auth', 'secret'
        }

    async def anonymize_execution_trace(self, trace: Dict[str, Any], tenant_id: int) -> Dict[str, Any]:
        """
        Anonymize a complete execution trace for fine-tuning.

        Args:
            trace: The execution trace containing steps and metadata
            tenant_id: Tenant ID (will be removed from final output)

        Returns:
            Dict[str, Any]: Anonymized trace safe for ML training
        """
        try:
            logger.info(f"Anonymizing execution trace for tenant {tenant_id}")

            # Create a deep copy to avoid modifying original
            anonymized_trace = json.loads(json.dumps(trace))

            # Remove tenant-specific metadata
            if 'metadata' in anonymized_trace:
                original_metadata = anonymized_trace['metadata']
                anonymized_trace['metadata'] = self._anonymize_metadata(
                    original_metadata, tenant_id
                )

                # Remove fields that contain PII
                keys_to_remove = []
                for key in anonymized_trace['metadata'].keys():
                    if key in self.fields_to_remove:
                        keys_to_remove.append(key)

                for key in keys_to_remove:
                    del anonymized_trace['metadata'][key]

            # Anonymize each step in the trace
            if 'steps' in anonymized_trace:
                anonymized_trace['steps'] = [
                    self._anonymize_step(step, tenant_id)
                    for step in anonymized_trace['steps']
                ]

            # Add anonymization metadata
            anonymized_trace['_anonymization_info'] = {
                'anonymized_at': datetime.utcnow().isoformat(),
                'original_tenant_id_hash': hashlib.sha256(str(tenant_id).encode()).hexdigest(),
                'version': '1.0'
            }

            logger.info("Successfully anonymized execution trace")
            return anonymized_trace

        except Exception as e:
            logger.error(f"Failed to anonymize execution trace: {e}")
            raise

    async def anonymize_job_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Anonymize job data for fine-tuning.

        Args:
            job_data: Job data dictionary

        Returns:
            Dict[str, Any]: Anonymized job data
        """
        try:
            anonymized_data = {}

            for key, value in job_data.items():
                if key in self.fields_to_remove:
                    # Skip fields that contain PII
                    continue
                elif key in self.fields_to_anonymize:
                    # Anonymize fields that might contain sensitive data
                    if isinstance(value, str):
                        # Try to parse as JSON first for deeper anonymization
                        try:
                            parsed_json = json.loads(value)
                            if isinstance(parsed_json, (dict, list)):
                                anonymized_json = self._anonymize_data_structure(parsed_json)
                                anonymized_data[key] = json.dumps(anonymized_json)
                            else:
                                anonymized_data[key] = self._anonymize_text_field(value)
                        except (json.JSONDecodeError, TypeError):
                            anonymized_data[key] = self._anonymize_text_field(value)
                    else:
                        anonymized_data[key] = self._anonymize_text_field(str(value))
                elif isinstance(value, dict):
                    # Recursively anonymize nested dictionaries
                    anonymized_data[key] = await self.anonymize_job_data(value)
                elif isinstance(value, list):
                    # Anonymize list items if they're dictionaries
                    anonymized_data[key] = [
                        await self.anonymize_job_data(item) if isinstance(item, dict) else item
                        for item in value
                    ]
                else:
                    # Check if it's a string that might contain JSON
                    if isinstance(value, str):
                        # Try to parse as JSON first for deeper anonymization
                        try:
                            parsed_json = json.loads(value)
                            if isinstance(parsed_json, (dict, list)):
                                anonymized_json = self._anonymize_data_structure(parsed_json)
                                anonymized_data[key] = json.dumps(anonymized_json)
                            else:
                                anonymized_data[key] = self._anonymize_text_field(value)
                        except (json.JSONDecodeError, TypeError):
                            anonymized_data[key] = self._anonymize_text_field(value)
                    else:
                        # Keep other fields as-is
                        anonymized_data[key] = value

            return anonymized_data

        except Exception as e:
            logger.error(f"Failed to anonymize job data: {e}")
            raise

    def _anonymize_step(self, step: Dict[str, Any], tenant_id: int) -> Dict[str, Any]:
        """
        Anonymize a single execution trace step.

        Args:
            step: Step dictionary
            tenant_id: Tenant ID

        Returns:
            Dict[str, Any]: Anonymized step
        """
        anonymized_step = {}

        for key, value in step.items():
            if key in self.fields_to_remove:
                # Skip fields containing PII
                continue
            elif key == 'thought':
                # Anonymize reasoning while preserving structure
                anonymized_step[key] = self._anonymize_reasoning(value)
            elif key == 'action_input':
                # Anonymize tool inputs
                anonymized_step[key] = self._anonymize_action_input(value)
            elif key == 'observation_result':
                # Anonymize tool outputs
                anonymized_step[key] = self._anonymize_observation_result(value)
            elif key == 'raw_data':
                # Anonymize raw step data
                anonymized_step[key] = self._anonymize_raw_data(value)
            else:
                # Keep other fields (step_number, timestamp, step_type, etc.)
                anonymized_step[key] = value

        return anonymized_step

    def _anonymize_metadata(self, metadata: Dict[str, Any], tenant_id: int) -> Dict[str, Any]:
        """
        Anonymize trace metadata.

        Args:
            metadata: Metadata dictionary
            tenant_id: Tenant ID

        Returns:
            Dict[str, Any]: Anonymized metadata
        """
        anonymized_metadata = {}

        for key, value in metadata.items():
            if key in self.fields_to_remove:
                continue
            elif key == 'job_type':
                # Keep job type but anonymize if it contains sensitive info
                anonymized_metadata[key] = self._anonymize_job_type(value)
            elif isinstance(value, dict):
                anonymized_metadata[key] = self._anonymize_metadata(value, tenant_id)
            elif isinstance(value, list):
                anonymized_metadata[key] = [
                    self._anonymize_metadata(item, tenant_id) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                anonymized_metadata[key] = self._anonymize_text_field(str(value))

        return anonymized_metadata

    def _anonymize_reasoning(self, thought: str) -> str:
        """
        Anonymize reasoning text while preserving structure and patterns.

        Args:
            thought: Reasoning text

        Returns:
            str: Anonymized reasoning
        """
        if not thought:
            return thought

        # Replace PII patterns with generic placeholders
        anonymized = thought

        for pattern_name, pattern in self.pii_patterns.items():
            anonymized = re.sub(pattern, f'<{pattern_name.upper()}>', anonymized)

        # Replace specific identifiers with generic ones
        anonymized = re.sub(r'\buser_\d+\b', '<USER_ID>', anonymized)
        anonymized = re.sub(r'\btenant_\d+\b', '<TENANT_ID>', anonymized)
        anonymized = re.sub(r'\bproject_\d+\b', '<PROJECT_ID>', anonymized)

        return anonymized

    def _anonymize_action_input(self, action_input: str) -> str:
        """
        Anonymize tool action inputs.

        Args:
            action_input: JSON string of tool input

        Returns:
            str: Anonymized action input
        """
        try:
            if not action_input:
                return action_input

            data = json.loads(action_input)
            anonymized_data = self._anonymize_data_structure(data)
            return json.dumps(anonymized_data)
        except (json.JSONDecodeError, TypeError):
            # If it's not JSON, treat as plain text
            return self._anonymize_text_field(action_input)

    def _anonymize_observation_result(self, observation_result: str) -> str:
        """
        Anonymize tool observation results.

        Args:
            observation_result: Tool output

        Returns:
            str: Anonymized observation result
        """
        try:
            if not observation_result:
                return observation_result

            data = json.loads(observation_result)
            anonymized_data = self._anonymize_data_structure(data)
            return json.dumps(anonymized_data)
        except (json.JSONDecodeError, TypeError):
            # If it's not JSON, treat as plain text
            return self._anonymize_text_field(observation_result)

    def _anonymize_raw_data(self, raw_data: str) -> str:
        """
        Anonymize raw step data.

        Args:
            raw_data: Raw data JSON string

        Returns:
            str: Anonymized raw data
        """
        try:
            if not raw_data:
                return raw_data

            data = json.loads(raw_data)
            anonymized_data = self._anonymize_data_structure(data)
            return json.dumps(anonymized_data)
        except (json.JSONDecodeError, TypeError):
            # If it's not JSON, treat as plain text
            return self._anonymize_text_field(raw_data)

    def _anonymize_data_structure(self, data: Any) -> Any:
        """
        Recursively anonymize data structures.

        Args:
            data: Data to anonymize

        Returns:
            Any: Anonymized data
        """
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if key in self.fields_to_remove:
                    continue  # Skip fields containing PII

                # Check if the key itself contains PII patterns
                key_str = str(key).lower()
                contains_pii = any(pattern in key_str for pattern in ['email', 'phone', 'api', 'key', 'secret', 'token', 'password', 'credential', 'auth'])

                if contains_pii:
                    continue  # Skip keys that suggest PII content

                if isinstance(value, (dict, list)):
                    anonymized_value = self._anonymize_data_structure(value)
                    # If the anonymized value is empty (all PII removed), skip this key
                    if isinstance(anonymized_value, dict) and len(anonymized_value) == 0:
                        continue
                    if isinstance(anonymized_value, list) and len(anonymized_value) == 0:
                        continue
                    result[key] = anonymized_value
                elif isinstance(value, str):
                    # Try to parse as JSON first for deeper anonymization
                    try:
                        parsed_json = json.loads(value)
                        if isinstance(parsed_json, (dict, list)):
                            anonymized_json = self._anonymize_data_structure(parsed_json)
                            result[key] = json.dumps(anonymized_json)
                        else:
                            result[key] = self._anonymize_text_field(value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = self._anonymize_text_field(value)
                else:
                    result[key] = value
            return result
        elif isinstance(data, list):
            return [self._anonymize_data_structure(item) for item in data]
        elif isinstance(data, str):
            return self._anonymize_text_field(data)
        else:
            return data

    def _anonymize_text_field(self, text: str) -> str:
        """
        Anonymize text fields by removing PII patterns.

        Args:
            text: Text to anonymize

        Returns:
            str: Anonymized text
        """
        if not text:
            return text

        # Apply all PII patterns
        for pattern_name, pattern in self.pii_patterns.items():
            text = re.sub(pattern, f'<{pattern_name.upper()}>', text)

        # Replace specific identifiers
        text = re.sub(r'\buser_\d+\b', '<USER_ID>', text)
        text = re.sub(r'\btenant_\d+\b', '<TENANT_ID>', text)
        text = re.sub(r'\bproject_\d+\b', '<PROJECT_ID>', text)

        return text

    def _anonymize_job_type(self, job_type: str) -> str:
        """
        Anonymize job type if it contains sensitive information.

        Args:
            job_type: Job type string

        Returns:
            str: Anonymized job type
        """
        # Remove sensitive patterns from job type
        for pattern in self.pii_patterns.values():
            job_type = re.sub(pattern, '<REDACTED>', job_type)

        return job_type
