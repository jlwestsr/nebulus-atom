"""
Cognition service for "System 2" thinking.

Provides deliberate reasoning, task analysis, and self-critique capabilities
for more reliable handling of complex tasks.
"""

import re
from typing import List, Optional, Tuple

from nebulus_atom.models.cognition import (
    TaskComplexity,
    ReasoningStep,
    ClarificationQuestion,
    CognitionResult,
    ThoughtRecord,
    SelfCritiqueResult,
)
from nebulus_atom.models.failure_memory import FailureContext
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


# Keywords indicating complexity
COMPLEXITY_INDICATORS = {
    "high": [
        "refactor",
        "redesign",
        "architect",
        "implement",
        "build",
        "create system",
        "add feature",
        "authentication",
        "security",
        "database",
        "migration",
        "deploy",
        "configure",
        "integrate",
        "optimize",
        "scale",
        "test suite",
        "ci/cd",
        "api",
    ],
    "medium": [
        "add",
        "create",
        "update",
        "modify",
        "change",
        "fix bug",
        "write function",
        "write class",
        "implement method",
        "add test",
        "update config",
        "install",
    ],
    "low": [
        "list",
        "show",
        "read",
        "cat",
        "ls",
        "pwd",
        "echo",
        "print",
        "display",
        "what is",
        "where is",
        "find",
        "check",
        "status",
        "version",
        "help",
    ],
}

# Keywords suggesting ambiguity
AMBIGUITY_INDICATORS = [
    "somehow",
    "maybe",
    "might",
    "could",
    "should",
    "something like",
    "similar to",
    "kind of",
    "sort of",
    "not sure",
    "i think",
    "probably",
    "possibly",
    "best way",
    "good way",
    "right way",
]

# Keywords indicating multi-step work
MULTI_STEP_INDICATORS = [
    "and then",
    "after that",
    "followed by",
    "next",
    "first",
    "second",
    "finally",
    "also",
    "additionally",
    "as well as",
    "along with",
    "including",
]


class CognitionService:
    """
    Provides cognitive analysis and reasoning capabilities.

    Implements "System 2" thinking for deliberate, analytical
    processing of complex tasks.
    """

    def __init__(self) -> None:
        """Initialize the cognition service."""
        self._thought_history: List[ThoughtRecord] = []

    def analyze_task(
        self,
        user_input: str,
        context: Optional[str] = None,
        failure_context: Optional[FailureContext] = None,
    ) -> CognitionResult:
        """
        Analyze a task to determine complexity and approach.

        Args:
            user_input: The user's request/task description.
            context: Optional additional context (pinned files, history).
            failure_context: Optional failure memory context for confidence adjustment.

        Returns:
            CognitionResult with analysis and recommendations.
        """
        logger.info(f"Analyzing task: {user_input[:100]}...")

        # Normalize input
        input_lower = user_input.lower().strip()

        # Classify complexity
        complexity = self._classify_complexity(input_lower)

        # Detect ambiguity
        ambiguity_score, ambiguous_phrases = self._detect_ambiguity(input_lower)

        # Estimate steps
        estimated_steps = self._estimate_steps(input_lower, complexity)

        # Generate reasoning chain based on complexity
        reasoning_chain = self._generate_reasoning(
            user_input, complexity, ambiguity_score
        )

        # Identify potential risks
        risks = self._identify_risks(input_lower, complexity)

        # Inject failure warnings into risks
        if failure_context and failure_context.warning_messages:
            for warning in failure_context.warning_messages:
                risks.append(warning)

        # Generate clarification questions if needed
        clarification_needed = (
            ambiguity_score > 0.5 or complexity == TaskComplexity.COMPLEX
        )
        clarifications = []
        if clarification_needed:
            clarifications = self._generate_clarifications(
                user_input, complexity, ambiguous_phrases
            )

        # Calculate overall confidence
        failure_penalty = failure_context.total_penalty if failure_context else 0.0
        confidence = self._calculate_confidence(
            complexity, ambiguity_score, len(clarifications), failure_penalty
        )

        # Generate recommended approach
        approach = self._recommend_approach(complexity, estimated_steps, confidence)

        result = CognitionResult(
            task_complexity=complexity,
            reasoning_chain=reasoning_chain,
            recommended_approach=approach,
            confidence=confidence,
            clarification_needed=clarification_needed and confidence < 0.7,
            clarification_questions=clarifications,
            estimated_steps=estimated_steps,
            potential_risks=risks,
        )

        logger.info(
            f"Task analysis complete: complexity={complexity.value}, "
            f"confidence={confidence:.2f}, steps={estimated_steps}"
        )

        return result

    def _classify_complexity(self, input_lower: str) -> TaskComplexity:
        """Classify task complexity based on keywords and patterns."""
        # Check for high complexity indicators
        for indicator in COMPLEXITY_INDICATORS["high"]:
            if indicator in input_lower:
                return TaskComplexity.COMPLEX

        # Check for medium complexity indicators
        for indicator in COMPLEXITY_INDICATORS["medium"]:
            if indicator in input_lower:
                return TaskComplexity.MODERATE

        # Check for explicit low complexity indicators
        for indicator in COMPLEXITY_INDICATORS["low"]:
            if input_lower.startswith(indicator) or f" {indicator}" in input_lower:
                return TaskComplexity.SIMPLE

        # Check input length as a heuristic
        word_count = len(input_lower.split())
        if word_count <= 5:
            return TaskComplexity.SIMPLE
        elif word_count <= 15:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.COMPLEX

    def _detect_ambiguity(self, input_lower: str) -> Tuple[float, List[str]]:
        """
        Detect ambiguity in the task description.

        Returns:
            Tuple of (ambiguity_score 0-1, list of ambiguous phrases found)
        """
        found_indicators = []

        for indicator in AMBIGUITY_INDICATORS:
            if indicator in input_lower:
                found_indicators.append(indicator)

        # Score based on number of indicators and input specificity
        base_score = min(len(found_indicators) * 0.15, 0.6)

        # Increase score if task lacks specific details
        has_specific_path = bool(re.search(r"[/\\][\w.-]+", input_lower))
        has_specific_name = bool(re.search(r'`[\w_]+`|"[\w_]+"', input_lower))

        if not has_specific_path and not has_specific_name:
            base_score += 0.2

        return min(base_score, 1.0), found_indicators

    def _estimate_steps(self, input_lower: str, complexity: TaskComplexity) -> int:
        """Estimate the number of steps required."""
        # Base estimate from complexity
        base_steps = {
            TaskComplexity.SIMPLE: 1,
            TaskComplexity.MODERATE: 2,
            TaskComplexity.COMPLEX: 4,
        }[complexity]

        # Adjust for multi-step indicators
        additional_steps = sum(
            1 for indicator in MULTI_STEP_INDICATORS if indicator in input_lower
        )

        return min(base_steps + additional_steps, 10)

    def _generate_reasoning(
        self,
        user_input: str,
        complexity: TaskComplexity,
        ambiguity_score: float,
    ) -> List[ReasoningStep]:
        """Generate a reasoning chain for the task."""
        steps = []

        # Step 1: Task understanding
        steps.append(
            ReasoningStep(
                step_number=1,
                thought=f"Understanding the request: '{user_input[:100]}...'",
                conclusion=f"Task classified as {complexity.value} complexity",
                confidence=0.9,
            )
        )

        if complexity == TaskComplexity.SIMPLE:
            steps.append(
                ReasoningStep(
                    step_number=2,
                    thought="This is a straightforward request",
                    conclusion="Can proceed with direct execution",
                    confidence=0.95,
                )
            )
        elif complexity == TaskComplexity.MODERATE:
            steps.append(
                ReasoningStep(
                    step_number=2,
                    thought="This requires some planning but is well-defined",
                    conclusion="Will break into clear sub-tasks",
                    confidence=0.85,
                )
            )
            steps.append(
                ReasoningStep(
                    step_number=3,
                    thought="Identifying dependencies and order of operations",
                    conclusion="Approach determined, ready to execute",
                    confidence=0.8,
                )
            )
        else:  # COMPLEX
            steps.append(
                ReasoningStep(
                    step_number=2,
                    thought="This is a complex task requiring careful analysis",
                    conclusion="Need to understand requirements fully before proceeding",
                    confidence=0.7 - (ambiguity_score * 0.3),
                )
            )
            steps.append(
                ReasoningStep(
                    step_number=3,
                    thought="Identifying potential approaches and trade-offs",
                    conclusion="Multiple implementation paths possible",
                    confidence=0.6,
                )
            )
            steps.append(
                ReasoningStep(
                    step_number=4,
                    thought="Considering risks and edge cases",
                    conclusion="Should verify understanding before major changes",
                    confidence=0.65,
                )
            )

        return steps

    def _identify_risks(
        self, input_lower: str, complexity: TaskComplexity
    ) -> List[str]:
        """Identify potential risks in the task."""
        risks = []

        # File system risks
        if any(word in input_lower for word in ["delete", "remove", "rm ", "drop"]):
            risks.append("Destructive operation - ensure backups exist")

        # Security risks
        if any(
            word in input_lower
            for word in ["password", "secret", "key", "token", "credential"]
        ):
            risks.append("Security-sensitive - avoid logging sensitive values")

        # Database risks
        if any(
            word in input_lower for word in ["database", "migration", "schema", "sql"]
        ):
            risks.append("Database modification - test on non-production first")

        # Complexity risks
        if complexity == TaskComplexity.COMPLEX:
            risks.append("Complex task - consider incremental implementation")

        return risks

    def _generate_clarifications(
        self,
        user_input: str,
        complexity: TaskComplexity,
        ambiguous_phrases: List[str],
    ) -> List[ClarificationQuestion]:
        """Generate clarification questions for ambiguous tasks."""
        questions = []

        # Generic clarifications for complex tasks
        if complexity == TaskComplexity.COMPLEX:
            questions.append(
                ClarificationQuestion(
                    question="What is the expected outcome or success criteria?",
                    importance="high",
                )
            )

        # Architecture questions for implementation tasks
        if any(
            word in user_input.lower()
            for word in ["implement", "add", "create", "build"]
        ):
            questions.append(
                ClarificationQuestion(
                    question="Are there existing patterns in the codebase I should follow?",
                    importance="medium",
                )
            )

        # Scope questions for modification tasks
        if any(
            word in user_input.lower()
            for word in ["refactor", "update", "change", "modify"]
        ):
            questions.append(
                ClarificationQuestion(
                    question="What is the scope of changes - single file or system-wide?",
                    importance="high",
                )
            )

        return questions[:3]  # Limit to 3 questions

    def _calculate_confidence(
        self,
        complexity: TaskComplexity,
        ambiguity_score: float,
        num_clarifications: int,
        failure_penalty: float = 0.0,
    ) -> float:
        """Calculate overall confidence in understanding the task."""
        # Base confidence from complexity
        base_confidence = {
            TaskComplexity.SIMPLE: 0.95,
            TaskComplexity.MODERATE: 0.80,
            TaskComplexity.COMPLEX: 0.60,
        }[complexity]

        # Reduce for ambiguity
        confidence = base_confidence - (ambiguity_score * 0.3)

        # Reduce for needed clarifications
        confidence -= num_clarifications * 0.05

        # Reduce for failure history
        confidence -= failure_penalty

        return max(0.1, min(1.0, confidence))

    def _recommend_approach(
        self,
        complexity: TaskComplexity,
        estimated_steps: int,
        confidence: float,
    ) -> str:
        """Generate recommended approach based on analysis."""
        if confidence < 0.5:
            return "Seek clarification before proceeding"

        if complexity == TaskComplexity.SIMPLE:
            return "Direct execution - single tool call"
        elif complexity == TaskComplexity.MODERATE:
            return f"Sequential execution - {estimated_steps} steps"
        else:
            return (
                f"Planned execution - create explicit plan with {estimated_steps} tasks"
            )

    def critique_output(
        self,
        original_task: str,
        tool_name: str,
        tool_output: str,
    ) -> SelfCritiqueResult:
        """
        Critique tool output for correctness and completeness.

        Args:
            original_task: The original user request.
            tool_name: Name of the tool that was executed.
            tool_output: The output from the tool.

        Returns:
            SelfCritiqueResult with validation and suggestions.
        """
        issues = []
        suggestions = []

        # Check for error indicators
        error_patterns = [
            r"error",
            r"exception",
            r"failed",
            r"not found",
            r"permission denied",
            r"no such file",
            r"traceback",
        ]

        output_lower = tool_output.lower()
        for pattern in error_patterns:
            if re.search(pattern, output_lower):
                issues.append(f"Output contains error indicator: '{pattern}'")

        # Check for empty or minimal output
        if len(tool_output.strip()) < 10:
            issues.append("Output is very short - may indicate failure")

        # Check for truncation
        if tool_output.endswith("...") or "[truncated]" in tool_output:
            suggestions.append(
                "Output may be truncated - consider reading full content"
            )

        is_valid = len(issues) == 0
        confidence = 0.9 if is_valid else 0.4
        should_retry = len(issues) > 0 and "error" in output_lower

        return SelfCritiqueResult(
            is_valid=is_valid,
            issues_found=issues,
            suggestions=suggestions,
            confidence=confidence,
            should_retry=should_retry,
        )

    def record_thought(
        self,
        session_id: str,
        thought_type: str,
        content: str,
        confidence: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> ThoughtRecord:
        """
        Record a thought for telemetry and debugging.

        Args:
            session_id: Current session identifier.
            thought_type: Type of thought (analysis, reasoning, critique, verification).
            content: The thought content.
            confidence: Confidence level 0-1.
            metadata: Optional additional metadata.

        Returns:
            The recorded ThoughtRecord.
        """
        record = ThoughtRecord(
            session_id=session_id,
            thought_type=thought_type,
            content=content,
            confidence=confidence,
            metadata=metadata or {},
        )

        self._thought_history.append(record)
        logger.debug(f"Recorded thought [{thought_type}]: {content[:50]}...")

        return record

    def get_thought_history(
        self, session_id: Optional[str] = None
    ) -> List[ThoughtRecord]:
        """Get thought history, optionally filtered by session."""
        if session_id:
            return [t for t in self._thought_history if t.session_id == session_id]
        return list(self._thought_history)

    def clear_thought_history(self, session_id: Optional[str] = None) -> None:
        """Clear thought history, optionally for a specific session."""
        if session_id:
            self._thought_history = [
                t for t in self._thought_history if t.session_id != session_id
            ]
        else:
            self._thought_history.clear()


class CognitionServiceManager:
    """Manages CognitionService instances per session."""

    def __init__(self) -> None:
        """Initialize the manager."""
        self._services: dict[str, CognitionService] = {}
        self._default_service = CognitionService()

    def get_service(self, session_id: str = "default") -> CognitionService:
        """Get or create a CognitionService for the session."""
        if session_id not in self._services:
            self._services[session_id] = CognitionService()
        return self._services[session_id]
