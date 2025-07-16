# pychangeset

A tool for automating version bumps, changelog generation and release PRs in Python projects, inspired by [Changesets](https://github.com/changesets/changesets).

## Installation

```bash
# Use with uvx (recommended)
uvx changeset

# Or install from PyPI
pip install pychangeset
```

## Quick Start

### 0. Initialize

```bash
uvx changeset
```

This will:
- Run `changeset init`, creating a .changeset/ directory in your project
- Prompt the user to `add` a changeset, which will:
  - Detect which packages have changes
  - Ask what type of change for each (major/minor/patch)
  - Prompt for a description
  - Create a changeset file in `.changeset/`

### 1. Track `.changset/`

```bash
git add .changeset/
git commit -m "Add changeset"
git push
```

### 2. Automated Release Process

To get the most out of pychangeset, add these workflows to your repository:

### `.github/workflows/changesets.yml`

When you merge to your main branch, the `changesets` workflow will create or update a Release PR with:
   - Updated CHANGELOG.md files
   - Bumped version numbers
   - Consolidated PR description

### `.github/workflows/release.yml`

When the Release PR is merged, the `release` workflow:
- Publishes packages to PyPI
- Creates git tags
- Creates GitHub releases

## Commands

### `changeset init`
Initialize changesets in your project.

### `changeset add` / `changeset`
Create a new changeset interactively.

Options:
- `--all`: Include all packages without prompting

### `changeset version`
Process changesets and bump versions.

Options:
- `--dry-run`: Preview changes without applying them
- `--skip-changelog`: Skip changelog generation

### `changeset changelog`
Generate changelogs from changesets.

Options:
- `--dry-run`: Preview changelog without writing files
- `--output-pr-description <file>`: Write PR description to file

### `changeset check-changeset`
Check if changesets exist for the current branch (useful for CI).

Options:
- `--skip-ci`: Skip check in CI environment

## Changelog Format

Changelogs are generated with PR and commit metadata:

```markdown
# package-name

## 1.2.0

### Minor Changes

- [#123](link-to-pr) [`abc123`](link-to-commit) Thanks @username! - Description of change

### Patch Changes

- [#124](link-to-pr) [`def456`](link-to-commit) Thanks @username! - Bug fix description
```

## Development

```bash
# Clone the repository
git clone https://github.com/the-roaring/pychangeset.git
cd pychangeset

# Install with uv
uv sync

# Run tests
uv run pytest

# Run the tool locally
uv run changeset
```

## License

MIT
