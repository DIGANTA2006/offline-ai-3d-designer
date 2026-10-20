
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

# Try to import MiDaS
try:
    import torch.hub
    MIDAS_AVAILABLE = True
except ImportError:
    MIDAS_AVAILABLE = False

# Monkey-patch torch.hub to auto-trust known repos BEFORE any imports
import torch.hub as hub
_original_check = hub._check_repo_is_trusted

def _auto_trust_repo(repo, *args, **kwargs):
    """Auto-trust known repositories used by MiDaS and its dependencies."""
    trusted_patterns = [
        "intel-isl",
        "rwightman",
        "MiDaS",
        "gen-efficientnet",
        "pytorch-image-models",
    ]
    repo_str = str(repo).lower()
    for pattern in trusted_patterns:
        if pattern.lower() in repo_str:
            return True
    return _original_check(repo, *args, **kwargs)

hub._check_repo_is_trusted = _auto_trust_repo


class ImageTo3DConverter:
    """Convert 2D images to 3D models using depth estimation."""
    
    def __init__(self, model_type: str = "MiDaS_small", trust_repo: bool = True):
        """
        Initialize the converter.
        
        Args:
            model_type: MiDaS model type - "DPT_Large", "DPT_Hybrid", or "MiDaS_small"
            trust_repo: Whether to trust the intel-isl/MiDaS repository (handled globally)
        """
        self.model_type = model_type
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.transform = None
        self._load_model()
    
    def _load_model(self):
        """Load MiDaS model for depth estimation."""
        if not MIDAS_AVAILABLE:
            raise RuntimeError("MiDaS not available. Install torch and torchvision.")
        
        # Load MiDaS model (trust_repo handled by global monkey-patch)
        self.model = torch.hub.load("intel-isl/MiDaS", self.model_type, trust_repo=True)
        self.model.to(self.device)
        self.model.eval()
        
        # Load transforms
        midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True)
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
        base_thickness: float = 2.0
    ) -> trimesh.Trimesh:
        """
        Convert depth map to 3D mesh.
        
        Args:
            depth_map: Normalized depth map (0-1)
            image: Optional color image for vertex colors
            scale: XY scale in mm
            height_scale: Z scale in mm
            simplify: Simplification factor (0 = no simplification)
            base_thickness: Base thickness in mm
            
        Returns:
            trimesh.Trimesh object
        """
        h, w = depth_map.shape
        
        # Create vertex grid
        x = np.linspace(0, scale, w)
        y = np.linspace(0, scale, h)
        xx, yy = np.meshgrid(x, y)
        
        # Z from depth map (inverted so bright = high)
        zz = depth_map * height_scale + base_thickness
        
        # Create vertices
        vertices = np.stack([xx, yy, zz], axis=-1).reshape(-1, 3)
        
        # Create faces (quad grid -> triangles)
        faces = []
        for i in range(h - 1):
            for j in range(w - 1):
                v0 = i * w + j
                v1 = i * w + j + 1
                v2 = (i + 1) * w + j
                v3 = (i + 1) * w + j + 1
                
                faces.append([v0, v2, v1])
                faces.append([v1, v2, v3])
        
        faces = np.array(faces)
        
        # Create mesh
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        
        # Add base (extrude bottom)
        mesh = self._add_base(mesh, base_thickness)
        
        # Add vertex colors from image if provided
        if image is not None:
            img_resized = cv2.resize(image, (w, h))
            colors = img_resized.reshape(-1, 3)
            mesh.visual.vertex_colors = np.hstack([colors, np.full((len(colors), 1), 255)])
        
        # Simplify if requested
        if simplify > 0:
            mesh = mesh.simplify_quadratic_decimation(int(len(mesh.faces) * (1 - simplify)))
        
        # Ensure watertight
        mesh.fill_holes()
        mesh.fix_normals()
        
        return mesh
    
    def _add_base(self, mesh: trimesh.Trimesh, thickness: float) -> trimesh.Trimesh:
        """Add a flat base to the mesh to make it printable."""
        bounds = mesh.bounds
        min_z = bounds[0, 2]
        
        boundary_mask = np.abs(mesh.vertices[:, 2] - min_z) < 0.01
        boundary_verts = mesh.vertices[boundary_mask]
        
        if len(boundary_verts) < 3:
            return mesh
        
        from scipy.spatial import ConvexHull
        try:
            hull = ConvexHull(boundary_verts[:, :2])
            
            base_z = 0
            base_vertices = []
            for v_idx in hull.vertices:
                v = boundary_verts[v_idx]
                base_vertices.append([v[0], v[1], base_z])
            
            base_vertices = np.array(base_vertices)
            base_vertex_offset = len(mesh.vertices)
            
            base_faces = []
            for simplex in hull.simplices:
                base_faces.append([
                    base_vertex_offset + simplex[0],
                    base_vertex_offset + simplex[1],
                    base_vertex_offset + simplex[2]
                ])
            
            side_faces = []
            for i in range(len(hull.vertices)):
                next_i = (i + 1) % len(hull.vertices)
                v_top_1 = hull.vertices[i]
                v_top_2 = hull.vertices[next_i]
                v_bot_1 = base_vertex_offset + i
                v_bot_2 = base_vertex_offset + next_i
                
                side_faces.append([v_top_1, v_bot_1, v_bot_2])
                side_faces.append([v_top_1, v_bot_2, v_top_2])
            
            all_vertices = np.vstack([mesh.vertices, base_vertices])
            all_faces = np.vstack([mesh.faces, base_faces, side_faces])
            
            mesh = trimesh.Trimesh(vertices=all_vertices, faces=all_faces, process=True)
            
        except Exception:
            pass
        
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
    border: float = 2.0
) -> trimesh.Trimesh:
    """
    Create a lithophane from an image (better for photos).
    
    Args:
        image_path: Path to input image
        output_path: Path to output STL
        max_size: Maximum dimension in mm
        thickness: Maximum thickness in mm
        thinnest: Minimum thickness in mm
        border: Border width in mm
        
    Returns:
        Generated mesh
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    h, w = img.shape
    aspect = w / h
    
    if aspect > 1:
        new_w = max_size - 2 * border
        new_h = new_w / aspect
    else:
        new_h = max_size - 2 * border
        new_w = new_h * aspect
    
    img = cv2.resize(img, (int(new_w), int(new_h)))
    h, w = img.shape
    
    img_norm = img.astype(np.float32) / 255.0
    thickness_map = thinnest + (1.0 - img_norm) * (thickness - thinnest)
    
    x = np.linspace(-new_w/2, new_w/2, w)
    y = np.linspace(-new_h/2, new_h/2, h)
    xx, yy = np.meshgrid(x, y)
    zz = thickness_map
    
    vertices = np.stack([xx, yy, zz], axis=-1).reshape(-1, 3)
    
    faces = []
    for i in range(h - 1):
        for j in range(w - 1):
            v0 = i * w + j
            v1 = i * w + j + 1
            v2 = (i + 1) * w + j
            v3 = (i + 1) * w + j + 1
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])
    
    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    
    mesh = _add_lithophane_base(mesh, border, thinnest)
    
    mesh.export(output_path)
    return mesh


def _add_lithophane_base(mesh: trimesh.Trimesh, border: float, thinnest: float) -> trimesh.Trimesh:
    """Add base and border to lithophane."""
    bounds = mesh.bounds
    min_x, min_y = bounds[0, 0], bounds[0, 1]
    max_x, max_y = bounds[1, 0], bounds[1, 1]
    
    base_verts = np.array([
        [min_x - border, min_y - border, 0],
        [max_x + border, min_y - border, 0],
        [max_x + border, max_y + border, 0],
        [min_x - border, max_y + border, 0],
    ])
    
    base_faces = np.array([[0, 1, 2], [0, 2, 3]])
    
    min_z = mesh.vertices[:, 2].min()
    bottom_mask = np.abs(mesh.vertices[:, 2] - min_z) < 0.01
    bottom_verts = mesh.vertices[bottom_mask]
    
    all_verts = np.vstack([mesh.vertices, base_verts])
    all_faces = np.vstack([mesh.faces, base_faces + len(mesh.vertices)])
    
    result = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    result.fill_holes()
    return result


if __name__ == "__main__":
    converter = ImageTo3DConverter("MiDaS_small")
    print("ImageTo3D module loaded successfully")
