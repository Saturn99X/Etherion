import logging
import asyncio
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import re

from src.database.db import get_db, session_scope
from src.database.models import User, UserObservation, Job, ExecutionTraceStep
from src.database.models import Tenant
from src.utils.tenant_context import get_tenant_context
from src.core.caching import get_cache_manager
from src.services.observation_performance_monitor import (
    start_observation_timing,
    end_observation_timing,
    record_observation_error
)

logger = logging.getLogger(__name__)

class UserObservationService:
    """Service for recording and analyzing user observation patterns"""

    def __init__(self):
        self.db = get_db()
        self.cache_manager = get_cache_manager()

    def record_interaction(self, user_id: int, tenant_id: int, interaction_data: Dict[str, Any]) -> None:
        """
        Record a user interaction for pattern analysis

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            interaction_data: Dictionary containing interaction details
        """
        timer_id = start_observation_timing('record_interaction', user_id, tenant_id)

        try:
            with session_scope() as session:
                # Get or create user observation record
                observation = session.query(UserObservation).filter(
                    UserObservation.user_id == user_id,
                    UserObservation.tenant_id == tenant_id
                ).first()

                if not observation:
                    observation = UserObservation(
                        user_id=user_id,
                        tenant_id=tenant_id
                    )
                    session.add(observation)

                # Analyze and update observation patterns
                self._analyze_communication_style(observation, interaction_data)
                self._analyze_success_patterns(observation, interaction_data)
                self._analyze_behavioral_patterns(observation, interaction_data)
                self._analyze_content_preferences(observation, interaction_data)

                # Update metadata
                observation.observation_count += 1
                observation.last_observation_at = datetime.utcnow()
                observation.confidence_score = self._calculate_confidence_score(observation)
                observation.updated_at = datetime.utcnow()

                session.commit()
                logger.info(f"Recorded observation for user {user_id}, count: {observation.observation_count}")

            # Record successful timing
            duration = end_observation_timing(timer_id, 'record_interaction', user_id, tenant_id)
            logger.debug(f"Recorded interaction for user {user_id} in {duration:.3f}s")

        except Exception as e:
            # Record error timing
            duration = end_observation_timing(timer_id, 'record_interaction', user_id, tenant_id)
            record_observation_error('record_interaction', tenant_id, e)
            logger.error(f"Error recording user observation: {e}")
            raise

    def _analyze_communication_style(self, observation: UserObservation, interaction_data: Dict[str, Any]) -> None:
        """Analyze and update communication style preferences"""
        try:
            # Analyze response content for tone
            response_content = interaction_data.get('response_content', '')
            if response_content:
                # Simple tone analysis based on keywords and structure
                tone_score = self._analyze_tone(response_content)
                self._update_field_confidence(observation, 'preferred_tone', tone_score)

                # Analyze response length
                length_score = self._analyze_response_length(response_content)
                self._update_field_confidence(observation, 'response_length_preference', length_score)

                # Analyze technical level
                technical_score = self._analyze_technical_level(response_content)
                self._update_field_confidence(observation, 'technical_level', technical_score)

                # Analyze formality
                formality_score = self._analyze_formality(response_content)
                self._update_field_confidence(observation, 'formality_level', formality_score)

        except Exception as e:
            logger.warning(f"Error analyzing communication style: {e}")

    def _analyze_success_patterns(self, observation: UserObservation, interaction_data: Dict[str, Any]) -> None:
        """Analyze success and failure patterns"""
        try:
            success_indicators = interaction_data.get('success_indicators', {})
            tools_used = interaction_data.get('tools_used', [])
            approaches_used = interaction_data.get('approaches_used', [])

            if success_indicators.get('success', False):
                # Record successful tools
                if tools_used:
                    self._update_json_list_field(observation, 'successful_tools', tools_used)

                # Record successful approaches
                if approaches_used:
                    self._update_json_list_field(observation, 'successful_approaches', approaches_used)
            else:
                # Record failed approaches
                if approaches_used:
                    self._update_json_list_field(observation, 'failed_approaches', approaches_used)

        except Exception as e:
            logger.warning(f"Error analyzing success patterns: {e}")

    def _analyze_behavioral_patterns(self, observation: UserObservation, interaction_data: Dict[str, Any]) -> None:
        """Analyze behavioral patterns"""
        try:
            # Analyze response time expectations
            response_time = interaction_data.get('response_time')
            if response_time:
                rt_score = self._analyze_response_time_patterns(response_time)
                self._update_field_confidence(observation, 'response_time_expectations', rt_score)

            # Analyze follow-up patterns
            follow_up_count = interaction_data.get('follow_up_count', 0)
            if follow_up_count > 0:
                fu_score = self._analyze_follow_up_patterns(follow_up_count)
                self._update_field_confidence(observation, 'follow_up_frequency', fu_score)

            # Analyze peak activity hours
            current_hour = datetime.utcnow().hour
            self._update_json_list_field(observation, 'peak_activity_hours', [str(current_hour)])

        except Exception as e:
            logger.warning(f"Error analyzing behavioral patterns: {e}")

    def _analyze_content_preferences(self, observation: UserObservation, interaction_data: Dict[str, Any]) -> None:
        """Analyze content preferences"""
        try:
            content = interaction_data.get('content', '')
            if content:
                # Analyze complexity
                complexity_score = self._analyze_complexity(content)
                self._update_field_confidence(observation, 'complexity_level', complexity_score)

                # Analyze example requirements
                examples_score = self._analyze_example_requirements(content)
                self._update_field_confidence(observation, 'example_requirements', examples_score)

        except Exception as e:
            logger.warning(f"Error analyzing content preferences: {e}")

    def _analyze_tone(self, content: str) -> Dict[str, float]:
        """Analyze tone from content"""
        scores = {'formal': 0, 'casual': 0, 'technical': 0, 'friendly': 0}

        # Formal indicators
        if re.search(r'\b(therefore|moreover|furthermore|consequently|however)\b', content, re.I):
            scores['formal'] += 1
        if re.search(r'\b(I would|we should|it is recommended)\b', content, re.I):
            scores['formal'] += 1

        # Casual indicators
        if re.search(r'\b(hey|cool|awesome|yeah|you know)\b', content, re.I):
            scores['casual'] += 1
        if len(content.split('!')) > 3:  # Multiple exclamations
            scores['casual'] += 1

        # Technical indicators
        if re.search(r'\b(api|function|implementation|algorithm|framework)\b', content, re.I):
            scores['technical'] += 1
        if re.search(r'\b\d+\.?\d*\s*(ms|kb|mb|gb|percent|api|json|xml)\b', content, re.I):
            scores['technical'] += 1

        # Friendly indicators
        if re.search(r'\b(thank you|please|appreciate|glad|happy)\b', content, re.I):
            scores['friendly'] += 1
        if re.search(r'\b\U0001F600-\U0001F64F', content):  # Emojis
            scores['friendly'] += 1

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            for key in scores:
                scores[key] = scores[key] / total

        return scores

    def _analyze_response_length(self, content: str) -> Dict[str, float]:
        """Analyze preferred response length"""
        word_count = len(content.split())
        scores = {'concise': 0, 'detailed': 0, 'comprehensive': 0}

        if word_count < 50:
            scores['concise'] = 1.0
        elif word_count < 200:
            scores['detailed'] = 0.7
            scores['concise'] = 0.3
        else:
            scores['comprehensive'] = 1.0

        return scores

    def _analyze_technical_level(self, content: str) -> Dict[str, float]:
        """Analyze technical level"""
        technical_terms = ['api', 'implementation', 'framework', 'algorithm', 'database', 'endpoint']
        advanced_terms = ['asynchronous', 'concurrency', 'microservice', 'kubernetes', 'docker']

        term_count = sum(1 for term in technical_terms if term in content.lower())
        advanced_count = sum(1 for term in advanced_terms if term in content.lower())

        scores = {'beginner': 0, 'intermediate': 0, 'expert': 0}

        if term_count == 0:
            scores['beginner'] = 1.0
        elif advanced_count == 0:
            scores['intermediate'] = 0.8
            scores['beginner'] = 0.2
        else:
            scores['expert'] = 1.0

        return scores

    def _analyze_formality(self, content: str) -> Dict[str, float]:
        """Analyze formality level"""
        formal_phrases = ['I would like to', 'It is important to', 'Please be advised', 'In accordance with']
        informal_phrases = ['Hey', 'You know', 'Cool', 'Awesome', 'No worries']

        formal_count = sum(1 for phrase in formal_phrases if phrase in content)
        informal_count = sum(1 for phrase in informal_phrases if phrase in content)

        scores = {'high': 0, 'medium': 0, 'low': 0}

        if formal_count > informal_count:
            scores['high'] = min(1.0, formal_count * 0.3)
            scores['medium'] = max(0, 1.0 - scores['high'])
        elif informal_count > 0:
            scores['low'] = min(1.0, informal_count * 0.4)
            scores['medium'] = max(0, 1.0 - scores['low'])
        else:
            scores['medium'] = 1.0

        return scores

    def _analyze_response_time_patterns(self, response_time: float) -> Dict[str, float]:
        """Analyze response time patterns (in seconds)"""
        scores = {'immediate': 0, 'same-day': 0, 'relaxed': 0}

        if response_time < 300:  # 5 minutes
            scores['immediate'] = 1.0
        elif response_time < 3600:  # 1 hour
            scores['same-day'] = 0.8
            scores['immediate'] = 0.2
        else:
            scores['relaxed'] = 1.0

        return scores

    def _analyze_follow_up_patterns(self, follow_up_count: int) -> Dict[str, float]:
        """Analyze follow-up frequency patterns"""
        scores = {'never': 0, 'occasional': 0, 'regular': 0}

        if follow_up_count == 0:
            scores['never'] = 1.0
        elif follow_up_count <= 2:
            scores['occasional'] = 1.0
        else:
            scores['regular'] = 1.0

        return scores

    def _analyze_complexity(self, content: str) -> Dict[str, float]:
        """Analyze content complexity"""
        sentences = content.split('.')
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0

        scores = {'simple': 0, 'moderate': 0, 'complex': 0}

        if avg_sentence_length < 10:
            scores['simple'] = 1.0
        elif avg_sentence_length < 20:
            scores['moderate'] = 1.0
        else:
            scores['complex'] = 1.0

        return scores

    def _analyze_example_requirements(self, content: str) -> Dict[str, float]:
        """Analyze example requirements"""
        example_indicators = ['for example', 'such as', 'like', 'e.g.', 'sample', 'demo']
        count = sum(1 for indicator in example_indicators if indicator in content.lower())

        scores = {'none': 0, 'some': 0, 'extensive': 0}

        if count == 0:
            scores['none'] = 1.0
        elif count <= 2:
            scores['some'] = 1.0
        else:
            scores['extensive'] = 1.0

        return scores

    def _update_field_confidence(self, observation: UserObservation, field_name: str, new_scores: Dict[str, float]) -> None:
        """Update field with confidence-weighted averaging"""
        try:
            current_value = getattr(observation, field_name, "")

            if not current_value:
                # First observation - use new scores directly
                best_score = max(new_scores.items(), key=lambda x: x[1])
                setattr(observation, field_name, best_score[0])
                return

            # Parse current value
            try:
                current_scores = json.loads(current_value) if current_value.startswith('{') else {current_value: 1.0}
            except:
                current_scores = {current_value: 1.0}

            # Weight by confidence and observation count
            confidence_weight = min(0.3, observation.observation_count * 0.1)

            for category, score in new_scores.items():
                if category in current_scores:
                    # Weighted average with existing scores
                    current_scores[category] = (
                        current_scores[category] * (1 - confidence_weight) +
                        score * confidence_weight
                    )
                else:
                    current_scores[category] = score * confidence_weight

            # Normalize and pick best
            total = sum(current_scores.values())
            if total > 0:
                for category in current_scores:
                    current_scores[category] /= total

            best_category = max(current_scores.items(), key=lambda x: x[1])
            setattr(observation, field_name, json.dumps(current_scores) if len(current_scores) > 1 else best_category[0])

        except Exception as e:
            logger.warning(f"Error updating field confidence for {field_name}: {e}")

    def _update_json_list_field(self, observation: UserObservation, field_name: str, new_items: List[str]) -> None:
        """Update JSON list fields with frequency counting"""
        try:
            current_value = getattr(observation, field_name, "[]")
            try:
                current_list = json.loads(current_value) if current_value else []
            except:
                current_list = []

            # Count frequencies
            counter = Counter(current_list)
            for item in new_items:
                counter[item] += 1

            # Keep top items (limit to 10 most frequent)
            most_common = [item for item, _ in counter.most_common(10)]
            setattr(observation, field_name, json.dumps(most_common))

        except Exception as e:
            logger.warning(f"Error updating JSON list field {field_name}: {e}")

    def _calculate_confidence_score(self, observation: UserObservation) -> float:
        """Calculate overall confidence score based on observation frequency and consistency"""
        try:
            # Base confidence from observation count
            count_confidence = min(1.0, observation.observation_count / 10.0)

            # Consistency bonus (if fields have consistent values)
            consistency_bonus = 0.0
            total_fields = 0

            # Check string fields for consistency
            string_fields = [
                'preferred_tone', 'response_length_preference', 'technical_level',
                'formality_level', 'patience_level', 'detail_orientation',
                'risk_tolerance', 'decision_making_style', 'learning_style',
                'response_time_expectations', 'follow_up_frequency',
                'complexity_level', 'example_requirements', 'visual_vs_text'
            ]

            for field in string_fields:
                value = getattr(observation, field, "")
                if value and not value.startswith('{'):
                    consistency_bonus += 0.1
                    total_fields += 1

            if total_fields > 0:
                consistency_bonus = min(0.3, consistency_bonus / total_fields)

            return min(1.0, count_confidence + consistency_bonus)

        except Exception as e:
            logger.warning(f"Error calculating confidence score: {e}")
            return 0.0

    async def get_user_observations(self, user_id: int, tenant_id: int) -> Optional[UserObservation]:
        """Get user observation data with caching"""
        timer_id = start_observation_timing('get_user_observations', user_id, tenant_id)

        try:
            cache_key = f"user_observations:{tenant_id}:{user_id}"
            cached_data = await self.cache_manager.get_db_query(cache_key)

            if cached_data:
                # Reconstruct a lightweight object with attribute access
                try:
                    from types import SimpleNamespace
                    if isinstance(cached_data, dict):
                        return SimpleNamespace(**cached_data)  # type: ignore[return-value]
                except Exception:
                    pass

            with session_scope() as session:
                observation = session.query(UserObservation).filter(
                    UserObservation.user_id == user_id,
                    UserObservation.tenant_id == tenant_id
                ).first()

                if observation:
                    # Store a JSON-serializable snapshot in cache to avoid ORM serialization issues
                    await self.cache_manager.set_db_query(cache_key, self._observation_to_cache(observation), expire=300)  # 5 minutes

                # Record successful timing
                duration = end_observation_timing(timer_id, 'get_user_observations', user_id, tenant_id)
                logger.debug(f"Retrieved observations for user {user_id} in {duration:.3f}s")

                return observation

        except Exception as e:
            # Record error timing
            duration = end_observation_timing(timer_id, 'get_user_observations', user_id, tenant_id)
            record_observation_error('get_user_observations', tenant_id, e)
            logger.error(f"Error getting user observations: {e}")
            return None

    @staticmethod
    def _observation_to_cache(observation: UserObservation) -> Dict[str, Any]:
        """Serialize a UserObservation into a JSON-serializable dict for caching."""
        try:
            return {
                # Identity
                "user_id": observation.user_id,
                "tenant_id": observation.tenant_id,
                # Communication Preferences
                "preferred_tone": observation.preferred_tone,
                "response_length_preference": observation.response_length_preference,
                "technical_level": observation.technical_level,
                "formality_level": observation.formality_level,
                # Success Patterns (JSON strings as stored)
                "successful_tools": observation.successful_tools,
                "successful_approaches": observation.successful_approaches,
                "failed_approaches": observation.failed_approaches,
                # Content Preferences
                "complexity_level": observation.complexity_level,
                # Metadata
                "observation_count": observation.observation_count,
                "confidence_score": observation.confidence_score,
                "last_observation_at": observation.last_observation_at.isoformat() if getattr(observation, "last_observation_at", None) else None,
            }
        except Exception:
            # Minimal fallback to avoid cache failures
            return {
                "user_id": getattr(observation, "user_id", None),
                "tenant_id": getattr(observation, "tenant_id", None),
                "preferred_tone": getattr(observation, "preferred_tone", ""),
                "response_length_preference": getattr(observation, "response_length_preference", ""),
                "technical_level": getattr(observation, "technical_level", ""),
                "formality_level": getattr(observation, "formality_level", ""),
                "successful_tools": getattr(observation, "successful_tools", ""),
                "successful_approaches": getattr(observation, "successful_approaches", ""),
                "failed_approaches": getattr(observation, "failed_approaches", ""),
                "complexity_level": getattr(observation, "complexity_level", ""),
                "observation_count": getattr(observation, "observation_count", 0),
                "confidence_score": getattr(observation, "confidence_score", 0.0),
                "last_observation_at": None,
            }

    async def generate_system_instructions(self, user_id: int, tenant_id: int) -> str:
        """Generate system instructions based on user observations"""
        timer_id = start_observation_timing('generate_system_instructions', user_id, tenant_id)

        try:
            observation = await self.get_user_observations(user_id, tenant_id)
            if not observation:
                return ""

            instructions = [
                f"Communication Style: Use {observation.preferred_tone} tone with {observation.response_length_preference} responses.",
                f"Technical Level: Adjust complexity to {observation.technical_level} level.",
                f"Formality: Maintain {observation.formality_level} formality level."
            ]

            if observation.successful_tools:
                instructions.append(f"Preferred Tools: Use these tools when appropriate: {observation.successful_tools}")

            if observation.successful_approaches:
                instructions.append(f"Successful Approaches: {observation.successful_approaches}")

            if observation.failed_approaches:
                instructions.append(f"Failed Approaches to Avoid: {observation.failed_approaches}")

            if observation.complexity_level:
                instructions.append(f"Content Complexity: Provide {observation.complexity_level} level of complexity.")

            result = "\n".join(instructions)

            # Record successful timing
            duration = end_observation_timing(timer_id, 'generate_system_instructions', user_id, tenant_id)
            logger.debug(f"Generated system instructions for user {user_id} in {duration:.3f}s")

            return result

        except Exception as e:
            # Record error timing
            duration = end_observation_timing(timer_id, 'generate_system_instructions', user_id, tenant_id)
            record_observation_error('generate_system_instructions', tenant_id, e)
            logger.error(f"Error generating system instructions: {e}")
            return ""

    async def record_execution_trace_observation(self, job_id: str, user_id: int, tenant_id: int, execution_data: Dict[str, Any]) -> None:
        """Record observations from execution traces"""
        try:
            # Extract relevant data from execution trace
            trace_steps = execution_data.get('trace_steps', [])
            success = execution_data.get('success', False)
            tools_used = execution_data.get('tools_used', [])
            execution_time = execution_data.get('execution_time', 0)

            interaction_data = {
                'response_content': execution_data.get('final_output', ''),
                'success_indicators': {'success': success},
                'tools_used': tools_used,
                'approaches_used': ['orchestrator_execution'],
                'response_time': execution_time,
                'follow_up_count': len([s for s in trace_steps if s.get('step_type') == 'ACTION']),
                'content': execution_data.get('goal_description', '')
            }

            self.record_interaction(user_id, tenant_id, interaction_data)

        except Exception as e:
            logger.error(f"Error recording execution trace observation: {e}")

    def get_personality_profile(self, user_id: int, tenant_id: int) -> Dict[str, Any]:
        """Get comprehensive personality profile for user"""
        try:
            observation = self.get_user_observations(user_id, tenant_id)
            if not observation:
                return {"error": "No observations available"}

            profile = {
                "user_id": user_id,
                "communication_preferences": {
                    "preferred_tone": observation.preferred_tone,
                    "response_length": observation.response_length_preference,
                    "technical_level": observation.technical_level,
                    "formality_level": observation.formality_level
                },
                "personality_traits": {
                    "patience_level": observation.patience_level,
                    "detail_orientation": observation.detail_orientation,
                    "risk_tolerance": observation.risk_tolerance,
                    "decision_making_style": observation.decision_making_style,
                    "learning_style": observation.learning_style
                },
                "success_patterns": {
                    "successful_tools": observation.successful_tools,
                    "successful_approaches": observation.successful_approaches,
                    "failed_approaches": observation.failed_approaches
                },
                "behavioral_patterns": {
                    "peak_activity_hours": observation.peak_activity_hours,
                    "response_time_expectations": observation.response_time_expectations,
                    "follow_up_frequency": observation.follow_up_frequency
                },
                "content_preferences": {
                    "complexity_level": observation.complexity_level,
                    "example_requirements": observation.example_requirements,
                    "visual_vs_text": observation.visual_vs_text
                },
                "metadata": {
                    "observation_count": observation.observation_count,
                    "confidence_score": observation.confidence_score,
                    "last_observation": observation.last_observation_at.isoformat() if observation.last_observation_at else None
                }
            }

            return profile

        except Exception as e:
            logger.error(f"Error generating personality profile: {e}")
            return {"error": str(e)}

    async def process_execution_trace_for_observations(self, job_id: str, user_id: int, tenant_id: int) -> None:
        """Process execution trace data to extract and record user observations"""
        try:
            from src.database.models import ExecutionTraceStep

            with session_scope() as session:
                # Get all execution trace steps for the job
                trace_steps = session.query(ExecutionTraceStep).filter(
                    ExecutionTraceStep.job_id == job_id,
                    ExecutionTraceStep.tenant_id == tenant_id
                ).order_by(ExecutionTraceStep.step_number.asc()).all()

                if not trace_steps:
                    logger.warning(f"No execution trace steps found for job {job_id}")
                    return

                # Extract tools used from action steps
                tools_used = []
                for step in trace_steps:
                    if step.action_tool and step.step_type.value == "ACTION":
                        tools_used.append(step.action_tool)

                # Extract final output from the last observation step
                final_output = ""
                for step in reversed(trace_steps):
                    if step.observation_result and step.step_type.value == "OBSERVATION":
                        final_output = step.observation_result
                        break

                # Extract execution time from first to last step
                if trace_steps:
                    start_time = trace_steps[0].timestamp
                    end_time = trace_steps[-1].timestamp
                    execution_time = (end_time - start_time).total_seconds()
                else:
                    execution_time = 0

                # Determine success based on final output
                success = len(final_output.strip()) > 0 and "error" not in final_output.lower()

                # Create observation data from execution trace
                execution_interaction = {
                    'response_content': final_output,
                    'success_indicators': {'success': success},
                    'tools_used': list(set(tools_used)),  # Remove duplicates
                    'approaches_used': ['execution_trace_analysis'],
                    'response_time': execution_time,
                    'follow_up_count': len([s for s in trace_steps if s.step_type.value == "ACTION"]),
                    'content': f"Execution trace analysis for job {job_id}"
                }

                # Record the observation
                self.record_interaction(user_id, tenant_id, execution_interaction)

                logger.info(f"Processed {len(trace_steps)} execution trace steps for user {user_id}, job {job_id}")

        except Exception as e:
            logger.error(f"Error processing execution trace for observations: {e}")

    def integrate_with_logging_system(self, user_id: int, tenant_id: int, log_message: str, log_level: str = "INFO") -> None:
        """Integrate observation recording with existing logging system"""
        try:
            # Analyze log message for potential observation data
            observation_data = self._extract_observation_from_log(log_message, log_level)

            if observation_data:
                # Record the observation
                self.record_interaction(user_id, tenant_id, observation_data)
                logger.info(f"Recorded observation from log message for user {user_id}")

        except Exception as e:
            logger.warning(f"Error integrating observation with logging system: {e}")

    def _extract_observation_from_log(self, log_message: str, log_level: str) -> Optional[Dict[str, Any]]:
        """Extract potential observation data from log messages"""
        try:
            # Only process error and warning logs for failure pattern analysis
            if log_level.upper() not in ['ERROR', 'WARNING', 'CRITICAL']:
                return None

            # Look for specific patterns in log messages
            if "timeout" in log_message.lower():
                return {
                    'response_content': f"System timeout detected: {log_message}",
                    'success_indicators': {'success': False},
                    'tools_used': [],
                    'approaches_used': ['timeout_failure'],
                    'response_time': 0,
                    'follow_up_count': 0,
                    'content': 'System timeout pattern detected'
                }

            elif "error" in log_message.lower() and "tool" in log_message.lower():
                # Extract tool name if mentioned
                import re
                tool_match = re.search(r'tool[:\s]+([^\s,]+)', log_message, re.I)
                tool_name = tool_match.group(1) if tool_match else "unknown_tool"

                return {
                    'response_content': f"Tool error detected: {log_message}",
                    'success_indicators': {'success': False},
                    'tools_used': [tool_name],
                    'approaches_used': ['tool_failure'],
                    'response_time': 0,
                    'follow_up_count': 0,
                    'content': f'Tool failure pattern for {tool_name}'
                }

            elif "success" in log_message.lower() and "completion" in log_message.lower():
                return {
                    'response_content': f"Successful completion: {log_message}",
                    'success_indicators': {'success': True},
                    'tools_used': [],
                    'approaches_used': ['successful_completion'],
                    'response_time': 0,
                    'follow_up_count': 0,
                    'content': 'Successful completion pattern detected'
                }

            return None

        except Exception as e:
            logger.warning(f"Error extracting observation from log: {e}")
            return None

    async def background_observation_processing(self, user_id: int, tenant_id: int) -> None:
        """Background task to process and analyze accumulated observations"""
        try:
            observation = self.get_user_observations(user_id, tenant_id)
            if not observation:
                return

            # Perform pattern analysis and update confidence scores
            if observation.observation_count > 5:  # Only analyze after sufficient data
                # Update personality traits based on observed patterns
                self._update_personality_traits(observation)

                # Update success metrics
                self._update_success_metrics(observation)

                # Recalculate confidence score
                observation.confidence_score = self._calculate_confidence_score(observation)

                # Save updates
                with session_scope() as session:
                    session.merge(observation)
                    session.commit()

                logger.info(f"Background observation processing completed for user {user_id}")

        except Exception as e:
            logger.error(f"Error in background observation processing: {e}")

    def _update_personality_traits(self, observation: UserObservation) -> None:
        """Update personality traits based on observed patterns"""
        try:
            # Analyze patience based on response time expectations
            if observation.response_time_expectations:
                if "immediate" in observation.response_time_expectations:
                    observation.patience_level = "low"
                elif "relaxed" in observation.response_time_expectations:
                    observation.patience_level = "high"
                else:
                    observation.patience_level = "medium"

            # Analyze detail orientation based on response length preferences
            if observation.response_length_preference:
                if "comprehensive" in observation.response_length_preference:
                    observation.detail_orientation = "high"
                elif "concise" in observation.response_length_preference:
                    observation.detail_orientation = "low"
                else:
                    observation.detail_orientation = "medium"

            # Analyze risk tolerance based on successful vs failed approaches
            if observation.successful_approaches or observation.failed_approaches:
                try:
                    successful_count = len(json.loads(observation.successful_approaches)) if observation.successful_approaches else 0
                    failed_count = len(json.loads(observation.failed_approaches)) if observation.failed_approaches else 0

                    if successful_count > failed_count * 2:
                        observation.risk_tolerance = "aggressive"
                    elif failed_count > successful_count:
                        observation.risk_tolerance = "conservative"
                    else:
                        observation.risk_tolerance = "balanced"
                except:
                    pass

        except Exception as e:
            logger.warning(f"Error updating personality traits: {e}")

    def _update_success_metrics(self, observation: UserObservation) -> None:
        """Update success metrics based on observed patterns"""
        try:
            # Calculate completion rates by analyzing success patterns
            if observation.observation_count > 0:
                try:
                    successful_count = len(json.loads(observation.successful_approaches)) if observation.successful_approaches else 0
                    total_attempts = observation.observation_count

                    success_rate = successful_count / total_attempts if total_attempts > 0 else 0

                    # Store success metrics
                    success_metrics = {
                        "overall_success_rate": success_rate,
                        "total_observations": observation.observation_count,
                        "successful_interactions": successful_count
                    }

                    observation.completion_rates_by_task_type = json.dumps(success_metrics)

                except Exception as e:
                    logger.warning(f"Error updating success metrics: {e}")

        except Exception as e:
            logger.warning(f"Error updating success metrics: {e}")


# Global user observation service instance
_user_observation_service: Optional[UserObservationService] = None


def get_user_observation_service() -> UserObservationService:
    """Get the global user observation service instance."""
    global _user_observation_service
    if _user_observation_service is None:
        _user_observation_service = UserObservationService()
    return _user_observation_service
