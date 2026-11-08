# Drawing Measurement Review and CAD Association v1

**Status:** The transcription-review ledger is on main via PR #29. Explicit, user-selected CAD field associations are implemented in the current feature branch and remain subject to PR CI/review.
**Purpose:** Preserve source measurements as immutable evidence while allowing a user to deliberately associate a confirmed reading with one compatible Blueprint field.

## Immutable source and review sidecar

The original OCR/vision response remains immutable in `ProjectVersion.spec.ocrResults[].spec.blueprint.visual_measurements`.

User decisions are stored beside it at `ProjectVersion.spec.ocrResults[].visualMeasurementReviews`. Each decision references a candidate by its array index and records:

- Decision: `confirmed_reading` or `rejected`.
- User-reviewed numeric value and unit for confirmed readings.
- Optional plain-language feature description and review note.
- Optional `targetBinding` selecting an exact base-sketch field or a feature index/field.
- Server-generated review timestamp and authenticated user ID.

No source OCR value, source visual candidate or source Blueprint field is overwritten when a review or association is saved.

## Explicit CAD field association

The review UI lists only compatible Blueprint targets. The user must select one explicitly; AI feature hints and matching labels never create a binding automatically.

Supported base-sketch targets are outer diameter, central bore diameter, overall length, overall width, solid thickness, and sheet-enclosure wall thickness, with body-type restrictions.

Supported feature targets are allowlisted by feature type: hole/pattern count, diameter, explicit radius fields, pattern angles, ring-step diameters/depth, pocket dimensions/depth, and fillet radius. Ambiguous coordinate offsets and unsupported fields are deliberately excluded.

The authenticated `POST /api/projects/[projectId]/drawing-review` route validates:
- Same-origin request, authentication, project ownership and paid-feature entitlement.
- Bounded request size, unique candidate indices and valid candidate range.
- Candidate kind/unit compatibility with the selected target.
- Feature index and field allowlists, body-type restrictions and field-specific limits.
- At most one candidate mapped to a target field in a single save.

Length values are converted to millimetres when a saved association is applied. Angles remain degrees and count values remain integers. A saved confirmed association is applied to a copied Blueprint only when the user requests reviewed CAD generation. The original saved Blueprint and OCR evidence remain untouched. Any direct edit to a mapped field or removal of a feature invalidates affected bindings instead of silently retargeting them.

## UI behavior and engineering boundary

The drawing panel lets the user correct a reading, optionally select an exact CAD field, confirm/reject the reading, and save the review. A binding is applied only when the reading is confirmed and the association is saved. Changing the value, unit, target, body type, or relevant feature state resets or invalidates the affected approval.

A manual field association records the user's intended mapping; it does **not** prove that a dimension leader/arrow or extension line points to the selected feature or view. The user must compare the source drawing and the CAD target. Visual candidates remain separate from the source Blueprint. No unreviewed or AI-inferred candidate is promoted into CAD geometry.

The CAD geometry generator remains deterministic. Export validity and a saved binding do not establish drawing accuracy, tolerance compliance, strength, manufacturability, or physical print acceptance.

## Verification

The web route regression script covers same-origin rejection, owner-scoped lookup, valid length/angle/count readings, unit-kind mismatch, duplicate candidate indices, unknown candidate/feature indices, incompatible CAD fields and body/profile combinations, unsupported feature fields, duplicate target bindings, rejected-candidate binding prevention, audit logging, and preservation of original OCR/Blueprint evidence. The `test:drawing-measurement-bindings` suite verifies millimetre normalization, application to a defensive Blueprint copy, and rejection of pending, unsaved or invalid measurements.
