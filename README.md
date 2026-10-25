# Offline AI 3D Designer

An offline CAD generator that creates 3D models from natural language descriptions. Uses **build123d** for geometry operations and exports to **STEP** and **STL** formats.

## Features

- 🎯 **Conservative text-to-CAD**: Dimensioned descriptions for supported primitives; underspecified geometry fails instead of inventing dimensions
- 🔧 **Feature-based geometry**: Box, cylinder, sphere, cone, torus, wedge, polygon extrusion, revolution, loft and sweep
- ⚙️ **Boolean operations**: Union, difference and intersection, with dependency-cycle and empty-solid checks
- 📐 **Unit support**: mm, cm, inch and m normalized to kernel millimeters
- 📤 **Exports**: STEP boundary-representation and STL mesh exports with stronger manifold/watertight validation
- 🖼️ **Image relief and drawing OCR**: Closed heightfield/lithophane meshes plus OCR text/annotation extraction for supported PDF and raster drawings (not exact automatic reconstruction)
- 🧩 **Slicing integration**: CuraEngine-backed slicing only; no fake placeholder G-code fallback
- 🖥️ **CLI & GUI**: Command-line and desktop graphical interfaces
- 🧪 **Regression tests**: CAD, unit, profile, parser, mesh and slicer safety tests

## Quick Start

### Installation

```bash
# Clone or navigate to the project
cd "Offline AI 3D Designer"

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate.bat  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### Command Line Usage

```bash
# Basic box with hole
python -m ai3d_designer.cli "Create a 40x20x10mm box with a 5mm hole"

# Cylinder
python -m ai3d_designer.cli "cylinder radius 10 height 50"

# Sphere
python -m ai3d_designer.cli "sphere radius 15"

# Custom output and name
python -m ai3d_designer.cli "50x30x20 box" --output ./my_parts --name my_box

# Validate only (no export)
python -m ai3d_designer.cli "40x20x10 box" --validate-only

# Export only STEP format
python -m ai3d_designer.cli "box 30x30x30" --format step
```

### GUI Usage

```bash
# Run the GUI
python run_gui.py

# Or on Windows, double-click run.bat
```

The GUI provides:
- Text input for natural language descriptions
- Quick example buttons
- Export format selection (STEP/STL)
- Output directory selection
- Real-time log output
- Validation and export buttons

## Supported Natural Language Patterns

| Pattern | Example |
|---------|---------|
| Box with dimensions | `40x20x10 box`, `50x30x20mm box` |
| Box with hole | `Create a 40x20x10mm box with a 5mm hole` |
| Cylinder | `cylinder radius 10 height 50` |
| Sphere | `sphere radius 15` |

## Project Structure

```
Offline AI 3D Designer/
├── src/ai3d_designer/
│   ├── cli/                 # Command-line interface
│   ├── gui/                 # Desktop GUI
│   ├── core/spec/           # Pydantic CAD specification models
│   ├── core/geometry/       # build123d geometry engine
│   ├── core/export/         # STEP/STL export and validation
│   └── core/nlp/            # Local-LLM and rule-based parsing
├── tests/
│   ├── test_spec.py         # Spec model tests
│   └── test_geometry.py     # Geometry engine tests
├── output/                  # Generated files (created automatically)
├── run_gui.py               # GUI launcher
├── run.bat                  # Windows batch launcher
├── requirements.in           # Pinned desktop dependencies
└── pyproject.toml           # Project configuration
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_geometry.py -v
```

## Engineering accuracy and limitations

The rule-based parser only generates geometry for recognized descriptions with enough dimensions. It may reject ambiguous or unsupported text; this is preferable to presenting a guessed shape as dimensionally correct. Extrusion/revolution/loft/sweep use explicit polygon profile metadata.

Single-view images produce approximate relief meshes and lithophanes. A single photo does not contain enough information to guarantee hidden geometry, exact scale, dimensions, threads, fits, or tolerances. Drawing OCR extracts visible text and common annotations (dimension triplets, diameters, radii, fits, threads, tolerances, materials and surface finish) when the Tesseract/PyMuPDF runtime is configured. It is not a complete drawing-understanding system: users must review the extraction and provide a supported, fully dimensioned description before CAD generation. Exact automatic reconstruction of arbitrary views remains unimplemented.

The slicer requires a compatible CuraEngine and actual printer/extruder definitions. Without those it returns a clear failure rather than dummy G-code. Its structural checks are not a substitute for the real slicer preview and printer-specific safety review. The desktop "Approve Print" action is currently simulation-only; no physical printer transport is implemented.

See [CAD Engine Reliability Guide](docs/CAD_ENGINE_RELIABILITY.md) for feature metadata, coordinate conventions, supported operations and print-safety boundaries.

## Requirements

- Python 3.10+
- build123d (CAD kernel)
- OCP (OpenCascade Python bindings)
- pydantic (data validation)
- numpy (numerical operations)

See `pyproject.toml` for the installable package and optional development dependencies; `requirements.in` and `requirements.lock` are the pinned Windows environment inputs.

## License

MIT License - Feel free to use and modify.
