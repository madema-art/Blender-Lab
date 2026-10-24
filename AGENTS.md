# Blender Lab

This repository is a simple browser canvas for real Blender creations. Preserve the small interface, model shelf, animation tools, and review controls.

- Stack: vanilla JavaScript, Three.js, Vite. Start with README.md and src/main.js.
- Run `npm ci`, `npm test`, and `npm run build` before delivering changes.
- The active creation source is always `creations/active/scene.py`.
- The generated active model is always `public/models/active-creation.glb`; keep it first in `public/models/manifest.json`.
- Every manifest entry should carry an `updated` ISO timestamp. The library lists creations newest first by this field; the builder stamps the active entry automatically. Do not rename the `Active Creation` or `Alien Flying Saucer` entries: the Windows launcher's readiness check looks for them.
- To build it, use `/opt/bpy-venv/bin/python tools/build_active_creation.py`. This environment's Blender Python is confirmed working (bpy 5.2.2); do not assume other Python interpreters can import bpy.
- The builder resets to an empty Blender scene before executing the source. For a new creation, replace the active source with a blank scene before adding the requested objects. For an edit, read and modify the existing source so the creation remains cumulative.
- Save each finished creation as its own library entry before starting a new one: `python3 tools/save_creation.py --name "<Name>"`. It copies the active source and GLB under that name and never overwrites an existing creation. Use a new name for each creation.
- Give new creations Blender Lab materials: build meshes with `tools/lab_shapes.py` and declare materials with `lab.surface()` from `tools/lab_materials.py` (see README, "Materials and textures"). Pick the recipe that matches each surface, use `feather`/`eye` cards with geometry-authored UVs, and spend atlas resolution with `texel` on faces and hero details. The builder unwraps, bakes, and merges automatically; keep its report within budget rather than raising limits.
- Prefer texture detail to extra geometry. Do not add post-processing or extra shadow-casting lights to the viewer.
- Commit the Python source and its generated GLB together. GitHub main is the source of truth; the local launcher syncs commits and Vite reloads changed models.
- Keep other repository models in the shelf. The Studio moth is a Three.js animation example, not a Blender build.
- Preserve clips, materials, rigs, and original scale when importing. Viewer transforms use a parent wrapper.
- Opening local files must not upload them. Exporting downloads a new artifact.
- Do not modify any other repository.

## Controllable creatures

- New animated creatures must be designed for Play Mode from the beginning. Set `bpy.context.scene['lab_controllable'] = True` and `lab_play_profile` to a JSON capability profile (schema and anatomy requirements in `docs/play-mode.md`). The builder must reject missing real clips before replacing the active GLB.
- Use rig-specific templates, never invent animation names or map incompatible anatomy to a generic gait. `tools/play_authoring.py` supports only the current Griffon V2 and Red Dragon rigs. Unsupported rigs need new authored templates and visual QA.
- Preserve source rigs and original GLBs. Locomotion must have keyed skeletal motion, clean loops, in-place strides matched to controller speed, stable roots, and tested takeoff/landing poses. Preserve Dragon membrane helper bones and Griffon feather transforms.
- Validate animation sidecars against their original skeletons. Run `npm test`, the Blender readiness validator, and browser play checks; inspect exported poses in actual playback. Never claim physical gamepad testing when only simulated input is available.
