"""Run with Blender: blender -b model.blend --python tools/export_blend.py -- output.glb"""
import os
import sys
import bpy

if '--' not in sys.argv or len(sys.argv[sys.argv.index('--') + 1:]) != 1:
    raise SystemExit('Expected one output .glb path after --')
output = os.path.abspath(sys.argv[sys.argv.index('--') + 1])
if not output.lower().endswith('.glb'):
    raise SystemExit('Output must end in .glb')
os.makedirs(os.path.dirname(output), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=output, export_format='GLB', export_animations=True)
print(f'Exported {output}')
