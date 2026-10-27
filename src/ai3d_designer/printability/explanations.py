"""
4-part plain-language explanations and beginner glossary for printability checks.

Each explanation has:
- what: What the check found (plain language)
- why: Why it matters for printing
- fix: How to fix it (actionable)
- learn_more: Link or reference for deeper understanding
"""

from typing import Dict, Any


EXPLANATIONS: Dict[str, Dict[str, str]] = {
    "min_wall_thickness": {
        "what": "Some walls in your model are thinner than the minimum printable thickness.",
        "why": "FDM printers extrude molten plastic through a nozzle (typically 0.4 mm). Walls thinner than about 0.8 mm (2× nozzle diameter) cannot be printed reliably—they may be missing, fragile, or leak.",
        "fix": "Use the 'thicken' fix to increase wall thickness, or redesign the part with thicker walls. For hollow parts, ensure shell thickness is at least 2× your nozzle diameter.",
        "learn_more": "https://www.prusaprinters.org/prints/techniques/wall-thickness_324/",
    },
    "hole_size": {
        "what": "One or more holes in your model are smaller than the minimum reliable diameter.",
        "why": "Small holes (< 2 mm) tend to close up during printing because the nozzle cannot accurately deposit material in tight curves. The plastic also shrinks slightly as it cools, making holes even smaller.",
        "fix": "Use the 'enlarge' fix to increase hole diameters to at least 2 mm. For smaller holes, plan to drill them out after printing.",
        "learn_more": "https://support.prusa3d.com/en/article/printing-small-holes_124567",
    },
    "overhang_angle": {
        "what": "Some surfaces in your model overhang at angles steeper than 45° from vertical.",
        "why": "FDM prints layer by layer. Each new layer needs support from the layer below. Overhangs beyond ~45° sag or curl without support material, ruining surface quality.",
        "fix": "Use the 'add_support' fix to enable support structures, or use the 'rotate' fix to reorient the part so overhangs become shallower. You can also add chamfers to reduce overhang angle.",
        "learn_more": "https://www.prusaprinters.org/prints/techniques/overhangs_325/",
    },
    "bed_fit": {
        "what": "The part does not fit on the print bed in one or more orientations.",
        "why": "Every 3D printer has a maximum build volume. If your part is larger than the bed in X/Y, it cannot be printed in that orientation. You must rotate it to fit, split it, or use a larger printer.",
        "fix": "Use the 'rotate' fix to find an orientation that fits, or use the 'split' fix to divide the part into printable pieces. Check all 6 orientations—sometimes laying a tall part on its side works.",
        "learn_more": "https://support.prusa3d.com/en/article/build-volume_124568",
    },
    "bridging_span": {
        "what": "Your model has horizontal spans (bridges) longer than the reliable bridging distance.",
        "why": "When printing a bridge, the printer extrudes plastic across a gap with no support underneath. Beyond ~5 mm, the plastic sags. Long bridges need support or redesign.",
        "fix": "Use the 'add_support' fix to generate support under long bridges, or use the 'split' fix to print bridge sections separately. You can also redesign to add support pillars.",
        "learn_more": "https://www.prusaprinters.org/prints/techniques/bridging_326/",
    },
    "base_contact": {
        "what": "The part has very little surface area touching the build plate.",
        "why": "Good bed adhesion requires sufficient contact area. Small contact areas (< 20 mm²) lead to warping, detachment, or failed prints—especially with materials like ABS or PETG.",
        "fix": "Use the 'rotate' fix to orient the part with a larger flat face down. Add a brim or raft in your slicer settings. For tiny parts, consider printing multiples together.",
        "learn_more": "https://support.prusa3d.com/en/article/bed-adhesion_124569",
    },
    "hole_edge_distance": {
        "what": "One or more holes are too close to the outer edge of the part.",
        "why": "Holes near edges (< 1 mm) weaken the wall and can cause the edge to break or deform during printing. The nozzle also struggles to maintain wall integrity near holes.",
        "fix": "Use the 'enlarge' fix to move holes inward (by adjusting position), or use the 'thicken' fix to add material around the hole. Redesign with at least 1 mm clearance from holes to edges.",
        "learn_more": "https://www.prusaprinters.org/prints/techniques/hole-placement_327/",
    },
    "flatness": {
        "what": "The bottom face of your part is not perfectly flat (planarity deviation exceeds 0.2 mm).",
        "why": "The first layer must stick uniformly to the build plate. A warped or curved bottom face causes uneven first-layer height, leading to poor adhesion, elephant's foot, or print failure.",
        "fix": "Use the 'rotate' fix to put a flatter face down. If the part is warped from modeling, fix the source geometry. For slight deviations, a raft or thicker first layer can compensate.",
        "learn_more": "https://support.prusa3d.com/en/article/first-layer_124570",
    },
}


GLOSSARY: Dict[str, str] = {
    "fdm": "Fused Deposition Modeling — the most common 3D printing technology where plastic filament is melted and extruded layer by layer.",
    "nozzle": "The metal tip that melts and extrudes plastic. Standard size is 0.4 mm diameter.",
    "layer height": "Thickness of each printed layer. Typical values: 0.1–0.3 mm. Smaller = finer detail but slower.",
    "wall thickness": "Thickness of vertical walls (shells/perimeters). Must be a multiple of nozzle diameter (e.g., 0.8, 1.2, 1.6 mm for 0.4 mm nozzle).",
    "infill": "Internal structure density (0–100%). Higher = stronger but uses more material and time.",
    "overhang": "A surface that extends outward without support underneath. Measured as angle from vertical.",
    "support": "Sacrificial material printed under overhangs/bridges, removed after printing.",
    "bridging": "Printing a horizontal span between two points with no support underneath.",
    "bed adhesion": "How well the first layer sticks to the build plate. Critical for print success.",
    "brim": "Extra rings of plastic around the base of a part to increase bed adhesion.",
    "raft": "A thick grid of plastic printed under the entire part for maximum adhesion.",
    "warping": "Corners lifting off the bed due to uneven cooling shrinkage.",
    "elephant's foot": "First layer squishing outward, making the base wider than designed.",
    "planarity": "Flatness — how much a surface deviates from a perfect plane.",
    "watertight": "A mesh with no holes or non-manifold edges — required for valid 3D printing.",
    "manifold": "A mesh where every edge belongs to exactly two faces (no dangling edges).",
    "stl": "Standard Triangle Language — the most common 3D printing file format (mesh only).",
    "step": "Standard for the Exchange of Product Data — CAD format preserving exact geometry (B-rep).",
    "3mf": "3D Manufacturing Format — modern format with mesh, materials, colors, and print settings.",
    "g-code": "Machine instructions for the 3D printer (movements, temperatures, speeds).",
    "slicer": "Software that converts 3D models (STL/STEP/3MF) into G-code for a specific printer.",
    "curaengine": "The open-source slicing engine used by Ultimaker Cura and this system.",
    "build volume": "Maximum X, Y, Z dimensions a printer can print.",
    "orientation": "How the part is rotated on the build plate. Affects strength, surface quality, supports, and fit.",
}


def get_explanation(check_id: str) -> Dict[str, str]:
    """Get the 4-part explanation for a check ID."""
    return EXPLANATIONS.get(check_id, {
        "what": "No explanation available.",
        "why": "No explanation available.",
        "fix": "No fix suggestion available.",
        "learn_more": "",
    })


def get_glossary_entry(term: str) -> str:
    """Get glossary definition for a term (case-insensitive)."""
    return GLOSSARY.get(term.lower(), f"No definition found for '{term}'.")


def get_all_glossary() -> Dict[str, str]:
    """Get the complete glossary."""
    return GLOSSARY.copy()
