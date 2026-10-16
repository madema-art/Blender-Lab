# Blender Lab v0.1

A quiet, GitHub-based studio for viewing Blender creations in Three.js and trying their animations. A model shelf, a large viewport, and the controls you actually need.

## Run

Requires Node.js 22.12+ (or 24).

1. Clone this repository and open its folder in a terminal.
2. Run `npm ci`.
3. Run `npm run dev` and open the printed local address.

`npm test` checks animation playback and GLB export/import. `npm run build` produces a static site in `dist/`; `npm run preview` serves that build. The GitHub check workflow tests/builds each push and provides a downloadable build artifact.

## Included

- Procedural Studio moth with Flutter and Glide clips. This is a Three.js demo, not a Blender-generated asset.
- Load multiple self-contained `.glb` files with Open GLB or drag-and-drop.
- Orbit, pan, zoom, frame model, front and side views.
- Animation selection, play/pause, restart, timeline scrubbing, and playback speed.
- Grid, wireframe, turntable, scale, and yaw adjustments.
- Download a transparent PNG snapshot or export the current model as GLB, including clips and wrapper transforms.
- Responsive layout and keyboard shortcuts: **Space** plays/pauses; **F** frames the model.

## Add models to the permanent shelf

Put a self-contained GLB into `public/models/`. Add a corresponding entry to `public/models/manifest.json`, for example an object with `"name": "Castaway"` and `"file": "castaway.glb"` inside its array. Paths are relative to `public/models/`. Commit both files. The shelf loads them at startup.

Files opened from your computer stay in browser memory and disappear from the shelf on reload. Export downloads a new file; it does not overwrite your original or commit to GitHub. Nothing uploads your local models.

## Blender / AI workflow

Keep model-building Python scripts and optional `.blend` sources under `assets/<model>/`. Export GLB to `public/models/`, update the manifest, test in the Lab, and commit scripts and exports together. Future AI sessions should read `AGENTS.md` first.

In desktop Blender, choose **File → Export → glTF 2.0 → glTF Binary (.glb)**. Include animations and pack textures. For headless Blender, `tools/export_blend.py` exports the loaded scene; invoke it with Blender's `--background`, `--python`, and an output path after `--`.

## Scope

v0.1 inspects exported models and makes basic object transforms. Mesh editing, rig editing, animation authoring, and rebuilding assets remain Blender/Python tasks. Blender/bpy is not installed by this project. Only self-contained GLB is supported; compressed Draco/KTX2 assets require decoding support that is not included yet. Large assets depend on your browser/GPU memory.

## Hosting

The `dist/` build can be served on any static host, including GitHub Pages. Build URLs are relative so repository subpaths work. Hosting has not been configured by this repository's check workflow.
