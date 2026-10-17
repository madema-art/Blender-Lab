"""A simple cube in the active Blender Lab creation."""

import bpy

bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 0.0))
cube = bpy.context.object
cube.name = "Active Cube"

material = bpy.data.materials.new(name="Sky Blue")
material.diffuse_color = (0.12, 0.48, 0.82, 1.0)
shader = material.node_tree.nodes.get("Principled BSDF")
shader.inputs["Base Color"].default_value = (0.12, 0.48, 0.82, 1.0)
shader.inputs["Roughness"].default_value = 0.42
cube.data.materials.append(material)
