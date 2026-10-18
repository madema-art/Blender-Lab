#!/usr/bin/env python3
"""Build Blender Lab's active creation from creations/active/scene.py.

Run with /opt/bpy-venv/bin/python tools/build_active_creation.py from any
working directory. The script resets Blender to an empty scene, executes the
active source, exports a temporary self-contained GLB, validates and imports
it, then atomically replaces public/models/active-creation.glb.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import struct
import sys
import tempfile
from datetime import datetime, timezone

import bpy


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "creations" / "active" / "scene.py"
DEFAULT_OUTPUT = ROOT / "public" / "models" / "active-creation.glb"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def read_glb(path: Path) -> dict:
    """Check the GLB 2 header, JSON chunk and self-contained asset shape."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("export is not a GLB file")
    magic, version, total_length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or total_length != len(data):
        raise ValueError("invalid GLB 2 header or file length")
    json_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != JSON_CHUNK or 20 + json_length > len(data):
        raise ValueError("GLB does not begin with a valid JSON chunk")
    document = json.loads(data[20:20 + json_length].decode("utf-8").rstrip(" \t\r\n\0"))
    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError("GLB asset version must be 2.0")
    if any(buffer.get("uri") for buffer in document.get("buffers", [])):
        raise ValueError("GLB references an external buffer")
    if any(image.get("uri") and not image["uri"].startswith("data:") for image in document.get("images", [])):
        raise ValueError("GLB references an external image")
    offset = 20 + json_length
    if offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("truncated GLB chunk header")
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        if chunk_type != BIN_CHUNK or offset + 8 + chunk_length > len(data):
            raise ValueError("invalid GLB binary chunk")
    return document


def stamp_manifest(output: Path) -> None:
    """Record the build time on the shelf entry so Blender Lab lists the active creation as newest."""
    manifest = output.parent / "manifest.json"
    if not manifest.is_file():
        return
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for entry in entries:
        if entry.get("file") == output.name:
            entry["updated"] = stamp
    manifest.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(source: Path, output: Path) -> tuple[int, int]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"active Blender source not found: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    runpy.run_path(str(source), run_name="__main__")

    fd, temp_name = tempfile.mkstemp(prefix=".active-creation-", suffix=".glb", dir=output.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        result = bpy.ops.export_scene.gltf(
            filepath=str(temp_path),
            export_format="GLB",
            export_animations=True,
            export_cameras=False,
            export_lights=False,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Blender GLB export did not finish: {result}")
        document = read_glb(temp_path)

        # Verify Blender itself can read the generated GLB before publishing it.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        import_result = bpy.ops.import_scene.gltf(filepath=str(temp_path))
        if "FINISHED" not in import_result:
            raise RuntimeError(f"Blender could not re-import its GLB: {import_result}")
        objects = len(bpy.context.scene.objects)
        meshes = sum(obj.type == "MESH" for obj in bpy.context.scene.objects)
        if len(document.get("nodes", [])) and not objects:
            raise RuntimeError("GLB contains nodes but Blender imported no scene objects")
        temp_path.chmod(0o644)
        os.replace(temp_path, output)
        stamp_manifest(output)
        return objects, meshes
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        objects, meshes = build(args.source, args.output)
    except Exception as error:
        print(f"[Blender Lab] Build failed: {error}", file=sys.stderr)
        return 1
    print(f"[Blender Lab] Wrote {args.output.resolve()} ({objects} objects, {meshes} meshes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
