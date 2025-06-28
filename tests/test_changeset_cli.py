"""Tests for the main changeset CLI commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from changeset.changeset import cli


class TestInitCommand:
    """Test the init command."""

    def test_init_creates_changeset_directory(
        self, cli_runner: CliRunner, temp_repo: Path
    ):
        """Test that init creates the .changeset directory."""
        with cli_runner.isolated_filesystem(temp_dir=temp_repo):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert (Path.cwd() / ".changeset").exists()
            assert (Path.cwd() / ".changeset" / "config.json").exists()
            assert (Path.cwd() / ".changeset" / "README.md").exists()

    def test_init_detects_main_branch(self, cli_runner: CliRunner, temp_repo: Path):
        """Test that init correctly detects the main branch."""
        with cli_runner.isolated_filesystem(temp_dir=temp_repo):
            # Create a main branch
            import subprocess
            subprocess.run(["git", "checkout", "-b", "main"], capture_output=True)

            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            with open(".changeset/config.json") as f:
                config = json.load(f)
            assert config["baseBranch"] == "main"

    def test_init_handles_existing_directory(
        self, cli_runner: CliRunner, initialized_changeset_project: Path
    ):
        """Test that init handles existing .changeset directory."""
        import os
        os.chdir(initialized_changeset_project)
        result = cli_runner.invoke(cli, ["init"], input="n\n")

        assert result.exit_code == 0
        assert ".changeset directory already exists" in result.output


class TestAddCommand:
    """Test the add command."""

    @pytest.mark.integration
    def test_add_creates_changeset_interactive(
        self, cli_runner: CliRunner, initialized_changeset_project: Path, mocker
    ):
        """Test creating a changeset interactively."""
        import os
        os.chdir(initialized_changeset_project)

        # Create a change
        new_file = initialized_changeset_project / "test_package" / "new_file.py"
        new_file.parent.mkdir(exist_ok=True)
        new_file.write_text("# New file")

        # Mock the interactive prompts
        mocker.patch(
            'changeset.changeset.questionary.checkbox',
            return_value=mocker.Mock(
                ask=mocker.Mock(return_value=['changed_test-package'])
            )
        )
        mocker.patch('changeset.changeset.questionary.select', return_value=mocker.Mock(
            ask=mocker.Mock(return_value='patch')
        ))
        mocker.patch('changeset.changeset.questionary.text', return_value=mocker.Mock(
            ask=mocker.Mock(return_value='Test changeset description')
        ))
        mocker.patch(
            'changeset.changeset.questionary.confirm',
            return_value=mocker.Mock(
                ask=mocker.Mock(return_value=False)  # Don't confirm major version
            )
        )

        # Run add command
        result = cli_runner.invoke(cli, ["add"], catch_exceptions=False)

        # Check the command succeeded
        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Check changeset was created
        changesets = list((initialized_changeset_project / ".changeset").glob("*.md"))
        changesets = [c for c in changesets if c.name != "README.md"]
        assert len(changesets) == 1

    def test_add_with_all_flag(
        self, cli_runner: CliRunner, multi_package_project: Path, mocker
    ):
        """Test add command with --all flag."""
        import os
        os.chdir(multi_package_project)

        # Initialize changesets first
        cli_runner.invoke(cli, ["init"])

        # Mock the interactive prompts for both packages
        select_mock = mocker.patch("changeset.changeset.questionary.select")
        # One for each package
        select_mock.return_value.ask.side_effect = ['patch', 'patch']

        text_mock = mocker.patch("changeset.changeset.questionary.text")
        text_mock.return_value.ask.return_value = 'Test all packages'

        result = cli_runner.invoke(
            cli,
            ["add", "--all"],
            catch_exceptions=False
        )

        # Check the command succeeded
        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Should have created a changeset
        changesets = list((multi_package_project / ".changeset").glob("*.md"))
        changesets = [c for c in changesets if c.name != "README.md"]
        assert len(changesets) == 1

        # Check content includes both packages
        content = changesets[0].read_text()
        assert "package1" in content
        assert "package2" in content


class TestVersionCommand:
    """Test the version command."""

    def test_version_bumps_package_version(
        self, cli_runner: CliRunner, initialized_changeset_project: Path
    ):
        """Test that version command bumps the package version."""
        import os
        os.chdir(initialized_changeset_project)

        # Create a changeset
        changeset_content = """---
"test-package": minor
---

Added new feature
"""
        (
            initialized_changeset_project / ".changeset" / "test-change.md"
        ).write_text(changeset_content)

        # Run version command
        result = cli_runner.invoke(cli, ["version", "--skip-changelog"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Check version was bumped
        import toml
        with open(initialized_changeset_project / "pyproject.toml") as f:
            data = toml.load(f)

        assert data["project"]["version"] == "0.2.0"

        # Check changeset was removed
        assert not (
            initialized_changeset_project / ".changeset" / "test-change.md"
        ).exists()

    def test_version_dry_run(self, cli_runner: CliRunner, sample_changeset: Path):
        """Test version command with --dry-run."""
        project_dir = sample_changeset.parent.parent

        import os
        os.chdir(project_dir)

        result = cli_runner.invoke(cli, ["version", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run - no changes made" in result.output

        # Changeset should still exist
        assert sample_changeset.name in [
            f.name for f in (project_dir / ".changeset").glob("*.md")
        ]

    def test_version_no_changesets(
        self, cli_runner: CliRunner, initialized_changeset_project: Path
    ):
        """Test version command when no changesets exist."""
        import os
        os.chdir(initialized_changeset_project)

        result = cli_runner.invoke(cli, ["version"])

        assert result.exit_code == 0
        assert "No changesets found" in result.output


class TestCheckChangesetCommand:
    """Test the check-changeset command."""

    def test_check_changeset_on_main_branch(
        self, cli_runner: CliRunner, initialized_changeset_project: Path
    ):
        """Test check-changeset on main branch (should skip)."""
        import os
        os.chdir(initialized_changeset_project)

        result = cli_runner.invoke(cli, ["check-changeset"])

        assert result.exit_code == 0
        assert "Skipping changeset check for branch: main" in result.output

    def test_check_changeset_on_feature_branch_without_changeset(
        self, cli_runner: CliRunner, initialized_changeset_project: Path
    ):
        """Test check-changeset on feature branch without changeset."""
        import os
        import subprocess
        os.chdir(initialized_changeset_project)

        # Create feature branch
        subprocess.run(["git", "checkout", "-b", "feature/test"], capture_output=True)

        result = cli_runner.invoke(cli, ["check-changeset"])

        assert result.exit_code == 1
        assert "No changeset found for feature branch" in result.output

    def test_check_changeset_on_feature_branch_with_changeset(
        self, cli_runner: CliRunner, sample_changeset: Path
    ):
        """Test check-changeset on feature branch with changeset."""
        project_dir = sample_changeset.parent.parent

        import os
        import subprocess
        os.chdir(project_dir)

        # Create feature branch and add changeset
        subprocess.run(["git", "checkout", "-b", "feature/test"], capture_output=True)
        subprocess.run(["git", "add", str(sample_changeset)], capture_output=True)

        result = cli_runner.invoke(cli, ["check-changeset"])

        assert result.exit_code == 0
        assert "Found changeset(s) for branch" in result.output
