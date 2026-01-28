import pytest
from mini_nebulus.services.ast_service import ASTService


@pytest.fixture
def dummy_codebase(tmp_path):
    # Create a dummy python file using single quotes for docstrings to avoid escaping hell
    code = "import os\nfrom typing import List\n\nclass TestClass:\n    'This is a test class.'\n    def method_one(self):\n        pass\n\ndef top_level_function():\n    'Top level docstring.'\n    pass\n"
    file_path = tmp_path / "test_module.py"
    file_path.write_text(code)
    return tmp_path


def test_generate_map(dummy_codebase):
    service = ASTService(root_dir=str(dummy_codebase))
    result = service.generate_map()

    assert "test_module.py" in result
    info = result["test_module.py"]

    assert "os" in info["imports"]
    assert "typing.List" in info["imports"]

    assert len(info["classes"]) == 1
    cls = info["classes"][0]
    assert cls["name"] == "TestClass"
    assert "method_one" in cls["methods"]
    assert cls["docstring"] == "This is a test class."

    assert len(info["functions"]) == 1
    func = info["functions"][0]
    assert func["name"] == "top_level_function"
    assert func["docstring"] == "Top level docstring."


def test_find_symbol(dummy_codebase):
    service = ASTService(root_dir=str(dummy_codebase))
    service.generate_map()

    # Find Class
    matches = service.find_symbol("TestClass")
    assert len(matches) == 1
    assert matches[0]["type"] == "class"
    assert matches[0]["name"] == "TestClass"

    # Find Method
    matches = service.find_symbol("method_one")
    assert len(matches) == 1
    assert matches[0]["type"] == "method"
    assert matches[0]["name"] == "TestClass.method_one"

    # Find Function
    matches = service.find_symbol("top_level_function")
    assert len(matches) == 1
    assert matches[0]["type"] == "function"

    # Case insensitive
    matches = service.find_symbol("testclass")
    assert len(matches) == 1
