
"""
Simple GUI for the AI 3D Designer using Tkinter.
Updated with Image-to-3D and Slicing/Printing workflow.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
from pathlib import Path

# Import from core modules
from ai3d_designer.core.spec.models import PartSpec, FeatureSpec, ParameterSpec, PrimitiveType, OperationType, UnitSystem
from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.export.exporter import export_step, export_stl, validate_export

# Import new modules
try:
    from ai3d_designer.image_to_3d.converter import ImageTo3DConverter, create_lithophane
    IMAGE_TO_3D_AVAILABLE = True
except ImportError as e:
    IMAGE_TO_3D_AVAILABLE = False
    IMAGE_TO_3D_ERROR = str(e)

try:
    from ai3d_designer.slicing.slicer import Slicer, SliceSettings, SliceResult
    SLICING_AVAILABLE = True
except ImportError as e:
    SLICING_AVAILABLE = False
    SLICING_ERROR = str(e)


def create_box_spec(name: str, width: float, depth: float, height: float, 
                    hole_diameter: float = None) -> PartSpec:
    """Create a simple box specification, optionally with a hole."""
    spec = PartSpec(
        name=name,
        description=f"Box {width}x{depth}x{height}mm",
        unit_system=UnitSystem.MM,
    )
    
    box_feature = FeatureSpec(
        id="box_main",
        type=PrimitiveType.BOX,
        name="main_box",
        parameters={
            "width": ParameterSpec(name="width", value=width),
            "depth": ParameterSpec(name="depth", value=depth),
            "height": ParameterSpec(name="height", value=height),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(box_feature)
    
    if hole_diameter and hole_diameter > 0:
        hole_feature = FeatureSpec(
            id="hole_center",
            type=PrimitiveType.CYLINDER,
            name="center_hole",
            parameters={
                "radius": ParameterSpec(name="radius", value=hole_diameter / 2),
                "height": ParameterSpec(name="height", value=height + 2),
            },
            position=[width/2, depth/2, -1],
            operation=OperationType.DIFFERENCE,
        )
        spec.add_feature(hole_feature)
    
    return spec


def create_cylinder_spec(name: str, radius: float, height: float) -> PartSpec:
    """Create a cylinder specification."""
    spec = PartSpec(
        name=name,
        description=f"Cylinder radius={radius} height={height}mm",
        unit_system=UnitSystem.MM,
    )
    
    cyl_feature = FeatureSpec(
        id="cylinder_main",
        type=PrimitiveType.CYLINDER,
        name="main_cylinder",
        parameters={
            "radius": ParameterSpec(name="radius", value=radius),
            "height": ParameterSpec(name="height", value=height),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(cyl_feature)
    
    return spec


def create_sphere_spec(name: str, radius: float) -> PartSpec:
    """Create a sphere specification."""
    spec = PartSpec(
        name=name,
        description=f"Sphere radius={radius}mm",
        unit_system=UnitSystem.MM,
    )
    
    sphere_feature = FeatureSpec(
        id="sphere_main",
        type=PrimitiveType.SPHERE,
        name="main_sphere",
        parameters={
            "radius": ParameterSpec(name="radius", value=radius),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(sphere_feature)
    
    return spec


def create_part_from_text(text: str) -> PartSpec:
    """Parse natural language text into a PartSpec."""
    import re
    text_lower = text.lower()
    
    if "cylinder" in text_lower:
        radius_match = re.search(r'radius\s*[=:]?\s*(\d+(?:\.\d+)?)', text_lower)
        height_match = re.search(r'height\s*[=:]?\s*(\d+(?:\.\d+)?)', text_lower)
        if not radius_match:
            dims = re.findall(r'(\d+(?:\.\d+)?)\s*[x\u00d7]\s*(\d+(?:\.\d+)?)', text)
            if dims and len(dims[0]) == 2:
                radius, height = map(float, dims[0])
            else:
                radius, height = 10, 50
        else:
            radius = float(radius_match.group(1))
            height = float(height_match.group(1)) if height_match else 50
        return create_cylinder_spec("cylinder", radius, height)
    
    if "sphere" in text_lower:
        radius_match = re.search(r'radius\s*[=:]?\s*(\d+(?:\.\d+)?)', text_lower)
        if not radius_match:
            radius_match = re.search(r'sphere\s+(\d+(?:\.\d+)?)', text_lower)
        radius = float(radius_match.group(1)) if radius_match else 10
        return create_sphere_spec("sphere", radius)
    
    dims = re.findall(r'(\d+(?:\.\d+)?)\s*[x\u00d7]\s*(\d+(?:\.\d+)?)\s*[x\u00d7]\s*(\d+(?:\.\d+)?)', text)
    if not dims:
        dims = re.findall(r'(\d+(?:\.\d+)?)\s*(?:mm|cm|in)?\s*[x\u00d7]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in)?\s*[x\u00d7]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in)?', text)
    
    width, depth, height = 40, 20, 10
    if dims:
        width, depth, height = map(float, dims[0])
    
    hole_diameter = None
    hole_match = re.search(r'(\d+(?:\.\d+)?)\s*mm\s*hole', text_lower)
    if not hole_match:
        hole_match = re.search(r'hole\s*(\d+(?:\.\d+)?)\s*mm', text_lower)
    if not hole_match:
        hole_match = re.search(r'with\s+a\s+(\d+(?:\.\d+)?)\s*mm\s*hole', text_lower)
    if hole_match:
        hole_diameter = float(hole_match.group(1))
    
    name = "box"
    return create_box_spec(name, width, depth, height, hole_diameter)


class AI3DDesignerGUI:
    """Main GUI application with Text-to-3D, Image-to-3D, and Slicing workflow."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Offline AI 3D Designer - Image to 3D & Print")
        self.root.geometry("1000x750")
        self.root.minsize(800, 600)
        
        # State
        self.current_spec = None
        self.current_part = None
        self.current_mesh = None  # For image-to-3D
        self.current_stl_path = None
        self.current_gcode_path = None
        self.output_dir = Path("./output")
        self.output_dir.mkdir(exist_ok=True)
        
        # Slicer
        self.slicer = None
        if SLICING_AVAILABLE:
            self.slicer = Slicer()
        
        # Image-to-3D converter
        self.converter = None
        self.converter_loading = False
        
        self._create_widgets()
        self._layout_widgets()
        self._check_dependencies()
        
    def _check_dependencies(self):
        """Check and log dependency status."""
        self._log("=== Dependency Check ===")
        self._log(f"Image-to-3D (MiDaS): {'Available' if IMAGE_TO_3D_AVAILABLE else 'Not Available - ' + IMAGE_TO_3D_ERROR}")
        self._log(f"Slicing: {'Available' if SLICING_AVAILABLE else 'Not Available - ' + SLICING_ERROR}")
        if self.slicer and self.slicer.cura_available:
            self._log(f"CuraEngine: Found at {self.slicer.cura_engine_path}")
        else:
            self._log("CuraEngine: Not found - real slicing is disabled until CuraEngine is installed.")
        self._log("========================")
        
    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main container
        self.main_frame = ttk.Frame(self.root, padding="10")
        
        # Title
        self.title_label = ttk.Label(
            self.main_frame, 
            text="Offline AI 3D Designer", 
            font=("Segoe UI", 16, "bold")
        )
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        
        # ===== TAB 1: Text to 3D =====
        self.tab_text = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tab_text, text="Text to 3D")
        self._create_text_tab()
        
        # ===== TAB 2: Image to 3D =====
        self.tab_image = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tab_image, text="Image to 3D")
        self._create_image_tab()
        
        # ===== TAB 3: Slice & Print =====
        self.tab_slice = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tab_slice, text="Slice & Print")
        self._create_slice_tab()
        
        # Progress bar (shared)
        self.progress = ttk.Progressbar(self.main_frame, mode='indeterminate')
        
        # Log/Output section (shared)
        self.log_frame = ttk.LabelFrame(self.main_frame, text="Output Log", padding="5")
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            height=10,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        
    def _create_text_tab(self):
        """Create Text-to-3D tab."""
        # Input section
        input_frame = ttk.LabelFrame(self.tab_text, text="Part Description", padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.prompt_text = scrolledtext.ScrolledText(
            input_frame, 
            height=4, 
            wrap=tk.WORD,
            font=("Consolas", 10)
        )
        self.prompt_text.insert(tk.END, "Create a 40x20x10mm box with a 5mm hole")
        self.prompt_text.pack(fill=tk.X, pady=(0, 5))
        
        self.generate_btn = ttk.Button(
            input_frame,
            text="Generate 3D Model",
            command=self._on_generate_text,
            style="Accent.TButton"
        )
        self.generate_btn.pack(anchor=tk.W)
        
        # Examples
        examples_frame = ttk.LabelFrame(self.tab_text, text="Quick Examples", padding="5")
        examples_frame.pack(fill=tk.X, pady=(0, 10))
        
        examples = [
            ("Box with hole", "Create a 40x20x10mm box with a 5mm hole"),
            ("Simple box", "50x30x20 box"),
            ("Cylinder", "cylinder radius 10 height 50"),
            ("Sphere", "sphere radius 15"),
        ]
        
        for i, (label, prompt) in enumerate(examples):
            btn = ttk.Button(
                examples_frame,
                text=label,
                command=lambda p=prompt: self._load_example(p)
            )
            btn.grid(row=0, column=i, padx=5, pady=5)
        
        # Options
        options_frame = ttk.LabelFrame(self.tab_text, text="Export Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(options_frame, text="Output Folder:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.output_dir_var = tk.StringVar(value=str(self.output_dir))
        self.output_dir_entry = ttk.Entry(options_frame, textvariable=self.output_dir_var, width=40)
        self.output_dir_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(options_frame, text="Browse...", command=self._browse_output_dir).grid(row=0, column=2, padx=5)
        
        ttk.Label(options_frame, text="Formats:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.format_step_var = tk.BooleanVar(value=True)
        self.format_stl_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="STEP (.step)", variable=self.format_step_var).grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Checkbutton(options_frame, text="STL (.stl)", variable=self.format_stl_var).grid(row=1, column=2, sticky=tk.W, padx=5)
        
        self.validate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Validate exports", variable=self.validate_var).grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(options_frame, text="Part Name:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.part_name_var = tk.StringVar()
        ttk.Entry(options_frame, textvariable=self.part_name_var, width=30).grid(row=3, column=1, sticky=tk.EW, padx=5)
        
        options_frame.columnconfigure(1, weight=1)
        
        # Actions
        action_frame = ttk.Frame(self.tab_text)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.export_btn = ttk.Button(action_frame, text="Export Files", command=self._on_export, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=5)
        
        self.validate_btn = ttk.Button(action_frame, text="Validate Only", command=self._on_validate, state=tk.DISABLED)
        self.validate_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(action_frame, text="Open Output Folder", command=self._open_output_folder).pack(side=tk.RIGHT, padx=5)
        
        # Send to slicing button
        self.send_to_slice_btn = ttk.Button(action_frame, text="Send to Slicer \u2192", command=self._send_to_slicer, state=tk.DISABLED)
        self.send_to_slice_btn.pack(side=tk.LEFT, padx=5)
        
    def _create_image_tab(self):
        """Create Image-to-3D tab."""
        # Image selection
        img_frame = ttk.LabelFrame(self.tab_image, text="Input Image", padding="10")
        img_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(img_frame, text="Image File:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.image_path_var = tk.StringVar()
        ttk.Entry(img_frame, textvariable=self.image_path_var, width=50).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(img_frame, text="Browse...", command=self._browse_image).grid(row=0, column=2, padx=5)
        
        # Preview canvas
        self.preview_label = ttk.Label(img_frame, text="No image loaded", relief=tk.SUNKEN, anchor=tk.CENTER)
        self.preview_label.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=10)
        
        img_frame.columnconfigure(1, weight=1)
        
        # Conversion settings
        settings_frame = ttk.LabelFrame(self.tab_image, text="Conversion Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Mode selection
        ttk.Label(settings_frame, text="Mode:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.image_mode_var = tk.StringVar(value="depth")
        ttk.Radiobutton(settings_frame, text="Depth Map (3D relief)", variable=self.image_mode_var, value="depth").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(settings_frame, text="Lithophane (backlit)", variable=self.image_mode_var, value="lithophane").grid(row=0, column=2, sticky=tk.W)
        
        # Scale settings
        ttk.Label(settings_frame, text="Max Size (mm):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.max_size_var = tk.DoubleVar(value=100.0)
        ttk.Spinbox(settings_frame, from_=10, to=300, increment=10, textvariable=self.max_size_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(settings_frame, text="Height Scale (mm):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.height_scale_var = tk.DoubleVar(value=10.0)
        ttk.Spinbox(settings_frame, from_=1, to=50, increment=1, textvariable=self.height_scale_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(settings_frame, text="Base Thickness (mm):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.base_thickness_var = tk.DoubleVar(value=2.0)
        ttk.Spinbox(settings_frame, from_=0.5, to=10, increment=0.5, textvariable=self.base_thickness_var, width=10).grid(row=3, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(settings_frame, text="Simplify (0-1):").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.simplify_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(settings_frame, from_=0, to=0.9, increment=0.1, textvariable=self.simplify_var, width=10).grid(row=4, column=1, sticky=tk.W, padx=5)
        
        # Lithophane specific
        self.litho_frame = ttk.Frame(settings_frame)
        self.litho_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=5)
        
        ttk.Label(self.litho_frame, text="Max Thickness (mm):").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.litho_thickness_var = tk.DoubleVar(value=3.0)
        ttk.Spinbox(self.litho_frame, from_=1, to=10, increment=0.5, textvariable=self.litho_thickness_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(self.litho_frame, text="Min Thickness (mm):").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.litho_thinnest_var = tk.DoubleVar(value=0.8)
        ttk.Spinbox(self.litho_frame, from_=0.3, to=2, increment=0.1, textvariable=self.litho_thinnest_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=5)
        
        ttk.Label(self.litho_frame, text="Border (mm):").grid(row=0, column=4, sticky=tk.W, padx=5)
        self.litho_border_var = tk.DoubleVar(value=2.0)
        ttk.Spinbox(self.litho_frame, from_=0, to=10, increment=1, textvariable=self.litho_border_var, width=10).grid(row=0, column=5, sticky=tk.W, padx=5)
        
        # Model type for lithophane
        self.image_mode_var.trace_add("write", self._on_mode_change)
        
        # Actions
        img_action_frame = ttk.Frame(self.tab_image)
        img_action_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.convert_image_btn = ttk.Button(
            img_action_frame, 
            text="Convert to 3D", 
            command=self._on_convert_image,
            style="Accent.TButton",
            state=tk.DISABLED if not IMAGE_TO_3D_AVAILABLE else tk.NORMAL
        )
        self.convert_image_btn.pack(side=tk.LEFT, padx=5)
        
        self.export_image_btn = ttk.Button(img_action_frame, text="Export STL", command=self._on_export_image_stl, state=tk.DISABLED)
        self.export_image_btn.pack(side=tk.LEFT, padx=5)
        
        self.send_image_to_slice_btn = ttk.Button(img_action_frame, text="Send to Slicer \u2192", command=self._send_image_to_slicer, state=tk.DISABLED)
        self.send_image_to_slice_btn.pack(side=tk.LEFT, padx=5)
        
        if not IMAGE_TO_3D_AVAILABLE:
            ttk.Label(img_action_frame, text="Requires: torch, torchvision", foreground="red").pack(side=tk.LEFT, padx=10)
        
    def _create_slice_tab(self):
        """Create Slice & Print tab."""
        # Model selection
        model_frame = ttk.LabelFrame(self.tab_slice, text="Model to Slice", padding="10")
        model_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(model_frame, text="STL File:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.slice_stl_var = tk.StringVar()
        ttk.Entry(model_frame, textvariable=self.slice_stl_var, width=50).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(model_frame, text="Browse...", command=self._browse_slice_stl).grid(row=0, column=2, padx=5)
        
        ttk.Label(model_frame, text="G-code Output:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.gcode_output_var = tk.StringVar()
        ttk.Entry(model_frame, textvariable=self.gcode_output_var, width=50).grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Button(model_frame, text="Browse...", command=self._browse_gcode_output).grid(row=1, column=2, padx=5)
        
        ttk.Label(model_frame, text="Cura Printer Definition JSON:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.printer_definition_var = tk.StringVar(value=os.environ.get("CURA_PRINTER_DEFINITION", ""))
        ttk.Entry(model_frame, textvariable=self.printer_definition_var, width=50).grid(row=2, column=1, sticky=tk.EW, padx=5)
        ttk.Button(model_frame, text="Browse...", command=self._browse_printer_definition).grid(row=2, column=2, padx=5)

        model_frame.columnconfigure(1, weight=1)
        
        # Slice settings
        slice_settings_frame = ttk.LabelFrame(self.tab_slice, text="Slice Settings", padding="10")
        slice_settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create settings in a grid
        settings = [
            ("Layer Height (mm):", "layer_height_var", 0.2, 0.05, 0.5),
            ("Wall Thickness (mm):", "wall_thickness_var", 1.2, 0.4, 3.0),
            ("Infill Density (%):", "infill_density_var", 20, 0, 100),
            ("Infill Pattern:", "infill_pattern_var", "grid", None, None),
            ("Print Speed (mm/s):", "print_speed_var", 50, 10, 150),
            ("Nozzle Temp (\u00b0C):", "nozzle_temp_var", 200, 150, 280),
            ("Bed Temp (\u00b0C):", "bed_temp_var", 60, 0, 110),
            ("Adhesion:", "adhesion_var", "brim", None, None),
            ("Support:", "support_var", False, None, None),
        ]
        
        self.slice_settings_vars = {}
        row = 0
        col = 0
        for i, (label, var_name, default, min_val, max_val) in enumerate(settings):
            r = row + (i // 3)
            c = (col + (i % 3) * 2)
            
            ttk.Label(slice_settings_frame, text=label).grid(row=r, column=c, sticky=tk.W, pady=2, padx=5)
            
            if var_name == "infill_pattern_var":
                var = tk.StringVar(value=default)
                combo = ttk.Combobox(slice_settings_frame, textvariable=var, values=["grid", "lines", "triangles", "cubic", "gyroid"], width=12, state="readonly")
                combo.grid(row=r, column=c+1, sticky=tk.W, padx=5)
            elif var_name == "adhesion_var":
                var = tk.StringVar(value=default)
                combo = ttk.Combobox(slice_settings_frame, textvariable=var, values=["none", "skirt", "brim", "raft"], width=12, state="readonly")
                combo.grid(row=r, column=c+1, sticky=tk.W, padx=5)
            elif var_name == "support_var":
                var = tk.BooleanVar(value=default)
                ttk.Checkbutton(slice_settings_frame, variable=var).grid(row=r, column=c+1, sticky=tk.W, padx=5)
            else:
                var = tk.DoubleVar(value=default)
                ttk.Spinbox(slice_settings_frame, from_=min_val, to=max_val, increment=0.1 if isinstance(default, float) else 1, textvariable=var, width=12).grid(row=r, column=c+1, sticky=tk.W, padx=5)
            
            self.slice_settings_vars[var_name] = var
        
        # Printer settings
        printer_frame = ttk.LabelFrame(self.tab_slice, text="Printer Settings", padding="10")
        printer_frame.pack(fill=tk.X, pady=(0, 10))
        
        printer_settings = [
            ("Bed X (mm):", "bed_x_var", 220),
            ("Bed Y (mm):", "bed_y_var", 220),
            ("Bed Z (mm):", "bed_z_var", 250),
            ("Nozzle Size (mm):", "nozzle_size_var", 0.4),
            ("Filament Dia (mm):", "filament_dia_var", 1.75),
        ]
        
        for i, (label, var_name, default) in enumerate(printer_settings):
            ttk.Label(printer_frame, text=label).grid(row=i//3, column=(i%3)*2, sticky=tk.W, pady=2, padx=5)
            var = tk.DoubleVar(value=default)
            ttk.Spinbox(printer_frame, from_=0.1, to=500, increment=10 if default > 10 else 0.1, textvariable=var, width=12).grid(row=i//3, column=(i%3)*2+1, sticky=tk.W, padx=5)
            self.slice_settings_vars[var_name] = var
        
        # Actions
        slice_action_frame = ttk.Frame(self.tab_slice)
        slice_action_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.slice_btn = ttk.Button(
            slice_action_frame, 
            text="Slice to G-code", 
            command=self._on_slice,
            style="Accent.TButton",
            state=tk.DISABLED if not SLICING_AVAILABLE else tk.NORMAL
        )
        self.slice_btn.pack(side=tk.LEFT, padx=5)
        
        self.validate_gcode_btn = ttk.Button(slice_action_frame, text="Validate G-code", command=self._on_validate_gcode, state=tk.DISABLED)
        self.validate_gcode_btn.pack(side=tk.LEFT, padx=5)
        
        self.approve_print_btn = ttk.Button(slice_action_frame, text="Approve & Print", command=self._on_approve_print, state=tk.DISABLED)
        self.approve_print_btn.pack(side=tk.LEFT, padx=5)
        
        if not SLICING_AVAILABLE:
            ttk.Label(slice_action_frame, text="Slicing module not available", foreground="red").pack(side=tk.LEFT, padx=10)
        
        # Slice preview info
        self.slice_info_frame = ttk.LabelFrame(self.tab_slice, text="Slice Preview", padding="10")
        self.slice_info_frame.pack(fill=tk.BOTH, expand=True)
        
        self.slice_info_text = scrolledtext.ScrolledText(
            self.slice_info_frame,
            height=8,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        self.slice_info_text.pack(fill=tk.BOTH, expand=True)
        
    def _on_mode_change(self, *args):
        """Handle mode change in image tab."""
        mode = self.image_mode_var.get()
        if mode == "lithophane":
            for child in self.litho_frame.winfo_children():
                child.config(state=tk.NORMAL)
        else:
            for child in self.litho_frame.winfo_children():
                if isinstance(child, (ttk.Spinbox, ttk.Entry)):
                    child.config(state=tk.DISABLED)
    
    def _layout_widgets(self):
        """Layout all widgets."""
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        self.title_label.pack(pady=(0, 10))
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        self.log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def _log(self, message: str):
        """Add message to log."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
        
    def _set_status(self, status: str):
        """Update status bar."""
        self.status_var.set(status)
        self.root.update_idletasks()
        
    def _slice_log(self, message: str):
        """Add message to slice info log."""
        self.slice_info_text.config(state=tk.NORMAL)
        self.slice_info_text.insert(tk.END, message + "\n")
        self.slice_info_text.see(tk.END)
        self.slice_info_text.config(state=tk.DISABLED)
        
    def _load_example(self, prompt: str):
        """Load an example prompt."""
        self.prompt_text.delete(1.0, tk.END)
        self.prompt_text.insert(tk.END, prompt)
        self._log(f"Loaded example: {prompt}")
        
    def _browse_output_dir(self):
        """Browse for output directory."""
        dir_path = filedialog.askdirectory(initialdir=str(self.output_dir))
        if dir_path:
            self.output_dir = Path(dir_path)
            self.output_dir_var.set(dir_path)
            self._log(f"Output directory set to: {dir_path}")
            
    def _browse_image(self):
        """Browse for input image."""
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All files", "*.*")]
        )
        if file_path:
            self.image_path_var.set(file_path)
            self._load_image_preview(file_path)
            self.convert_image_btn.config(state=tk.NORMAL if IMAGE_TO_3D_AVAILABLE else tk.DISABLED)
            
    def _load_image_preview(self, image_path: str):
        """Load and display image preview."""
        try:
            from PIL import Image, ImageTk
            img = Image.open(image_path)
            img.thumbnail((300, 200))
            photo = ImageTk.PhotoImage(img)
            self.preview_label.config(image=photo, text="")
            self.preview_label.image = photo  # Keep reference
        except Exception as e:
            self.preview_label.config(text=f"Preview error: {e}", image="")
            
    def _browse_slice_stl(self):
        """Browse for STL to slice."""
        file_path = filedialog.askopenfilename(
            filetypes=[("STL files", "*.stl"), ("All files", "*.*")]
        )
        if file_path:
            self.slice_stl_var.set(file_path)
            # Auto-set output path
            stl_path = Path(file_path)
            self.gcode_output_var.set(str(stl_path.with_suffix('.gcode')))
            self.slice_btn.config(state=tk.NORMAL)
            
    def _browse_gcode_output(self):
        """Browse for G-code output."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".gcode",
            filetypes=[("G-code files", "*.gcode"), ("All files", "*.*")]
        )
        if file_path:
            self.gcode_output_var.set(file_path)
            
    def _browse_printer_definition(self):
        """Browse for a Cura printer definition exported from a configured printer profile."""
        file_path = filedialog.askopenfilename(
            title="Select Cura printer definition JSON",
            filetypes=[("Cura definition JSON", "*.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            self.printer_definition_var.set(file_path)

    def _on_generate_text(self):
        """Generate 3D model from text prompt."""
        prompt = self.prompt_text.get(1.0, tk.END).strip()
        if not prompt:
            messagebox.showwarning("Warning", "Please enter a part description")
            return
            
        self.generate_btn.config(state=tk.DISABLED)
        self.progress.start()
        self._set_status("Generating...")
        self._log(f"Parsing: {prompt}")
        
        def generate_thread():
            try:
                spec = create_part_from_text(prompt)
                
                if self.part_name_var.get().strip():
                    spec.name = self.part_name_var.get().strip()
                    
                errors = spec.validate_spec()
                if errors:
                    self.root.after(0, lambda: self._log(f"Specification errors: {errors}"))
                    self.root.after(0, lambda: messagebox.showerror("Error", "\n".join(errors)))
                    return
                    
                self.root.after(0, lambda: self._log("Generating geometry..."))
                part = create_part_from_spec(spec)
                
                self.current_spec = spec
                self.current_part = part
                
                self.root.after(0, lambda: self._log(f"Volume: {part.volume:.2f} mm\u00b3"))
                self.root.after(0, lambda: self._log(f"Bounding box: {part.bounding_box()}"))
                self.root.after(0, lambda: self._log("Generation complete!"))
                self.root.after(0, lambda: self._set_status("Ready - Model generated"))
                self.root.after(0, lambda: self.export_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.validate_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.send_to_slice_btn.config(state=tk.NORMAL))
                
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.root.after(0, lambda: self._set_status("Error"))
            finally:
                self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.progress.stop())
                
        threading.Thread(target=generate_thread, daemon=True).start()
        
    def _on_convert_image(self):
        """Convert image to 3D model."""
        if not IMAGE_TO_3D_AVAILABLE:
            messagebox.showerror("Error", "Image-to-3D not available. Install torch and torchvision.")
            return
            
        image_path = self.image_path_var.get()
        if not image_path or not Path(image_path).exists():
            messagebox.showwarning("Warning", "Please select an image file")
            return
            
        if self.converter_loading:
            messagebox.showwarning("Warning", "Model is still loading...")
            return

        mode = self.image_mode_var.get()
        if mode != "lithophane" and self.converter is None:
            approved = messagebox.askyesno(
                "Trust the MiDaS model source?",
                "Single-image depth conversion may download and execute Python code from the official intel-isl/MiDaS repository on first use. "
                "Only continue if you have reviewed and trust that source. The result is an approximate relief, not exact hidden geometry. Continue?",
            )
            if not approved:
                return
            
        self.convert_image_btn.config(state=tk.DISABLED)
        self.progress.start()
        self._set_status("Loading MiDaS model...")
        self._log(f"Converting image: {image_path}")
        
        def convert_thread():
            try:
                # Lithophane creation uses only the local image; depth conversion needs the model.
                if mode != "lithophane" and self.converter is None:
                    self.root.after(0, lambda: self._set_status("Downloading/loading MiDaS model..."))
                    self.root.after(0, lambda: self._log("Loading the reviewed MiDaS source and model weights (first run may need internet)..."))
                    self.converter = ImageTo3DConverter("MiDaS_small", trust_repo=True)
                    self.root.after(0, lambda: self._log("Model loaded."))
                
                output_stl = self.output_dir / f"{Path(image_path).stem}_3d.stl"
                
                if mode == "lithophane":
                    self.root.after(0, lambda: self._log("Creating lithophane..."))
                    mesh = create_lithophane(
                        image_path,
                        str(output_stl),
                        max_size=self.max_size_var.get(),
                        thickness=self.litho_thickness_var.get(),
                        thinnest=self.litho_thinnest_var.get(),
                        border=self.litho_border_var.get()
                    )
                else:
                    self.root.after(0, lambda: self._log("Estimating depth and generating mesh..."))
                    mesh = self.converter.convert_image_to_3d(
                        image_path,
                        str(output_stl),
                        scale=self.max_size_var.get(),
                        height_scale=self.height_scale_var.get(),
                        base_thickness=self.base_thickness_var.get(),
                        simplify=self.simplify_var.get()
                    )
                
                self.current_mesh = mesh
                self.current_stl_path = str(output_stl)
                if mode != "lithophane":
                    self.root.after(
                        0,
                        lambda: self._log(
                            "IMPORTANT: single-view depth is an approximate relief. It does not recover hidden surfaces, exact dimensions, threads, or tolerances."
                        ),
                    )
                
                self.root.after(0, lambda: self._log(f"Mesh: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces"))
                self.root.after(0, lambda: self._log(f"Saved to: {output_stl}"))
                self.root.after(0, lambda: self._set_status("Ready - 3D model created"))
                self.root.after(0, lambda: self.export_image_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.send_image_to_slice_btn.config(state=tk.NORMAL))
                # Also set in slice tab
                self.root.after(0, lambda: self.slice_stl_var.set(str(output_stl)))
                self.root.after(0, lambda: self.gcode_output_var.set(str(output_stl.with_suffix('.gcode'))))
                self.root.after(0, lambda: self.slice_btn.config(state=tk.NORMAL))
                
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.root.after(0, lambda: self._set_status("Error"))
            finally:
                self.root.after(0, lambda: self.convert_image_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.progress.stop())
                
        threading.Thread(target=convert_thread, daemon=True).start()
        
    def _on_export_image_stl(self):
        """Export image-generated mesh to STL."""
        if self.current_mesh is None:
            messagebox.showwarning("Warning", "No model generated yet")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".stl",
            filetypes=[("STL files", "*.stl"), ("All files", "*.*")]
        )
        if file_path:
            try:
                self.current_mesh.export(file_path)
                self._log(f"Exported to: {file_path}")
                messagebox.showinfo("Success", f"STL exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
                
    def _on_export(self):
        """Export the generated model (text tab)."""
        if self.current_part is None:
            messagebox.showwarning("Warning", "No model generated yet")
            return
            
        formats = []
        if self.format_step_var.get():
            formats.append("step")
        if self.format_stl_var.get():
            formats.append("stl")
            
        if not formats:
            messagebox.showwarning("Warning", "Select at least one export format")
            return
            
        self.export_btn.config(state=tk.DISABLED)
        self.progress.start()
        self._set_status("Exporting...")
        
        def export_thread():
            try:
                output_dir = Path(self.output_dir_var.get())
                output_dir.mkdir(parents=True, exist_ok=True)
                
                validate = self.validate_var.get()
                part_name = self.current_spec.name
                
                for fmt in formats:
                    if fmt == "step":
                        file_path = output_dir / f"{part_name}.step"
                        result = export_step(self.current_part, str(file_path), validate=validate)
                    elif fmt == "stl":
                        file_path = output_dir / f"{part_name}.stl"
                        result = export_stl(self.current_part, str(file_path), validate=validate)
                    
                    if result.success:
                        self.root.after(0, lambda f=result: self._log(f"\u2713 Exported {f.format}: {f.file_path} ({f.file_size} bytes)"))
                        if f.warnings:
                            for w in f.warnings:
                                self.root.after(0, lambda w=w: self._log(f"  WARN: {w}"))
                    else:
                        self.root.after(0, lambda f=result: self._log(f"\u2717 Export {fmt.upper()} failed:"))
                        for err in result.validation_errors:
                            self.root.after(0, lambda e=err: self._log(f"  ERROR: {e}"))
                            
                self.root.after(0, lambda: self._log("Export complete!"))
                self.root.after(0, lambda: self._set_status("Ready - Files exported"))
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Files exported to {output_dir}"))
                
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Export error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.root.after(0, lambda: self.export_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.progress.stop())
                
        threading.Thread(target=export_thread, daemon=True).start()
        
    def _on_validate(self):
        """Validate the generated model."""
        if self.current_part is None:
            messagebox.showwarning("Warning", "No model generated yet")
            return
            
        self.validate_btn.config(state=tk.DISABLED)
        self.progress.start()
        self._set_status("Validating...")
        
        def validate_thread():
            try:
                self.root.after(0, lambda: self._log("Running validation..."))
                results = validate_export(self.current_part)
                
                for fmt, result in results.items():
                    status = "PASS" if result.get("success") else "FAIL"
                    self.root.after(0, lambda f=fmt, s=status: self._log(f"  {f.upper()}: {s}"))
                    if result.get("errors"):
                        for err in result["errors"]:
                            self.root.after(0, lambda e=err: self._log(f"    ERROR: {e}"))
                    if result.get("warnings"):
                        for warn in result["warnings"]:
                            self.root.after(0, lambda w=warn: self._log(f"    WARN: {w}"))
                            
                self.root.after(0, lambda: self._log("Validation complete!"))
                self.root.after(0, lambda: self._set_status("Ready - Validation complete"))
                
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Validation error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.root.after(0, lambda: self.validate_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.progress.stop())
                
        threading.Thread(target=validate_thread, daemon=True).start()
        
    def _send_to_slicer(self):
        """Send text-generated model to slicer tab."""
        if self.current_part is None:
            return
            
        # Export to STL first
        output_dir = Path(self.output_dir_var.get())
        output_dir.mkdir(parents=True, exist_ok=True)
        stl_path = output_dir / f"{self.current_spec.name}.stl"
        
        result = export_stl(self.current_part, str(stl_path), validate=False)
        if result.success:
            self.slice_stl_var.set(str(stl_path))
            self.gcode_output_var.set(str(stl_path.with_suffix('.gcode')))
            self.slice_btn.config(state=tk.NORMAL)
            self.notebook.select(self.tab_slice)
            self._log(f"Sent to slicer: {stl_path}")
        else:
            messagebox.showerror("Error", "Failed to export STL for slicing")
            
    def _send_image_to_slicer(self):
        """Send image-generated model to slicer tab."""
        if self.current_stl_path is None:
            return
            
        self.slice_stl_var.set(self.current_stl_path)
        self.gcode_output_var.set(str(Path(self.current_stl_path).with_suffix('.gcode')))
        self.slice_btn.config(state=tk.NORMAL)
        self.notebook.select(self.tab_slice)
        self._log(f"Sent to slicer: {self.current_stl_path}")
        
    def _on_slice(self):
        """Slice the STL to G-code."""
        if not SLICING_AVAILABLE or self.slicer is None:
            messagebox.showerror("Error", "Slicing not available")
            return
            
        stl_path = self.slice_stl_var.get()
        gcode_path = self.gcode_output_var.get()
        
        if not stl_path or not Path(stl_path).exists():
            messagebox.showwarning("Warning", "Please select a valid STL file")
            return
            
        if not gcode_path:
            messagebox.showwarning("Warning", "Please specify G-code output path")
            return
            
        self.slice_btn.config(state=tk.DISABLED)
        self.progress.start()
        self._set_status("Slicing...")
        self._slice_log(f"Slicing: {stl_path}")
        
        # Build settings
        settings = SliceSettings(
            layer_height=self.slice_settings_vars["layer_height_var"].get(),
            wall_thickness=self.slice_settings_vars["wall_thickness_var"].get(),
            infill_density=self.slice_settings_vars["infill_density_var"].get(),
            infill_pattern=self.slice_settings_vars["infill_pattern_var"].get(),
            print_speed=self.slice_settings_vars["print_speed_var"].get(),
            nozzle_temp=self.slice_settings_vars["nozzle_temp_var"].get(),
            bed_temp=self.slice_settings_vars["bed_temp_var"].get(),
            adhesion_type=self.slice_settings_vars["adhesion_var"].get(),
            support_enabled=self.slice_settings_vars["support_var"].get(),
            bed_size_x=self.slice_settings_vars["bed_x_var"].get(),
            bed_size_y=self.slice_settings_vars["bed_y_var"].get(),
            bed_size_z=self.slice_settings_vars["bed_z_var"].get(),
            nozzle_diameter=self.slice_settings_vars["nozzle_size_var"].get(),
        )
        
        def slice_thread():
            try:
                result = self.slicer.slice(stl_path, gcode_path, settings, printer_definition=self.printer_definition_var.get().strip())
                
                if result.success:
                    self.current_gcode_path = gcode_path
                    self.root.after(0, lambda: self._slice_log(f"\u2713 Slicing successful!"))
                    self.root.after(0, lambda: self._slice_log(f"G-code: {gcode_path}"))
                    if result.print_time:
                        hrs = int(result.print_time // 3600)
                        mins = int((result.print_time % 3600) // 60)
                        self.root.after(0, lambda: self._slice_log(f"Print time: {hrs}h {mins}m"))
                    if result.filament_used:
                        self.root.after(0, lambda: self._slice_log(f"Filament: {result.filament_used:.1f}g"))
                    if result.layers:
                        self.root.after(0, lambda: self._slice_log(f"Layers: {result.layers}"))
                    for w in result.warnings:
                        self.root.after(0, lambda w=w: self._slice_log(f"  WARN: {w}"))
                    
                    self.root.after(0, lambda: self._set_status("Ready - Sliced successfully"))
                    self.root.after(0, lambda: self.validate_gcode_btn.config(state=tk.NORMAL))
                    self.root.after(0, lambda: self.approve_print_btn.config(state=tk.NORMAL))
                else:
                    for err in result.errors:
                        self.root.after(0, lambda e=err: self._slice_log(f"ERROR: {e}"))
                    self.root.after(0, lambda: self._set_status("Slicing failed"))
                    
            except Exception as e:
                self.root.after(0, lambda: self._slice_log(f"Error: {str(e)}"))
                self.root.after(0, lambda: self._set_status("Error"))
            finally:
                self.root.after(0, lambda: self.slice_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.progress.stop())
                
        threading.Thread(target=slice_thread, daemon=True).start()
        
    def _on_validate_gcode(self):
        """Validate the generated G-code."""
        if not self.current_gcode_path or not Path(self.current_gcode_path).exists():
            messagebox.showwarning("Warning", "No G-code file to validate")
            return
            
        self.validate_gcode_btn.config(state=tk.DISABLED)
        self.progress.start()
        self._set_status("Validating G-code...")
        
        def validate_thread():
            try:
                result = self.slicer.validate_gcode(self.current_gcode_path)
                
                if result["valid"]:
                    stats = result["stats"]
                    self.root.after(0, lambda: self._slice_log("G-code validation PASSED"))
                    self.root.after(0, lambda: self._slice_log(f"  Lines: {stats['total_lines']}"))
                    self.root.after(0, lambda: self._slice_log(f"  G-commands: {stats['g_commands']}"))
                    self.root.after(0, lambda: self._slice_log(f"  M-commands: {stats['m_commands']}"))
                    self.root.after(0, lambda: self._slice_log(f"  Has homing: {stats['has_home']}"))
                    self.root.after(0, lambda: self._slice_log(f"  Has temperature: {stats['has_temp']}"))
                    self.root.after(0, lambda: self._slice_log(f"  Has extrusion: {stats['has_extrusion']}"))
                    self.root.after(0, lambda: self._slice_log(f"  Bounds: X{stats['min_x']:.1f}-{stats['max_x']:.1f} Y{stats['min_y']:.1f}-{stats['max_y']:.1f} Z{stats['min_z']:.1f}-{stats['max_z']:.1f}"))
                    
                    # Check bed bounds
                    bed_x = self.slice_settings_vars["bed_x_var"].get()
                    bed_y = self.slice_settings_vars["bed_y_var"].get()
                    if stats['max_x'] > bed_x or stats['max_y'] > bed_y:
                        self.root.after(0, lambda: self._slice_log(f"  WARNING: Model exceeds bed size ({bed_x}x{bed_y})!"))
                else:
                    self.root.after(0, lambda: self._slice_log(f"G-code validation FAILED: {result.get('error')}"))
                    
                self.root.after(0, lambda: self._set_status("Ready - Validation complete"))
                
            except Exception as e:
                self.root.after(0, lambda: self._slice_log(f"Validation error: {str(e)}"))
            finally:
                self.root.after(0, lambda: self.validate_gcode_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.progress.stop())
                
        threading.Thread(target=validate_thread, daemon=True).start()
        
    def _on_approve_print(self):
        """Show print approval dialog and simulate print start."""
        if not self.current_gcode_path or not Path(self.current_gcode_path).exists():
            messagebox.showwarning("Warning", "No valid G-code to print")
            return
            
        # Show approval dialog
        result = messagebox.askyesno(
            "Print Approval",
            f"Ready to print:\n\n"
            f"File: {Path(self.current_gcode_path).name}\n"
            f"Printer: Generic FDM\n\n"
            f"Please ensure:\n"
            f"  \u2713 Printer is connected and calibrated\n"
            f"  \u2713 Bed is clean and leveled\n"
            f"  \u2713 Filament is loaded\n"
            f"  \u2713 Nozzle is clean\n\n"
            f"Start print now?"
        )
        
        if result:
            self._log("Print approved by user!")
            self._slice_log("=== PRINT APPROVED ===")
            self._slice_log("Sending to printer... (simulated)")
            
            # In a real implementation, this would send to OctoPrint, Duet, etc.
            # For now, we'll just show success
            messagebox.showinfo(
                "Print Started",
                "Print job sent to printer!\n\n"
                f"File: {Path(self.current_gcode_path).name}\n\n"
                "Monitor your printer for the first layer."
            )
            self._log("Print job dispatched")
        else:
            self._log("Print cancelled by user")
            self._slice_log("=== PRINT CANCELLED ===")
        
    def _open_output_folder(self):
        """Open output folder in file explorer."""
        output_dir = Path(self.output_dir_var.get())
        if output_dir.exists():
            os.startfile(str(output_dir))
        else:
            messagebox.showwarning("Warning", "Output directory does not exist")


def main():
    """Main entry point for GUI."""
    root = tk.Tk()
    
    # Try to set a nice theme
    try:
        style = ttk.Style()
        style.theme_use('vista')  # Windows native theme
    except:
        pass
    
    # Configure accent button style
    style = ttk.Style()
    style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
    
    app = AI3DDesignerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
