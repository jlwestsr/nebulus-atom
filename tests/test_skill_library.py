import pytest
from unittest.mock import patch
from nebulus_atom.services.skill_service import SkillService


@pytest.fixture
def temp_dirs(tmp_path):
    local = tmp_path / "local_skills"
    global_ = tmp_path / "global_skills"
    local.mkdir()
    global_.mkdir()
    return local, global_


def test_publish_skill(temp_dirs):
    local_dir, global_dir = temp_dirs

    # Create a dummy skill
    skill_file = local_dir / "my_skill.py"
    skill_file.write_text("def my_func():\n    return 'hello'")

    with patch("nebulus_atom.config.Config.GLOBAL_SKILLS_PATH", str(global_dir)):
        service = SkillService(skills_dir=str(local_dir))
        # Ensure correct path is used
        service.global_skills_dir = str(global_dir)

        service.load_skills()
        assert "my_func" in service.skills

        # Publish
        result = service.publish_skill("my_skill")
        assert "published to global library" in result

        assert (global_dir / "my_skill.py").exists()


def test_load_global_skill(temp_dirs):
    local_dir, global_dir = temp_dirs

    # Create global skill
    (global_dir / "global_skill.py").write_text(
        "def global_func():\n    return 'world'"
    )

    with patch("nebulus_atom.config.Config.GLOBAL_SKILLS_PATH", str(global_dir)):
        service = SkillService(skills_dir=str(local_dir))
        service.global_skills_dir = str(global_dir)

        service.load_skills()

        # Check namespacing
        assert "global.global_func" in service.skills

        # Execute
        result = service.execute_skill("global.global_func", {})
        assert result == "world"
