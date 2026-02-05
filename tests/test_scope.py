"""Tests for worker scope enforcement."""

from nebulus_swarm.overlord.scope import ScopeConfig, ScopeMode


class TestScopeMode:
    def test_unrestricted_value(self):
        assert ScopeMode.UNRESTRICTED.value == "unrestricted"

    def test_directory_value(self):
        assert ScopeMode.DIRECTORY.value == "directory"

    def test_explicit_value(self):
        assert ScopeMode.EXPLICIT.value == "explicit"


class TestScopeConfig:
    def test_unrestricted_allows_all(self):
        scope = ScopeConfig.unrestricted()
        assert scope.is_write_allowed("any/path/file.py")
        assert scope.is_write_allowed("deeply/nested/dir/file.txt")

    def test_directory_allows_matching_paths(self):
        scope = ScopeConfig(
            mode=ScopeMode.DIRECTORY,
            allowed_patterns=["src/components/**", "tests/components/**"],
        )
        assert scope.is_write_allowed("src/components/Button.tsx")
        assert scope.is_write_allowed("src/components/deep/nested/File.tsx")
        assert scope.is_write_allowed("tests/components/test_button.py")

    def test_directory_blocks_non_matching_paths(self):
        scope = ScopeConfig(
            mode=ScopeMode.DIRECTORY,
            allowed_patterns=["src/components/**"],
        )
        assert not scope.is_write_allowed("src/utils/helper.py")
        assert not scope.is_write_allowed("README.md")
        assert not scope.is_write_allowed("package.json")

    def test_explicit_allows_exact_files(self):
        scope = ScopeConfig(
            mode=ScopeMode.EXPLICIT,
            allowed_patterns=["src/app.py", "tests/test_app.py"],
        )
        assert scope.is_write_allowed("src/app.py")
        assert scope.is_write_allowed("tests/test_app.py")
        assert not scope.is_write_allowed("src/other.py")

    def test_from_json_string(self):
        scope = ScopeConfig.from_json('["src/**", "tests/**"]')
        assert scope.mode == ScopeMode.DIRECTORY
        assert scope.is_write_allowed("src/foo.py")

    def test_from_json_empty_means_unrestricted(self):
        scope = ScopeConfig.from_json("")
        assert scope.mode == ScopeMode.UNRESTRICTED

    def test_from_json_invalid_means_unrestricted(self):
        scope = ScopeConfig.from_json("not valid json")
        assert scope.mode == ScopeMode.UNRESTRICTED

    def test_to_json(self):
        scope = ScopeConfig(
            mode=ScopeMode.DIRECTORY,
            allowed_patterns=["src/**"],
        )
        json_str = scope.to_json()
        assert "src/**" in json_str

    def test_violation_message(self):
        scope = ScopeConfig(
            mode=ScopeMode.DIRECTORY,
            allowed_patterns=["src/**"],
        )
        msg = scope.violation_message("README.md")
        assert "README.md" in msg
        assert "src/**" in msg
