# Offline AI3D Designer: Team Execution Plan

Product owner and architect: Diganta chakraborty
Developer 1: CAD and data engineering (Python)
Developer 2: Platform and web engineering (TypeScript, Next.js)
Engineering assistant and tools: Claude, ChatGPT, Gemini, the local Nemotron agent, Cursor, GitHub, CATIA


## important note:  ChatGPT works as devolaper 2 and local Nemotron agent works as a devolaper 1 with there speacisific task . who are localy work give the poweshell code . project folder E:\MY PROJECT FOLDER\Offline AI 3D Designer>

## This is Current Directory Tree: 

 offline-ai-3d-designer-main/
├── .github/workflows/
│   ├── cad-engine-tests.yml
│   ├── codeql.yml
│   └── web-checks.yml
├── docs/
│   ├── CAD_ENGINE_RELIABILITY.md
│   ├── DRAWING_TO_CAD_V1.md
│   └── STORAGE_RETENTION.md
├── python-backend/
│   ├── cura_resources/
│   │   ├── NOTICE.md
│   │   └── definitions/
│   │       ├── generic_fdm_extruder.def.json
│   │       └── generic_fdm_printer.def.json
│   ├── .env.example
│   ├── Dockerfile
│   ├── debug_parser.py (+ .bak-20261020-235959)
│   ├── main.py (+ 4 .bak-* files)
│   ├── nixpacks.toml
│   ├── railway.toml
│   └── requirements.txt
├── src/ai3d_designer/
│   ├── __init__.py (+ .bak-20261018-121535)
│   ├── ai/__init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   └── main.py (+ .bak-20261021-000148)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── export/        (__init__.py, exporter.py)
│   │   ├── geometry/      (__init__.py, engine.py)
│   │   ├── licensing/     (__init__.py, manager.py)
│   │   ├── nlp/           (__init__.py, parser.py + .bak-20261020-235928)
│   │   ├── ocr/           (__init__.py, extractor.py)
│   │   ├── spec/          (__init__.py, models.py)
│   │   ├── storage/       (__init__.py, storage.py)
│   │   ├── validation/    (__init__.py, validator.py)
│   │   └── worker/        (__init__.py, worker.py)
│   ├── drawing_to_cad/
│   │   ├── __init__.py
│   │   ├── blueprint.py
│   │   ├── extraction.py
│   │   ├── generator.py
│   │   ├── sprocket_cad.py
│   │   └── sprocket_spec.py
│   ├── export/            (__init__.py, exporter.py)
│   ├── geometry/          (__init__.py, engine.py)
│   ├── gui/               (app.py)
│   ├── image_to_3d/       (__init__.py, converter.py, mesh.py)
│   ├── licensing/         (__init__.py)
│   ├── ocr/               (__init__.py, pipeline.py)
│   ├── slicing/           (__init__.py, slicer.py)
│   ├── spec/              (__init__.py, models.py)
│   ├── storage/           (__init__.py)
│   ├── ui/                (__init__.py)
│   ├── validation/        (__init__.py)
│   └── worker/            (__init__.py)
├── tests/
│   ├── test_cli.py
│   ├── test_compatibility_imports.py
│   ├── test_drawing_to_cad_blueprint.py
│   ├── test_drawing_vision_timeout.py
│   ├── test_export_validation.py
│   ├── test_geometry.py
│   ├── test_geometry_regressions.py
│   ├── test_image_mesh.py
│   ├── test_image_relief.py
│   ├── test_legacy_geometry_adapter.py
│   ├── test_ocr_api.py
│   ├── test_ocr_extractor.py
│   ├── test_ocr_pipeline.py
│   ├── test_parser.py
│   ├── test_parser_regressions_pr2.py
│   ├── test_slicer.py
│   ├── test_slicer_safety.py
│   ├── test_spec.py
│   ├── test_sprocket_cad.py
│   └── test_sprocket_spec.py
├── web/
│   ├── prisma/
│   │   ├── schema.prisma
│   │   └── migrations/
│   │       ├── migration_lock.toml
│   │       ├── 20261019000000_init/migration.sql
│   │       ├── 20261019163400_account_deletion_schedule/migration.sql
│   │       └── 20261024133000_storage_retention/migration.sql
│   ├── public/            (file.svg, globe.svg, next.svg, vercel.svg, window.svg)
│   ├── scripts/           (test-project-retention.mjs)
│   ├── src/
│   │   ├── app/
│   │   │   ├── admin/page.tsx (+ .bak-20261020-123928)
│   │   │   ├── api/
│   │   │   │   ├── auth/session/route.ts
│   │   │   │   ├── billing/ (cancel, status, subscribe, verify, webhook)
│   │   │   │   ├── cad/[...path]/route.ts
│   │   │   │   ├── cron/account-deletion/route.ts
│   │   │   │   ├── projects/
│   │   │   │   │   ├── route.ts
│   │   │   │   │   └── [projectId]/
│   │   │   │   │       ├── files/[fileType]/route.ts
│   │   │   │   │       ├── files/source/[fileIndex]/route.ts
│   │   │   │   │       ├── generate-from-drawing/route.ts
│   │   │   │   │       ├── ocr/route.ts
│   │   │   │   │       ├── retention/route.ts
│   │   │   │   │       ├── slice/route.ts
│   │   │   │   │       └── versions/[versionId]/route.ts
│   │   │   │   ├── upload/route.ts
│   │   │   │   └── users/me/route.ts
│   │   │   ├── dashboard/
│   │   │   │   ├── billing/page.tsx
│   │   │   │   ├── projects/
│   │   │   │   │   ├── page.tsx
│   │   │   │   │   ├── new/page.tsx
│   │   │   │   │   └── [projectId]/page.tsx
│   │   │   │   ├── upload/page.tsx
│   │   │   │   ├── dashboard-content.tsx (+ .bak-20261020-123928)
│   │   │   │   └── page.tsx
│   │   │   ├── login/page.tsx
│   │   │   ├── profile/page.tsx
│   │   │   ├── signup/page.tsx
│   │   │   ├── favicon.ico
│   │   │   ├── globals.css
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx (+ .bak-20261020-123928)
│   │   ├── components/
│   │   │   ├── auth/auth-panel.tsx (+ .bak-20261020-230039)
│   │   │   ├── billing/billing-panel.tsx
│   │   │   ├── profile/profile-form.tsx (+ .bak-20261020-123928)
│   │   │   ├── projects/ (drawing-processor.tsx, project-retention-controls.tsx, slice-panel.tsx)
│   │   │   ├── ui/ (button.tsx, card.tsx, input.tsx, label.tsx)
│   │   │   ├── upload/ (file-drop-zone.tsx, upload-panel.tsx + .bak-20261020-124855)
│   │   │   ├── sign-out-button.tsx
│   │   │   ├── theme-provider.tsx
│   │   │   └── theme-toggle.tsx
│   │   └── lib/
│   │       ├── api/cad-client.ts (+ .bak-20261020-234212)
│   │       ├── auth/server.ts
│   │       ├── firebase/ (admin.ts, client.ts)
│   │       ├── security/same-origin.ts (+ .bak-20261021-075031)
│   │       ├── upload/validation.ts
│   │       ├── cad-service-config.ts
│   │       ├── prisma.ts
│   │       ├── project-retention-core.ts
│   │       ├── project-retention.ts
│   │       └── utils.ts
│   ├── .env.example
│   ├── .gitignore
│   ├── README.md (+ .bak-20261020-123928)
│   ├── components.json
│   ├── eslint.config.mjs
│   ├── next.config.ts
│   ├── package-lock.json
│   ├── package.json (+ .bak-20261020-230448)
│   ├── postcss.config.mjs
│   ├── tsconfig.json
│   └── vercel.json
├── .gitignore
├── CAD_ENGINE_AUDIT.md
├── DEPLOYMENT.md
├── NEXT_SESSION_HANDOFF.md
├── README.md
├── SECURITY.md
├── WORK_STATUS.md
├── pyproject.toml
├── requirements-dev.in
├── requirements.in
├── requirements.lock
├── run.bat
├── run_gui.py
└── vercel.json


This is the single plan for the team. Work is organised by workstream, with one owner per task and gates between phases. Nothing here is a promise of a date. A phase is finished when its gate passes.

Assumption: Developer 1 is strongest in Python and Developer 2 in web work. If the skills are the other way round, swap the owners in section 7. The rest of the plan is unchanged.

---

## 1. The goal

Make any part. A person describes the part in plain words, or gives a dimensioned drawing, a sketch with dimensions, a datasheet, or a component list. The system understands it, asks for anything missing, builds a real editable 3D model, checks it for printing, explains every problem in plain language, and delivers print-ready files (STEP, STL, 3MF, ZIP) or G-code for a chosen printer.

### 1.1 What "any part" means in practice

"Any part" is reached in layers, and every layer is measured:

1. **Expressible:** the part can be written in the feature language (section 5). Parts that need a feature we do not have yet are refused with the missing feature named.
2. **Buildable:** the kernel produces a valid solid for it.
3. **Verified:** the model matches the requested dimensions and passes the geometry checks.
4. **Printable:** the printability checks run, and every issue has an explanation and a fix.

A part is "supported" only when it passes all four layers. Coverage is the share of a fixed benchmark of diverse parts that is supported in each release. Coverage grows with each feature we add. We report the number honestly and do not claim a fixed percentage in advance.

### 1.2 What we will not claim

- A photo gives no reliable scale, so a photo alone is never treated as an exact dimension.
- Free-form organic shapes (sculptures, scanned meshes) are not parametric CAD. They are a separate phase.
- Printed strength or load is never promised without testing.

---

## 2. Product scope

**Inputs**
- Plain description (text)
- Dimensioned drawing (PDF or image)
- Sketch with dimensions (image)
- Component list or datasheet (PDF, text, or a product page the user confirms)
- Template from the gallery

**Outputs**
- Design: STEP (CATIA and other CAD), STL and 3MF (printing), ZIP with files, dimension report, and print guide
- Slicing: G-code for a chosen printer, with time and filament estimates; or slicing of a user's own STL

**Core user loop**
1. Describe or upload.
2. The system reads the input and proposes the part as a feature program, with a summary in words.
3. Questions for any missing value, one at a time. Values are never guessed.
4. Component values (if any) are shown with their source, and the user confirms them.
5. Fit check (for enclosures and anything containing parts).
6. Build, preview, and printability check with explanations and fixes.
7. User approves. Export or slice.

**Product rules**
- Free plan: one active project; a second project is blocked with a clear choice (delete or upgrade). Nothing is deleted automatically.
- Pro plan: unlimited projects, subject to one shared subscription check.
- Delete: removes the project, its files, and its versions, after a confirmation that shows the space freed.

---

## 3. Model decisions

The rule: use the most capable general model that the data rules allow first. Build a dedicated model only when a measured gap shows it is needed, and only for the step that has the gap.

### 3.1 The three model roles

| Role | Job | First option | Dedicated option (only if measured gap) |
|---|---|---|---|
| Planner | Turns description or read drawing into a feature program (section 5) | General LLM with a strict schema, output validated by code | Small planner fine-tuned on description-to-program pairs generated from our own feature library |
| Reader | Finds views, dimension text, and symbols in drawings | OCR (Tesseract or PaddleOCR) plus a general vision model | Dedicated detector and classifier trained on synthetic drawings from our kernel, plus real drawings with permission |
| Researcher | Extracts component specifications from datasheets | General long-context model, output must cite the page | Dedicated extractor trained on labelled datasheet pages |

### 3.2 The gate for dedicated models

Before any dedicated model is built, these benchmarks are run with the first option:

- **B1 Text to program:** 300 descriptions across all families (Diganta curates; ChatGPT drafts paraphrases, Diganta reviews).
- **B2 Drawing to program:** 100 real drawings (with permission) and 100 synthetic drawings with known values.
- **B3 Datasheet to specification:** 30 datasheets (Gemini long-context check, Diganta verifies a sample by hand).

Measured on each benchmark:
- Valid program rate (passes the schema and the feature checker)
- Dimension accuracy (within 0.1 mm of the known value)
- Hallucination rate (any value not present in the input) — target zero
- Correct refusals and correct questions
- Latency and cost per request
- Data-rule compliance (is the provider allowed to see this data?)

Proposed targets (to confirm at the gate):
- Valid program rate of at least 98 percent on B1
- Dimension accuracy of at least 95 percent on B2 synthetic drawings, and a stated lower target on real drawings
- Zero hallucinated values on B3 (any unsupported value fails the datasheet)

If the first option meets the targets within the data rules, no dedicated model is built. If it misses a target, the dedicated model for that role is built, and its benchmark is run the same way before it replaces the first option.

### 3.3 Hardware and data

- Developer laptops (RTX 3050 Laptop GPU, 4 GB VRAM) are used for development and small tests, not for training large models.
- Training runs on a rented GPU, chosen by Developer 1 and recorded in the decision log.
- Inference for dedicated models runs on the server, behind the same validators as the general model.
- Customer drawings are never used for training without written permission. Synthetic drawings come from our own generator and carry no third-party rights.
- Whether drawings may go to a hosted general model depends on C-DAC's data rule. Until that is confirmed, the first option uses only a provider or deployment that the rule allows.

### 3.4 Safety rule for all models

No model output is trusted directly. Every output passes:
1. The schema validator (types, units, ranges, allowed operations)
2. The feature checker (references to faces and edges exist; holes are inside walls)
3. The kernel build and verification
4. The printability check
A model can propose; code decides.

---

## 4. Architecture

```
Input (text | drawing | sketch | datasheet | template)
   |
   v
Reader (OCR and vision)             Researcher (datasheets, cited)
   |                                   |
   +---------------+-------------------+
                   v
             Planner (model)
                   |
                   v
   Feature program (validated, section 5)
                   |
                   v
    Questions for missing values  --> user answers
                   |
                   v
   Fit check (if components)
                   |
                   v
   Kernel build (isolated process, time and memory limits)
                   |
                   v
   Verification (valid solid, dimensions, feature checks)
                   |
                   v
   Printability check (six bed orientations) + explanations
                   |
                   v
   User approval
          |                    |
          v                    v
   Export (STEP, STL,     Slicing (chosen printer
   3MF, ZIP, report)      profile, G-code, time, filament)
```

Services:
- Web app (Next.js, Prisma, sign-in, subscriptions, project library)
- CAD service (Python, FastAPI, build123d on OpenCASCADE, OCR, planner calls, fit check, printability, slicing)
- Slicer (CuraEngine with printer profiles), on the CAD service host
- Database and private file storage

---

## 5. The feature program (the language the planner writes)

The planner never writes raw CAD code. It writes a feature program: a typed JSON document that the kernel interprets. This keeps output safe, checkable, and explainable.

### 5.1 Structure

```
program:
  name, unit (mm), description (plain words)
  parameters: named values with units, ranges, and sources
  steps: ordered list, each with
    id, operation, inputs (references to earlier steps), parameters,
    and an optional reference to a face or edge by name, never by raw index
```

### 5.2 Operations (version 1)

- Primitives: box, cylinder, sphere, cone, torus, wedge
- Sketches: rectangle, circle, polygon (closed, no self-crossing), slot
- Solid operations: extrude (distance), revolve (full or angle), union, difference, intersection
- Features: hole (through or blind), pocket (rectangle or circle), boss, linear pattern, circular pattern, mirror
- Edge treatment: fillet and chamfer, selected by named edge set (for example "top outer edges")
- Thin shell: wall thickness with selected open faces
- Checks: bounding box, feature count, hole position inside wall

### 5.3 Operations (later releases, each with tests)

- Sweep along a path, loft between sketches, draft angles, countersinks, threads (as cosmetic or real), gears, snap-fit clips, living hinges, assemblies

### 5.4 Rules the feature checker enforces

- Every dimension has a unit and a source (user, drawing, datasheet, or default)
- Defaults are shown and must be confirmed before export
- Holes and pockets must be inside a wall with a minimum margin
- Named references must exist
- No step can use a value that is not in the parameters

---

## 6. Repository layout

```
offline-ai-3d-designer/
  web/                      Next.js app (Developer 2)
  python-backend/           FastAPI CAD service entry point (Developer 1)
  src/ai3d_designer/
    program/                feature program schema, validator, interpreter (Developer 1)
    kernel/                 build123d operations, one module per feature family (Developer 1)
    reader/                 page rendering, OCR, view detection (Developer 1)
    planner/                model calls, prompts, output validation (Developer 1)
    researcher/             datasheet search and extraction, cited (Developer 1 backend, Developer 2 UI)
    fitcheck/               component fit calculation (Developer 1)
    printability/           bed fit, overhang, wall, hole checks, explanations text keys (Developer 1)
    slicing/                CuraEngine wrapper, printer profiles, G-code checks (Developer 1)
    export/                 STEP, STL, 3MF, ZIP, report (Developer 1)
  models/                   dedicated model code and notes, only when a gate says so (Developer 1)
  data/
    golden/                 benchmark sets B1, B2, B3 and expected results (Diganta curates)
    synthetic/              generator and seeds (Developer 1)
  tests/                    unit, geometry, and golden tests
  docs/                     user guide, admin guide, decisions, architecture
  scripts/                  batch runs, packaging, deployment helpers
```

---

## 7. Team and roles

### 7.1 Owners

| Person or tool | Main responsibility | Does not own |
|---|---|---|
| Diganta | Product owner and architect. Owns scope, decisions, golden sets, printer tests, CATIA checks, C-DAC contact, and approval at every gate | Day-to-day code |
| Developer 1 (CAD and data) | Feature program, kernel, reader, planner integration, fit check, printability, slicing, exports, synthetic data, dedicated model training if a gate asks for it | Web pages, billing |
| Developer 2 (platform and web) | Web app, screens, sign-in and subscriptions, project library and storage rules, API integration, deployment, monitoring, security headers and checks | CAD geometry |
| Claude | Engineering assistant: writes specifications, drop-in code files, tests, and reviews when asked. Works through GitHub like the developers | Final merges (owners merge) |
| ChatGPT | Copy for the interface, questions in plain words, glossary, user guide drafts, paraphrases for the benchmark sets | Code |
| Gemini | Long-document work: datasheets for benchmark B3, printer manuals for printer profiles, checking the glossary for accuracy | Code |
| Local Nemotron agent and Cursor | Batch runs of the benchmarks on Diganta's laptop, packaging scripts, local test runs | Production deployment |
| GitHub | Source, branches, pull requests, CI, the issue board for every task | — |
| CATIA | Opens STEP files for the check; the first real-world test of exports | — |

### 7.2 Review rules

- Every pull request has one reviewer who is not its author.
- Developer 1 reviews Developer 2's service calls and data handling. Developer 2 reviews Developer 1's API and any user-facing messages.
- Diganta reviews every pull request that changes the feature program, the planner, a benchmark, or a gate.

---

## 8. Workstreams and tasks

Task IDs are used in branch names (for example `feature/WS3-T04-planner-validator`) and in pull request titles.

### WS1: Product, decisions, and client (owner: Diganta)

- T01 Scope sign-off with C-DAC, including the catalogue and the "any part" definition in section 1.1
- T02 Data-rule decision: which providers may see drawings and datasheets
- T03 Storage and plan rules (section 2), written and approved
- T04 Printer list for the slicing profiles, and printer test plan
- T05 Acceptance criteria per gate, written in advance
- T06 Golden sets B1, B2, B3 curated and labelled (with ChatGPT drafts and Gemini checks)

### WS2: Feature program and kernel (owner: Developer 1; reviewer: Diganta)

- T10 Feature program schema, version 1, with the unit and source rules (section 5.4)
- T11 Schema validator with tests for every rule
- T12 Interpreter that maps program steps to kernel operations
- T13 Kernel operations, version 1 list (section 5.2), each with geometry tests against known volumes and bounding boxes
- T14 Named face and edge references, with tests on selection stability
- T15 Isolation: each build in a separate process with time and memory limits
- T16 Feature checker (section 5.4) with tests
- T17 Golden geometry tests run on every change (CI gate)

### WS3: Describe and planner (owner: Developer 1; benchmark: Diganta)

- T20 Planner prompt set: one prompt per family plus the refusal and question prompts
- T21 Planner calls through the agreed provider (T02), with output restricted to the schema
- T22 Question engine: one plain question at a time for each missing required value, with a measuring hint
- T23 Refusal engine: explains what is unsupported, names the missing feature, and suggests the closest family
- T24 Benchmark B1 harness: runs 300 descriptions, reports the metrics in section 3.2
- T25 Gate decision: first option meets targets, or a dedicated planner is started (WS9)

### WS4: Drawing reader (owner: Developer 1; data: Diganta)

- T30 Page rendering from PDF and image, with size and quality checks
- T31 OCR of dimension text with symbol handling (Ø, R, ±, °), returning confidence per token
- T32 View detection (front, top, side, section) using the first option; labelled examples for evaluation
- T33 Dimension-to-feature linking, rules first, planner second
- T34 Grounding check: every value in the program must appear in the OCR output or be marked as a user entry
- T35 Benchmark B2 harness, with synthetic and real sets reported separately
- T36 Gate decision: first option meets targets, or dedicated reader is started (WS9)

### WS5: Components and fit check (owner: Developer 1 for logic; Developer 2 for the research UI)

- T40 Component specification schema (the DeskClock file is the first example)
- T41 Datasheet search and page extraction through the agreed provider, with the source URL stored
- T42 Confirmation screen: every extracted value shown with its source; unconfirmed values block the fit check
- T43 Fit check: compares each component with the interior with clearances, and reports the shortfall in mm
- T44 Benchmark B3 harness, with a zero-hallucination rule
- T45 Gate decision on the researcher option

### WS6: Printability and explanations (owner: Developer 1 for checks; Developer 2 for display; copy: ChatGPT)

- T50 Checks: minimum wall, hole size, overhang, bed fit in six orientations, bridging span, base contact, hole-to-edge distance, flatness
- T51 Fix actions: rotate, thicken, enlarge, split, add support, with each fix applied to the program and re-verified
- T52 Explanation text keys with the four parts: what, why, fix, learn more
- T53 Glossary entries for every key term used in explanations
- T54 Display of checks in the interface, including checks that pass

### WS7: Slicing, printers, and exports (owner: Developer 1; printer tests: Diganta)

- T60 CuraEngine installed and verified in the service image
- T61 Printer profiles for two printers, from the printers' manuals (Gemini check), tested by printing
- T62 Slicing service returning G-code, time, and filament; G-code structure check
- T63 Slicing of a user's own STL, with the same profiles
- T64 Exports: STEP, STL, 3MF, ZIP with the report and print guide
- T65 CATIA check of STEP output (Diganta), with the findings logged

### WS8: Web product and screens (owner: Developer 2; design: ChatGPT; review: Diganta)

- T70 Five screens: home, questions, preview and check, print, results
- T71 Template gallery with a few examples per family
- T72 Preview: 3D viewer with dimension list and the summary in words
- T73 Beginner mode and advanced mode switch
- T74 Accessibility basics and mobile layout check
- T75 Interface copy (ChatGPT drafts, Diganta approves)

### WS9: Dedicated models (owner: Developer 1; starts only after a gate says so)

- T80 Synthetic data generator from the feature library, with seeds and labels
- T81 Dataset split by family so that test items are never seen in training
- T82 Training scripts, run on a rented GPU, with the run recorded in the decision log
- T83 Evaluation on the same benchmarks as the first option
- T84 Integration behind the same validators, with a switch to fall back to the first option

### WS10: Platform, storage, billing, deployment, and security (owner: Developer 2; service hardening: Developer 1)

- T90 Sign-in and session checks on every private route
- T91 Project library: create, open, delete, with confirmation and storage meter
- T92 Free plan rule (one project) enforced inside the same database transaction as creation
- T93 Subscription check in one shared helper used by every paid route
- T94 Rate limits on planner, reader, slicing, and generation routes
- T95 Upload checks: type by content, size limits, no executable files
- T96 Deployment in the environment chosen under T02, with separate staging and production
- T97 Monitoring and alerts: errors, job duration, queue size, cost per job
- T98 Backup and one tested restore
- T99 Security review, internal first, external before handover if C-DAC requires it

### WS11: Quality, testing, and release (owner: Diganta for benchmarks; Developer 1 for harness; Developer 2 for end-to-end tests)

- T110 Unit, geometry, and golden tests in CI on every pull request
- T111 End-to-end browser tests: sign-in, describe, question, preview, check, export, slice, delete
- T112 Benchmark runs on each release candidate, with a results table in docs
- T113 Print tests: each release candidate has printed samples recorded in docs
- T114 User testing with non-technical people, recorded findings, fixes logged

### WS12: Documentation and handover (owner: Developer 2 publishes; drafts: ChatGPT; approval: Diganta)

- T120 User guide
- T121 Administrator guide (deployment, backup, restore, plan rules)
- T122 Architecture and decisions log kept current
- T123 Source handover: repository ownership, credentials handled through an agreed secure channel, list of third-party accounts

---

## 9. Phases and gates

Phases overlap where tasks are independent. A gate is passed only when its exit criteria are met and Diganta has signed it in the decision log. There are no fixed dates in this plan.

**P0 Foundation.** Repository layout in section 6 in place. CI green. CAD service starts and passes its tests. Container image builds as non-root.
Exit: T17 runs in CI; the service health check passes in the staging environment.

**P1 Feature program and kernel.** WS2 complete for version 1 operations.
Exit: every version 1 operation has passing geometry tests; the feature checker rejects every invalid case in its test list; no build runs outside its isolated process.

**P2 Describe.** WS3 complete. B1 benchmark run and gate decision made.
Exit: B1 targets met with the first option, or the dedicated planner is started under WS9 with its own benchmark.

**P3 Read drawings.** WS4 complete. B2 benchmark run and gate decision made.
Exit: B2 targets met, or the dedicated reader is started under WS9.

**P4 Components and fit check.** WS5 complete. B3 benchmark run and gate decision made.
Exit: no unconfirmed value reaches a fit check; zero hallucinated values on B3.

**P5 Printability and explanations.** WS6 complete.
Exit: every check has all four explanation parts; every fix is re-verified; every check result is shown, including passes.

**P6 Slicing and exports.** WS7 complete.
Exit: G-code produced and checked for both printer profiles; exports open in CATIA (STEP) and the standard slicer (STL); samples printed and recorded.

**P7 Product.** WS8 and WS10 complete for the screens, storage, plans, and deployment.
Exit: end-to-end tests pass; the free-plan rule holds under parallel requests.

**P8 Hardening and acceptance.** WS11 and WS12 complete. Security review done.
Exit: release candidate benchmarks recorded; user testing findings closed or logged; handover documents signed; C-DAC acceptance criteria met or each gap listed and accepted in writing.

---

## 10. Quality standard

Every release is measured the same way:
- Test results (unit, geometry, golden, end-to-end) with counts and failures listed
- Benchmark tables B1, B2, B3 with every metric in section 3.2
- Print test records for each printer profile
- Known limitations, written in plain words, in the user guide

A release is not claimed as "any part" in general. It is claimed as the coverage measured on the benchmark set, with the list of supported operations.

---

## 11. Working rules

- Work in branches named after the task ID. One task per pull request.
- A pull request needs: the task ID, tests for any changed behaviour, a line in the docs if the user sees a change, and no secrets in the code.
- Geometry changes must keep the golden geometry tests passing.
- Planner or benchmark changes need Diganta's review.
- Secrets live in environment settings or the hosting provider's secret store only.
- GitHub issues are the single source of truth for status. A task is done when its pull request is merged and its definition of done is met.
- Tools (Claude, ChatGPT, Gemini, the Nemotron agent) produce drafts and checks. A person owns each output and merges it. Nothing from a tool goes to production without an owner's review.
- Gate reviews happen when a gate's exit criteria are met, not on a calendar.

---

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Planner invents a value | Wrong part | Schema, grounding check, and questions for missing values; zero-hallucination target |
| Drawing quality is poor | Wrong dimensions | Quality check on input; visible confidence; mandatory review before build |
| Data rules block the best provider | Lower accuracy or delay | Decision T02 early; dedicated model path prepared |
| Dedicated model training costs more than planned | Budget overrun | Start only after a measured gap; rented GPU with a cost cap |
| Developer skills do not match the plan | Slower progress | Swap owners in section 7; reviews across the two developers |
| Printed parts fail in use | Trust damage | Explicit "test before relying on it"; print tests per release |
| Scope grows with each new request | No release | New requests become feature-program operations with their own tests; coverage report shows what is added |
| Copyright or licence of datasheets and manuals | Legal risk | Use public documents, cite the source, store no copied text beyond short extracts |
| Storage rules disputed | User anger | Explicit delete only; block at the limit, never auto-delete |

---

## 13. Decision log

| Decision | Default until decided | Owner | Decided |
|---|---|---|---|
| Data rule for hosted models (T02) | Only providers and deployments that C-DAC approves | Diganta | |
| First-option planner provider | To be chosen by benchmark B1 within the data rule | Diganta and Developer 1 | |
| Hosting environment | To be confirmed with C-DAC | Diganta | |
| Printers for slicing profiles | Two printers, named by owner | Diganta | |
| Free plan rule | One active project, block at limit | Diganta | |
| Targets for B1, B2, B3 | Section 3.2 proposals | Diganta | |
| Rented GPU provider and cost cap | Not chosen | Developer 1 | |
| External security review timing | After internal review, before handover if required | Diganta | |
| Developer role assignment | Developer 1 CAD and data; Developer 2 platform and web | Diganta | |

---

## 14. Summary

The product is one system that turns any description, drawing, sketch, datasheet, or component list into a verified, print-ready part. Its strength comes from three things: a checked feature language that every part is written in, a planner and reader that propose but never decide, and printability checks that explain every problem. General models come first. Dedicated models are built only where a measured benchmark shows the gap. Developer 1 builds the geometry, reading, and printing engine. Developer 2 builds the product around it. Diganta owns the decisions, the golden sets, the printer tests, and every gate.

---

## 15. Current product status (verified on the uploaded code and the patched copy)

### 15.1 What exists, by layer

| Layer | What exists | Where | Status |
|---|---|---|---|
| Web app | Next.js, Prisma, Firebase sign-in, Razorpay subscriptions, project pages, upload, slicing route | `web/` (Vercel) | Lint passes. Type check and production build not verified (generated Prisma client needed) |
| CAD service | FastAPI, build123d 0.13 on OpenCASCADE, Tesseract OCR, vision adapter, slicing wrapper, health check | `python-backend/`, `src/ai3d_designer/` (Railway, Docker) | Starts and reports healthy. Authentication fails closed. A live box build works. Docker build not verified |
| Shared engine | Text parser, blueprint generator, validators, STEP and STL export, image relief | `src/ai3d_designer/` | 176 tests pass |
| Desktop app | Legacy PySide6 GUI and CLI | `src/ai3d_designer/gui`, `cli` | Not tested this round. Not the main product |

### 15.2 Capability status against the goal

| Capability | Status | Gap | Task |
|---|---|---|---|
| Text description of a supported shape (box, cylinder, sphere, cone, torus, wedge, tube, holes) | Working | Phrasing coverage is narrow; more test cases needed | T10 to T13, T20 to T23 |
| Text description of an unmodelled feature (fillet, chamfer, thread, tolerance, countersink, sprocket teeth) | Refused with the reason | Feature not yet built | T13, later operations |
| Dimensioned drawing to model (flange, plate, open enclosure, revolve, holes, pockets) | Partial, with human review | Accuracy not measured on real drawings | T30 to T36 |
| Drawing reading (OCR and vision) | Partial | Falls back to labelled text when the vision provider fails. Hosted provider receives drawings by default | T32, T35, T02 |
| Photo or sketch to CAD | Not supported (approximate relief only) | Photos have no reliable scale | Later phase |
| Sprocket | Preview only, not engagement-certified | ISO 606 tooth form not built | Later phase |
| Datasheet research and fit check | Not built (specification template only) | Research, citation and fit logic missing | T40 to T45 |
| Printability checks and explanations | Not built as a module. Only validity and watertight checks exist | Bed fit, overhang, minimum wall, hole size, and the four-part explanations are missing | T50 to T54 |
| Slicing to G-code | Web route and validator exist. CuraEngine not installed in the sandbox (slicing reports unavailable) | Printer profiles, time and filament, container install | T60 to T63 |
| Exports | STEP and STL working for the text path | ZIP, 3MF and dimension report not found in the code | T64 |
| Storage | 10-project cap with automatic pruning and an "important" pin. Free monthly generation limit. Version delete and account delete. No project-level delete | Free plan must be one project; project delete missing | T91, T92 |
| Sign-in and subscriptions | Present. Razorpay webhook signature checked | Access checks repeated per route | T90, T93 |
| User interface | Original screens, not redesigned | Five-screen flow, explanations, storage meter | T70 to T75 |
| Dedicated models | None | Built only after a gate | WS9 |
| Deployment | Configured in docs. Not verified here | Staging, monitoring, backup and restore | T96 to T98 |

---

## 16. Errors register

### 16.1 Fixed and verified in this round

| ID | Where | Problem | Fix |
|---|---|---|---|
| E-01 | `drawing_to_cad/extraction.py` line 902 | Syntax error. Backend would not start | Colon added |
| C-01 | Text parser | Requested features silently dropped, reported as success | Unmodelled features refused with the reason |
| Label ambiguity | Text parser | Numbers assigned to the wrong labels (for example tube inner diameter) | Each number has one owner. Conflicts refused. Comma-separated labels recommended |
| E-02 | `tests/test_image_relief.py` | Test imported a removed helper | Rewritten against the current API |
| E-03, E-04 | Parser entry point | Unknown unit raised an exception. LLM path received an unsupported argument | Parse error returned. Argument handled |
| E-05 | Vision timeout | Code capped at 30 s, documents said 110 s | Decision: 30 s cap. Docs and tests aligned |
| E-06 | Vision output limit | 2048 tokens could cut JSON silently | 4096 tokens. Truncated output rejected |
| E-07 to E-13 | Test expectations | Renamed methods, message wording, G-code layer markers, unit storage, torus definition | Tests aligned to intended behaviour. Torus requires an explicit major radius |
| E-09 | Slicer | Output path checked after CuraEngine lookup | Check moved first |
| E-14 | Models | Deprecated UTC call | Timezone-aware timestamps |
| Self-intersection | Geometry engine | Crossing profiles gave a misleading error | Explicit "self-intersects" error |
| S-01 | CAD service authentication | Could be disabled by setting `APP_ENV=development` | Always required. Health reports ready only when the token is set |
| S-02 | `python-backend/Dockerfile` | Container ran as root | Unprivileged user added. Not yet built here (see OPEN-02) |
| S-05 | Repository | 18 backup copies of old code | Deleted. `*.bak*` ignored |
| S-10 | CAD service | Unused in-memory job dictionary | Removed |

### 16.2 Open

| ID | Where | Problem | Next step | Task |
|---|---|---|---|---|
| OPEN-01 | Web type check | Errors consistent with a missing generated Prisma client. Binaries not downloadable in the sandbox | Run type check and build in CI with network access; fix any real type errors | T96, WS11 |
| OPEN-02 | Container image | Not built here. Non-root user and CuraEngine install unverified | Build in CI; run the health check as non-root | T60, T96 |
| OPEN-03 | `python-backend/debug_parser.py` | Debug script with an invalid escape sequence | Delete from the production branch | Release hygiene |
| OPEN-04 | Backend dependencies | No lock file; only minimum versions | Create a lock file on Python 3.11 and scan for vulnerabilities | Service hardening (Developer 1) |
| OPEN-05 | Licence | README says MIT. `pyproject.toml` says proprietary | Owner decision; make both files agree | T01 |
| OPEN-06 | `WORK_STATUS.md`, `NEXT_SESSION_HANDOFF.md` | Still claim 97 tests and old status | Update to 176 tests and this status | T122 |
| OPEN-07 | Slice route | Admin users not allowed, unlike the other paid routes | Use the shared access helper | T93 |
| OPEN-08 | Vision adapter | No switch to block drawings going to a hosted provider | Add a setting that defaults to blocked; show a disclosure | T02, T84 |
| OPEN-09 | Web and CAD routes | No rate limits on planner, reader, slicing, generation | Add per-user limits | T94 |
| OPEN-10 | CAD service CORS | Credentials allowed though the service is server-to-server only | Remove or restrict | Service hardening |
| OPEN-11 | Text parser | Label resolution heuristic has limited test cases | Add mixed-phrasing cases to the tests; keep refusing conflicts | T11, T13 |
| OPEN-12 | Desktop app | Not tested this round | Owner decides whether the desktop app is in scope | T25 (decision) |
| OPEN-13 | Storage | Free plan limit is 10 projects, not one. No project delete | Implement the agreed rule and delete | T91, T92 |

---

## 17. Loopholes (how each is closed)

| ID | Loophole | Effect | Closed by | Interim rule |
|---|---|---|---|---|
| L-01 | Grounding checks that a number exists in the drawing, not that it belongs to the right feature | Right number on the wrong feature passes | T34 grounding; T42 and T54 review display | Reviewer confirms each value against the drawing |
| L-02 | The review flag is a boolean sent by the client | No record of who reviewed what | Review log in project versions (U-07) | Log reviewer, time and changed fields |
| L-03 | Values edited by the user skip grounding | Output is only as good as the reviewer | Mark edited values; keep the edit history | Show "edited by reviewer" on each value |
| L-04 | A valid, watertight solid can still be the wrong part | Wrong part exported | T16 bounding-box and feature checks against the spec; T65 CATIA check; T113 print tests | Export labelled "verify against drawing" until confirmed |
| L-05 | Default values (for example height and wall) can be exported unnoticed | Unconfirmed dimensions reach the user | Export blocked until defaults are confirmed (U-02) | Block export now |
| L-06 | The sprocket preview looks like a usable sprocket | Wrong gear used | Labelling and export block (U-02, sprocket item) | Label every sprocket output; refuse export |
| L-07 | Vision failure falls back to text silently | User trusts a partial reading | Visible fallback banner (U-14) | Show the banner now |
| L-08 | OCR misreads symbols and digits (Ø, ±, 0 and 8) | Wrong dimensions | Confidence per token (T31); benchmark (T35) | Flag low-confidence tokens for review |
| L-09 | Text inside a drawing could steer the planner | Unexpected output | Schema-restricted planner output (T21); grounding (T34) | Treat drawing text as data only |
| L-10 | Access rules repeated in every route | One route missed | One helper for every paid route (U-12) | Review each paid route against the helper |
| L-11 | Parallel requests exceed the free-plan limit | Free users get more than allowed | Limit check and insert in one transaction (U-11) | None until built |
| L-12 | The desktop licence check works offline and can be bypassed | Lost revenue | Owner decision: sell the web product, or add an online check (U-21) | Do not sell the desktop build as paid |
| L-13 | First request after idle is slow and looks like a failure | Users think the product is broken | Health check warm-up, one retry, clear message (T97) | Retry once with a message |
| L-14 | Demo runs on an environment with missing settings | Failure in front of the client | Staging environment and end-to-end tests (T96, T111) | Demo only on staging after a dry run |
| L-15 | Client drawings sent to a third-party model | Data-rule breach | Data rule (T02); switch (T84); OPEN-08 | Block hosted providers until decided |
| L-16 | Client requests read as promises ("any part", "exact copy") | Dispute | Scope and exclusions in the SRS (section 1.2 of this plan) | Refusal message names the missing feature |
| L-17 | Label resolution in the text parser is heuristic | Rare wrong assignment | More tests (OPEN-11); refusal on any conflict | Refuse when in doubt |
| L-18 | A printer profile does not match the real printer | Failed prints | Profile tests (T61); print tests per release (T113) | State the profile name and warn |
| L-19 | G-code validation checks structure, not printability | Unprintable file accepted | Printability checks (T50) and explanations (T52); disclaimer | Disclaimer on every slice |
| L-20 | Hosting outside India may conflict with C-DAC data rules | Rework or rejection | Decision T02 and hosting T96 | Decide before any client data is uploaded |
| L-21 | Free-plan limit in code is 10, not one | Wrong plan behaviour | T92 | Change to one |
| L-22 | Halted or past-due subscriptions keep tier PRO in the record | Access depends only on status | Access helper checks status, not tier (T93) | Never check tier alone |
| L-23 | A wrong `APP_ENV` value changes behaviour | Unsafe configuration | Authentication fixed; configuration checked at boot (U-16) | Set `APP_ENV=production` on hosted services |
| L-24 | Printed strength or load promised | Liability | Explanation rule (T52): never claim load without testing | Load warnings on hooks and clips |
| L-25 | Datasheets or manuals copied beyond short extracts | Copyright risk | Cite sources; store short extracts only (T41) | Store the source link, not the document |

---

## 18. Upgrades required (what must change, mapped to tasks)

### 18.1 Developer 1 (CAD and data)

| ID | Upgrade | Task |
|---|---|---|
| U-01 | Feature program schema, interpreter, and version 1 operations, replacing ad hoc builders | T10 to T13 |
| U-02 | Feature checker: defaults must be confirmed before export; references validated; holes inside walls | T16 |
| U-03 | Printability module: minimum wall, hole size, overhang, bed fit in six orientations, bridging, base contact | T50, T51 |
| U-04 | Explanation keys with the four parts (what, why, fix, learn more) | T52, T53 |
| U-05 | Fit-check module and component specification validation | T40, T43 |
| U-06 | Planner prompt set with schema-restricted output and question and refusal engines | T20 to T23 |
| U-07 | Reader: confidence per token, grounding, review log hooks | T31, T34 |
| U-08 | Slicing: CuraEngine in the image, printer profiles, G-code structure check, time and filament | T60 to T63 |
| U-09 | Exports: 3MF, ZIP with report and print guide | T64 |
| U-10 | Service hardening: rate limits, CORS removal, debug file removal, dependency lock file | T94, OPEN-03, OPEN-04, OPEN-10 |

### 18.2 Developer 2 (platform and web)

| ID | Upgrade | Task |
|---|---|---|
| U-11 | Project delete, and the free-plan rule enforced in one transaction | T91, T92 |
| U-12 | One access helper for every paid route, including the slice route, checking status | T93, OPEN-07 |
| U-13 | Five-screen interface and explanation display | T70 to T73 |
| U-14 | Review screen with blanks and defaults highlighted; visible fallback banner | T42, T70 |
| U-15 | Storage meter and plan limits in plain words | T91 |
| U-16 | Staging and production separated; settings validated at startup; health checks | T96, T97 |
| U-17 | Web type check and build in CI with the Prisma client generated | OPEN-01 |
| U-18 | Rate limits and upload checks at the web layer | T94, T95 |
| U-19 | End-to-end browser tests | T111 |
| U-20 | Status documents updated to the verified state | OPEN-06 |

### 18.3 Diganta (decisions and data)

| ID | Decision or data | Task |
|---|---|---|
| U-21 | Licence: web product only, or an online check for the desktop build | OPEN-05, L-12 |
| U-22 | Data rule and hosting environment | T02, L-15, L-20 |
| U-23 | Golden sets B1, B2, B3 | T06 |
| U-24 | Printer profiles and print tests | T04, T113 |
| U-25 | Desktop app scope | OPEN-12 |

### 18.4 Order of work before any demo or release

1. Close the silent-default and review gaps: L-05 (block export on defaults), L-01 and L-02 (review and log), L-07 (fallback banner).
2. Verify the two unverified builds: OPEN-01 (web type check and build) and OPEN-02 (container image as non-root, with CuraEngine).
3. Finish the must-have types through U-01 to U-03.
4. Add printability explanations (U-04) and the fit check (U-05) before any component feature is shown.
5. Put slicing, exports, and the access helper in place (U-08, U-09, U-12).
6. Deploy to staging, run the end-to-end tests, and record the results (U-16, U-19).
