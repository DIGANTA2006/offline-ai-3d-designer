"""Compatibility imports for the canonical core geometry engine.

Keep one implementation so the desktop GUI, CLI, API, and package-level imports
cannot drift into different CAD behavior.
"""
from ..core.geometry.engine import GeometryEngine, create_part_from_spec

__all__ = ["GeometryEngine", "create_part_from_spec"]
