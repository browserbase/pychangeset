#!/usr/bin/env python3
"""Main entry point for changeset command."""

import sys

from changeset.changeset import cli


def main():
    # If no command is specified, default to 'add'
    args = sys.argv[:]
    if len(args) == 1:
        args.append("add")
    elif len(args) == 2 and args[1] == "--all":
        args[1] = "add"
        args.append("--all")

    sys.argv = args
    cli()


if __name__ == "__main__":
    main()
