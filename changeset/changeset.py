#!/usr/bin/env python3
"""
Changeset CLI - Interactive tool for creating changeset files.
Similar to JavaScript changesets but for Python projects.
"""

import json
import os
import re
import sys
import tomllib
from datetime import datetime
from pathlib import Path

import click
import git
import questionary
import toml
from packaging.version import InvalidVersion, Version
from questionary import Choice
from rich.console import Console
from rich.prompt import Confirm

console = Console()

CHANGESET_DIR = Path(".changeset")
CONFIG_FILE = CHANGESET_DIR / "config.json"


def init_changesets():
    """Initialize changesets configuration."""
    # Create .changeset directory
    CHANGESET_DIR.mkdir(exist_ok=True)

    # Create config.json with simplified config
    config = {
        "changeTypes": {
            "major": {"description": "Breaking changes", "emoji": "💥"},
            "minor": {"description": "New features", "emoji": "✨"},
            "patch": {"description": "Bug fixes and improvements", "emoji": "🐛"},
        },
        "baseBranch": "main",
    }

    # Detect base branch automatically
    try:
        repo = git.Repo(".")
        remote_refs = [ref.name for ref in repo.remote().refs]

        has_main = any("main" in ref for ref in remote_refs)
        has_master = any("master" in ref for ref in remote_refs)

        if has_main and has_master:
            console.print(
                "❌ Error: Both 'main' and 'master' branches exist in the repository.",
                style="red",
            )
            console.print("Please remove one of them to avoid ambiguity.", style="red")
            sys.exit(1)
        elif has_main:
            base_branch = "main"
        elif has_master:
            base_branch = "master"
        else:
            # Fallback to checking local branches
            local_branches = [branch.name for branch in repo.branches]
            if "main" in local_branches and "master" in local_branches:
                console.print(
                    "❌ Error: Both 'main' and 'master' branches exist.",
                    style="red",
                )
                console.print(
                    "Please remove one of them to avoid ambiguity.", style="red"
                )
                sys.exit(1)
            elif "main" in local_branches:
                base_branch = "main"
            elif "master" in local_branches:
                base_branch = "master"
            else:
                # Default to main if no branches exist yet
                base_branch = "main"
    except Exception:
        # Default to main if git is not available
        base_branch = "main"

    config["baseBranch"] = base_branch
    console.print(f"✅ Detected base branch: {base_branch}", style="green")

    # Write config
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    # Create README.md
    readme_path = CHANGESET_DIR / "README.md"
    readme_content = """# Changesets

This directory contains changeset files that track changes.

## Creating a changeset

Run `changeset` or `changeset add` to create a new changeset.

## More info

See https://github.com/browserbase/pychangeset for more information.
"""

    with open(readme_path, "w") as f:
        f.write(readme_content)


def load_config() -> dict:
    """Load changeset configuration."""
    if not CONFIG_FILE.exists():
        # Auto-initialize if config doesn't exist
        console.print("🚀 Initializing changesets...", style="cyan bold")
        init_changesets()
        console.print("✨ Changesets initialized successfully!\n", style="green bold")

    with open(CONFIG_FILE) as f:
        return json.load(f)


def find_python_projects(root_path: Path = Path(".")) -> list[tuple[Path, str]]:
    """Find all Python projects (directories with pyproject.toml) in the repository."""
    projects = []

    # Find all pyproject.toml files
    for pyproject_path in root_path.rglob("pyproject.toml"):
        # Skip hidden directories and common build/env directories
        parts = pyproject_path.parts
        if any(
            part.startswith(".")
            or part in ["venv", "env", "build", "dist", "__pycache__"]
            for part in parts
        ):
            continue

        # Read the project name
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                project_name = data.get("project", {}).get(
                    "name", pyproject_path.parent.name
                )
                projects.append((pyproject_path.parent, project_name))
        except Exception:
            # If we can't read it, use the directory name
            projects.append((pyproject_path.parent, pyproject_path.parent.name))

    return sorted(projects, key=lambda x: x[1])


def get_changed_files() -> set[str]:
    """Get set of changed files in the filesystem (unstaged and staged)."""
    try:
        repo = git.Repo(".")

        changed_files = set()

        # Get unstaged changes
        for item in repo.index.diff(None):
            if item.a_path:
                changed_files.add(item.a_path)
            if item.b_path:
                changed_files.add(item.b_path)

        # Get staged changes
        for item in repo.index.diff("HEAD"):
            if item.a_path:
                changed_files.add(item.a_path)
            if item.b_path:
                changed_files.add(item.b_path)

        # Get untracked files
        for item in repo.untracked_files:
            changed_files.add(item)

        return changed_files
    except Exception:
        return set()


def get_project_changes(
    projects: list[tuple[Path, str]], changed_files: set[str]
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    """Determine which projects have changes."""
    changed_projects = []
    unchanged_projects = []

    repo_root = Path(".").resolve()

    for project_path, project_name in projects:
        # Resolve the project path to absolute
        project_abs_path = project_path.resolve()

        # Calculate relative path
        try:
            project_rel_path = project_abs_path.relative_to(repo_root)
        except ValueError:
            # If project is not under repo root, skip it
            continue

        has_changes = False

        # Check if any changed file is within this project
        for changed_file in changed_files:
            try:
                changed_file_path = Path(changed_file)
                # If it's the root project (.), any change counts
                if str(project_rel_path) == ".":
                    has_changes = True
                    break
                # Otherwise check if the file is under the project directory
                changed_file_path.relative_to(project_rel_path)
                has_changes = True
                break
            except ValueError:
                # File is not under this project directory
                continue

        if has_changes:
            changed_projects.append((project_path, project_name))
        else:
            unchanged_projects.append((project_path, project_name))

    return changed_projects, unchanged_projects


def select_packages(
    changed_projects: list[tuple[Path, str]], unchanged_projects: list[tuple[Path, str]]
) -> list[tuple[Path, str]]:
    """Interactive package selection using questionary."""

    # Check if we're in a non-interactive environment
    if not os.isatty(0):
        # In CI/CD or non-interactive mode, just return changed packages
        console.print(
            "🐍 Non-interactive mode detected. Selecting changed packages...",
            style="yellow",
        )
        if changed_projects:
            console.print("\nChanged packages selected:", style="green")
            for _, name in changed_projects:
                console.print(f"  • {name}", style="green")
        return changed_projects

    # Build choices list
    choices = []
    package_map = {}

    # Add section separators and packages
    if changed_projects:
        # Add a visual separator for changed packages
        choices.append(questionary.Separator("── Changed packages ──"))
        for path, name in changed_projects:
            value = f"changed_{name}"
            choices.append(Choice(title=name, value=value, checked=True))
            package_map[value] = (path, name)

    if unchanged_projects:
        # Add a visual separator for unchanged packages
        choices.append(questionary.Separator("── Unchanged packages ──"))
        for path, name in unchanged_projects:
            value = f"unchanged_{name}"
            choices.append(Choice(title=name, value=value, checked=False))
            package_map[value] = (path, name)

    # If no packages at all
    if not package_map:
        console.print("No packages found in the repository.", style="yellow")
        return []

    # Show the checkbox prompt
    selected = questionary.checkbox(
        "Which packages would you like to include?",
        choices=choices,
        instruction="(Use ↑↓ to move, space to select, enter to confirm)",
    ).ask()

    if selected is None:
        console.print("❌ Cancelled", style="red")
        return []

    # Extract actual packages from the results
    result = []
    for value in selected:
        if value in package_map:
            result.append(package_map[value])

    return result


def generate_changeset_name() -> str:
    """Generate a unique changeset filename."""
    import coolname

    # Generate names until we find one that doesn't exist
    for _ in range(10):  # 10 attempts
        name = coolname.generate_slug(3)
        if not (CHANGESET_DIR / f"{name}.md").exists():
            return name

    # Fallback to timestamp + random string after 100 attempts
    import uuid

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = str(uuid.uuid4()).split("-")[0][:6]
    return f"changeset-{timestamp}-{random_suffix}"


def create_changeset(packages: list[tuple[str, str]], description: str) -> str:
    """Create a changeset file and return its path."""
    # Generate filename
    filename = f"{generate_changeset_name()}.md"
    filepath = CHANGESET_DIR / filename

    # Create changeset content
    content = "---\n"
    for package_name, change_type in packages:
        content += f'"{package_name}": {change_type}\n'
    content += "---\n\n"
    content += description + "\n"

    with open(filepath, "w") as f:
        f.write(content)

    return str(filepath)


def parse_changeset(filepath: Path) -> list[tuple[str, str, str]]:
    """Parse a changeset file and return list of (package, change_type, description)."""
    with open(filepath) as f:
        content = f.read()

    # Parse frontmatter
    lines = content.strip().split("\n")

    if lines[0] != "---":
        raise ValueError(f"Invalid changeset format in {filepath}")

    # Find end of frontmatter
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError(f"Invalid changeset format in {filepath}")

    # Parse packages and change types
    packages = []
    for line in lines[1:end_idx]:
        if line.strip():
            match = re.match(r'"(.+)":\s*(\w+)', line.strip())
            if match:
                package = match.group(1)
                change_type = match.group(2)
                packages.append((package, change_type))

    # Get description (everything after frontmatter)
    description = "\n".join(lines[end_idx + 1 :]).strip()

    # Return with same description for all packages
    return [(pkg, ct, description) for pkg, ct in packages]


def get_changesets() -> list[tuple[Path, str, str, str]]:
    """Get all changeset files and parse them."""
    changesets = []

    for filepath in CHANGESET_DIR.glob("*.md"):
        if filepath.name == "README.md":
            continue

        try:
            parsed = parse_changeset(filepath)
            for package, change_type, description in parsed:
                changesets.append((filepath, package, change_type, description))
        except Exception as e:
            console.print(f"⚠️  Error parsing {filepath}: {e}", style="yellow")

    return changesets


def determine_version_bump(changes: list[str]) -> str:
    """Determine the version bump type based on change types."""
    has_major = any(ct == "major" for ct in changes)
    has_minor = any(ct == "minor" for ct in changes)

    if has_major:
        return "major"
    elif has_minor:
        return "minor"
    else:
        return "patch"


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse semantic version string."""
    try:
        v = Version(version_str)
        # We only support simple X.Y.Z versions for changesets
        if v.pre or v.post or v.dev or v.local:
            raise ValueError(f"Invalid version format: {version_str}")
        return v.major, v.minor, v.micro
    except InvalidVersion:
        raise ValueError(f"Invalid version format: {version_str}")


def bump_version(current_version: str, bump_type: str) -> str:
    """Bump version based on type."""
    major, minor, patch = parse_version(current_version)

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    else:  # patch
        return f"{major}.{minor}.{patch + 1}"


def find_project_pyproject(package_name: str) -> Path:
    """Find the pyproject.toml for a given package."""
    # Use existing find_python_projects function
    projects = find_python_projects()

    for project_path, project_name in projects:
        if project_name == package_name:
            return project_path / "pyproject.toml"

    raise ValueError(f"Could not find pyproject.toml for package: {package_name}")


def update_pyproject_version(filepath: Path, new_version: str):
    """Update version in pyproject.toml using toml library."""
    with open(filepath, "rb") as f:
        data = tomllib.load(f)

    # Update version
    if "project" in data:
        data["project"]["version"] = new_version
    else:
        raise ValueError(f"No [project] section in {filepath}")

    # Write back using toml library
    with open(filepath, "w") as f:
        toml.dump(data, f)


def get_current_version(pyproject_path: Path) -> str:
    """Get current version from pyproject.toml."""
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    return data.get("project", {}).get("version", "0.0.0")


@click.group()
def cli():
    """Changeset management for Python projects."""
    pass


@cli.command()
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option("--output-pr-description", help="File to write PR description to")
def changelog(dry_run: bool, output_pr_description: str):
    """Generate changelogs from changesets."""
    # Pass through to the changelog module
    import sys

    from changeset.changelog import main as changelog_main
    original_argv = sys.argv
    try:
        sys.argv = ["changelog"]
        if dry_run:
            sys.argv.append("--dry-run")
        if output_pr_description:
            sys.argv.extend(["--output-pr-description", output_pr_description])
        changelog_main()
    finally:
        sys.argv = original_argv


@cli.command()
def init():
    """Initialize changesets in your project."""
    console.print("🚀 Initializing changesets...", style="cyan bold")

    # Check if already initialized
    if CHANGESET_DIR.exists():
        console.print("⚠️  .changeset directory already exists", style="yellow")
        if not Confirm.ask("Do you want to reinitialize?"):
            return

    init_changesets()

    console.print("✅ Created .changeset directory", style="green")
    console.print("✅ Created config.json", style="green")
    console.print("✅ Created README.md", style="green")
    console.print("\n✨ Changesets initialized successfully!", style="green bold")
    console.print("\nNext steps:", style="yellow")
    console.print("  1. Run 'changeset' to create your first changeset")
    console.print("  2. Commit the .changeset directory to your repository")


@cli.command(name="add")
@click.option("--all", is_flag=True, help="Include all packages without prompting")
def add(all: bool):
    """Create a new changeset for tracking changes."""

    console.print("🐍 Creating a new changeset...\n", style="cyan bold")

    # Find all Python projects
    projects = find_python_projects()

    if not projects:
        console.print(
            "❌ No Python projects found (no pyproject.toml files)", style="red"
        )
        sys.exit(1)

    # Get changed files
    changed_files = get_changed_files()

    # Determine which projects have changes
    changed_projects, unchanged_projects = get_project_changes(projects, changed_files)

    # Select packages
    if all:
        selected_packages = projects
    elif len(projects) == 1:
        # Skip selection if there's only one package
        selected_packages = projects
    else:
        selected_packages = select_packages(changed_projects, unchanged_projects)

    if not selected_packages:
        console.print("❌ No packages selected", style="red")
        sys.exit(1)

    # Get change type and description for each package
    config = load_config()
    change_types = config.get("changeTypes", {})

    package_changes = []

    for project_path, project_name in selected_packages:
        # Try to get the current version
        current_version = "unknown"
        try:
            pyproject_path = project_path / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)
                    current_version = data.get("project", {}).get("version", "unknown")
        except Exception:
            pass

        # Build choices for change type selection (patch first, major last)
        type_choices = []
        type_order = ["patch", "minor", "major"]  # Preferred order

        for ct in type_order:
            if ct in change_types:
                info = change_types[ct]
                emoji = info.get("emoji", "")
                desc = info.get("description", ct)
                type_choices.append({"name": f"{emoji} {ct} - {desc}", "value": ct})

        # Use questionary for change type selection
        change_type = questionary.select(
            f"What kind of change is this for '{project_name}'? "
            f"(current version is {current_version})",
            choices=type_choices,
            instruction="(↑↓ to move, enter to confirm)",
        ).ask()

        if change_type is None:
            console.print("❌ Cancelled", style="red")
            sys.exit(1)

        # Confirm major changes
        if change_type == "major":
            console.print("\n⚠️  Warning: Major version bump!", style="yellow bold")
            console.print(
                "This will trigger a major version bump (e.g., 1.2.3 → 2.0.0)"
            )
            console.print("Major bumps should only be used for breaking changes.")

            if not questionary.confirm(
                "Are you sure this is a breaking change?", default=False
            ).ask():
                console.print("Cancelled. Please select minor or patch instead.")
                continue

        package_changes.append((project_name, change_type))

    if not package_changes:
        console.print("❌ No changes recorded", style="red")
        sys.exit(1)

    # Get description
    console.print("\n📝 Please describe the change:", style="yellow bold")
    console.print("(This will be used in the changelog)", style="dim")

    description = questionary.text("Description:").ask()

    if not description or not description.strip():
        console.print("❌ Description cannot be empty!", style="red")
        sys.exit(1)

    # Create the changeset
    changeset_path = create_changeset(package_changes, description.strip())

    console.print(f"\n✅ Changeset created: {changeset_path}", style="green bold")

    # Show preview
    console.print("\nPreview:", style="cyan")
    with open(changeset_path) as f:
        content = f.read()
        for line in content.split("\n"):
            if line.strip():
                console.print(f"  {line}")

    console.print(
        "\n💡 Tip: Commit this changeset with your changes!", style="bright_black"
    )


@cli.command(name="check-changeset")
@click.option("--skip-ci", is_flag=True, help="Skip check in CI environment")
def check_changeset(skip_ci: bool):
    """Check if a changeset exists for the current branch."""
    # Pass the skip_ci flag through
    import sys

    from changeset.check_changeset import main as check_main
    original_argv = sys.argv
    try:
        sys.argv = ["check-changeset"]
        if skip_ci:
            sys.argv.append("--skip-ci")
        check_main()
    finally:
        sys.argv = original_argv


@cli.command()
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option("--skip-changelog", is_flag=True, help="Skip changelog generation")
def version(dry_run: bool, skip_changelog: bool):
    """Process changesets and bump version."""

    console.print("📦 Processing changesets...\n", style="cyan bold")

    config = load_config()
    changesets = get_changesets()

    if not changesets:
        console.print("No changesets found. Nothing to do!", style="yellow")
        return

    # Group changesets by package
    package_changes = {}
    changeset_files = set()

    for filepath, package, change_type, desc in changesets:
        changeset_files.add(filepath)
        if package not in package_changes:
            package_changes[package] = {"changes": [], "descriptions": []}
        package_changes[package]["changes"].append(change_type)
        package_changes[package]["descriptions"].append(
            {"type": change_type, "description": desc, "changeset": filepath.name}
        )

    # Show changesets
    total_changesets = sum(len(info["changes"]) for info in package_changes.values())
    console.print(
        f"Found {total_changesets} change(s) across {len(package_changes)} package(s):",
        style="green",
    )

    for package, info in package_changes.items():
        console.print(f"\n📦 {package}:")
        for change_type in info["changes"]:
            emoji = config["changeTypes"].get(change_type, {}).get("emoji", "")
            desc = info["descriptions"][0]["description"].split("\n")[0][:60]
            console.print(f"  {emoji} {change_type}: {desc}...")

    if dry_run:
        console.print("\n🔍 Dry run - no changes made", style="yellow")
        return

    # Update versions for each package
    updated_packages = []

    for package, info in package_changes.items():
        console.print(f"\n📝 Updating {package}...", style="cyan")

        # Find pyproject.toml for this package
        try:
            pyproject_path = find_project_pyproject(package)
        except ValueError as e:
            console.print(f"  ❌ {e}", style="red")
            continue

        # Determine version bump
        bump_type = determine_version_bump(info["changes"])
        current_version = get_current_version(pyproject_path)
        new_version = bump_version(current_version, bump_type)

        console.print(
            f"  Version bump: {current_version} → {new_version} ({bump_type})"
        )

        # Update pyproject.toml
        update_pyproject_version(pyproject_path, new_version)
        console.print(f"  ✓ Updated {pyproject_path}")

        updated_packages.append(
            {
                "package": package,
                "version": new_version,
                "previous_version": current_version,
                "entries": info["descriptions"],
            }
        )

    # Pass updated packages to changelog generation
    if not skip_changelog and updated_packages:
        console.print("\n📜 Ready for changelog generation...", style="cyan")

    # Remove processed changesets
    if updated_packages:
        console.print("\n🗑️  Removing processed changesets...", style="cyan")

        for filepath in changeset_files:
            filepath.unlink()
            console.print(f"  ✓ Removed {filepath.name}")

    console.print(
        f"\n✅ Updated {len(updated_packages)} package(s)!", style="green bold"
    )
    if not skip_changelog:
        console.print(
            "📝 Don't forget to run the changelog script next!", style="yellow"
        )


if __name__ == "__main__":
    # If no command is specified, default to 'add'
    if len(sys.argv) == 1:
        sys.argv.insert(1, "add")
    elif len(sys.argv) == 2 and sys.argv[1] == "--all":
        sys.argv[1] = "add"
        sys.argv.append("--all")
    cli()
