"""Brutal green orc with tusks, spiked shoulders, and a rusted axe for Blender Lab's active creation."""

import bpy
import math


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


skin = material("Ugly green skin", (0.22, 0.40, 0.14), 0.7)
skin_dark = material("Bruised green skin", (0.12, 0.24, 0.07), 0.75)
bone = material("Yellowed bone", (0.86, 0.80, 0.66), 0.45)
leather = material("Filthy leather", (0.27, 0.16, 0.08), 0.8)
iron = material("Rusted iron", (0.32, 0.30, 0.28), 0.5)
wound = material("Dried blood", (0.35, 0.05, 0.04), 0.5)
eye_glow = material("Angry eyes", (1.0, 0.35, 0.05), 0.2, emission=4.0)
dark = material("Matted hair", (0.08, 0.07, 0.05), 0.9)
mouth = material("Dark mouth", (0.18, 0.03, 0.03), 0.6)


def place(kind, name, mat, location, scale=(1, 1, 1), rotation=(0, 0, 0), **options):
    getattr(bpy.ops.mesh, f"primitive_{kind}_add")(location=location, **options)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    obj.data.materials.append(mat)
    return obj


def smooth(obj):
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


# Legs and feet. Cubes keep Blender's default size of 2, so their scale is a half-extent.
for side, x in (("left", -0.2), ("right", 0.2)):
    smooth(place("cylinder", f"Orc | {side.title()} thigh", skin, (x, 0, 0.73), vertices=16, radius=0.16, depth=0.6))
    smooth(place("cylinder", f"Orc | {side.title()} calf", skin_dark, (x, 0.02, 0.27), vertices=16, radius=0.13, depth=0.52))
    place("cube", f"Orc | {side.title()} foot", leather, (x, 0.1, 0.07), scale=(0.14, 0.27, 0.07))

# Hips, gut, and chest. The gut hangs forward over a leather loincloth.
smooth(place("uv_sphere", "Orc | Hips", skin, (0, 0, 0.98), (0.3, 0.26, 0.26), segments=20, ring_count=12, radius=1))
smooth(place("uv_sphere", "Orc | Gut", skin, (0, -0.04, 1.18), (0.44, 0.34, 0.3), segments=24, ring_count=14, radius=1))
smooth(place("uv_sphere", "Orc | Chest", skin, (0, 0, 1.56), (0.5, 0.34, 0.5), segments=28, ring_count=16, radius=1))
place("cube", "Orc | Loincloth", leather, (0, -0.25, 0.85), scale=(0.22, 0.04, 0.28))
for x in (-0.2, 0.2):
    smooth(place("uv_sphere", f"Orc | Pec muscle {x:+.1f}", skin_dark, (x, -0.31, 1.6), (0.2, 0.06, 0.18), segments=16, ring_count=10, radius=1))
for index, rotation_z in enumerate((0.55, 0.45, 0.6)):
    place("cylinder", f"Orc | Chest scar {index + 1}", wound, (0.0, -0.36, 1.42 + index * 0.14), rotation=(math.pi / 2, 0, rotation_z), vertices=6, radius=0.012, depth=0.32)


# Thick neck and bulging shoulders with bone spikes.
place("cylinder", "Orc | Neck", skin_dark, (0, 0, 2.1), vertices=14, radius=0.17, depth=0.3)
for side, x, angle in (("left", -0.5, -1.0), ("right", 0.5, 1.0)):
    smooth(place("uv_sphere", f"Orc | {side.title()} shoulder", skin, (x, 0, 1.98), (0.2, 0.2, 0.18), segments=16, ring_count=10, radius=1))
    place("cone", f"Orc | {side.title()} shoulder spike", bone, (x * 1.12, 0, 2.2), rotation=(0, angle, 0), vertices=6, radius1=0.07, radius2=0.0, depth=0.36)


# Arms: heavy upper arms, forearms, and fists. The right fist grips the axe.
for side, x in (("left", -0.6), ("right", 0.6)):
    smooth(place("cylinder", f"Orc | {side.title()} upper arm", skin, (x, 0, 1.6), rotation=(0, -x * 0.25, 0), vertices=16, radius=0.14, depth=0.62))
    smooth(place("cylinder", f"Orc | {side.title()} forearm", skin_dark, (x * 1.05, -0.08, 1.1), rotation=(0.25, 0, 0), vertices=16, radius=0.12, depth=0.56))
    smooth(place("ico_sphere", f"Orc | {side.title()} fist", skin, (x * 1.05, -0.16, 0.8), (1, 1.1, 0.9), subdivisions=2, radius=0.16))


# Axe in the right hand: a long haft with a notched iron blade.
place("cylinder", "Orc | Axe haft", leather, (0.7, -0.25, 0.95), rotation=(0.2, 0, 0), vertices=8, radius=0.03, depth=1.1)
place("cube", "Orc | Axe blade", iron, (0.7, -0.25, 1.5), scale=(0.03, 0.24, 0.16))
place("cone", "Orc | Axe blade point", iron, (0.7, -0.5, 1.5), rotation=(math.pi / 2, 0, 0), vertices=4, radius1=0.12, radius2=0.0, depth=0.18)


# Head: a squat skull with a heavy brow, sunken eyes, a flat broken nose, and a jutting jaw.
smooth(place("uv_sphere", "Orc | Skull", skin, (0, 0, 2.45), (0.29, 0.32, 0.33), segments=28, ring_count=16, radius=1))
smooth(place("uv_sphere", "Orc | Brow ridge", skin_dark, (0, -0.3, 2.5), (0.3, 0.12, 0.08), segments=20, ring_count=10, radius=1))
for side, x in (("left", -0.12), ("right", 0.12)):
    place("uv_sphere", f"Orc | {side.title()} eye socket", dark, (x, -0.26, 2.44), (0.07, 0.05, 0.05), segments=12, ring_count=8, radius=1)
    place("uv_sphere", f"Orc | {side.title()} eye", eye_glow, (x, -0.29, 2.44), segments=10, ring_count=6, radius=0.03)
smooth(place("uv_sphere", "Orc | Broken nose", skin_dark, (0, -0.3, 2.35), (0.07, 0.06, 0.09), segments=12, ring_count=8, radius=1))
smooth(place("uv_sphere", "Orc | Jaw", skin, (0, -0.18, 2.2), (0.27, 0.21, 0.14), segments=20, ring_count=12, radius=1))
place("uv_sphere", "Orc | Mouth", mouth, (0, -0.3, 2.27), (0.2, 0.04, 0.05), segments=12, ring_count=8, radius=1)
for side, x in (("left", -0.14), ("right", 0.14)):
    place("cone", f"Orc | {side.title()} tusk", bone, (x, -0.3, 2.3), rotation=(0.2, 0, -x * 1.2), vertices=10, radius1=0.05, radius2=0.0, depth=0.38)
for index, x in enumerate((-0.08, -0.03, 0.03, 0.08)):
    place("cone", f"Orc | Lower tooth {index + 1}", bone, (x, -0.31, 2.25), vertices=6, radius1=0.015, radius2=0.0, depth=0.05)
for side, x in (("left", -0.3), ("right", 0.3)):
    smooth(place("cone", f"Orc | {side.title()} ear", skin, (x, 0.02, 2.5), rotation=(0, math.copysign(math.pi / 2, x), 0), vertices=10, radius1=0.07, radius2=0.0, depth=0.3))
place("cylinder", "Orc | Cheek scar", wound, (0.15, -0.27, 2.35), rotation=(math.pi / 2, 0, 0.6), vertices=6, radius=0.01, depth=0.12)
for index, (x, z) in enumerate(((-0.2, 2.32), (0.1, 2.2))):
    smooth(place("uv_sphere", f"Orc | Wart {index + 1}", skin_dark, (x, -0.27, z), segments=8, ring_count=6, radius=0.03))

# Spiky matted ridge running back over the skull.
for index, y in enumerate((0.16, 0.04, -0.08, -0.2)):
    height = 0.3 - index * 0.03
    place("cone", f"Orc | Scalp spike {index + 1}", dark, (0, y, 2.76 - index * 0.02), rotation=(-0.3, 0, 0), vertices=6, radius1=0.06, radius2=0.0, depth=height)
