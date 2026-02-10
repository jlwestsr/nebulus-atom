"""GitHub issue sync for the Overlord work queue.

Separated from work_queue.py to isolate subprocess/gh CLI dependency.
Syncs GitHub issues (by label) into the work queue via `gh issue list`.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from nebulus_swarm.overlord.registry import OverlordConfig
from nebulus_swarm.overlord.work_queue import WorkQueue

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Summary of a GitHub sync operation."""

    new_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)


def sync_github_issues(
    queue: WorkQueue,
    config: OverlordConfig,
    *,
    label: str = "nebulus-ready",
    project_filter: Optional[str] = None,
    token_budget: Optional[int] = None,
) -> SyncResult:
    """Sync GitHub issues into the work queue.

    For each project with a remote, runs `gh issue list` to find issues
    with the given label and upserts them into the queue.

    Args:
        queue: The work queue to sync into.
        config: Overlord config with project definitions.
        label: GitHub label to filter issues by.
        project_filter: Optional single project to sync.

    Returns:
        SyncResult with counts and any errors.
    """
    result = SyncResult()

    for name, proj in config.projects.items():
        if project_filter and name != project_filter:
            continue

        if not proj.remote:
            result.skipped_count += 1
            continue

        try:
            issues = _run_gh_issue_list(proj.remote, label)
        except Exception as e:
            msg = f"{name}: gh CLI error: {e}"
            logger.error(msg)
            result.errors.append(msg)
            continue

        external_source = f"github:{proj.remote}"

        for issue in issues:
            issue_number = str(issue.get("number", ""))
            title = issue.get("title", "Untitled")
            body = issue.get("body") or ""
            labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
            priority = _map_labels_to_priority(labels)

            try:
                task_id, is_new = queue.upsert_from_github(
                    external_id=issue_number,
                    external_source=external_source,
                    title=title,
                    project=name,
                    description=body,
                    priority=priority,
                    token_budget=token_budget,
                )
                if is_new:
                    result.new_count += 1
                else:
                    result.updated_count += 1
            except Exception as e:
                msg = f"{name}#{issue_number}: upsert error: {e}"
                logger.error(msg)
                result.errors.append(msg)

    return result


def _run_gh_issue_list(remote: str, label: str) -> list[dict]:
    """Run `gh issue list` and return parsed JSON.

    Args:
        remote: GitHub remote in owner/repo format.
        label: Label to filter by.

    Returns:
        List of issue dicts with number, title, body, labels keys.

    Raises:
        RuntimeError: If the gh command fails.
    """
    cmd = [
        "gh",
        "issue",
        "list",
        "-R",
        remote,
        "--json",
        "number,title,body,labels",
        "--label",
        label,
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"gh issue list failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )

    return json.loads(proc.stdout) if proc.stdout.strip() else []


def _map_labels_to_priority(labels: list[str]) -> str:
    """Map GitHub labels to a task priority.

    Args:
        labels: List of label names from the issue.

    Returns:
        Priority string: "critical", "high", "medium", or "low".
    """
    lower_labels = {lbl.lower() for lbl in labels}

    if "critical" in lower_labels or "p0" in lower_labels:
        return "critical"
    if "high-priority" in lower_labels or "p1" in lower_labels:
        return "high"
    if "low-priority" in lower_labels or "p3" in lower_labels:
        return "low"
    return "medium"


__all__ = ["SyncResult", "sync_github_issues"]
