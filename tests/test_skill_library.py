import unittest
import os
import shutil
from unittest.mock import patch
from mini_nebulus.services.skill_service import SkillService


class TestSkillLibrary(unittest.TestCase):
    def setUp(self):
        self.test_local_dir = "tests/test_skills"
        self.test_global_dir = "tests/test_global_skills"

        for d in [self.test_local_dir, self.test_global_dir]:
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d)

        # Patch Config.GLOBAL_SKILLS_PATH
        self.config_patcher = patch(
            "mini_nebulus.config.Config.GLOBAL_SKILLS_PATH", self.test_global_dir
        )
        self.config_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        for d in [self.test_local_dir, self.test_global_dir]:
            if os.path.exists(d):
                shutil.rmtree(d)

    def test_publish_and_load_global(self):
        service = SkillService(skills_dir=self.test_local_dir)

        # 1. Create a local skill file
        skill_code = 'def test_skill(name: str):\n    return f"Hello {name}"'
        with open(os.path.join(self.test_local_dir, "my_skill.py"), "w") as f:
            f.write(skill_code)

        # 2. Publish it
        result = service.publish_skill("my_skill")
        self.assertIn("published to global library", result)

        # Verify file exists in global dir
        self.assertTrue(
            os.path.exists(os.path.join(self.test_global_dir, "my_skill.py"))
        )

        # 3. Load skills and check for global namespace
        service.load_skills()
        self.assertIn("global.test_skill", service.skills)

        # 4. Execute global skill
        exec_result = service.execute_skill("global.test_skill", {"name": "World"})
        self.assertEqual(exec_result, "Hello World")


if __name__ == "__main__":
    unittest.main()
