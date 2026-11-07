"""Docker-build smoke test for a real CuraEngine STL-to-G-code run.

This is intentionally an integration test: it starts the installed CuraEngine
binary with the repository's bundled printer/extruder definitions. It does not
mock subprocesses and it rejects output that fails the project's G-code checks.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from ai3d_designer.slicing.slicer import SliceSettings, Slicer, get_slicing_capability


def _write_cube_stl(path: Path, size: float = 10.0) -> None:
    vertices = {
        "000": (0.0, 0.0, 0.0),
        "100": (size, 0.0, 0.0),
        "110": (size, size, 0.0),
        "010": (0.0, size, 0.0),
        "001": (0.0, 0.0, size),
        "101": (size, 0.0, size),
        "111": (size, size, size),
        "011": (0.0, size, size),
    }
    triangles = [
        ("000", "110", "100"), ("000", "010", "110"),
        ("001", "101", "111"), ("001", "111", "011"),
        ("000", "100", "101"), ("000", "101", "001"),
        ("010", "011", "111"), ("010", "111", "110"),
        ("000", "001", "011"), ("000", "011", "010"),
        ("100", "110", "111"), ("100", "111", "101"),
    ]

    lines = ["solid deterministic_cube"]
    for a, b, c in triangles:
        p1, p2, p3 = vertices[a], vertices[b], vertices[c]
        u = tuple(p2[i] - p1[i] for i in range(3))
        v = tuple(p3[i] - p1[i] for i in range(3))
        normal = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        length = math.sqrt(sum(component * component for component in normal))
        normal = tuple(component / length for component in normal)
        lines.append("  facet normal " + " ".join(f"{value:.6f}" for value in normal))
        lines.append("    outer loop")
        for point in (p1, p2, p3):
            lines.append("      vertex " + " ".join(f"{value:.6f}" for value in point))
        lines.extend(["    endloop", "  endfacet"])
    lines.append("endsolid deterministic_cube")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    capability = get_slicing_capability()
    if not capability["available"]:
        raise RuntimeError("CuraEngine capability probe failed: " + str(capability["reason"]))

    slicer = Slicer()
    if not slicer._printer_def_path or not slicer._extruder_def_path:
        raise RuntimeError("Cura printer and extruder definitions were not resolved.")

    with tempfile.TemporaryDirectory(prefix="curaengine-smoke-") as directory:
        work = Path(directory)
        stl_path = work / "deterministic-cube.stl"
        gcode_path = work / "deterministic-cube.gcode"
        _write_cube_stl(stl_path)

        result = slicer.slice(
            str(stl_path),
            str(gcode_path),
            settings=SliceSettings(),
            timeout_seconds=45.0,
        )
        if not result.success or not result.gcode_path:
            raise RuntimeError("Real CuraEngine slice failed: " + "; ".join(result.errors))

        validation = slicer.validate_gcode(str(gcode_path))
        if not validation["valid"]:
            raise RuntimeError("Real CuraEngine G-code failed validation: " + str(validation["error"]))
        if validation["stats"]["deposition_moves"] <= 0:
            raise RuntimeError("Real CuraEngine output contains no positive extrusion on a print move.")
        if validation["stats"]["extrusion_length_mm"] <= 0 or not result.filament_length_m or result.filament_length_m <= 0:
            raise RuntimeError("Real CuraEngine output has zero or unknown filament extrusion length.")

        print(
            "CURAENGINE_REAL_SLICE_PASS "
            f"bytes={gcode_path.stat().st_size} "
            f"layers={validation['stats']['layers']} "
            f"print_time_seconds={result.print_time!r} "
            f"filament_length_m={result.filament_length_m!r} "
            f"filament_length_source={result.filament_length_source!r} "
            f"extrusion_length_mm={validation['stats']['extrusion_length_mm']!r} "
            f"deposition_moves={validation['stats']['deposition_moves']} "
            f"filament_grams={result.filament_used!r} "
            f"filament_weight_estimated={result.filament_weight_estimated}"
        )


if __name__ == "__main__":
    main()
