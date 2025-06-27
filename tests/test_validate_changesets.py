"""Tests for changeset validation."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from changeset.validate_changesets import main as validate_main, validate_changeset_file as validate_changeset


class TestValidateChangeset:
    """Test changeset validation logic."""
    
    def test_validate_valid_changeset(self, tmp_path: Path):
        """Test validating a properly formatted changeset."""
        changeset_file = tmp_path / "valid.md"
        changeset_file.write_text("""---
"my-package": patch
---

This is a valid changeset
""")
        
        assert validate_changeset(changeset_file) is True
    
    def test_validate_multiple_packages(self, tmp_path: Path):
        """Test validating changeset with multiple packages."""
        changeset_file = tmp_path / "multi.md"
        changeset_file.write_text("""---
"package-one": minor
"package-two": patch
---

Changes affecting multiple packages
""")
        
        assert validate_changeset(changeset_file) is True
    
    def test_validate_missing_frontmatter(self, tmp_path: Path):
        """Test validating changeset without frontmatter."""
        changeset_file = tmp_path / "invalid.md"
        changeset_file.write_text("Just some text without frontmatter")
        
        assert validate_changeset(changeset_file) is False
    
    def test_validate_incomplete_frontmatter(self, tmp_path: Path):
        """Test validating changeset with incomplete frontmatter."""
        changeset_file = tmp_path / "incomplete.md"
        changeset_file.write_text("""---
"my-package": patch

No closing frontmatter
""")
        
        assert validate_changeset(changeset_file) is False
    
    def test_validate_invalid_change_type(self, tmp_path: Path):
        """Test validating changeset with invalid change type."""
        changeset_file = tmp_path / "invalid-type.md"
        changeset_file.write_text("""---
"my-package": invalid-type
---

Invalid change type
""")
        
        assert validate_changeset(changeset_file) is False
    
    def test_validate_missing_description(self, tmp_path: Path):
        """Test validating changeset without description."""
        changeset_file = tmp_path / "no-desc.md"
        changeset_file.write_text("""---
"my-package": patch
---
""")
        
        assert validate_changeset(changeset_file) is False
    
    def test_validate_empty_package_name(self, tmp_path: Path):
        """Test validating changeset with empty package name."""
        changeset_file = tmp_path / "empty-package.md"
        changeset_file.write_text("""---
"": patch
---

Empty package name
""")
        
        assert validate_changeset(changeset_file) is False


class TestValidateCLI:
    """Test the validate changesets CLI."""
    
    def test_validate_cli_valid_files(self, cli_runner: CliRunner, tmp_path: Path):
        """Test CLI with valid changeset files."""
        # Create valid changesets
        (tmp_path / "change1.md").write_text("""---
"package": patch
---

Valid change 1
""")
        
        (tmp_path / "change2.md").write_text("""---
"package": minor
---

Valid change 2
""")
        
        with cli_runner.isolated_filesystem(temp_dir=tmp_path.parent):
            result = cli_runner.invoke(
                validate_main,
                [str(tmp_path / "change1.md"), str(tmp_path / "change2.md")]
            )
            
            assert result.exit_code == 0
            assert "Valid changeset" in result.output
    
    def test_validate_cli_invalid_file(self, cli_runner: CliRunner, tmp_path: Path):
        """Test CLI with invalid changeset file."""
        invalid_file = tmp_path / "invalid.md"
        invalid_file.write_text("Not a valid changeset")
        
        with cli_runner.isolated_filesystem(temp_dir=tmp_path.parent):
            result = cli_runner.invoke(validate_main, [str(invalid_file)])
            
            assert result.exit_code == 1
            assert "Missing or invalid frontmatter start" in result.output
    
    def test_validate_cli_no_files(self, cli_runner: CliRunner):
        """Test CLI with no files provided."""
        result = cli_runner.invoke(validate_main, [])
        
        assert result.exit_code == 0  # Should exit cleanly when no files provided