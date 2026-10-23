
"""
Image to 3D conversion module using depth estimation (MiDaS) and mesh generation.
"""
import os
import torch
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
import trimesh
from PIL import Image

# Use PyTorch Hub normally; never monkey-patch global repository trust policy.
try:
    import torch.hub
    MIDAS_AVAILABLE = True
except ImportError:
    MIDAS_AVAILABLE = False

from .mesh import build_closed_heightfield


class ImageTo3DConverter:
    """Convert 2D images to 3D models using depth estimation."""
    
    def __init__(self, model_type: str = "MiDaS_small", trust_repo: bool = False):
        """
        Initialize the converter.
        
        Args:
            model_type: MiDaS model type - "DPT_Large", "DPT_Hybrid", or "MiDaS_small"
            trust_repo: Explicit opt-in to execute code from the MiDaS source repository on first download.
        """
        self.model_type = model_type
        self.trust_repo = trust_repo
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.transform = None
        self._load_model()
    
    def _load_model(self):
        """Load MiDaS model for depth estimation."""
        if not MIDAS_AVAILABLE:
            raise RuntimeError("MiDaS not available. Install torch and torchvision.")
        
        if not self.trust_repo:
            raise RuntimeError(
                "Loading MiDaS may download and execute code from the intel-isl/MiDaS repository. "
                "Review that source and explicitly opt in with trust_repo=True before using image-to-3D."
            )
        self.model = torch.hub.load("intel-isl/MiDaS", self.model_type, trust_repo=self.trust_repo)
        self.model.to(self.device)
        self.model.eval()
        
        # Load transforms
        midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=self.trust_repo)
        if self.model_type == "DPT_Large" or self.model_type == "DPT_Hybrid":
            self.transform = midas_transforms.dpt_transform
        else:
            self.transform = midas_transforms.small_transform
    
    def estimate_depth(self, image_path: str) -> np.ndarray:
        """
        Estimate depth map from image.
        
        Args:
            image_path: Path to input image
            
        Returns:
            Depth map as numpy array (normalized 0-1)
        """
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Transform
        input_batch = self.transform(img).to(self.device)
        
        # Predict
        with torch.no_grad():
            prediction = self.model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()
        
        depth_map = prediction.cpu().numpy()
        
        # Normalize to 0-1
        depth_min = depth_map.min()
        depth_max = depth_map.max()
        if depth_max > depth_min:
            depth_map = (depth_map - depth_min) / (depth_max - depth_min)
        
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
        """Convert a depth map into a closed approximate relief mesh.

        This is a heightfield extrusion, not reconstruction of hidden geometry.
        """
        depth = np.asarray(depth_map, dtype=np.float64)
        if depth.ndim != 2 or min(depth.shape, default=0) < 2:
            raise ValueError("Depth map must be a 2-D array with at least 2 rows and columns.")
        if not np.isfinite(depth).all():
            raise ValueError("Depth map contains non-finite values.")
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("XY scale must be a finite positive number of millimeters.")
        if not np.isfinite(height_scale) or height_scale < 0:
            raise ValueError("Height scale must be a finite non-negative number of millimeters.")
        if not np.isfinite(base_thickness) or base_thickness <= 0:
            raise ValueError("Base thickness must be a finite positive number of millimeters.")
        if not np.isfinite(simplify) or not 0 <= simplify < 1:
            raise ValueError("Simplification must be in the range [0, 1).")

        height, width = depth.shape
        xx, yy = np.meshgrid(np.linspace(0, scale, width), np.linspace(0, scale, height))
        zz = np.clip(depth, 0.0, 1.0) * height_scale + base_thickness
        color_grid = None
        if image is not None:
            rgb = np.asarray(cv2.resize(image, (width, height)), dtype=np.uint8)
            color_grid = rgb[:, :, :3]

        mesh = build_closed_heightfield(xx, yy, zz, bottom_z=0.0, vertex_colors=color_grid)
        if simplify > 0:
            target_faces = max(12, int(len(mesh.faces) * (1.0 - simplify)))
            simplifier = getattr(mesh, "simplify_quadric_decimation", None)
            if simplifier is not None:
                mesh = simplifier(face_count=target_faces)
            else:
                legacy_simplifier = getattr(mesh, "simplify_quadratic_decimation", None)
                if legacy_simplifier is None:
                    raise RuntimeError("Mesh simplification is unavailable in the installed trimesh version.")
                mesh = legacy_simplifier(target_faces)
            if not mesh.is_watertight or not mesh.is_volume or mesh.volume <= 0:
                raise ValueError("Mesh simplification produced an invalid solid; retry with simplification set to 0.")
        mesh.fix_normals()
        return mesh

    def convert_image_to_3d(
        self,
        image_path: str,
        output_path: str,
        scale: float = 50.0,
        height_scale: float = 10.0,
        base_thickness: float = 2.0,
        simplify: float = 0.0,
        format: str = "stl"
    ) -> trimesh.Trimesh:
        """
        Full pipeline: image -> depth -> mesh -> export.
        
        Args:
            image_path: Path to input image
            output_path: Path to output file
            scale: XY scale in mm
            height_scale: Z scale in mm
            base_thickness: Base thickness in mm
            simplify: Simplification factor (0-1)
            format: Output format (stl, obj, ply)
            
        Returns:
            Generated mesh
        """
        img = cv2.imread(image_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img is not None else None
        
        self._log(f"Estimating depth from {image_path}...")
        depth_map = self.estimate_depth(image_path)
        
        self._log("Generating 3D mesh...")
        mesh = self.depth_to_mesh(
            depth_map,
            image=img_rgb,
            scale=scale,
            height_scale=height_scale,
            base_thickness=base_thickness,
            simplify=simplify
        )
        
        self._log(f"Exporting to {output_path}...")
        mesh.export(output_path)
        
        self._log(f"Done! Mesh: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
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
    """Create a closed solid lithophane with a thin perimeter border."""
    if not all(np.isfinite(value) for value in (max_size, thickness, thinnest, border)):
        raise ValueError("Lithophane dimensions must be finite numbers.")
    if max_size <= 0 or border < 0 or max_size <= 2 * border:
        raise ValueError("max_size must be positive and greater than twice the non-negative border.")
    if thinnest <= 0 or thickness <= thinnest:
        raise ValueError("Thickness must be greater than a positive minimum thickness.")

    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")
    original_h, original_w = img.shape
    if min(original_h, original_w) < 2:
        raise ValueError("Lithophane image must be at least 2 x 2 pixels.")

    aspect = original_w / original_h
    if aspect > 1:
        new_w = max_size - 2 * border
        new_h = new_w / aspect
    else:
        new_h = max_size - 2 * border
        new_w = new_h * aspect
    pixel_w = max(2, int(round(new_w)))
    pixel_h = max(2, int(round(new_h)))
    img = cv2.resize(img, (pixel_w, pixel_h), interpolation=cv2.INTER_AREA)
    image_h, image_w = img.shape

    normalized = img.astype(np.float64) / 255.0
    thickness_map = thinnest + (1.0 - normalized) * (thickness - thinnest)
    # Insert a flat-thinnest ring around the image and let the shared mesh
    # helper create bottom and side walls for a truly closed solid.
    padded = np.pad(thickness_map, 1, mode="constant", constant_values=thinnest)
    inner_x = np.linspace(-new_w / 2, new_w / 2, image_w)
    inner_y = np.linspace(-new_h / 2, new_h / 2, image_h)
    x = np.concatenate(([inner_x[0] - border], inner_x, [inner_x[-1] + border]))
    y = np.concatenate(([inner_y[0] - border], inner_y, [inner_y[-1] + border]))
    xx, yy = np.meshgrid(x, y)
    mesh = build_closed_heightfield(xx, yy, padded, bottom_z=0.0)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(destination))
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("Lithophane export failed to produce a non-empty file.")
    return mesh

if __name__ == "__main__":
    converter = ImageTo3DConverter("MiDaS_small")
    print("ImageTo3D module loaded successfully")
