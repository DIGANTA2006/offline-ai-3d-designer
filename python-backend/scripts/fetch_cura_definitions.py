"""Fetch the Cura 4.13 base definitions required by the bundled generic profiles.

The upstream commit is immutable and matches the CuraEngine 4.13 runtime used by
the backend image. Definitions and the upstream license are retained in the
container image; generated files are not checked into this repository.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen


CURA_REPOSITORY_COMMIT = "11af2cf24d76186f1ec9d353a1cb134eea22f199"
CURA_RAW_BASE = (
    "https://raw.githubusercontent.com/Ultimaker/Cura/"
    + CURA_REPOSITORY_COMMIT
)
RESOURCE_DIR = Path(__file__).resolve().parents[1] / "cura_resources"
DEFINITIONS_DIR = RESOURCE_DIR / "definitions"

RESOURCES = (
    ("resources/definitions/fdmprinter.def.json", DEFINITIONS_DIR / "fdmprinter.def.json", 600_000),
    ("resources/definitions/fdmextruder.def.json", DEFINITIONS_DIR / "fdmextruder.def.json", 50_000),
    ("LICENSE", RESOURCE_DIR / "CURA-UPSTREAM-LICENSE.txt", 20_000),
)


def fetch_bytes(upstream_path: str, maximum_bytes: int) -> bytes:
    url = f"{CURA_RAW_BASE}/{upstream_path}"
    request = Request(
        url,
        headers={"User-Agent": "offline-ai-3d-designer-build/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"Upstream download failed with HTTP {response.status}: {upstream_path}")
        data = response.read(maximum_bytes + 1)

    if not data:
        raise RuntimeError(f"Upstream resource is empty: {upstream_path}")
    if len(data) > maximum_bytes:
        raise RuntimeError(f"Upstream resource exceeded the configured size limit: {upstream_path}")
    return data


def validate_definition(name: str, payload: bytes) -> None:
    try:
        definition = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cura definition is not valid JSON: {name}") from exc

    if not isinstance(definition, dict):
        raise RuntimeError(f"Cura definition root must be a JSON object: {name}")
    if not isinstance(definition.get("name"), str) or not definition["name"].strip():
        raise RuntimeError(f"Cura definition is missing its name: {name}")
    if not isinstance(definition.get("settings"), dict):
        raise RuntimeError(f"Cura definition is missing its settings object: {name}")
    if definition.get("inherits"):
        raise RuntimeError(f"Expected a base definition without inheritance: {name}")


def atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=destination.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> None:
    fetched: list[tuple[Path, bytes]] = []
    for upstream_path, destination, maximum_bytes in RESOURCES:
        payload = fetch_bytes(upstream_path, maximum_bytes)
        if destination.suffix == ".json":
            validate_definition(destination.name, payload)
        elif b"GNU LESSER GENERAL PUBLIC LICENSE" not in payload:
            raise RuntimeError("The pinned Cura upstream license file is not the expected LGPL text.")
        fetched.append((destination, payload))

    # Only write files once all three upstream resources passed validation.
    for destination, payload in fetched:
        atomic_write(destination, payload)
        print(f"FETCHED_CURA_RESOURCE {destination.name} bytes={len(payload)}")

    print(f"CURA_DEFINITIONS_SOURCE_COMMIT={CURA_REPOSITORY_COMMIT}")


if __name__ == "__main__":
    main()
