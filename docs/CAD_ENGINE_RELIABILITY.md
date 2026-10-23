# CAD Engine Reliability: current behavior and usage

This document describes the guarded CAD-to-mesh-to-slicing pipeline. The project aims to produce inspectable, parameterized geometry; it does **not** promise exact reconstruction of every arbitrary object from a text prompt or one photograph.

## Geometry conventions

- Kernel coordinates and exported mechanical dimensions are millimeters.
- A `PartSpec.unit_system` is the fallback for dimensions whose `ParameterSpec.unit` was omitted. An explicitly provided parameter unit takes precedence.
- Feature translations are always millimeters. Rotation values are Euler degrees in X/Y/Z order.
- The first feature must use the `union` operation; later features may use union, difference, or intersection.
- Parent dependencies are stably topologically ordered. Duplicate feature IDs, missing parents, cycles and empty boolean results fail with errors rather than being silently ignored.

## Supported basic features

The engine supports box, cylinder, sphere, cone, torus, wedge, polygon extrusion, polygon revolution, multi-section loft, and profile/path sweep. All values must be finite, and required dimensions must be present.

### Polygon metadata formats

Profiles are closed polygon wires. Use at least three distinct points for a closed profile and at least two for an open sweep path. A profile can be an array of points or an object:

```json
{
  "unit": "mm",
  "points": [[0, 0], [20, 0], [20, 10], [0, 10]]
}
```

- **Extrusion**: set `type: "extrusion"`, `parameters.height`, and `metadata.profile`.
- **Revolution**: set `type: "revolution"` and `metadata.profile`. A two-coordinate profile is interpreted as radius/height in the XZ plane and revolved around the Z axis. The optional `parameters.angle` is in degrees from greater than zero through 360; omitted means 360 degrees.
- **Loft**: set `type: "loft"` and `metadata.profiles` to at least two profile objects. Each section can specify `z` or a three-number `offset`. Use matching, consistently ordered closed outlines for predictable lofts.
- **Sweep**: set `type: "sweep"`, `metadata.profile`, and `metadata.path`; the path is open. Complex path/profile combinations must be tested in the preview because kernel support and topology can still fail.

Profile points, offsets and explicit profile units are converted to millimeters. OpenCascade/build123d can still reject self-intersecting, twisted, or otherwise non-planar/degenerate profiles; the engine returns a feature-specific error instead of claiming success.

## Natural-language parser boundaries

The deterministic rule parser is deliberately conservative:
- It recognizes dimensioned primitive descriptions and common dimension triplets such as `50 x 30 x 10 mm box`.
- Mixed explicit length units are normalized to millimeters.
- A single centered through-hole is implemented as a Boolean subtraction for a supported box/cylinder, and a tube/pipe can be built from an outer cylinder minus a specified inner bore.
- A tube requires its inner diameter or wall thickness. A shape without its required dimensions is rejected rather than filled with invented defaults.
- Multiple-hole patterns are not inferred without explicit coordinates/spacing; unsupported language returns an error.
- Free-form LLM output remains an untrusted proposal and must pass schema and geometry validation.

The parser is not a substitute for a dimensioned engineering drawing, GD&T, material specification, or tolerance design.

## Drawing OCR workflow

The FastAPI service includes bounded PDF/raster OCR using Tesseract and PyMuPDF. The project page can analyze privately uploaded source drawings, store extracted text/annotations with the project version, and present the extraction for review. Recognized annotations include dimension triplets, diameter/radius values, tolerances, fits, common threads, material names, surface-finish notation and view labels when legible.

The OCR route rejects unsupported file types, oversized inputs, PDFs over eight pages, and rendered pages/images over 24 megapixels. The service image installs Tesseract English data; health reports OCR availability only when the Python packages and binary are detected.

OCR output is explicitly marked for review. The user must edit/confirm a dimensioned description before the generator attempts CAD creation. The generator uses the conservative text parser and only returns STEP/STL if the specification, geometry and exports pass validation. A drawing's views, internal features, GD&T, and full mechanical intent are not automatically reconstructed; unsupported/underspecified descriptions fail instead of producing a guessed model. Outputs are marked as approximations until compared against the source drawing.

## Mesh/image conversion

`build_closed_heightfield` constructs top, bottom and side surfaces and checks watertightness and positive volume. Lithophanes and single-view MiDaS depth images produce approximate relief meshes. One image cannot reliably recover hidden surfaces, scale, threads, internal cavities, manufacturing dimensions or tolerances. For photogrammetry/true multi-view reconstruction, use validated multi-view imagery and an appropriately trained reconstruction pipeline.

Loading the MiDaS repository can download and execute external Python code. The desktop GUI now asks for explicit consent before enabling that flow and does not globally override PyTorch Hub's trust checks.

## STL/STEP validation

STEP export remains a CAD-kernel boundary-representation export. STL validation rejects missing/empty files, non-finite coordinates, open/non-watertight surfaces, inconsistent orientation, degenerate triangles and invalid/empty manifold construction. This is a geometry validity gate, not a certification that an object meets a functional requirement or will print successfully.

## Slicing and printing

- A real `CuraEngine` executable and the matching Cura printer/extruder definition JSON(s) are required.
- The GUI accepts more than one Cura definition file (selected together). Definition files must match the target printer, extruder, firmware and installed CuraEngine version.
- The old “basic” fallback created only a few placeholder layers and must not be used for printing. It has been removed; without CuraEngine/profile, slicing now returns a clear failure and does not create G-code.
- Input STL must be watertight, have positive volume, and fit the configured build dimensions. G-code must be non-empty, have recognized movement commands, positive extrusion and layer markers before the engine reports slicing success.
- The desktop GUI's **Approve Print** button is simulation-only. This project does not currently connect to a physical printer, OctoPrint, Klipper, or a network print controller. No real print is started from the desktop app.
- Structural G-code checks are heuristic, not firmware safety certification. Inspect the actual Cura layer preview, travel, support, temperatures, start/end G-code and bed coordinates before sending it through a verified printer-host workflow.

## Tests and release path

The `CAD Engine Tests` workflow compiles the Python source and runs the regression suite for specification constraints, units, feature dependencies, profiles, conservative parsing, STL/manifold validation, image heightfield meshes, slicer settings and prevention of placeholder G-code.

Use the feature branch and verify its CI before merging. Passing regression tests are necessary but not enough: exercise representative engineering parts with known dimensions in the GUI, inspect STEP/STL exports in a CAD viewer, and preview slicer output for the actual printer. Do not claim arbitrary CAD generation is perfect.
