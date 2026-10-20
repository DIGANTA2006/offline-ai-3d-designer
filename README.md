# Offline AI 3D Designer

An offline CAD generator that creates 3D models from natural language descriptions. Uses **build123d** for geometry operations and exports to **STEP** and **STL** formats.

## Features

- 🎯 **Natural Language Input**: Describe parts in plain English
- 🔧 **Primitive Shapes**: Box, Cylinder, Sphere, Cone, Torus, Wedge
- ⚙️ **Boolean Operations**: Union, Difference, Intersection
- 📐 **Unit Support**: mm, cm, inch, m
- 📤 **Export Formats**: STEP (CAD) and STL (3D printing)
- ✅ **Validation**: Geometry validation before export
- 🖥️ **CLI & GUI**: Command-line and graphical interfaces
- 🧪 **Tested**: Comprehensive test suite

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
pip install -r requirements.txt
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
│   ├── cli/main.py          # Command-line interface
│   ├── gui/app.py           # Tkinter GUI
│   ├── spec/models.py       # Pydantic data models
│   ├── geometry/engine.py   # build123d geometry engine
│   └── export/exporter.py   # STEP/STL export with validation
├── tests/
│   ├── test_spec.py         # Spec model tests
│   └── test_geometry.py     # Geometry engine tests
├── output/                  # Generated files (created automatically)
├── run_gui.py               # GUI launcher
├── run.bat                  # Windows batch launcher
├── requirements.txt         # Python dependencies
└── pyproject.toml           # Project configuration
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_geometry.py -v
```

## Requirements

- Python 3.10+
- build123d (CAD kernel)
- OCP (OpenCascade Python bindings)
- pydantic (data validation)
- numpy (numerical operations)

See `requirements.txt` for complete list.

## License

MIT License - Feel free to use and modify.
