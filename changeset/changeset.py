#!/usr/bin/env python3
"""
Changeset CLI - Interactive tool for creating changeset files.
Similar to JavaScript changesets but for Python projects.
"""

import json
import os
import random
import string
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import click
import git
import questionary
from questionary import Choice
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

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
            "major": {
                "description": "Breaking changes",
                "emoji": "💥"
            },
            "minor": {
                "description": "New features",
                "emoji": "✨"
            },
            "patch": {
                "description": "Bug fixes and improvements",
                "emoji": "🐛"
            }
        }
    }

    # Detect base branch automatically
    try:
        repo = git.Repo(".")
        remote_refs = [ref.name for ref in repo.remote().refs]
        
        has_main = any('main' in ref for ref in remote_refs)
        has_master = any('master' in ref for ref in remote_refs)
        
        if has_main and has_master:
            console.print("❌ Error: Both 'main' and 'master' branches exist in the repository.", style="red")
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
                console.print("❌ Error: Both 'main' and 'master' branches exist in the repository.", style="red")
                console.print("Please remove one of them to avoid ambiguity.", style="red")
                sys.exit(1)
            elif "main" in local_branches:
                base_branch = "main"
            elif "master" in local_branches:
                base_branch = "master"
            else:
                # Default to main if no branches exist yet
                base_branch = "main"
    except:
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

This directory contains changeset files that track changes to packages in this repository.

## Creating a changeset

Run `changeset` or `changeset add` to create a new changeset.

## More info

See https://github.com/browserbase/pychangeset for more information.
"""

    with open(readme_path, "w") as f:
        f.write(readme_content)

    # Add .gitkeep to preserve empty directory
    gitkeep_path = CHANGESET_DIR / ".gitkeep"
    gitkeep_path.touch()


def load_config() -> Dict:
    """Load changeset configuration."""
    if not CONFIG_FILE.exists():
        # Auto-initialize if config doesn't exist
        # TODO: actual project root detection
        console.print("🚀 Initializing changesets...", style="cyan bold")
        init_changesets()
        console.print("✨ Changesets initialized successfully!\n", style="green bold")

    with open(CONFIG_FILE) as f:
        return json.load(f)


def find_python_projects(root_path: Path = Path(".")) -> List[Tuple[Path, str]]:
    """Find all Python projects (directories with pyproject.toml) in the repository."""
    projects = []

    # Find all pyproject.toml files
    for pyproject_path in root_path.rglob("pyproject.toml"):
        # Skip hidden directories and common build/env directories
        parts = pyproject_path.parts
        if any(part.startswith('.') or part in ['venv', 'env', 'build', 'dist', '__pycache__'] for part in parts):
            continue

        # Read the project name
        try:
            with open(pyproject_path, 'rb') as f:
                data = tomllib.load(f)
                project_name = data.get('project', {}).get('name', pyproject_path.parent.name)
                projects.append((pyproject_path.parent, project_name))
        except Exception:
            # If we can't read it, use the directory name
            projects.append((pyproject_path.parent, pyproject_path.parent.name))

    return sorted(projects, key=lambda x: x[1])


def get_changed_files() -> Set[str]:
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


def get_project_changes(projects: List[Tuple[Path, str]], changed_files: Set[str]) -> Tuple[List[Tuple[Path, str]], List[Tuple[Path, str]]]:
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


def select_packages(changed_projects: List[Tuple[Path, str]], unchanged_projects: List[Tuple[Path, str]]) -> List[Tuple[Path, str]]:
    """Interactive package selection using questionary."""

    # Check if we're in a non-interactive environment
    import os
    if not os.isatty(0):
        # In CI/CD or non-interactive mode, just return changed packages
        console.print("🐍 Non-interactive mode detected. Selecting changed packages...", style="yellow")
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
        instruction="(Use ↑↓ to move, space to select, enter to confirm)"
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
    for _ in range(10): # 10 attempts
        name = coolname.generate_slug(3)
        if not (CHANGESET_DIR / f"{name}.md").exists():
            return name

    # Fallback to timestamp + random string after 100 attempts
    import uuid
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = str(uuid.uuid4()).split('-')[0][:6]
    return f"changeset-{timestamp}-{random_suffix}"


def create_changeset(packages: List[Tuple[str, str]], description: str) -> str:
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


@click.group()
def cli():
    """Changeset management for Python projects."""
    pass




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
        console.print("❌ No Python projects found (no pyproject.toml files)", style="red")
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
                with open(pyproject_path, 'rb') as f:
                    data = tomllib.load(f)
                    current_version = data.get('project', {}).get('version', 'unknown')
        except:
            pass

        # Build choices for change type selection (patch first, major last)
        type_choices = []
        type_order = ["patch", "minor", "major"]  # Preferred order

        for ct in type_order:
            if ct in change_types:
                info = change_types[ct]
                emoji = info.get("emoji", "")
                desc = info.get("description", ct)
                type_choices.append({
                    "name": f"{emoji} {ct} - {desc}",
                    "value": ct
                })

        # Use questionary for change type selection
        change_type = questionary.select(
            f"What kind of change is this for '{project_name}'? (current version is {current_version})",
            choices=type_choices,
            instruction="(↑↓ to move, enter to confirm)"
        ).ask()

        if change_type is None:
            console.print("❌ Cancelled", style="red")
            sys.exit(1)

        # Confirm major changes
        if change_type == "major":
            console.print("\n⚠️  Warning: Major version bump!", style="yellow bold")
            console.print("This will trigger a major version bump (e.g., 1.2.3 → 2.0.0)")
            console.print("Major bumps should only be used for breaking changes.")

            if not questionary.confirm("Are you sure this is a breaking change?", default=False).ask():
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

    console.print("\n💡 Tip: Commit this changeset with your changes!", style="bright_black")




if __name__ == "__main__":
    # If no command is specified, default to 'add'
    if len(sys.argv) == 1:
        sys.argv.insert(1, "add")
    elif len(sys.argv) == 2 and sys.argv[1] == "--all":
        sys.argv[1] = "add"
        sys.argv.append("--all")
    cli()
