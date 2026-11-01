# Hardware Fit Check

## Purpose

The hardware fit-check workflow compares a selected component's confirmed width, depth, and height with a user's confirmed enclosure interior dimensions. It is an axis-aligned bounding-box check, not a full CAD interference, thermal, or manufacturing analysis.

## Web workflow

Authenticated users can open `/dashboard/fit-check`. The page loads the hardware preset list, requires confirmation of the exact component model/revision, accepts enclosure interior dimensions, and displays clearances, shortfalls, warnings, and limitations.

The Next.js route `/api/cad/fit-check/presets` proxies the protected Python endpoint `GET /api/v1/fit-check/presets`. The `POST /api/cad/fit-check` route proxies `POST /api/v1/fit-check`. Both require an application session; state-changing requests also require same-origin validation. Other direct CAD-generation routes remain disabled so they cannot bypass project persistence/quota checks.

## Service request

Example body for `POST /api/v1/fit-check`:

```json
{
  "presetId": "esp32_devkit",
  "componentConfirmed": true,
  "clearanceMm": 1.5,
  "enclosure": {
    "name": "ESP32 enclosure",
    "interior_width": 31.0,
    "interior_depth": 58.0,
    "interior_height": 22.0,
    "wall_thickness": 2.0,
    "confirmed": true
  }
}
```

For custom component requests, provide `component` instead of `presetId`, and set its `confirmed` property only after verifying the source dimensions. Exactly one of `presetId` and `component` must be supplied. The service rejects unconfirmed component or enclosure dimensions.

## Presets and provenance

The built-in presets are starting points, not universal truths for every board variant. Review the manufacturer's datasheet for the exact product revision before confirming dimensions or mounting-hole locations. The generic industrial IoT sensor node is marked as a default/example rather than a datasheet-confirmed product.

## Enclosure body and lid helpers

The Python `generate_enclosure_for_component()` helper creates an open-top enclosure-body PartSpec. `generate_lid_for_enclosure()` creates a separate lid PartSpec with a locating lip. They are separate physical pieces and must be validated/exported separately; do not Boolean-union a removable lid into the body. These helpers currently exist in the Python module and are regression-tested; they are not yet an end-to-end web project-generation workflow.

Derived geometry parameters are marked unconfirmed and must be reviewed before export. The fit-check API itself returns a report; it does not persist a project or create STEP/STL downloads.

## Limitations

- The current check is axis-aligned; it does not try 90-degree rotations or arbitrary placements.
- Mounting-hole alignment is checked only when enclosure boss coordinates are supplied.
- The check does not analyse keep-out volumes, port/cable access, heat, material, structural strength, tolerances, or printability.
- A passing result means only that the requested bounding dimensions fit under the supplied clearance rule.

## Tests

Run from the repository root with the Python environment installed:

```powershell
python -m pytest tests/test_fitcheck.py tests/test_fitcheck_api.py -q
```

The repository CI workflow also compiles the Python package, runs all Python regression tests, and builds the Railway Docker image. The integration PR must not be treated as fully verified until those jobs execute successfully.
