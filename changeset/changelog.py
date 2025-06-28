#!/usr/bin/env python3
"""
Changelog generation integrated with version bumping.
Generates changelogs with PR metadata and creates PR descriptions.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import click

# Import from changeset.py to reuse logic
from changeset.changeset import (
    bump_version,
    determine_version_bump,
    find_project_pyproject,
    get_current_version,
)
from changeset.changeset import (
    get_changesets as get_changesets_from_changeset,
)

CHANGESET_DIR = Path(".changeset")
CONFIG_FILE = CHANGESET_DIR / "config.json"


def load_config() -> dict:
    """Load changeset configuration."""
    if not CONFIG_FILE.exists():
        click.echo(click.style("❌ No changeset config found.", fg="red"))
        raise SystemExit(1)

    with open(CONFIG_FILE) as f:
        return json.load(f)


def get_git_info() -> dict:
    """Get git information for the current commit/PR."""
    info = {}

    # Get the current commit hash
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        info["commit"] = result.stdout.strip()[:7]  # Short hash
    except Exception:
        info["commit"] = None

    # Get GitHub repo info
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        remote_url = result.stdout.strip()
        # Extract owner/repo from URL
        match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
        if match:
            info["owner"] = match.group(1)
            info["repo"] = match.group(2)
            info["repo_url"] = f"https://github.com/{info['owner']}/{info['repo']}"
    except Exception:
        pass

    return info


def get_pr_metadata() -> dict:
    """Get PR metadata from environment or git."""
    metadata = {
        "pr_number": os.environ.get("PR_NUMBER"),
        "pr_author": os.environ.get("PR_AUTHOR"),
        "commit_hash": os.environ.get("COMMIT_SHA", ""),
    }

    # Always get git info for repo URL
    git_info = get_git_info()

    # Use git commit if not in environment
    if not metadata["commit_hash"]:
        metadata["commit_hash"] = git_info.get("commit", "")

    # Always use repo URL from git
    metadata["repo_url"] = git_info.get("repo_url", "")

    return metadata


def format_changelog_entry(entry: dict, config: dict, pr_metadata: dict) -> str:
    """Format a single changelog entry with PR and commit info."""
    description = entry["description"]
    pr_number = pr_metadata.get("pr_number")
    pr_author = pr_metadata.get("pr_author")
    commit_hash = pr_metadata.get("commit_hash", "")[:7]
    repo_url = pr_metadata.get("repo_url", "")

    # Build the entry
    parts = []

    # Add PR link if available
    if pr_number and repo_url:
        parts.append(f"[#{pr_number}]({repo_url}/pull/{pr_number})")

    # Add commit link if available
    if commit_hash and repo_url:
        parts.append(f"[`{commit_hash}`]({repo_url}/commit/{commit_hash})")

    # Add author thanks if available
    if pr_author:
        parts.append(f"Thanks @{pr_author}!")

    # Add description
    parts.append(f"- {description}")

    return " ".join(parts)


def generate_changelog_section(
    package: str, new_version: str, entries: list[dict], config: dict, pr_metadata: dict
) -> str:
    """Generate changelog section for a package version."""
    lines = []

    # Add version header
    lines.append(f"## {new_version}")
    lines.append("")

    # Group entries by change type
    grouped = {}
    for entry in entries:
        change_type = entry["type"]
        if change_type not in grouped:
            grouped[change_type] = []
        grouped[change_type].append(entry)

    # Add sections for each change type
    for change_type in ["major", "minor", "patch"]:
        if change_type not in grouped:
            continue

        # Get the change type label
        type_label = {
            "major": "Major Changes",
            "minor": "Minor Changes",
            "patch": "Patch Changes",
        }.get(change_type, f"{change_type.capitalize()} Changes")

        lines.append(f"### {type_label}")
        lines.append("")

        # Add each entry
        for entry in grouped[change_type]:
            lines.append(format_changelog_entry(entry, config, pr_metadata))

        lines.append("")

    return "\n".join(lines).strip()


def update_or_create_changelog(
    changelog_path: Path, package_name: str, new_section: str
) -> bool:
    """Update or create a changelog file."""
    if changelog_path.exists():
        content = changelog_path.read_text()
    else:
        # Create new changelog with package name header
        content = f"# {package_name}\n\n"

    # Insert the new section after the package name header
    lines = content.split("\n")
    insert_index = None

    # Find where to insert (after header, before first version)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            # Found header, insert after next blank line
            for j in range(i + 1, len(lines)):
                if not lines[j].strip():
                    insert_index = j + 1
                    break
            if insert_index is None:
                insert_index = i + 1
            break

    if insert_index is None:
        # No header found, just prepend
        new_content = new_section + "\n\n" + content
    else:
        # Insert at the found position
        lines.insert(insert_index, new_section)
        lines.insert(insert_index + 1, "")
        new_content = "\n".join(lines)

    # Write the updated content
    changelog_path.write_text(new_content)
    return True


def generate_pr_description(package_updates: list[dict]) -> str:
    """Generate a combined PR description for all package updates."""
    lines = ["# Releases", ""]

    for update in package_updates:
        package = update["package"]
        version = update["version"]
        changelog_content = update["changelog_content"]

        # Add package header
        lines.append(f"## {package}@{version}")
        lines.append("")

        # Add the changelog content (without the package header)
        # Skip the first line if it's a version header
        changelog_lines = changelog_content.split("\n")
        start_index = 0
        if changelog_lines and changelog_lines[0].startswith("## "):
            start_index = 1

        lines.extend(changelog_lines[start_index:])
        lines.append("")

    return "\n".join(lines)


def process_changesets_for_changelog() -> tuple[list[dict], str]:
    """
    Process changesets to generate changelog entries and PR description.
    Returns (package_updates, pr_description).
    """
    config = load_config()
    pr_metadata = get_pr_metadata()

    # Get all changesets
    changesets = get_changesets_from_changeset()
    if not changesets:
        return [], ""

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

    # Process each package
    package_updates = []

    for package, info in package_changes.items():
        # Find pyproject.toml
        try:
            pyproject_path = find_project_pyproject(package)
        except ValueError as e:
            click.echo(click.style(f"⚠️  {e}", fg="yellow"))
            continue

        # Determine new version
        bump_type = determine_version_bump(info["changes"])
        current_version = get_current_version(pyproject_path)
        new_version = bump_version(current_version, bump_type)

        # Generate changelog content
        changelog_content = generate_changelog_section(
            package, new_version, info["descriptions"], config, pr_metadata
        )

        # Find changelog path (same directory as pyproject.toml)
        changelog_path = pyproject_path.parent / "CHANGELOG.md"

        package_updates.append(
            {
                "package": package,
                "version": new_version,
                "current_version": current_version,
                "changelog_path": changelog_path,
                "changelog_content": changelog_content,
                "pyproject_path": pyproject_path,
            }
        )

    # Generate PR description
    pr_description = generate_pr_description(package_updates)

    return package_updates, pr_description


@click.command()
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option("--output-pr-description", help="File to write PR description to")
def main(dry_run: bool, output_pr_description: str):
    """Generate changelogs from changesets with version bumping."""

    click.echo(click.style("📜 Generating changelogs...\n", fg="cyan", bold=True))

    # Process changesets
    package_updates, pr_description = process_changesets_for_changelog()

    if not package_updates:
        click.echo(click.style("No changesets found. Nothing to do!", fg="yellow"))
        return

    # Show what will be done
    click.echo(
        click.style(f"Found updates for {len(package_updates)} package(s):", fg="green")
    )
    for update in package_updates:
        current = update["current_version"]
        new = update["version"]
        click.echo(f"  📦 {update['package']}: {current} → {new}")

    if dry_run:
        click.echo(
            click.style("\n🔍 Dry run mode - no changes will be made", fg="yellow")
        )
        click.echo("\n" + "=" * 60)
        click.echo(click.style("PR Description:", fg="cyan"))
        click.echo("=" * 60)
        click.echo(pr_description)
        click.echo("=" * 60)

        for update in package_updates:
            click.echo(
                click.style(f"\nChangelog for {update['changelog_path']}:", fg="cyan")
            )
            click.echo("-" * 60)
            click.echo(update["changelog_content"])
            click.echo("-" * 60)
        return

    # Update changelog files
    for update in package_updates:
        success = update_or_create_changelog(
            update["changelog_path"], update["package"], update["changelog_content"]
        )

        if success:
            click.echo(
                click.style(f"✅ Updated {update['changelog_path']}", fg="green")
            )
        else:
            click.echo(
                click.style(f"❌ Failed to update {update['changelog_path']}", fg="red")
            )

    # Write PR description if requested
    if output_pr_description:
        Path(output_pr_description).write_text(pr_description)
        click.echo(
            click.style(
                f"✅ Wrote PR description to {output_pr_description}", fg="green"
            )
        )

    click.echo(
        click.style("\n✅ Changelog generation complete!", fg="green", bold=True)
    )


if __name__ == "__main__":
    main()
