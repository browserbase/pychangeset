"""changeset - Version management and changelog generation for Python projects.
Inspired by changesets."""

from importlib.metadata import version as get_version

__version__ = get_version("changeset")
