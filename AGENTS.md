# Blender Lab

This is a simple studio for Blender exports, with fewer menus and clear animation playback. Preserve this focus.

- Stack: vanilla JavaScript, Three.js, Vite. Start with README.md and src/main.js.
- Run npm ci, npm test, and npm run build before delivering changes.
- Keep model source scripts in assets/<name>/ and runtime GLBs in public/models/.
- public/models/manifest.json is an array of {name, file}; file paths are relative to public/models/.
- Do not modify another game repository as part of Lab work.
- Preserve clips, materials, rigs, and original scale when importing. Viewer transforms use a parent wrapper.
- Opening local files must not upload them. Exporting downloads a new artifact.
- The Studio moth is a procedural Three.js test asset, not a Blender build.
- Blender/bpy availability must be checked before promising a headless rebuild.
