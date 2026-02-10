"""Tests for the Focus Context System."""

from __future__ import annotations


from nebulus_swarm.overlord.focus import (
    FocusContext,
    build_focus_context,
    _extract_section,
    _gather_recent_plans,
    _parse_business_md,
)


# --- FocusContext dataclass ---


def test_focus_context_defaults():
    ctx = FocusContext()
    assert ctx.business_priorities == []
    assert ctx.governance_rules == []
    assert ctx.tech_stack == []
    assert ctx.active_tracks == []
    assert ctx.plan_summaries == []


def test_format_for_prompt_empty():
    ctx = FocusContext()
    result = ctx.format_for_prompt()
    assert "No context available" in result


def test_format_for_prompt_with_priorities():
    ctx = FocusContext(
        business_priorities=[
            {"name": "Security", "priority": "high", "description": "Harden APIs"}
        ]
    )
    result = ctx.format_for_prompt()
    assert "Business Priorities" in result
    assert "Security" in result
    assert "high" in result
    assert "Harden APIs" in result


def test_format_for_prompt_with_governance():
    ctx = FocusContext(governance_rules=["No direct commits to main"])
    result = ctx.format_for_prompt()
    assert "Governance Rules" in result
    assert "No direct commits to main" in result


def test_format_for_prompt_with_tech_stack():
    ctx = FocusContext(tech_stack=[{"name": "Python", "role": "Primary language"}])
    result = ctx.format_for_prompt()
    assert "Tech Stack" in result
    assert "Python" in result


def test_format_for_prompt_with_tracks():
    ctx = FocusContext(active_tracks=[{"name": "Track 1", "status": "complete"}])
    result = ctx.format_for_prompt()
    assert "Active Tracks" in result
    assert "Track 1" in result


def test_format_for_prompt_with_plans():
    ctx = FocusContext(
        plan_summaries=[
            {
                "title": "Refactor Core",
                "date": "2026-02-10",
                "summary": "Major refactoring effort.",
            }
        ]
    )
    result = ctx.format_for_prompt()
    assert "Recent Plans" in result
    assert "Refactor Core" in result
    assert "2026-02-10" in result


# --- build_focus_context ---


def test_build_focus_context_empty_workspace(tmp_path):
    """Missing files should produce empty context, not crash."""
    ctx = build_focus_context(tmp_path)
    assert ctx.business_priorities == []
    assert ctx.governance_rules == []
    assert ctx.active_tracks == []
    assert ctx.plan_summaries == []
    assert ctx.workspace_root == tmp_path


def test_build_focus_context_with_business_md(tmp_path):
    business = tmp_path / "BUSINESS.md"
    business.write_text(
        "# Business\n\n"
        "## Priorities\n\n"
        "| Name | Priority | Description |\n"
        "|------|----------|-------------|\n"
        "| Security | High | Harden APIs |\n"
        "| Performance | Medium | Optimize queries |\n"
    )
    ctx = build_focus_context(tmp_path)
    assert len(ctx.business_priorities) == 2
    assert ctx.business_priorities[0]["name"] == "Security"
    assert ctx.business_priorities[0]["priority"] == "high"


def test_build_focus_context_with_tracks(tmp_path):
    tracks_dir = tmp_path / "conductor"
    tracks_dir.mkdir()
    tracks_file = tracks_dir / "tracks.md"
    tracks_file.write_text(
        "# Tracks\n\n"
        "## Track 1: Foundation\n"
        "Status: complete\n"
        "Core infrastructure for the system.\n\n"
        "## Track 2: Dispatch\n"
        "In progress — building dispatch loop.\n"
    )
    ctx = build_focus_context(tmp_path)
    assert len(ctx.active_tracks) == 2
    assert ctx.active_tracks[0]["name"] == "Foundation"
    assert ctx.active_tracks[0]["status"] == "complete"
    assert ctx.active_tracks[1]["status"] == "in-progress"


def test_build_focus_context_with_plans(tmp_path):
    plans_dir = tmp_path / "docs" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-02-10-refactor.md").write_text(
        "# Refactor Core\nMajor refactoring of the core system.\n"
    )
    (plans_dir / "2026-02-09-security.md").write_text(
        "# Security Hardening\nAdd auth to all endpoints.\n"
    )
    ctx = build_focus_context(tmp_path)
    assert len(ctx.plan_summaries) == 2
    assert ctx.plan_summaries[0]["title"] == "Refactor Core"
    assert ctx.plan_summaries[0]["date"] == "2026-02-10"


# --- _parse_business_md ---


def test_parse_business_md_governance_section(tmp_path):
    md = tmp_path / "BUSINESS.md"
    md.write_text(
        "# Business Doc\n\n"
        "## Governance Rules\n"
        "- No push to main without PR\n"
        "- All code must be reviewed\n"
        "- Tests required before merge\n\n"
        "## Other Section\n"
        "Not governance.\n"
    )
    result = _parse_business_md(md)
    assert len(result["governance"]) == 3
    assert "No push to main without PR" in result["governance"]


def test_parse_business_md_tech_stack(tmp_path):
    md = tmp_path / "BUSINESS.md"
    md.write_text(
        "# Business\n\n"
        "## Tech Stack\n\n"
        "| Name | Role |\n"
        "|------|------|\n"
        "| Python | Backend |\n"
        "| React | Frontend |\n"
    )
    result = _parse_business_md(md)
    assert len(result["tech_stack"]) == 2
    assert result["tech_stack"][0]["name"] == "Python"
    assert result["tech_stack"][0]["role"] == "Backend"


# --- _extract_section ---


def test_extract_section_found():
    content = "# Top\n\n## Governance\nRule 1\nRule 2\n\n## Other\nStuff\n"
    section = _extract_section(content, "governance")
    assert section is not None
    assert "Rule 1" in section
    assert "Rule 2" in section
    assert "Stuff" not in section


def test_extract_section_not_found():
    content = "# Top\n\n## Other\nStuff\n"
    section = _extract_section(content, "nonexistent")
    assert section is None


# --- _gather_recent_plans ---


def test_gather_recent_plans_limit(tmp_path):
    for i in range(5):
        (tmp_path / f"2026-02-{10 - i:02d}-plan{i}.md").write_text(
            f"# Plan {i}\nDescription for plan {i}.\n"
        )
    plans = _gather_recent_plans(tmp_path, limit=3)
    assert len(plans) == 3


def test_gather_recent_plans_empty(tmp_path):
    plans = _gather_recent_plans(tmp_path)
    assert plans == []
