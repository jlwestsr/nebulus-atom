"""LLM-based code review for PR analysis."""

import json
import logging
import re
from typing import Optional

from openai import OpenAI

from nebulus_swarm.reviewer.pr_reviewer import (
    InlineComment,
    PRDetails,
    ReviewDecision,
    ReviewResult,
)

logger = logging.getLogger(__name__)

# System prompt for code review
CODE_REVIEW_PROMPT = """You are an expert code reviewer. Analyze the pull request and provide a thorough review.

Your review should:
1. Check for bugs, logic errors, and edge cases
2. Identify security vulnerabilities
3. Assess code quality and maintainability
4. Verify the changes align with the PR description
5. Suggest improvements where appropriate

Respond with a JSON object in this exact format:
{
  "decision": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
  "confidence": 0.0-1.0,
  "summary": "Brief summary of review",
  "issues": ["List of issues found"],
  "suggestions": ["List of improvement suggestions"],
  "inline_comments": [
    {"path": "file.py", "line": 10, "body": "Comment text"}
  ]
}

Guidelines for decision:
- APPROVE: Code is ready to merge, any issues are minor
- REQUEST_CHANGES: Code has bugs, security issues, or significant problems
- COMMENT: Code is acceptable but has notable suggestions

Be concise but thorough. Focus on actionable feedback."""


class LLMReviewer:
    """Uses LLM to review PR code changes."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: int = 120,
    ):
        """Initialize LLM reviewer.

        Args:
            base_url: LLM API base URL.
            model: Model name to use.
            api_key: API key (may be "not-needed" for local models).
            timeout: Request timeout in seconds.
        """
        self.model = model
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )

    def review_pr(
        self, pr_details: PRDetails, max_diff_lines: int = 500
    ) -> ReviewResult:
        """Review a pull request using LLM.

        Args:
            pr_details: PR details to review.
            max_diff_lines: Maximum diff lines to send to LLM.

        Returns:
            ReviewResult with LLM analysis.
        """
        logger.info(f"Starting LLM review of {pr_details.repo}#{pr_details.number}")

        # Build the review prompt
        user_prompt = self._build_review_prompt(pr_details, max_diff_lines)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CODE_REVIEW_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,  # Lower temperature for more consistent reviews
            )

            content = response.choices[0].message.content
            return self._parse_review_response(content)

        except Exception as e:
            logger.error(f"LLM review failed: {e}")
            return ReviewResult(
                decision=ReviewDecision.COMMENT,
                summary=f"LLM review failed: {e}",
                confidence=0.0,
                issues=[f"Review error: {e}"],
            )

    def _build_review_prompt(self, pr_details: PRDetails, max_lines: int) -> str:
        """Build the user prompt for review.

        Args:
            pr_details: PR details.
            max_lines: Maximum diff lines to include.

        Returns:
            Formatted prompt string.
        """
        parts = [
            "# Pull Request Review Request",
            "",
            pr_details.get_diff_summary(),
            "",
            "## Code Changes",
            pr_details.get_full_diff(max_lines),
        ]

        return "\n".join(parts)

    def _parse_review_response(self, content: str) -> ReviewResult:
        """Parse LLM response into ReviewResult.

        Args:
            content: Raw LLM response content.

        Returns:
            Parsed ReviewResult.
        """
        # Try to extract JSON from response
        json_match = re.search(r"\{[\s\S]*\}", content)
        if not json_match:
            logger.warning("No JSON found in LLM response")
            return ReviewResult(
                decision=ReviewDecision.COMMENT,
                summary="Could not parse LLM response",
                confidence=0.0,
                issues=["Failed to parse review response"],
            )

        try:
            data = json.loads(json_match.group())

            # Parse decision
            decision_str = data.get("decision", "COMMENT").upper()
            try:
                decision = ReviewDecision(decision_str)
            except ValueError:
                decision = ReviewDecision.COMMENT

            # Parse inline comments
            inline_comments = []
            for comment in data.get("inline_comments", []):
                if (
                    isinstance(comment, dict)
                    and "path" in comment
                    and "body" in comment
                ):
                    inline_comments.append(
                        InlineComment(
                            path=comment["path"],
                            line=comment.get("line", 1),
                            body=comment["body"],
                        )
                    )

            return ReviewResult(
                decision=decision,
                summary=data.get("summary", "Review completed"),
                confidence=float(data.get("confidence", 0.5)),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                inline_comments=inline_comments,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from LLM response: {e}")
            return ReviewResult(
                decision=ReviewDecision.COMMENT,
                summary="Could not parse LLM response",
                confidence=0.0,
                issues=["JSON parse error in review response"],
            )

    def analyze_specific_file(
        self,
        filename: str,
        content: str,
        focus: str = "general",
    ) -> str:
        """Analyze a specific file for targeted review.

        Args:
            filename: Name of the file.
            content: File content or diff.
            focus: Review focus (security, performance, style, general).

        Returns:
            Analysis text from LLM.
        """
        focus_prompts = {
            "security": "Focus on security vulnerabilities, injection risks, and authentication issues.",
            "performance": "Focus on performance bottlenecks, memory leaks, and optimization opportunities.",
            "style": "Focus on code style, naming conventions, and documentation.",
            "general": "Provide a general code quality review.",
        }

        prompt = f"""Review this code file: {filename}

{focus_prompts.get(focus, focus_prompts["general"])}

```
{content[:5000]}
```

Provide a brief analysis (2-3 paragraphs max)."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"File analysis failed: {e}")
            return f"Analysis failed: {e}"


def create_review_summary(
    pr_details: PRDetails,
    llm_result: ReviewResult,
    checks_summary: Optional[str] = None,
) -> str:
    """Create a complete review summary combining LLM review and checks.

    Args:
        pr_details: PR details.
        llm_result: LLM review result.
        checks_summary: Optional automated checks summary.

    Returns:
        Formatted review summary for GitHub/Slack.
    """
    lines = [
        f"# AI Review: {pr_details.repo}#{pr_details.number}",
        "",
        f"**Title:** {pr_details.title}",
        f"**Decision:** {llm_result.decision.value}",
        f"**Confidence:** {llm_result.confidence:.0%}",
        "",
        "## Summary",
        f"{llm_result.summary}",
    ]

    if llm_result.issues:
        lines.append("")
        lines.append("## Issues")
        for issue in llm_result.issues:
            lines.append(f"- {issue}")

    if llm_result.suggestions:
        lines.append("")
        lines.append("## Suggestions")
        for suggestion in llm_result.suggestions:
            lines.append(f"- {suggestion}")

    if checks_summary:
        lines.append("")
        lines.append(checks_summary)

    if llm_result.can_auto_merge:
        lines.append("")
        lines.append("---")
        lines.append("*This PR is eligible for auto-merge.*")

    return "\n".join(lines)
