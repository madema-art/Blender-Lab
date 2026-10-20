#!/usr/bin/env python3
"""Save the active creation as its own library entry.

Run from anywhere: python3 tools/save_creation.py --name "Lighthouse"

Copies creations/active/scene.py to creations/<slug>/scene.py, copies the active
GLB to public/models/<slug>.glb, and adds a manifest entry dated like the active
build. Names must be new, so a saved creation is never overwritten.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "public" / "models"
MANIFEST = MODELS / "manifest.json"
ACTIVE_SOURCE = ROOT / "creations" / "active" / "scene.py"
ACTIVE_GLB = MODELS / "active-creation.glb"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError("the name needs at least one letter or number")
    return slug


def check_glb(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError(f"{path.name} is not a GLB file")


def save(name: str) -> str:
    name = name.strip()
    slug = slugify(name)
    file_name = f"{slug}.glb"
    source_dir = ROOT / "creations" / slug
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    active = next((entry for entry in entries if entry.get("file") == ACTIVE_GLB.name), None)
    if active is None:
        raise ValueError("the manifest has no Active Creation entry")
    taken = any(entry["name"].lower() == name.lower() or entry["file"] == file_name for entry in entries)
    if taken or (MODELS / file_name).exists() or source_dir.exists():
        raise ValueError(f"a creation named '{name}' already exists; choose another name")
    if not ACTIVE_SOURCE.is_file() or not ACTIVE_GLB.is_file():
        raise FileNotFoundError("there is no active creation to save")
    check_glb(ACTIVE_GLB)

    source_dir.mkdir(parents=True)
    shutil.copyfile(ACTIVE_SOURCE, source_dir / "scene.py")
    shutil.copyfile(ACTIVE_GLB, MODELS / file_name)
    entries.append({
        "name": name,
        "file": file_name,
        "updated": active.get("updated"),
        "creationSource": f"creations/{slug}/scene.py",
    })
    MANIFEST.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return file_name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="the creation's name, as it should appear in the library")
    args = parser.parse_args()
    try:
        file_name = save(args.name)
    except Exception as error:
        print(f"[Blender Lab] Could not save: {error}", file=sys.stderr)
        return 1
    print(f"[Blender Lab] Saved '{args.name.strip()}' as {file_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
