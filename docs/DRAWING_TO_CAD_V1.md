# Structured Drawing-to-CAD v1

## What changed

The authenticated Python API now supplements OCR with a typed drawing blueprint and deterministic build123d/OpenCASCADE generation. The project UI displays the blueprint and lets the user review/edit the supported numeric parameters before requesting STEP/STL output.

The path is:

1. Next.js retrieves the user's private source file and sends it to POST /api/v1/ocr/extract through the existing authenticated server-side proxy.
2. The backend extracts text/annotations using the current PyMuPDF/Tesseract pipeline, renders each PDF page for visual inspection, inventories explicit dimension values, and collects simple vector-PDF circle/rectangle candidates as evidence.
3. If a vision provider is configured, it receives the rendered pages, the dimension inventory and a JSON Schema. Otherwise the engine uses conservative explicitly-labelled-text fallback.
4. Numeric values are grounded by both value and dimension type (diameter, linear, radius, angle). Numeric fields that cannot be grounded are cleared; defaults and warnings are surfaced in the editor.
5. The user reviews the blueprint and submits it to POST /api/v1/generate. The deterministic generator builds the model, checks OpenCASCADE validity, checks for a single solid and positive volume, exports STEP/STL, and rejects an STL that is not watertight.
6. The existing Next.js generation route stores both exports privately in Vercel Blob and records the new project version.

## Vision provider configuration

Set these only on the Python CAD service (Railway Preview service for Preview testing).

### Ollama

- DRAWING_VISION_PROVIDER=ollama
- DRAWING_VISION_URL=https://<reachable-ollama-host> (the Ollama server base URL; it appends /api/chat)
- DRAWING_VISION_MODEL=qwen2.5vl:7b or another vision-capable Ollama model

Do not set the URL to http://localhost:11434 on Railway unless Ollama actually runs inside the same container. In a Railway container, localhost points to that container, not to the developer's laptop.

### OpenAI-compatible vision API

- DRAWING_VISION_PROVIDER=openai_compatible
- DRAWING_VISION_URL=https://<provider-base>/v1 (the adapter appends /chat/completions)
- DRAWING_VISION_MODEL=<vision-capable-model-name>
- DRAWING_VISION_API_KEY=<secret> (only if the provider requires one)

The provider must support image input and strict response_format: json_schema output. Keep the key server-side; do not create a NEXT_PUBLIC_... variable for it. If the provider is unreachable or rejects the schema, extraction falls back to labelled-text mode and marks the blueprint for review. A configured endpoint only means configured, not that the model is reachable or that its interpretation is accurate.

When no vision provider is configured, the feature remains useful for explicit dimensions labelled in recognized text, but it is not a visual scene-understanding engine. An unlabelled or scanned blueprint may produce an unresolved blueprint and require review.

## Blueprint schema and supported v1 geometry

The public schema is in src/ai3d_designer/drawing_to_cad/blueprint.py.

Supported base bodies:

- rotational_flange: circular flange/plate, optional central bore.
- prismatic_box: rectangular/polygonal extrusion.
- sheet_enclosure: simple open-top rectangular enclosure with a floor and uniform walls.
- revolved_profile: explicitly specified [radius, z] polygon revolved around Z.

Supported features:

- circular pattern of cylindrical cuts with evenly spaced holes;
- single cylindrical through/blind hole;
- cylindrical or rectangular through/blind pocket;
- fillet by explicit edge scope and radius.

Default solid height is 10 mm when absent; the field is flagged. The open-top enclosure wall defaults to 2.5 mm when absent; that field is flagged. Defaults make a provisional model possible but are not evidence from the drawing and must be reviewed. No default is treated as certified engineering data.

## Explicitly out of scope for this version

The v1 generator does not create exact involute/sprocket teeth, gear profiles, sheet-metal bends/flanges, threads, GD&T-driven geometry, arbitrary freeform surfaces, multi-body assemblies, or hidden geometry that cannot be inferred from the views. Such geometry must be marked in unsupported_geometry, which blocks export rather than silently substituting a smooth cylinder or box.

Simple vector PDF path candidates are evidence only. Their bounding rectangles are not automatically treated as real millimetre dimensions because PDF scale may depend on the view and drawing metadata. Calibration of PDF vector scale against a labelled dimension is a follow-up milestone.

## API contracts

### POST /api/v1/ocr/extract

Authenticated JSON request:

~~~json
{
  "fileName": "flange.pdf",
  "mimeType": "application/pdf",
  "fileBase64": "<base64 file bytes>"
}
~~~

The response retains the existing spec OCR fields and adds:

- blueprint: typed structured blueprint (or unresolved type if evidence is insufficient);
- dimensionInventory: explicit/recognized dimensions and kind;
- vectorGeometry: capped PDF path candidates in PDF points, not mm;
- blueprintSource, blueprintSourcePages, blueprintClearedFields, blueprintVisionModel.

### POST /api/v1/generate

Requires the current service-token authentication and reviewed=true. The server accepts a blueprint object as well as the legacy reviewedDescription field. When blueprint is supplied, deterministic blueprint generation takes precedence and does not require a free-text part prompt. The response contains Base64 STEP/STL, the normalized blueprint, validation metrics and warnings. The existing Vercel route persists output blobs and project versions.

## Safety and correctness limits

- Grounding verifies that a value appears in the inventory with the expected dimension kind; it cannot prove the value was attached to the correct feature or view. The UI review and a curated drawing golden set remain required.
- Visual models can still hallucinate feature associations or omit hidden details. A schema-valid answer is not proof of geometrical correctness.
- A valid single solid and watertight STL prove kernel/mesh properties, not equivalence to the original engineering drawing, tolerance compliance, material properties or suitability for manufacture.
- Review every model in a CAD viewer against the original source before use in manufacturing.

## Regression tests

tests/test_drawing_to_cad_blueprint.py checks defaults, dimension grounding, unsupported sprocket handling, vector-PDF rendering, and STEP/STL generation. tests/test_ocr_api.py verifies the existing API accepts a reviewed structured blueprint without requiring a shape phrase in the description.
