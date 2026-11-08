# Drawing Measurement Review Ledger v1

**Status:** Draft implementation in PR #29  
**Purpose:** Persist a user's review of image-read measurement candidates without converting those candidates into CAD parameters.

## Data contract

The original OCR/vision response remains immutable in \`ProjectVersion.spec.ocrResults[].spec.blueprint.visual_measurements\`.

User decisions are stored beside it at \`ProjectVersion.spec.ocrResults[].visualMeasurementReviews\`. Each decision references a candidate by its array index and records:

- Decision: \`confirmed_reading\` or \`rejected\`.
- User-reviewed numeric value and unit for confirmed readings.
- Optional plain-language feature description and review note.
- Server-generated review timestamp and authenticated user ID.

The review API is:

\`POST /api/projects/[projectId]/drawing-review\`

The route enforces same-origin requests, authenticated project ownership, the shared paid-feature entitlement check, bounded request size, unique candidate indices, candidate index range, supported units for the candidate kind, and finite/ranged values. The original OCR candidate object is not overwritten. Audit logging records the counts of confirmed and rejected readings.

## UI behavior

The drawing panel allows the user to correct the transcribed value/unit, describe which feature the callout refers to, add a note, and explicitly confirm or reject a reading. Any edit resets the decision to pending. The user saves the decisions explicitly; they are restored when the project page is reloaded.

**Critical engineering boundary:** confirming a reading means the person confirms the transcription shown by the review UI. It does not prove that the dimension leader/arrow is associated with the described feature, and it does not map that reading to a CAD parameter. The visual candidates remain separate from the Blueprint fields. They are stripped of UI-only review properties before the Blueprint is submitted to the deterministic generator. Applying a reviewed measurement to a specific geometry field is a separate future workflow requiring a feature-association control and its own confirmation gate.

## Verification

The web route regression script covers same-origin rejection, owner-scoped lookup, valid length/angle/count readings, unit-kind mismatch, duplicate candidate indices, out-of-range indices, audit logging and preservation of original OCR/Blueprint evidence.
