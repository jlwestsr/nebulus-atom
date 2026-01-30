import pytest
import os
from nebulus_atom.services.tool_executor import ToolExecutor


@pytest.fixture
def clean_skills():
    """Ensure we don't leave garbage skills."""
    skills_dir = "nebulus_atom/skills"
    test_skill_path = os.path.join(skills_dir, "test_math_skill.py")
    if os.path.exists(test_skill_path):
        os.remove(test_skill_path)
    yield
    if os.path.exists(test_skill_path):
        os.remove(test_skill_path)


@pytest.mark.asyncio
async def test_create_and_execute_skill(clean_skills):
    """Verify end-to-end skill creation and execution."""

    # Initialize ToolExecutor (loads skills)
    ToolExecutor.initialize()

    # 1. Create Skill Code
    skill_code = """
def execute(a: int, b: int) -> int:
    '''Multiplies two numbers.'''
    return a * b
"""

    # 2. Call create_skill tool
    result = await ToolExecutor.dispatch(
        "create_skill", {"name": "test_math_skill", "code": skill_code}
    )
    assert "created and loaded" in result

    # 3. Verify file exists
    assert os.path.exists("nebulus_atom/skills/test_math_skill.py")

    # 4. Execute the new skill directly via dispatch
    # Note: SkillService registers it as "test_math_skill.execute" usually,
    # but ToolExector logic might expose it differently depending on loader.
    # Let's check the loader logic: "test_math_skill" likely maps to the module functions.
    # Based on SkillService: if function name is 'execute', it might just register the module name?
    # Inspecting SkillService:
    #   reg_name = attr_name if no namespace.
    #   So it will be "execute". That's a collision risk!
    #   Wait, _load_from_path uses: pkgutil.iter_modules.
    #   Let's see: module = import_module(..).
    #   for attr_name, attr_value in getmembers(module):
    #       if isfunction: register(attr_name)
    #   So if I name the function `execute`, the tool is named `execute`.
    #   RISK: 'execute' is too generic.
    #   Correction: I should name the function `test_multiply`.

    # Let's rewrite the skill code to be safe
    skill_code_safe = """
def test_multiply(a: int, b: int) -> int:
    '''Multiplies two numbers.'''
    return a * b
"""
    await ToolExecutor.dispatch(
        "create_skill", {"name": "test_math_skill", "code": skill_code_safe}
    )

    # 5. Execute
    exec_result = await ToolExecutor.dispatch("test_multiply", {"a": 5, "b": 3})
    assert exec_result == "15"
