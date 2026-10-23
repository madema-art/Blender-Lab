"""Glowing, reflective glass cube around a cyan light core for Blender Lab's active creation."""

import bpy


def material(name, color, roughness=0.5, transmission=0.0, ior=1.45, emission=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = (*color, 1.0)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Transmission Weight"].default_value = transmission
    shader.inputs["IOR"].default_value = ior
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1.0)
        shader.inputs["Emission Strength"].default_value = emission
    return mat


glass = material("Reflective glass", (0.85, 0.97, 1.0), roughness=0.01, transmission=1.0, ior=1.5)
core = material("Glowing cyan core", (0.2, 0.85, 1.0), roughness=0.3, emission=4.0)


# Outer shell: a cube with softened, catching edges. Cubes keep Blender's default size of 2.
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1.0))
shell = bpy.context.object
shell.name = "Glow cube | Glass shell"
shell.data.materials.append(glass)
bevel = shell.modifiers.new("Soft edges", "BEVEL")
bevel.width = 0.07
bevel.segments = 4

# Inner core: a smaller cube that lights the glass from within.
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1.0))
light = bpy.context.object
light.name = "Glow cube | Light core"
light.scale = (0.45, 0.45, 0.45)
light.data.materials.append(core)
