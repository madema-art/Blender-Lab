"""Low-poly lighthouse on a rocky islet for Blender Lab's active creation."""

import bmesh
import bpy
import math
import random


def material(name, color, roughness=0.6, emission=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = (*color, 1.0)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1.0)
        shader.inputs["Emission Strength"].default_value = emission
    return mat


stone = material("Weathered stone", (0.36, 0.34, 0.31), 0.9)
white = material("Lighthouse white", (0.94, 0.93, 0.88), 0.5)
red = material("Lighthouse red", (0.74, 0.12, 0.09), 0.5)
iron = material("Iron gallery", (0.10, 0.11, 0.12), 0.4)
brass = material("Brass finial", (0.85, 0.62, 0.25), 0.3)
lamp = material("Lamp glass", (1.0, 0.80, 0.40), 0.1, emission=6.0)
window = material("Window glass", (0.12, 0.22, 0.30), 0.1)
oak = material("Oak door", (0.27, 0.16, 0.09), 0.7)
sea = material("Deep teal sea", (0.04, 0.27, 0.34), 0.15)


def place(kind, name, mat, location, scale=(1, 1, 1), **options):
    getattr(bpy.ops.mesh, f"primitive_{kind}_add")(location=location, **options)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    return obj


def smooth(obj):
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


# Water and islet. Cubes keep Blender's default size of 2, so their scale is a half-extent.
place("cylinder", "Sea | Water", sea, (0, 0, -0.02), vertices=48, radius=5.0, depth=0.04)

rng = random.Random(7)
rock = smooth(place("ico_sphere", "Islet | Rock", stone, (0, 0, 0), (1, 1, 0.35), subdivisions=3, radius=1.6))
for vertex in rock.data.vertices:
    vertex.co *= 1 + rng.uniform(-0.08, 0.08)

for index, (x, y, z, radius) in enumerate(((-1.35, -0.85, 0.02, 0.32), (1.30, -1.05, -0.02, 0.22), (-0.20, -1.60, 0.0, 0.28))):
    smooth(place("ico_sphere", f"Islet | Shore stone {index + 1}", stone, (x, y, z), (1, 1, 0.6), subdivisions=2, radius=radius))


# Striped tapering tower, one band per 0.5 units of height.
TOWER_BOTTOM = 0.4
TOWER_HEIGHT = 3.0


def tower_radius(z):
    return 0.62 - 0.22 * (z - TOWER_BOTTOM) / TOWER_HEIGHT


for band in range(6):
    z0 = TOWER_BOTTOM + band * 0.5
    z1 = z0 + 0.5
    place(
        "cone",
        f"Lighthouse | Tower band {band + 1}",
        white if band % 2 == 0 else red,
        (0, 0, (z0 + z1) / 2),
        vertices=24,
        radius1=tower_radius(z0),
        radius2=tower_radius(z1),
        depth=0.5,
    )

place("cube", "Lighthouse | Oak door", oak, (0, -0.6, 0.64), scale=(0.14, 0.05, 0.22))
place("cube", "Lighthouse | Tower window", window, (0, -0.5, 2.1), scale=(0.07, 0.04, 0.1))


# Gallery, railing, and lantern room.
place("cylinder", "Lighthouse | Gallery", iron, (0, 0, 3.44), vertices=24, radius=0.54, depth=0.08)
for post in range(12):
    angle = post * math.tau / 12
    place("cylinder", f"Lighthouse | Railing post {post + 1}", iron, (0.5 * math.cos(angle), 0.5 * math.sin(angle), 3.58), vertices=8, radius=0.018, depth=0.2)
place("torus", "Lighthouse | Railing", iron, (0, 0, 3.68), major_segments=32, minor_segments=6, major_radius=0.5, minor_radius=0.022)

place("cylinder", "Lighthouse | Lamp glass", lamp, (0, 0, 3.79), vertices=12, radius=0.28, depth=0.62)
for post in range(8):
    angle = post * math.tau / 8
    place("cylinder", f"Lighthouse | Lantern frame {post + 1}", iron, (0.3 * math.cos(angle), 0.3 * math.sin(angle), 3.79), vertices=6, radius=0.02, depth=0.62)
place("cone", "Lighthouse | Lantern roof", red, (0, 0, 4.28), vertices=12, radius1=0.38, radius2=0.03, depth=0.36)
smooth(place("uv_sphere", "Lighthouse | Brass finial", brass, (0, 0, 4.48), segments=12, ring_count=8, radius=0.07))


# Keeper's house tucked against the rock, with a gable roof built from explicit faces.
HOUSE_X, HOUSE_Y = 1.05, 0.15
place("cube", "Keeper house | Walls", white, (HOUSE_X, HOUSE_Y, 0.48), scale=(0.36, 0.3, 0.26))
place("cube", "Keeper house | Door", oak, (HOUSE_X - 0.36, HOUSE_Y, 0.4), scale=(0.04, 0.09, 0.16))
place("cube", "Keeper house | Window", window, (HOUSE_X, HOUSE_Y - 0.3, 0.62), scale=(0.1, 0.03, 0.08))

roof_points = [(-0.42, -0.36, 0.74), (0.42, -0.36, 0.74), (0.42, 0.0, 1.02), (-0.42, 0.0, 1.02), (-0.42, 0.36, 0.74), (0.42, 0.36, 0.74)]
roof_faces = [(0, 1, 2, 3), (3, 2, 5, 4), (0, 3, 4), (1, 5, 2)]
roof_mesh = bpy.data.meshes.new("Keeper house roof mesh")
roof_mesh.from_pydata(roof_points, [], roof_faces)
roof_mesh.update()
# Recalculate winding so the roof faces outward and renders from every viewing angle.
bm = bmesh.new()
bm.from_mesh(roof_mesh)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(roof_mesh)
bm.free()
roof_mesh.materials.append(red)
roof = bpy.data.objects.new("Keeper house | Roof", roof_mesh)
roof.location = (HOUSE_X, HOUSE_Y, 0)
bpy.context.collection.objects.link(roof)
