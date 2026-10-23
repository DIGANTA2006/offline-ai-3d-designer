"""Experimental image-to-relief mesh generation.

Depth estimation from one image is approximate; it is not a general engineering drawing-to-CAD
pipeline. Reliefs generated here must be reviewed before manufacture.
"""
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh
from PIL import Image

try:
    import torch
except (ImportError, OSError):
    torch = None
    MIDAS_AVAILABLE = False
else:
    MIDAS_AVAILABLE = True


def _build_watertight_heightfield(heights: np.ndarray, scale_x: float, scale_y: float) -> trimesh.Trimesh:
    """Create a closed solid with a height-map top, flat bottom, and perimeter walls."""
    height_map = np.asarray(heights, dtype=np.float64)
    if height_map.ndim != 2 or min(height_map.shape) < 2:
        raise ValueError("Height map must be 2D and at least 2 × 2 pixels.")
    if not np.isfinite(height_map).all() or np.any(height_map <= 0):
        raise ValueError("All height-map values must be finite and above the bottom plane.")
    if not np.isfinite(scale_x) or not np.isfinite(scale_y) or scale_x <= 0 or scale_y <= 0:
        raise ValueError("X and Y scale must be finite positive millimetre values.")

    rows, cols = height_map.shape
    xx, yy = np.meshgrid(
        np.linspace(-scale_x / 2.0, scale_x / 2.0, cols),
        np.linspace(-scale_y / 2.0, scale_y / 2.0, rows),
    )
    top = np.column_stack((xx.ravel(), yy.ravel(), height_map.ravel()))
    bottom = np.column_stack((xx.ravel(), yy.ravel(), np.zeros(rows * cols)))
    offset = rows * cols
    faces: list[list[int]] = []

    for row in range(rows - 1):
        for col in range(cols - 1):
            v0 = row * cols + col
            v1 = v0 + 1
            v2 = v0 + cols
            v3 = v2 + 1
            faces.extend(([v0, v1, v2], [v1, v3, v2]))
            faces.extend((
                [offset + v0, offset + v2, offset + v1],
                [offset + v1, offset + v2, offset + v3],
            ))

    perimeter = []
    perimeter.extend((rows - 1) * cols + col for col in range(cols))
    perimeter.extend(row * cols + cols - 1 for row in range(rows - 2, -1, -1))
    perimeter.extend(col for col in range(cols - 2, -1, -1))
    perimeter.extend(row * cols for row in range(1, rows - 1))
    for index, top_a in enumerate(perimeter):
        top_b = perimeter[(index + 1) % len(perimeter)]
        bottom_a = offset + top_a
        bottom_b = offset + top_b
        # The perimeter is traversed clockwise in XY. These triangles preserve
        # consistent outward winding without relying on trimesh's optional networkx.
        faces.extend(([top_a, top_b, bottom_b], [top_a, bottom_b, bottom_a]))

    mesh = trimesh.Trimesh(vertices=np.vstack((top, bottom)), faces=np.asarray(faces), process=True)
    if np.isfinite(mesh.volume) and mesh.volume < 0:
        mesh.invert()
    if not mesh.is_watertight or not mesh.is_volume or not np.isfinite(mesh.volume) or mesh.volume <= 0:
        raise ValueError("Generated height-field mesh is not a valid watertight solid.")
    return mesh


class ImageTo3DConverter:
    """Generate an approximate height-field relief from a single image."""

    def __init__(self, model_type: str = "MiDaS_small", trust_repo: bool = True):
        if not MIDAS_AVAILABLE or torch is None:
            raise RuntimeError(
                "MiDaS depth estimation is unavailable. Install a compatible torch/torchvision "
                "build and cache the model before using this feature."
            )
        self.model_type = model_type
        self.trust_repo = trust_repo
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.transform = None
        self._load_model()

    def _load_model(self) -> None:
        """Load only the fixed MiDaS repository without modifying global trust checks."""
        if torch is None:
            raise RuntimeError("PyTorch is not installed.")
        try:
            self.model = torch.hub.load(
                "intel-isl/MiDaS", self.model_type, trust_repo=self.trust_repo
            )
            self.model.to(self.device)
            self.model.eval()
            midas_transforms = torch.hub.load(
                "intel-isl/MiDaS", "transforms", trust_repo=self.trust_repo
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not load MiDaS. Check the installed torch/torchvision versions and "
                "model availability; remote model code is not trusted globally."
            ) from exc
        if self.model_type in {"DPT_Large", "DPT_Hybrid"}:
            self.transform = midas_transforms.dpt_transform
        else:
            self.transform = midas_transforms.small_transform

    def estimate_depth(self, image_path: str) -> np.ndarray:
        """Estimate normalized relative depth; values are not metric measurements."""
        if torch is None or self.model is None or self.transform is None:
            raise RuntimeError("MiDaS model is not initialized.")
        try:
            with Image.open(image_path) as source:
                image = np.asarray(source.convert("RGB"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not load image: {exc}") from exc

        input_batch = self.transform(image).to(self.device)
        with torch.inference_mode():
            prediction = self.model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=image.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()
        depth_map = prediction.detach().cpu().numpy().astype(np.float64)
        if not np.isfinite(depth_map).all():
            raise ValueError("Depth estimator returned non-finite values.")
        depth_min = float(depth_map.min())
        depth_max = float(depth_map.max())
        if depth_max > depth_min:
            depth_map = (depth_map - depth_min) / (depth_max - depth_min)
        else:
            depth_map = np.zeros_like(depth_map)
        return depth_map

    def depth_to_mesh(
        self,
        depth_map: np.ndarray,
        image: Optional[np.ndarray] = None,
        scale: float = 50.0,
        height_scale: float = 10.0,
        simplify: float = 0.0,
        base_thickness: float = 2.0,
    ) -> trimesh.Trimesh:
        """Create a watertight relief; scale is the maximum XY dimension in millimetres."""
        depth = np.asarray(depth_map, dtype=np.float64)
        if depth.ndim != 2 or min(depth.shape) < 2:
            raise ValueError("Depth map must be 2D and at least 2 × 2 pixels.")
        if not np.isfinite(depth).all():
            raise ValueError("Depth map cannot contain NaN or infinite values.")
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("Scale must be positive.")
        if not np.isfinite(height_scale) or height_scale <= 0:
            raise ValueError("Height scale must be positive.")
        if not np.isfinite(base_thickness) or base_thickness <= 0:
            raise ValueError("Base thickness must be positive.")
        if not np.isfinite(simplify) or simplify < 0 or simplify >= 1:
            raise ValueError("Simplification must be between 0 (none) and less than 1.")

        rows, cols = depth.shape
        if cols >= rows:
            scale_x, scale_y = scale, scale * rows / cols
        else:
            scale_x, scale_y = scale * cols / rows, scale
        heights = base_thickness + np.clip(depth, 0.0, 1.0) * height_scale
        mesh = _build_watertight_heightfield(heights, scale_x, scale_y)

        if image is not None:
            colors = np.asarray(image)
            if colors.ndim == 2:
                colors = np.repeat(colors[..., None], 3, axis=2)
            if colors.ndim != 3 or colors.shape[2] < 3:
                raise ValueError("Optional color image must contain RGB or RGBA channels.")
            colors = np.clip(colors[..., :3], 0, 255).astype(np.uint8)
            resized = Image.fromarray(colors).resize(
                (cols, rows), resample=Image.Resampling.BILINEAR
            )
            top_rgb = np.asarray(resized).reshape(-1, 3)
            top_rgba = np.column_stack((top_rgb, np.full(len(top_rgb), 255, dtype=np.uint8)))
            bottom_rgba = np.tile(np.array([[160, 160, 160, 255]], dtype=np.uint8), (len(top_rgb), 1))
            mesh.visual.vertex_colors = np.vstack((top_rgba, bottom_rgba))

        if simplify > 0:
            target_faces = max(12, int(len(mesh.faces) * (1.0 - simplify)))
            try:
                simplified = mesh.simplify_quadric_decimation(face_count=target_faces)
            except Exception as exc:
                raise RuntimeError(
                    "Mesh simplification failed. Disable simplification or install a supported "
                    "trimesh simplification backend."
                ) from exc
            if not simplified.is_watertight or not simplified.is_volume or simplified.volume <= 0:
                raise ValueError("Simplification produced an invalid mesh; retry with simplify=0.")
            mesh = simplified
        return mesh

    def convert_image_to_3d(
        self,
        image_path: str,
        output_path: str,
        scale: float = 50.0,
        height_scale: float = 10.0,
        base_thickness: float = 2.0,
        simplify: float = 0.0,
        format: str = "stl",
    ) -> trimesh.Trimesh:
        """Estimate relative depth, create a closed relief and export it."""
        output_format = format.lower().lstrip(".")
        if output_format not in {"stl", "obj", "ply"}:
            raise ValueError("Output format must be STL, OBJ, or PLY.")
        output = Path(output_path)
        if output.suffix.lower() != "." + output_format:
            raise ValueError("Output filename extension must match the selected export format.")
        try:
            with Image.open(image_path) as source:
                image = np.asarray(source.convert("RGB"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not load image: {exc}") from exc

        self._log(f"Estimating relative depth from {image_path}...")
        depth_map = self.estimate_depth(image_path)
        self._log("Generating and validating relief mesh...")
        mesh = self.depth_to_mesh(
            depth_map,
            image=image,
            scale=scale,
            height_scale=height_scale,
            base_thickness=base_thickness,
            simplify=simplify,
        )
        if not mesh.is_watertight or not mesh.is_volume or mesh.volume <= 0:
            raise ValueError("Refusing to export an invalid or non-watertight relief mesh.")

        output.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output), file_type=output_format)
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Relief export did not produce a non-empty file.")
        self._log(f"Done. Mesh has {len(mesh.vertices)} vertices and {len(mesh.faces)} faces.")
        return mesh

    def _log(self, msg: str):
        print(f"[ImageTo3D] {msg}")


def create_lithophane(
    image_path: str,
    output_path: str,
    max_size: float = 100.0,
    thickness: float = 3.0,
    thinnest: float = 0.8,
    border: float = 2.0,
) -> trimesh.Trimesh:
    """Create a watertight photo-relief lithophane, not an engineering CAD reconstruction."""
    if not np.isfinite(max_size) or max_size <= 0:
        raise ValueError("max_size must be a positive millimetre value.")
    if not np.isfinite(thickness) or not np.isfinite(thinnest) or thinnest <= 0 or thickness < thinnest:
        raise ValueError("Require thickness >= thinnest > 0.")
    if not np.isfinite(border) or border < 0 or max_size <= 2.0 * border:
        raise ValueError("border must be non-negative and less than half of max_size.")

    try:
        with Image.open(image_path) as source:
            grayscale = source.convert("L")
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not load image: {exc}") from exc

    source_w, source_h = grayscale.size
    if source_w < 2 or source_h < 2:
        raise ValueError("Image must be at least 2 × 2 pixels.")
    aspect = source_w / source_h
    inner_max = max_size - 2.0 * border
    if aspect >= 1.0:
        inner_w, inner_h = inner_max, inner_max / aspect
    else:
        inner_h, inner_w = inner_max, inner_max * aspect

    pixel_count = min(512, max(source_w, source_h))
    pixels_w = max(2, int(round(pixel_count * inner_w / max(inner_w, inner_h))))
    pixels_h = max(2, int(round(pixel_count * inner_h / max(inner_w, inner_h))))
    resized = grayscale.resize((pixels_w, pixels_h), resample=Image.Resampling.LANCZOS)
    gray = np.asarray(resized, dtype=np.float64) / 255.0

    if border > 0:
        pixel_pitch = min(inner_w / max(pixels_w - 1, 1), inner_h / max(pixels_h - 1, 1))
        border_px_x = max(1, int(round(border / pixel_pitch)))
        border_px_y = max(1, int(round(border / pixel_pitch)))
        # Black padding is deliberately thicker and strengthens the lithophane's frame.
        gray = np.pad(
            gray,
            ((border_px_y, border_px_y), (border_px_x, border_px_x)),
            mode="constant",
            constant_values=0.0,
        )

    height_map = thinnest + (1.0 - gray) * (thickness - thinnest)
    mesh = _build_watertight_heightfield(
        height_map,
        scale_x=inner_w + 2.0 * border,
        scale_y=inner_h + 2.0 * border,
    )
    if not mesh.is_watertight or not mesh.is_volume or mesh.volume <= 0:
        raise ValueError("Lithophane mesh failed watertight solid validation.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(output), file_type="stl")
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Lithophane export did not produce a non-empty STL file.")
    return mesh


if __name__ == "__main__":
    converter = ImageTo3DConverter("MiDaS_small")
    print("ImageTo3D module loaded successfully")
