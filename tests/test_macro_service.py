import os
import stat
from mini_nebulus.services.macro_service import MacroService


def test_create_macro(tmp_path):
    macro_dir = tmp_path / "macros"
    service = MacroService(macro_dir=str(macro_dir))

    commands = ["echo hello", "ls -la"]
    result = service.create_macro("test_macro", commands, "A test macro")

    expected_file = macro_dir / "test_macro.sh"

    assert str(expected_file) in result
    assert expected_file.exists()

    # Check executable permission
    st = os.stat(expected_file)
    assert bool(st.st_mode & stat.S_IEXEC)

    content = expected_file.read_text()
    assert "#!/bin/bash" in content
    assert "# A test macro" in content
    assert "echo hello" in content
    assert "ls -la" in content
