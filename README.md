# Blender Lab

A browser-based canvas for inspecting Blender creations. Blender Lab preserves the model shelf, animation controls, and review tools while the active creation is built with Blender Python in Work.

## Start Blender Lab on Windows

Double-click `Start-Blender-Lab.bat` in the repository root. It updates from GitHub `main`, installs dependencies when the lockfile changes, starts the local server, and opens Chrome. Keep the **Blender Lab Server** window open while you use the canvas. It checks GitHub every 15 seconds; when Work commits a changed active GLB, Vite reloads the page and the new model appears.

Requires Git for Windows, Node.js 22.12 or newer, and Google Chrome. No desktop Blender installation is needed on your PC. The launcher shows a readable error and keeps its window open if startup fails.

For development from a terminal, use `npm ci` and `npm run lab`. The simpler `npm run dev` command is still available, but it does not run the GitHub sync loop. Run `npm test` and `npm run build` to check the project.

## Active Blender creation

There is one predictable source for the current Work creation:

- Blender Python source: `creations/active/scene.py`
- Generated browser model: `public/models/active-creation.glb`
- Shelf registration: first entry in `public/models/manifest.json`

The source starts with an empty Blender scene. Work changes that Python file with `bpy`, then runs:

```sh
/opt/bpy-venv/bin/python tools/build_active_creation.py
```

The builder resets Blender to a blank scene, executes the source, exports a self-contained GLB, checks the GLB structure, imports it back with Blender, and only then replaces the active model. Keep the source and generated GLB together in the same GitHub commit. GitHub is the source of truth and keeps the version history.

### Working with Work

- Click **New Creation** to clear the canvas and begin from a blank creation. Then prompt Work to create or edit the active Blender scene. Work resets `creations/active/scene.py` to an empty scene for a new creation, or reads and modifies its current contents for an edit.
- For example: “Start with a cube,” “Make it into a canoe,” or “Add wooden ribs.” Work should update the active Python source, run the builder above, inspect the generated GLB, and commit both files to `main`.
- The server window pulls those commits automatically. The Vite watcher reloads the open canvas when the manifest or a model file changes.

The **Studio moth** remains on the shelf as a Three.js animation example. It is not the active Blender creation. Other repository GLBs can remain in the manifest shelf, and local GLBs can still be opened or dropped into the canvas for review.

## Canvas tools

Orbit, pan, zoom, frame, front and side views; animation selection and playback; timeline scrubbing and speed; grid, wireframe, turntable, scale and yaw; PNG snapshots; GLB export. Space toggles animation and F frames the model.

The app does not upload files opened from the computer. Export creates a downloaded copy and does not overwrite source assets or commit to GitHub.

## Build and hosting

`npm run build` creates `dist/`; `npm run preview` serves that build. Static hosting remains supported for review, but automatic GitHub sync is provided by the local `npm run lab` workflow.
