# Storage Retention and Temporary-File Cleanup

## Temporary processing files

- Drawing-page renders in `drawing_to_cad/extraction.py` and OCR PDF rasterization use byte buffers and Pillow/PyMuPDF images in memory; they do not write page PNGs into a persistent project directory.
- Tesseract is invoked through `pytesseract.image_to_data`, which manages its temporary input/output files with scoped cleanup; the request pipeline does not copy those scratch images to Blob or the database.
- STEP/STL exports in `drawing_to_cad/generator.py` are written inside `tempfile.TemporaryDirectory`. Its context manager removes the full directory on success and exceptions. The image-mesh export uses a temporary output file and removes it in a `finally` block.
- Web routes keep file bytes/Base64 in request memory while transferring to the CAD service and private Blob storage. New writes to JSON fields are passed through `compactStoredJson`, which strips inline data URLs/Base64 payloads and raw mesh arrays while retaining dimensions and feature parameters.

## CAD output versions

A generated version consists of its STEP/STL files and a `ProjectVersion` database row. By default, the system retains the **two most recent unprotected generated versions** per project. A protected version is exempt from automatic deletion, so the total may exceed two while versions are pinned. On each drawing CAD generation, automatic pruning deletes the older unprotected Blob files before removing the corresponding database row.

The project detail page shows every retained generated version and supports:
- **Protect / Protected** — toggles `ProjectVersion.isProtected`. Unprotecting a version immediately runs the pruning policy.
- **Delete** — explicitly deletes that version's STEP/STL/GLB blobs and the database row, even if it had been protected.

Downloads include a version ID so a protected older export remains independently downloadable.

## Project history

The active project limit is **10 projects per user**. Projects marked Important (`Project.isImportant`) are never chosen for automatic cleanup. When a new project/upload is created, the retention process removes the oldest unimportant, non-processing projects until the count is at or below ten. If ten or more projects exist and there is no safe unimportant project to remove, creation is rejected and the user must mark an old project unimportant or manually remove it first. Active Processing/Queued work is not chosen as a cleanup target.

## Operational notes

1. Apply the additive Prisma migration `20261024133000_storage_retention` to the Preview database before testing the new UI/API.
2. Set `PRIVATE_BLOB_READ_WRITE_TOKEN` for the target environment; it must have permission to delete from the same private Blob store used for uploads and CAD exports.
3. The automated cleanup runs when projects/uploads are created or CAD is generated and when a version is unprotected. Merely applying the migration does not retroactively delete old blobs or compact legacy JSON. Existing projects get pruned on the next successful creation/generation action; existing JSON payloads are stripped as their OCR/CAD records are next written.
4. Cleanup of existing local cache files or storage outside the Vercel Blob paths recorded in project rows is not attempted automatically. Keep backups of important models before manually deleting storage.

Blob deletion can take time to propagate through the storage CDN cache. Database records are removed only after the corresponding Blob deletion call succeeds for the relevant retention operation.
