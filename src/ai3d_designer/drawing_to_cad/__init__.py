"""Structured engineering-drawing interpretation and deterministic CAD generation.

This package is intentionally conservative: it generates only the supported
v1 feature set and surfaces unsupported or ungrounded geometry for review.
"""
from ai3d_designer.drawing_to_cad.blueprint import Blueprint, apply_defaults, lint

__all__ = ["Blueprint", "apply_defaults", "lint"]
