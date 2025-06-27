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
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

console = Console()

CHANGESET_DIR = Path(".changeset")
CONFIG_FILE = CHANGESET_DIR / "config.json"


def init_changesets(base_branch: str = "main", interactive: bool = True):
    """Initialize changesets configuration."""
    # Create .changeset directory
    CHANGESET_DIR.mkdir(exist_ok=True)

    # Create config.json with simplified config
    config = {
        "baseBranch": base_branch,
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

    # TODO: make this less complicated, just detect main or master
    # Ask for base branch if interactive
    if interactive:
        try:
            # Try to detect current git branch
            import git
            repo = git.Repo(".")
            current_branch = repo.active_branch.name
            default_branch = "main" if current_branch != "main" else current_branch
        except:
            default_branch = "main"

        base_branch = Prompt.ask("What is your base branch?", default=default_branch)
        config["baseBranch"] = base_branch

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
    """Get set of changed files compared to base branch."""
    config = load_config()
    base_branch = config.get("baseBranch", "main")
    
    try:
        repo = git.Repo(".")
        
        # Get current branch
        try:
            current_branch = repo.active_branch.name
        except TypeError:
            # Detached HEAD
            return set()
        
        # Get diff between current branch and base
        diff_output = repo.git.diff(f"{base_branch}...HEAD", "--name-only")
        
        if not diff_output:
            return set()
            
        return set(diff_output.strip().split("\n"))
    except Exception:
        return set()


def get_project_changes(projects: List[Tuple[Path, str]], changed_files: Set[str]) -> Tuple[List[Tuple[Path, str]], List[Tuple[Path, str]]]:
    """Determine which projects have changes."""
    changed_projects = []
    unchanged_projects = []
    
    repo_root = Path(".").resolve()
    
    for project_path, project_name in projects:
        project_rel_path = project_path.relative_to(repo_root)
        has_changes = False
        
        # Check if any changed file is within this project
        for changed_file in changed_files:
            try:
                # Check if the changed file is under the project directory
                Path(changed_file).relative_to(project_rel_path)
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
    """Interactive package selection UI."""
    console.print("\n🦋 Which packages would you like to include?", style="cyan bold")
    
    selected = []
    
    # Show changed packages
    if changed_projects:
        console.print("\n◉ [bold green]changed packages[/bold green]")
        for project_path, project_name in changed_projects:
            if Confirm.ask(f"  Include {project_name}?", default=True):
                selected.append((project_path, project_name))
    
    # Show unchanged packages
    if unchanged_projects:
        console.print("\n◯ [dim]unchanged packages[/dim]")
        for project_path, project_name in unchanged_projects:
            if Confirm.ask(f"  Include {project_name}?", default=False):
                selected.append((project_path, project_name))
    
    return selected


def generate_changeset_name() -> str:
    """Generate a unique changeset filename."""
    import coolname
    
    # Generate names until we find one that doesn't exist
    for _ in range(100):  # Max 100 attempts
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


@click.command()
@click.option("--all", is_flag=True, help="Include all packages without prompting")
def main(all: bool):
    """Create a new changeset for tracking changes."""
    
    console.print("🦋 Creating a new changeset...\n", style="cyan bold")
    
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
        console.print(f"\n📦 [bold]{project_name}[/bold]")
        
        # Select change type
        console.print("What kind of change is this?", style="yellow bold")
        
        choices = []
        for ct, info in change_types.items():
            emoji = info.get("emoji", "")
            desc = info.get("description", ct)
            choices.append((ct, f"{emoji} {ct} - {desc}"))
        
        for i, (_, display) in enumerate(choices, 1):
            console.print(f"  {i}) {display}")
        
        choice_num = Prompt.ask("\nSelect change type", choices=[str(i) for i in range(1, len(choices) + 1)])
        change_type = choices[int(choice_num) - 1][0]
        
        # Confirm major changes
        if change_type == "major":
            console.print("\n⚠️  Warning: Major version bump!", style="yellow bold")
            console.print("This will trigger a major version bump (e.g., 1.2.3 → 2.0.0)")
            console.print("Major bumps should only be used for breaking changes.")
            
            if not Confirm.ask("\nAre you sure this is a breaking change?", default=False):
                console.print("Cancelled. Please select minor or patch instead.")
                continue
        
        package_changes.append((project_name, change_type))
    
    if not package_changes:
        console.print("❌ No changes recorded", style="red")
        sys.exit(1)
    
    # Get description
    console.print("\n📝 Please describe the change:", style="yellow bold")
    console.print("(This will be used in the changelog)", style="dim")
    
    description = Prompt.ask("Description")
    
    if not description.strip():
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
    main()