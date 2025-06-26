#!/usr/bin/env python3
"""
Version management script - Processes changesets and bumps version.
"""

import json
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Dict, List, Tuple

import click
import toml


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


def get_changesets() -> List[Tuple[Path, str, str, str]]:
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
            click.echo(click.style(f"⚠️  Error parsing {filepath}: {e}", fg="yellow"))
    
    return changesets


def determine_version_bump(changes: List[str]) -> str:
    """Determine the version bump type based on change types."""
    has_major = any(ct == "major" for ct in changes)
    has_minor = any(ct == "minor" for ct in changes)
    
    if has_major:
        return "major"
    elif has_minor:
        return "minor"
    else:
        return "patch"


def parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse semantic version string."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


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
    
    raise ValueError(f"Could not find pyproject.toml for package: {package_name}")


def update_pyproject_version(filepath: Path, new_version: str):
    """Update version in pyproject.toml using toml library."""
    with open(filepath, 'rb') as f:
        data = tomllib.load(f)
    
    # Update version
    if 'project' in data:
        data['project']['version'] = new_version
    else:
        raise ValueError(f"No [project] section in {filepath}")
    
    # Write back using toml library
    with open(filepath, 'w') as f:
        toml.dump(data, f)


def get_current_version(pyproject_path: Path) -> str:
    """Get current version from pyproject.toml."""
    with open(pyproject_path, 'rb') as f:
        data = tomllib.load(f)
    
    return data.get('project', {}).get('version', '0.0.0')


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.option("--skip-changelog", is_flag=True, help="Skip changelog generation")
def main(dry_run: bool, skip_changelog: bool):
    """Process changesets and bump version."""
    
    click.echo(click.style("📦 Processing changesets...\n", fg="cyan", bold=True))
    
    config = load_config()
    changesets = get_changesets()
    
    if not changesets:
        click.echo(click.style("No changesets found. Nothing to do!", fg="yellow"))
        return
    
    # Group changesets by package
    package_changes = {}
    changeset_files = set()
    
    for filepath, package, change_type, desc in changesets:
        changeset_files.add(filepath)
        if package not in package_changes:
            package_changes[package] = {
                'changes': [],
                'descriptions': []
            }
        package_changes[package]['changes'].append(change_type)
        package_changes[package]['descriptions'].append({
            'type': change_type,
            'description': desc,
            'changeset': filepath.name
        })
    
    # Show changesets
    total_changesets = sum(len(info['changes']) for info in package_changes.values())
    click.echo(click.style(f"Found {total_changesets} change(s) across {len(package_changes)} package(s):", fg="green"))
    
    for package, info in package_changes.items():
        click.echo(f"\n📦 {package}:")
        for change_type in info['changes']:
            emoji = config["changeTypes"].get(change_type, {}).get("emoji", "")
            desc = info['descriptions'][0]['description'].split('\n')[0][:60]
            click.echo(f"  {emoji} {change_type}: {desc}...")
    
    if dry_run:
        click.echo(click.style("\n🔍 Dry run - no changes made", fg="yellow"))
        return
    
    # Update versions for each package
    updated_packages = []
    
    for package, info in package_changes.items():
        click.echo(click.style(f"\n📝 Updating {package}...", fg="cyan"))
        
        # Find pyproject.toml for this package
        try:
            pyproject_path = find_project_pyproject(package)
        except ValueError as e:
            click.echo(click.style(f"  ❌ {e}", fg="red"))
            continue
        
        # Determine version bump
        bump_type = determine_version_bump(info['changes'])
        current_version = get_current_version(pyproject_path)
        new_version = bump_version(current_version, bump_type)
        
        click.echo(f"  Version bump: {current_version} → {new_version} ({bump_type})")
        
        # Update pyproject.toml
        update_pyproject_version(pyproject_path, new_version)
        click.echo(f"  ✓ Updated {pyproject_path}")
        
        updated_packages.append({
            'package': package,
            'version': new_version,
            'previous_version': current_version,
            'entries': info['descriptions']
        })
    
    # Pass updated packages to changelog generation
    if not skip_changelog and updated_packages:
        click.echo(click.style("\n📜 Ready for changelog generation...", fg="cyan"))
    
    # Archive processed changesets
    if updated_packages:
        click.echo(click.style("\n🗂️  Archiving changesets...", fg="cyan"))
        
        # Create a single archive directory for this run
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = CHANGESET_DIR / "archive" / timestamp
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        for filepath in changeset_files:
            shutil.move(str(filepath), str(archive_dir / filepath.name))
            click.echo(f"  ✓ Archived {filepath.name}")
    
    click.echo(click.style(f"\n✅ Updated {len(updated_packages)} package(s)!", fg="green", bold=True))
    if not skip_changelog:
        click.echo(click.style("📝 Don't forget to run the changelog script next!", fg="yellow"))


if __name__ == "__main__":
    main()