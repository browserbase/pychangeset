# Changeset Tests

This directory contains the test suite for the changeset package.

## Running Tests

### Quick Test Run

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test file
uv run pytest tests/test_changeset_cli.py

# Run specific test class or method
uv run pytest tests/test_changeset_cli.py::TestInitCommand
uv run pytest tests/test_changeset_cli.py::TestInitCommand::test_init_creates_changeset_directory
```

### Test Options

```bash
# Run only unit tests (fast)
uv run pytest -m unit

# Run only integration tests (slower)
uv run pytest -m integration

# Skip slow tests
uv run pytest -m "not slow"

# Verbose output
uv run pytest -v

# Show print statements
uv run pytest -s

# Stop on first failure
uv run pytest -x

# Run tests in parallel (requires pytest-xdist)
uv run pytest -n auto
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_changeset_cli.py    # CLI command tests
├── test_changeset_parsing.py # Parsing and version logic tests
└── test_validate_changesets.py # Changeset validation tests
```

### conftest.py

Contains pytest fixtures used across all tests:

- `cli_runner`: Click test runner for CLI testing
- `temp_repo`: Creates a temporary git repository
- `sample_project`: Creates a single-package Python project
- `multi_package_project`: Creates a multi-package monorepo
- `initialized_changeset_project`: Project with changesets already set up
- `sample_changeset`: Creates a sample changeset file

### test_changeset_cli.py

Tests for the main CLI commands:

- **TestInitCommand**: Tests `changeset init`
  - Creates .changeset directory structure
  - Detects git branch correctly
  - Handles existing configurations

- **TestAddCommand**: Tests `changeset add`
  - Interactive changeset creation
  - Multi-package selection
  - `--all` flag functionality

- **TestVersionCommand**: Tests `changeset version`
  - Version bumping logic
  - Changeset processing
  - Dry-run mode

- **TestCheckChangesetCommand**: Tests `changeset check-changeset`
  - Branch detection
  - Changeset requirement enforcement

### test_changeset_parsing.py

Tests for core parsing and logic:

- **TestChangesetParsing**: Changeset file parsing
- **TestVersionBumping**: Semantic version calculations
- **TestProjectDiscovery**: Finding Python projects
- **TestGetChangesets**: Collecting changeset files

### test_validate_changesets.py

Tests for changeset validation:

- **TestValidateChangeset**: Validation logic
- **TestValidateCLI**: CLI interface for validation

## Writing New Tests

### Test Guidelines

1. **Use descriptive test names**: `test_<what>_<condition>_<expected_result>`
2. **One assertion per test** when possible
3. **Use fixtures** for common setup
4. **Mark tests appropriately**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
5. **Test edge cases**: Empty inputs, invalid data, error conditions

### Example Test

```python
def test_version_bump_major_change(cli_runner, initialized_changeset_project):
    """Test that major change correctly bumps to next major version."""
    # Arrange
    changeset_content = '''---
"my-package": major
---

Breaking change
'''
    (Path.cwd() / ".changeset" / "test.md").write_text(changeset_content)
    
    # Act
    result = cli_runner.invoke(cli, ["version", "--skip-changelog"])
    
    # Assert
    assert result.exit_code == 0
    with open("pyproject.toml") as f:
        data = toml.load(f)
    assert data["project"]["version"] == "1.0.0"
```

## Coverage Reports

After running tests with coverage, view the HTML report:

```bash
# Generate and open coverage report
uv run pytest --cov
open htmlcov/index.html  # macOS
# or
xdg-open htmlcov/index.html  # Linux
```

## Continuous Integration

Tests are automatically run on:
- Every push to main
- Every pull request
- Can be manually triggered

See `.github/workflows/tests.yml` for CI configuration.