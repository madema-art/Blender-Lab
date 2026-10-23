#!/usr/bin/env python3
"""Render Blender Lab's studio HDR environment: public/environments/lab-studio.hdr.

Run with /opt/bpy-venv/bin/python tools/make_studio_hdr.py. Cycles renders an equirectangular
panorama from the centre of a soft grey photo studio: a large warm key softbox, a cool fill
panel, an overhead strip, two narrow rim strips behind the subject, and a darker floor. The
result is a true high-dynamic-range light probe the viewer uses for image-based lighting.
It is generated here, so it carries no third-party licence.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public" / "environments" / "lab-studio.hdr"


def emissive(name, color, strength):
    mat = bpy.data.materials.new(name)
    tree = mat.node_tree
    tree.nodes.clear()
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*color, 1.0)
    emit.inputs["Strength"].default_value = strength
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emit.outputs[0], out.inputs[0])
    return mat


def panel(name, size, distance, azimuth, elevation, mat):
    """A rectangular light facing the origin. Azimuth 0 is in front of the subject (-Y)."""
    az, el = math.radians(azimuth), math.radians(elevation)
    position = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * distance
    bpy.ops.mesh.primitive_plane_add(size=1, location=position)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0], size[1], 1)
    obj.rotation_euler = (-position).to_track_quat("Z", "Y").to_euler()
    obj.rotation_euler.rotate_axis("X", math.pi)
    obj.data.materials.append(mat)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = False
    scene.render.resolution_x, scene.render.resolution_y = 1024, 512
    scene.render.image_settings.file_format = "HDR"
    scene.view_settings.view_transform = "Standard"

    world = bpy.data.worlds.new("Studio")
    scene.world = world
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.045, 0.05, 0.055, 1.0)

    # Cyclorama: soft grey walls, a slightly darker floor.
    bpy.ops.mesh.primitive_uv_sphere_add(radius=12, segments=48, ring_count=24)
    room = bpy.context.object
    wall = bpy.data.materials.new("Studio walls")
    shader = wall.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (0.32, 0.33, 0.34, 1.0)
    shader.inputs["Roughness"].default_value = 1.0
    room.data.materials.append(wall)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -1.6))
    floor = bpy.data.materials.new("Studio floor")
    shader = floor.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (0.12, 0.12, 0.125, 1.0)
    shader.inputs["Roughness"].default_value = 0.9
    bpy.context.object.data.materials.append(floor)

    panel("Key softbox", (4.0, 3.0), 6.0, -40, 38, emissive("Key", (1.0, 0.93, 0.84), 22))
    panel("Fill panel", (4.5, 3.0), 7.0, 65, 12, emissive("Fill", (0.82, 0.9, 1.0), 6))
    panel("Overhead strip", (6.0, 1.2), 6.5, 0, 82, emissive("Top", (1.0, 0.98, 0.95), 12))
    panel("Rim left", (0.8, 4.0), 6.0, 150, 25, emissive("Rim L", (0.95, 0.97, 1.0), 28))
    panel("Rim right", (0.8, 4.0), 6.0, -155, 25, emissive("Rim R", (1.0, 0.95, 0.9), 22))

    camera = bpy.data.objects.new("Probe", bpy.data.cameras.new("Probe"))
    scene.collection.objects.link(camera)
    camera.data.type = "PANO"
    camera.data.panorama_type = "EQUIRECTANGULAR"
    camera.rotation_euler = (math.pi / 2, 0, 0)  # horizon level; image centre looks along +Y
    scene.camera = camera

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(OUTPUT)
    bpy.ops.render.render(write_still=True)
    print(f"[Blender Lab] Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
