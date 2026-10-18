# Blender Lab

This repository is a simple browser canvas for real Blender creations. Preserve the small interface, model shelf, animation tools, and review controls.

- Stack: vanilla JavaScript, Three.js, Vite. Start with README.md and src/main.js.
- Run `npm ci`, `npm test`, and `npm run build` before delivering changes.
- The active creation source is always `creations/active/scene.py`.
- The generated active model is always `public/models/active-creation.glb`; keep it first in `public/models/manifest.json`.
- Every manifest entry should carry an `updated` ISO timestamp. The library lists creations newest first by this field; the builder stamps the active entry automatically. Do not rename the `Active Creation` or `Alien Flying Saucer` entries: the Windows launcher's readiness check looks for them.
- To build it, use `/opt/bpy-venv/bin/python tools/build_active_creation.py`. This environment's Blender Python is confirmed working (bpy 5.2.2); do not assume other Python interpreters can import bpy.
- The builder resets to an empty Blender scene before executing the source. For a new creation, replace the active source with a blank scene before adding the requested objects. For an edit, read and modify the existing source so the creation remains cumulative.
- Commit the Python source and its generated GLB together. GitHub main is the source of truth; the local launcher syncs commits and Vite reloads changed models.
- Keep other repository models in the shelf. The Studio moth is a Three.js animation example, not a Blender build.
- Preserve clips, materials, rigs, and original scale when importing. Viewer transforms use a parent wrapper.
- Opening local files must not upload them. Exporting downloads a new artifact.
- Do not modify any other repository.
