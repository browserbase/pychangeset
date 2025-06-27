"""Pytest configuration and fixtures."""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository for testing."""
    import subprocess
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path, check=True, capture_output=True
    )
    
    # Create initial commit
    (tmp_path / "README.md").write_text("# Test Project")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path, check=True, capture_output=True
    )
    
    yield tmp_path


@pytest.fixture
def sample_project(temp_repo: Path) -> Path:
    """Create a sample Python project with pyproject.toml."""
    # Create pyproject.toml
    pyproject_content = {
        "project": {
            "name": "test-package",
            "version": "0.1.0",
            "description": "Test package",
        }
    }
    
    import toml
    with open(temp_repo / "pyproject.toml", "w") as f:
        toml.dump(pyproject_content, f)
    
    # Create package directory
    (temp_repo / "test_package").mkdir()
    (temp_repo / "test_package" / "__init__.py").write_text("")
    
    return temp_repo


@pytest.fixture
def multi_package_project(temp_repo: Path) -> Path:
    """Create a multi-package project."""
    # Package 1
    pkg1_dir = temp_repo / "packages" / "package1"
    pkg1_dir.mkdir(parents=True)
    
    pyproject1 = {
        "project": {
            "name": "package1",
            "version": "1.0.0",
            "description": "Package 1",
        }
    }
    
    import toml
    with open(pkg1_dir / "pyproject.toml", "w") as f:
        toml.dump(pyproject1, f)
    
    # Package 2
    pkg2_dir = temp_repo / "packages" / "package2"
    pkg2_dir.mkdir(parents=True)
    
    pyproject2 = {
        "project": {
            "name": "package2",
            "version": "2.0.0",
            "description": "Package 2",
        }
    }
    
    with open(pkg2_dir / "pyproject.toml", "w") as f:
        toml.dump(pyproject2, f)
    
    return temp_repo


@pytest.fixture
def initialized_changeset_project(sample_project: Path) -> Path:
    """Create a project with changesets already initialized."""
    changeset_dir = sample_project / ".changeset"
    changeset_dir.mkdir()
    
    # Create config
    config = {
        "baseBranch": "main",
        "changeTypes": {
            "major": {"description": "Breaking changes", "emoji": "💥"},
            "minor": {"description": "New features", "emoji": "✨"},
            "patch": {"description": "Bug fixes and improvements", "emoji": "🐛"},
        }
    }
    
    with open(changeset_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    # Create README
    (changeset_dir / "README.md").write_text("# Changesets\n\nTest changesets.")
    
    return sample_project


@pytest.fixture
def sample_changeset(initialized_changeset_project: Path) -> Path:
    """Create a sample changeset file."""
    changeset_content = """---
"test-package": patch
---

Fixed a bug in the test functionality
"""
    
    changeset_file = initialized_changeset_project / ".changeset" / "test-change.md"
    changeset_file.write_text(changeset_content)
    
    return changeset_file