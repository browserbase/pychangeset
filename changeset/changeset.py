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
    """Interactive package selection with group selection support."""

    # Check if we're in an interactive terminal
    try:
        import os
        if not os.isatty(0):
            # Fallback to simple questionary if not in terminal
            return _select_packages_simple(changed_projects, unchanged_projects)
    except:
        pass

    try:
        # Try the advanced selector first
        return _select_packages_advanced(changed_projects, unchanged_projects)
    except:
        # Fallback to simple selector if advanced fails
        return _select_packages_simple(changed_projects, unchanged_projects)


def _select_packages_simple(changed_projects: List[Tuple[Path, str]], unchanged_projects: List[Tuple[Path, str]]) -> List[Tuple[Path, str]]:
    """Simple package selection using questionary with separators."""

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
        "🐍 Which packages would you like to include?",
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


def _select_packages_advanced(changed_projects: List[Tuple[Path, str]], unchanged_projects: List[Tuple[Path, str]]) -> List[Tuple[Path, str]]:
    """Advanced package selection with group selection support using prompt_toolkit."""

    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    # Build the list of items
    items = []
    package_map = {}

    # Add changed packages group
    if changed_projects:
        items.append({
            'type': 'group',
            'name': 'changed packages',
            'selected': True,
            'group': 'changed'
        })

        for path, name in changed_projects:
            items.append({
                'type': 'package',
                'name': name,
                'selected': True,
                'group': 'changed',
                'path': path
            })
            package_map[len(items) - 1] = (path, name)

    # Add unchanged packages group
    if unchanged_projects:
        items.append({
            'type': 'group',
            'name': 'unchanged packages',
            'selected': False,
            'group': 'unchanged'
        })

        for path, name in unchanged_projects:
            items.append({
                'type': 'package',
                'name': name,
                'selected': False,
                'group': 'unchanged',
                'path': path
            })
            package_map[len(items) - 1] = (path, name)

    if not items:
        console.print("No packages found in the repository.", style="yellow")
        return []

    # State management
    current_index = 0
    confirmed = False
    cancelled = False

    def get_formatted_text():
        """Generate the display text."""
        lines = []
        lines.append(('class:title', '🐍 Which packages would you like to include?\n\n'))

        for i, item in enumerate(items):
            # Cursor indicator
            cursor = '> ' if i == current_index else '  '

            # Selection indicator
            symbol = '◉' if item['selected'] else '◯'

            # Format based on type
            if item['type'] == 'group':
                line = f"{cursor}{symbol} {item['name']}"
                style = 'class:group.selected' if i == current_index else 'class:group'
            else:
                line = f"{cursor}  {symbol} {item['name']}"
                style = 'class:package.selected' if i == current_index else 'class:package'

            lines.append((style, line + '\n'))

        lines.append(('class:instruction', '\n(Use ↑↓ to move, space to select, enter to confirm)'))
        return lines

    def toggle_current():
        """Toggle the current selection."""
        nonlocal items
        current_item = items[current_index]

        if current_item['type'] == 'group':
            # Toggle group and all its packages
            new_state = not current_item['selected']
            current_item['selected'] = new_state

            # Update all packages in this group
            group_name = current_item['group']
            for item in items:
                if item['type'] == 'package' and item['group'] == group_name:
                    item['selected'] = new_state
        else:
            # Toggle individual package
            current_item['selected'] = not current_item['selected']

            # Update group state
            group_name = current_item['group']
            group_items = [item for item in items if item['type'] == 'package' and item['group'] == group_name]
            all_selected = all(item['selected'] for item in group_items)

            # Find and update the group header
            for item in items:
                if item['type'] == 'group' and item['group'] == group_name:
                    item['selected'] = all_selected
                    break

    # Key bindings
    kb = KeyBindings()

    @kb.add('up')
    @kb.add('k')
    def move_up(event):
        nonlocal current_index
        if current_index > 0:
            current_index -= 1

    @kb.add('down')
    @kb.add('j')
    def move_down(event):
        nonlocal current_index
        if current_index < len(items) - 1:
            current_index += 1

    @kb.add('space')
    def toggle_selection(event):
        toggle_current()

    @kb.add('enter')
    def confirm(event):
        nonlocal confirmed
        confirmed = True
        event.app.exit()

    @kb.add('c-c')
    @kb.add('c-d')
    @kb.add('escape')
    def cancel(event):
        nonlocal cancelled
        cancelled = True
        event.app.exit()

    # Style
    style = Style.from_dict({
        'title': 'bold cyan',
        'group': '',
        'group.selected': 'reverse',
        'package': '',
        'package.selected': 'reverse',
        'instruction': '#666666',
    })

    # Create the application
    layout = Layout(
        Window(
            content=FormattedTextControl(get_formatted_text),
            height=len(items) + 5,  # Account for title and instruction
        )
    )

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        mouse_support=False,
        full_screen=False,
    )

    # Run the application
    app.run()

    if cancelled:
        console.print("❌ Cancelled", style="red")
        return []

    # Extract selected packages
    result = []
    for i, item in enumerate(items):
        if item['type'] == 'package' and item['selected'] and i in package_map:
            result.append(package_map[i])

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
            "What kind of change is this?",
            choices=type_choices
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
