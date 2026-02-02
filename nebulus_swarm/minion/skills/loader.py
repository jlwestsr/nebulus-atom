"""Skill loader for Minion agent."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from nebulus_swarm.minion.skills.schema import Skill

logger = logging.getLogger(__name__)

# Default skills directory relative to repo root
SKILLS_DIR = ".nebulus/skills"

# Index file name
INDEX_FILE = "_index.yaml"


class SkillLoader:
    """Loads and manages skills from the repository."""

    def __init__(self, workspace: Path):
        """Initialize skill loader.

        Args:
            workspace: Path to the workspace (cloned repo).
        """
        self.workspace = workspace
        self.skills_dir = workspace / SKILLS_DIR
        self._skills: Dict[str, Skill] = {}
        self._loaded = False

    def load_skills(self) -> None:
        """Load all skills from the skills directory."""
        if not self.skills_dir.exists():
            logger.info(f"Skills directory not found: {self.skills_dir}")
            self._loaded = True
            return

        # Load index if it exists
        index_path = self.skills_dir / INDEX_FILE
        if index_path.exists():
            self._load_from_index(index_path)
        else:
            # Load all YAML files in directory
            self._load_all_yaml_files()

        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills")

    def _load_from_index(self, index_path: Path) -> None:
        """Load skills listed in index file.

        Args:
            index_path: Path to index file.
        """
        try:
            with open(index_path) as f:
                index = yaml.safe_load(f) or {}

            skill_files = index.get("skills", [])
            for filename in skill_files:
                skill_path = self.skills_dir / filename
                if skill_path.exists():
                    self._load_skill_file(skill_path)
                else:
                    logger.warning(f"Skill file not found: {skill_path}")

        except yaml.YAMLError as e:
            logger.error(f"Error parsing index file: {e}")

    def _load_all_yaml_files(self) -> None:
        """Load all YAML files in skills directory."""
        for path in self.skills_dir.glob("*.yaml"):
            if path.name == INDEX_FILE:
                continue
            self._load_skill_file(path)

        for path in self.skills_dir.glob("*.yml"):
            self._load_skill_file(path)

    def _load_skill_file(self, path: Path) -> None:
        """Load a single skill file.

        Args:
            path: Path to skill file.
        """
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data, dict):
                logger.warning(f"Invalid skill file: {path}")
                return

            skill = Skill.from_dict(data)
            self._skills[skill.name] = skill
            logger.debug(f"Loaded skill: {skill.name}")

        except yaml.YAMLError as e:
            logger.error(f"Error parsing skill file {path}: {e}")
        except Exception as e:
            logger.error(f"Error loading skill {path}: {e}")

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name.

        Args:
            name: Skill name.

        Returns:
            Skill or None if not found.
        """
        if not self._loaded:
            self.load_skills()
        return self._skills.get(name)

    def get_skill_instructions(self, name: str) -> Optional[str]:
        """Get a skill's instructions.

        Args:
            name: Skill name.

        Returns:
            Instructions string or None.
        """
        skill = self.get_skill(name)
        return skill.instructions if skill else None

    def list_skills(self) -> List[Dict[str, str]]:
        """List all available skills.

        Returns:
            List of skill summaries.
        """
        if not self._loaded:
            self.load_skills()

        return [
            {"name": skill.name, "description": skill.description}
            for skill in self._skills.values()
        ]

    def find_matching_skills(
        self,
        title: str,
        body: str,
        labels: List[str],
        files: Optional[List[str]] = None,
    ) -> List[Skill]:
        """Find skills that match an issue.

        Args:
            title: Issue title.
            body: Issue body.
            labels: Issue labels.
            files: Optional list of files.

        Returns:
            List of matching skills.
        """
        if not self._loaded:
            self.load_skills()

        matches = []
        for skill in self._skills.values():
            if skill.matches_issue(title, body, labels, files):
                matches.append(skill)

        return matches

    def get_combined_instructions(self, skill_names: List[str]) -> str:
        """Get combined instructions for multiple skills.

        Args:
            skill_names: List of skill names.

        Returns:
            Combined instructions string.
        """
        instructions = []
        for name in skill_names:
            skill = self.get_skill(name)
            if skill:
                instructions.append(f"### Skill: {skill.name}\n\n{skill.instructions}")

        return "\n\n".join(instructions)

    @property
    def skill_count(self) -> int:
        """Get number of loaded skills."""
        if not self._loaded:
            self.load_skills()
        return len(self._skills)

    @property
    def skill_names(self) -> List[str]:
        """Get list of skill names."""
        if not self._loaded:
            self.load_skills()
        return list(self._skills.keys())
