#!/usr/bin/env python3
"""
Changelog generation script - Generates changelog from changesets.
"""

import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click


CHANGESET_DIR = Path(".changeset")
CONFIG_FILE = CHANGESET_DIR / "config.json"


def load_config() -> Dict:
    """Load changeset configuration."""
    if not CONFIG_FILE.exists():
        click.echo(click.style("❌ No changeset config found.", fg="red"))
        sys.exit(1)
    
    with open(CONFIG_FILE) as f:
        return json.load(f)


def parse_changeset(filepath: Path) -> List[Tuple[str, str, str]]:
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
    description = "\n".join(lines[end_idx + 1:]).strip()
    
    # Return with same description for all packages
    return [(pkg, ct, description) for pkg, ct in packages]


def get_changesets() -> Dict[str, List[Dict]]:
    """Get all changeset files and parse them, grouped by package."""
    package_changes = {}
    
    for filepath in CHANGESET_DIR.glob("*.md"):
        if filepath.name == "README.md":
            continue
        
        try:
            parsed = parse_changeset(filepath)
            for package, change_type, description in parsed:
                if package not in package_changes:
                    package_changes[package] = []
                package_changes[package].append({
                    'type': change_type,
                    'description': description,
                    'changeset': filepath.name
                })
        except Exception as e:
            click.echo(click.style(f"⚠️  Error parsing {filepath}: {e}", fg="yellow"))
    
    return package_changes


def find_project_pyproject(package_name: str) -> Optional[Path]:
    """Find the pyproject.toml for a given package."""
    # Search for pyproject.toml files
    for pyproject_path in Path(".").rglob("pyproject.toml"):
        # Skip hidden directories
        if any(part.startswith('.') for part in pyproject_path.parts[:-1]):
            continue
            
        try:
            with open(pyproject_path, 'rb') as f:
                data = tomllib.load(f)
                if data.get('project', {}).get('name') == package_name:
                    return pyproject_path
        except Exception:
            continue
    
    return None


def get_current_version(pyproject_path: Path) -> str:
    """Get current version from pyproject.toml."""
    with open(pyproject_path, 'rb') as f:
        data = tomllib.load(f)
    
    return data.get('project', {}).get('version', '0.0.0')


def get_pr_info() -> Optional[Dict[str, str]]:
    """Get PR information if available."""
    try:
        # Try to get PR info from GitHub context (in Actions)
        pr_number = os.environ.get("GITHUB_PR_NUMBER")
        if pr_number:
            return {
                "number": pr_number,
                "url": f"https://github.com/{os.environ.get('GITHUB_REPOSITORY')}/pull/{pr_number}"
            }
        
        # Try to get from git branch name (if it contains PR number)
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            branch = result.stdout.strip()
            # Look for patterns like "pr-123" or "pull/123"
            match = re.search(r'(?:pr|pull)[/-](\d+)', branch, re.IGNORECASE)
            if match:
                pr_number = match.group(1)
                # Try to get repo info
                repo_result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    capture_output=True,
                    text=True
                )
                if repo_result.returncode == 0:
                    repo_url = repo_result.stdout.strip()
                    # Extract owner/repo from URL
                    match = re.search(r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$', repo_url)
                    if match:
                        repo = match.group(1)
                        return {
                            "number": pr_number,
                            "url": f"https://github.com/{repo}/pull/{pr_number}"
                        }
    except Exception:
        pass
    
    return None


def format_changelog_entry(entry: Dict, config: Dict) -> str:
    """Format a single changelog entry."""
    change_type = entry["type"]
    description = entry["description"]
    
    # Get emoji if configured
    emoji = config["changeTypes"].get(change_type, {}).get("emoji", "")
    
    # Format entry
    if emoji:
        line = f"- {emoji} **{change_type}**: {description}"
    else:
        line = f"- **{change_type}**: {description}"
    
    return line


def find_package_changelog(package_name: str, pyproject_path: Path) -> Path:
    """Find the CHANGELOG.md for a given package."""
    # Look for CHANGELOG.md in the same directory or parent
    for candidate in [
        pyproject_path.parent / "CHANGELOG.md",
        pyproject_path.parent.parent / "CHANGELOG.md",
    ]:
        if candidate.exists():
            return candidate
    
    # If not found, create it in the package directory
    return pyproject_path.parent / "CHANGELOG.md"


def generate_package_section(package: str, version: str, entries: List[Dict], config: Dict, date: str) -> str:
    """Generate changelog section for a package version."""
    # Start with version header
    section = f"## [{version}] - {date}\n\n"
    
    # Get PR info if available
    pr_info = get_pr_info()
    if pr_info:
        section += f"[View Pull Request]({pr_info['url']})\n\n"
    
    # Group entries by type
    grouped = {}
    for entry in entries:
        change_type = entry["type"]
        if change_type not in grouped:
            grouped[change_type] = []
        grouped[change_type].append(entry)
    
    # Add entries by type (in order: major, minor, patch)
    type_order = ["major", "minor", "patch"]
    
    for change_type in type_order:
        if change_type in grouped:
            type_info = config["changeTypes"].get(change_type, {})
            type_name = type_info.get("description", change_type.capitalize())
            
            section += f"### {type_name}\n\n"
            
            for entry in grouped[change_type]:
                section += format_changelog_entry(entry, config) + "\n"
            
            section += "\n"
    
    return section.strip() + "\n"


def update_changelog(changelog_path: Path, new_section: str, package: str, version: str):
    """Update the changelog file with new section."""
    if changelog_path.exists():
        with open(changelog_path) as f:
            current_content = f.read()
    else:
        # Create new changelog with header
        current_content = f"""# Changelog

All notable changes to {package} will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"""
    
    # Check if version already exists
    if f"## [{version}]" in current_content:
        click.echo(click.style(f"⚠️  Version {version} already exists in {changelog_path}", fg="yellow"))
        return False
    
    # Find where to insert (after the header, before first version)
    lines = current_content.split("\n")
    insert_index = None
    
    # Look for first version entry or end of header
    for i, line in enumerate(lines):
        if line.startswith("## ["):
            insert_index = i
            break
    
    if insert_index is None:
        # No versions yet, add at the end
        new_content = current_content.rstrip() + "\n\n" + new_section + "\n"
    else:
        # Insert before first version
        lines.insert(insert_index, new_section)
        lines.insert(insert_index + 1, "")  # Add blank line
        new_content = "\n".join(lines)
    
    # Write updated changelog
    with open(changelog_path, "w") as f:
        f.write(new_content)
    
    return True


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would be added without making changes")
@click.option("--date", help="Override the date (YYYY-MM-DD format)")
def main(dry_run: bool, date: Optional[str]):
    """Generate changelog from changesets."""
    
    click.echo(click.style("📜 Generating changelog...\n", fg="cyan", bold=True))
    
    config = load_config()
    
    # Get all changesets grouped by package
    package_changes = get_changesets()
    
    if not package_changes:
        click.echo(click.style("No changesets found. Nothing to do!", fg="yellow"))
        return
    
    # Use provided date or current date
    changelog_date = date or datetime.now().strftime("%Y-%m-%d")
    
    # Process each package
    for package, entries in package_changes.items():
        # Find the package's pyproject.toml
        pyproject_path = find_project_pyproject(package)
        if not pyproject_path:
            click.echo(click.style(f"⚠️  Could not find pyproject.toml for {package}", fg="yellow"))
            continue
        
        # Get current version from pyproject.toml
        version = get_current_version(pyproject_path)
        
        click.echo(click.style(f"📦 Processing {package} v{version}...", fg="green"))
        
        # Find changelog for this package
        changelog_path = find_package_changelog(package, pyproject_path)
        
        # Generate changelog section
        new_section = generate_package_section(package, version, entries, config, changelog_date)
        
        if dry_run:
            click.echo(click.style(f"\nChangelog for {changelog_path}:", fg="cyan"))
            click.echo("-" * 60)
            click.echo(new_section)
            click.echo("-" * 60)
        else:
            # Update changelog file
            if update_changelog(changelog_path, new_section, package, version):
                click.echo(click.style(f"  ✅ Updated {changelog_path}", fg="green"))
            else:
                click.echo(click.style(f"  ❌ Failed to update {changelog_path}", fg="red"))
    
    if not dry_run:
        click.echo(click.style("\n✅ Changelog generation complete!", fg="green", bold=True))
        
        # Show next steps
        click.echo(click.style("\n📝 Next steps:", fg="yellow"))
        click.echo("  1. Review the updated CHANGELOG.md files")
        click.echo("  2. Commit all changes (versions, changelogs, and removed changesets)")
        click.echo("  3. Push to update the PR")


if __name__ == "__main__":
    main()