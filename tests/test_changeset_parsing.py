"""Tests for changeset parsing and version bump logic."""

from pathlib import Path

import pytest

from changeset.changeset import (
    bump_version,
    determine_version_bump,
    find_python_projects,
    get_changesets,
    parse_changeset,
    parse_version,
)


class TestChangesetParsing:
    """Test changeset file parsing."""

    def test_parse_valid_changeset(self, tmp_path: Path):
        """Test parsing a valid changeset file."""
        changeset_content = """---
"my-package": minor
"other-package": patch
---

This is a test changeset with multiple packages
"""
        changeset_file = tmp_path / "test.md"
        changeset_file.write_text(changeset_content)

        result = parse_changeset(changeset_file)

        assert len(result) == 2
        assert result[0] == (
            "my-package", "minor", "This is a test changeset with multiple packages"
        )
        assert result[1] == (
            "other-package", "patch", "This is a test changeset with multiple packages"
        )

    def test_parse_changeset_invalid_format(self, tmp_path: Path):
        """Test parsing an invalid changeset file."""
        changeset_content = """Not a valid changeset"""
        changeset_file = tmp_path / "invalid.md"
        changeset_file.write_text(changeset_content)

        with pytest.raises(ValueError, match="Invalid changeset format"):
            parse_changeset(changeset_file)

    def test_parse_changeset_no_description(self, tmp_path: Path):
        """Test parsing a changeset with no description."""
        changeset_content = """---
"my-package": patch
---
"""
        changeset_file = tmp_path / "test.md"
        changeset_file.write_text(changeset_content)

        result = parse_changeset(changeset_file)

        assert len(result) == 1
        assert result[0] == ("my-package", "patch", "")


class TestVersionBumping:
    """Test version bumping logic."""

    @pytest.mark.parametrize("current,bump_type,expected", [
        ("1.0.0", "major", "2.0.0"),
        ("1.2.3", "major", "2.0.0"),
        ("0.1.0", "major", "1.0.0"),
        ("1.0.0", "minor", "1.1.0"),
        ("1.2.3", "minor", "1.3.0"),
        ("0.1.2", "minor", "0.2.0"),
        ("1.0.0", "patch", "1.0.1"),
        ("1.2.3", "patch", "1.2.4"),
        ("0.0.1", "patch", "0.0.2"),
    ])
    def test_bump_version(self, current: str, bump_type: str, expected: str):
        """Test version bumping for different bump types."""
        assert bump_version(current, bump_type) == expected

    def test_parse_version_valid(self):
        """Test parsing valid version strings."""
        assert parse_version("1.2.3") == (1, 2, 3)
        assert parse_version("0.0.1") == (0, 0, 1)
        assert parse_version("10.20.30") == (10, 20, 30)

    def test_parse_version_invalid(self):
        """Test parsing invalid version strings."""
        # These should work with packaging library
        assert parse_version("1.2") == (1, 2, 0)
        assert parse_version("1.2.3.4") == (1, 2, 3)

        # This should still raise an error
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("not-a-version")

        # Pre-release versions should also raise errors for changesets
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("1.0.0a1")

        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("1.0.0rc1")

    def test_determine_version_bump(self):
        """Test determining version bump from change types."""
        assert determine_version_bump(["patch", "patch"]) == "patch"
        assert determine_version_bump(["minor", "patch"]) == "minor"
        assert determine_version_bump(["major", "minor", "patch"]) == "major"
        assert determine_version_bump(["patch", "minor", "patch"]) == "minor"
        assert determine_version_bump([]) == "patch"  # Default to patch


class TestProjectDiscovery:
    """Test Python project discovery."""

    def test_find_single_project(self, sample_project: Path):
        """Test finding a single Python project."""
        import os
        os.chdir(sample_project)

        projects = find_python_projects()

        assert len(projects) == 1
        assert projects[0][1] == "test-package"

    def test_find_multiple_projects(self, multi_package_project: Path):
        """Test finding multiple Python projects."""
        import os
        os.chdir(multi_package_project)

        projects = find_python_projects()

        assert len(projects) == 2
        project_names = [p[1] for p in projects]
        assert "package1" in project_names
        assert "package2" in project_names

    def test_find_projects_ignores_hidden_directories(self, temp_repo: Path):
        """Test that hidden directories are ignored."""
        import os
        os.chdir(temp_repo)

        # Create hidden directory with pyproject.toml
        hidden_dir = temp_repo / ".hidden"
        hidden_dir.mkdir()

        import toml
        with open(hidden_dir / "pyproject.toml", "w") as f:
            toml.dump({"project": {"name": "hidden-package"}}, f)

        # Create normal package
        with open(temp_repo / "pyproject.toml", "w") as f:
            toml.dump({"project": {"name": "visible-package"}}, f)

        projects = find_python_projects()

        assert len(projects) == 1
        assert projects[0][1] == "visible-package"


class TestGetChangesets:
    """Test getting and parsing all changesets."""

    def test_get_changesets_multiple_files(self, initialized_changeset_project: Path):
        """Test getting multiple changeset files."""
        import os
        os.chdir(initialized_changeset_project)

        # Create multiple changesets
        changeset_dir = Path(".changeset")

        (changeset_dir / "change1.md").write_text("""---
"test-package": patch
---

First change
""")

        (changeset_dir / "change2.md").write_text("""---
"test-package": minor
---

Second change
""")

        changesets = get_changesets()

        assert len(changesets) == 2
        # Check that README.md is ignored
        assert all(cs[0].name != "README.md" for cs in changesets)

    def test_get_changesets_ignores_readme(self, initialized_changeset_project: Path):
        """Test that README.md is ignored when getting changesets."""
        import os
        os.chdir(initialized_changeset_project)

        changesets = get_changesets()

        assert len(changesets) == 0  # Only README.md exists
