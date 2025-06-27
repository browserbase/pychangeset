#!/usr/bin/env python3
"""
Version management script - Thin wrapper for changeset version command.
"""

import os
import subprocess
import sys


def main():
    """Run changeset version command."""
    # First try to run changeset.py directly (works in CI/CD)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    changeset_path = os.path.join(script_dir, "changeset.py")

    if os.path.exists(changeset_path):
        cmd = [sys.executable, changeset_path, "version", *sys.argv[1:]]
        sys.exit(subprocess.call(cmd))
    else:
        # Fallback to module execution
        cmd = [sys.executable, "-m", "changeset", "version", *sys.argv[1:]]
        sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
