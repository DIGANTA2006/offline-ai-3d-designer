"""Mesh utilities for image-derived printable heightfields.

The output is a closed 2-manifold triangle mesh with explicit top, bottom, and
side surfaces. A single depth image cannot recover hidden surfaces or certified
mechanical dimensions; this utility creates an approximate relief, not exact CAD.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import trimesh


def build_closed_heightfield(
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    top_z: np.ndarray,
    *,
    bottom_z: float = 0.0,
    vertex_colors: Optional[np.ndarray] = None,
) -> trimesh.Trimesh:
    """Build a watertight solid under a regular XY heightfield.

    x_grid, y_grid and top_z must be equally shaped 2-D arrays of at least 2x2.
    vertex_colors, when present, must be RGB/RGBA for each top-grid vertex.
    """
    x = np.asarray(x_grid, dtype=np.float64)
    y = np.asarray(y_grid, dtype=np.float64)
    z = np.asarray(top_z, dtype=np.float64)
    if x.ndim != 2 or x.shape != y.shape or x.shape != z.shape:
        raise ValueError("x_grid, y_grid, and top_z must be equally shaped 2-D arrays.")
    height, width = x.shape
    if height < 2 or width < 2:
        raise ValueError("A heightfield needs at least two rows and two columns.")
    if not (np.isfinite(x).all() and np.isfinite(y).all() and np.isfinite(z).all()):
        raise ValueError("Heightfield coordinates must contain only finite values.")
    if not np.isfinite(float(bottom_z)):
        raise ValueError("bottom_z must be finite.")
    if np.any(z <= bottom_z):
        raise ValueError("All top_z values must be above bottom_z to form a solid.")

    flat_top = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    flat_bottom = np.column_stack(
        (x.ravel(), y.ravel(), np.full(x.size, float(bottom_z), dtype=np.float64))
    )
    count = height * width
    faces: list[list[int]] = []

    # Top: outward normals point up. Bottom: reverse winding points down.
    for row in range(height - 1):
        for col in range(width - 1):
            v0 = row * width + col
            v1 = v0 + 1
            v2 = v0 + width
            v3 = v2 + 1
            faces.extend((
                [v0, v1, v2],
                [v1, v3, v2],
                [count + v0, count + v2, count + v1],
                [count + v1, count + v2, count + v3],
            ))

    # Trace the grid perimeter counter-clockwise and bridge it to the bottom.
    perimeter = list(range(width))
    perimeter.extend(row * width + width - 1 for row in range(1, height))
    perimeter.extend((height - 1) * width + col for col in range(width - 2, -1, -1))
    perimeter.extend(row * width for row in range(height - 2, 0, -1))
    for index, current in enumerate(perimeter):
        following = perimeter[(index + 1) % len(perimeter)]
        faces.append([current, current + count, following + count])
        faces.append([current, following + count, following])

    mesh = trimesh.Trimesh(
        vertices=np.vstack((flat_top, flat_bottom)),
        faces=np.asarray(faces, dtype=np.int64),
        process=True,
    )
    mesh.fix_normals()

    if vertex_colors is not None:
        colors = np.asarray(vertex_colors)
        if colors.shape[:2] != (height, width) or colors.ndim != 3 or colors.shape[2] not in (3, 4):
            raise ValueError("vertex_colors must be an H x W RGB or RGBA array matching the heightfield.")
        if colors.dtype.kind == "f" and colors.size and colors.max() <= 1.0:
            colors = colors * 255
        colors = np.clip(colors, 0, 255).astype(np.uint8).reshape(count, -1)
        if colors.shape[1] == 3:
            colors = np.column_stack((colors, np.full(count, 255, dtype=np.uint8)))
        # Give the bottom and sidewall vertices the closest available image color.
        mesh.visual.vertex_colors = np.vstack((colors, colors))

    if not mesh.is_watertight:
        raise ValueError("Generated heightfield mesh is not watertight.")
    if not mesh.is_volume or not np.isfinite(float(mesh.volume)) or mesh.volume <= 0:
        raise ValueError("Generated heightfield mesh does not enclose a positive volume.")
    return mesh
