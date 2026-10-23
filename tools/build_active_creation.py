#!/usr/bin/env python3
"""Build Blender Lab's active creation from creations/active/scene.py.

Run with /opt/bpy-venv/bin/python tools/build_active_creation.py from any
working directory. The script resets Blender to an empty scene, executes the
active source, bakes any Blender Lab materials into PBR textures
(tools/lab_materials.py), exports a temporary self-contained GLB, checks it
against the game-ready budget, imports it back, then atomically replaces
public/models/active-creation.glb.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
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


def read_glb(path: Path) -> tuple[dict, bytes]:
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
    binary = b""
    if offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("truncated GLB chunk header")
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        if chunk_type != BIN_CHUNK or offset + 8 + chunk_length > len(data):
            raise ValueError("invalid GLB binary chunk")
        binary = data[offset + 8:offset + 8 + chunk_length]
    return document, binary


def image_size(blob: bytes) -> tuple[int, int]:
    """Width and height of an embedded PNG or JPEG."""
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", blob[16:24])
    if blob[:2] == b"\xff\xd8":
        offset = 2
        while offset + 9 < len(blob):
            marker, length = blob[offset + 1], struct.unpack(">H", blob[offset + 2:offset + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack(">HH", blob[offset + 5:offset + 9])
                return width, height
            offset += 2 + length
    raise ValueError("embedded image is not a PNG or JPEG")


def asset_report(document: dict, binary: bytes) -> dict:
    """Game-readiness figures: geometry, draw calls, textures and their estimated GPU memory."""
    accessors, views = document.get("accessors", []), document.get("bufferViews", [])
    primitives = [p for mesh in document.get("meshes", []) for p in mesh["primitives"]]
    triangles = sum((accessors[p["indices"]]["count"] if "indices" in p else accessors[p["attributes"]["POSITION"]]["count"]) // 3
                    for p in primitives)
    vertices = sum(accessors[p["attributes"]["POSITION"]]["count"] for p in primitives)
    images = []
    for image in document.get("images", []):
        view = views[image["bufferView"]]
        start = view.get("byteOffset", 0)
        width, height = image_size(binary[start:start + view["byteLength"]])
        images.append({"name": image.get("name", ""), "mime": image.get("mimeType"), "size": (width, height),
                       "mb": width * height * 4 * 4 / 3 / 2 ** 20})
    untextured_uv = []
    materials = document.get("materials", [])
    for mesh in document.get("meshes", []):
        for p in mesh["primitives"]:
            material = materials[p["material"]] if "material" in p else {}
            textured = "baseColorTexture" in material.get("pbrMetallicRoughness", {}) or "normalTexture" in material
            if textured and "TEXCOORD_0" not in p["attributes"]:
                untextured_uv.append(mesh.get("name", "?"))
    return {"primitives": len(primitives), "triangles": triangles, "vertices": vertices, "materials": len(materials),
            "images": images, "texture_mb": sum(i["mb"] for i in images), "missing_uvs": untextured_uv}


def check_budget(report: dict, settings: dict) -> None:
    if report["missing_uvs"]:
        raise ValueError(f"textured meshes without UVs: {report['missing_uvs']}")
    for image in report["images"]:
        if max(image["size"]) > settings["max_texture_size"]:
            raise ValueError(f"texture {image['name']} is {image['size']}; the limit is {settings['max_texture_size']}")
    if report["texture_mb"] > settings["texture_budget_mb"]:
        raise ValueError(f"textures need about {report['texture_mb']:.0f} MB of GPU memory; the budget is {settings['texture_budget_mb']} MB")


def print_report(report: dict, baked: dict | None) -> None:
    print(f"[Blender Lab] {report['primitives']} draw calls, {report['triangles']:,} triangles, "
          f"{report['vertices']:,} vertices, {report['materials']} materials")
    if baked:
        print(f"[Blender Lab] Lab materials merged {baked['objects_before']} meshes into {baked['objects_after']}")
    for image in report["images"]:
        print(f"[Blender Lab]   texture {image['name'] or '(unnamed)'}: {image['size'][0]}x{image['size'][1]} "
              f"{image['mime']}, ~{image['mb']:.1f} MB on the GPU")
    if report["images"]:
        print(f"[Blender Lab] Texture memory ~{report['texture_mb']:.1f} MB with mipmaps")


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


def build(source: Path, output: Path, keep_textures: Path | None = None) -> tuple[int, int]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"active Blender source not found: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from tools import lab_materials
    bpy.ops.wm.read_factory_settings(use_empty=True)
    runpy.run_path(str(source), run_name="__main__")
    texture_dir = Path(tempfile.mkdtemp(prefix=".lab-textures-", dir=output.parent))
    settings = lab_materials._settings()

    fd, temp_name = tempfile.mkstemp(prefix=".active-creation-", suffix=".glb", dir=output.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        baked = lab_materials.finalize(texture_dir)
        if keep_textures and baked:
            shutil.copytree(texture_dir, keep_textures, dirs_exist_ok=True)
        result = bpy.ops.export_scene.gltf(
            filepath=str(temp_path),
            export_format="GLB",
            export_animations=True,
            export_cameras=False,
            export_lights=False,
            export_image_format="AUTO",  # JPEG base colour stays JPEG; data maps stay lossless PNG
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Blender GLB export did not finish: {result}")
        document, binary = read_glb(temp_path)
        report = asset_report(document, binary)
        print_report(report, baked)
        check_budget(report, settings)

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
        shutil.rmtree(texture_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--keep-textures", type=Path, help="also copy the baked texture images into this folder")
    args = parser.parse_args()
    try:
        objects, meshes = build(args.source, args.output, args.keep_textures)
    except Exception as error:
        print(f"[Blender Lab] Build failed: {error}", file=sys.stderr)
        return 1
    print(f"[Blender Lab] Wrote {args.output.resolve()} ({objects} objects, {meshes} meshes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
