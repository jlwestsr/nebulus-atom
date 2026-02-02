"""Prompt builder for Minion agent."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class IssueContext:
    """Context about the issue being worked on."""

    repo: str
    number: int
    title: str
    body: str
    labels: List[str]
    author: str


SYSTEM_PROMPT_TEMPLATE = """You are a Minion - an autonomous coding agent working on GitHub issues.

## Your Task

You are working on issue #{issue_number} in repository {repo}.

**Title:** {title}

**Description:**
{body}

**Labels:** {labels}

## Instructions

1. Analyze the issue to understand what needs to be done
2. Explore the codebase to understand the existing structure and patterns
3. Implement the solution following the project's conventions
4. Write or update tests if appropriate
5. Call `task_complete` when done, providing a summary of changes

## Guidelines

- Follow existing code patterns and style
- Make minimal, focused changes
- Prefer editing existing files over creating new ones
- Run tests to verify your changes work
- If you cannot complete the task, call `task_blocked` with a clear explanation

## Available Tools

You have access to these tools:
- `read_file` - Read file contents
- `write_file` - Create or overwrite files
- `edit_file` - Make targeted edits to files
- `list_directory` - List files and folders
- `search_files` - Search for patterns in code
- `glob_files` - Find files by pattern
- `run_command` - Execute shell commands (tests, builds, etc.)
- `list_skills` - See available skills
- `use_skill` - Load skill instructions
- `task_complete` - Signal successful completion
- `task_blocked` - Signal you cannot proceed

## Workspace

Your workspace is the cloned repository at `/workspace`. All file paths are relative to this root.

{skill_instructions}

Begin by exploring the codebase to understand its structure, then implement the solution.
"""


def build_system_prompt(
    issue: IssueContext,
    skill_instructions: Optional[str] = None,
) -> str:
    """Build the system prompt for the Minion agent.

    Args:
        issue: Issue context.
        skill_instructions: Optional pre-loaded skill instructions.

    Returns:
        Formatted system prompt.
    """
    labels_str = ", ".join(issue.labels) if issue.labels else "none"
    body = issue.body.strip() if issue.body else "(No description provided)"

    skill_section = ""
    if skill_instructions:
        skill_section = f"""
## Loaded Skills

The following skill instructions have been loaded to help with this task:

{skill_instructions}
"""

    return SYSTEM_PROMPT_TEMPLATE.format(
        issue_number=issue.number,
        repo=issue.repo,
        title=issue.title,
        body=body,
        labels=labels_str,
        skill_instructions=skill_section,
    )


def build_initial_message(issue: IssueContext) -> str:
    """Build the initial user message to start the agent.

    Args:
        issue: Issue context.

    Returns:
        Initial message to kick off the agent.
    """
    return f"""Please implement the solution for issue #{issue.number}: {issue.title}

Start by exploring the codebase to understand its structure, then make the necessary changes."""
