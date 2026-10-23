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
- Each finished creation is saved as its own library entry. Work runs `python3 tools/save_creation.py --name "<Name>"` before starting a new creation, so earlier creations stay in the library.
- For example: “Start with a cube,” “Make it into a canoe,” or “Add wooden ribs.” Work should update the active Python source, run the builder above, inspect the generated GLB, and commit both files to `main`.
- The server window pulls those commits automatically. The Vite watcher reloads the open canvas when the manifest or a model file changes.

The **Studio moth** remains on the shelf as a Three.js animation example. It is not the active Blender creation. Other repository GLBs can remain in the manifest shelf, and local GLBs can still be opened or dropped into the canvas for review.

## Materials and textures

Creations are built as game-ready assets: UV-mapped, textured with physically based (PBR) materials, and exported as portable glTF 2.0 that any standard engine reads. The pipeline lives in two Blender Python modules that every creation source can import.

**`tools/lab_shapes.py`** builds meshes that carry UVs: `loft` (tubes), `ellipsoid`, `feather` (feather cards), `skin_body` (organic trunks from a skin-modifier skeleton), plus `Batch` to merge many small pieces into one mesh.

**`tools/lab_materials.py`** turns material recipes into textures. A source declares materials with `lab.surface(name, recipe, color, **params)`:

| Recipe | For | Mapping |
| --- | --- | --- |
| `fur`, `plumage`, `skin`, `scales`, `keratin` | Animals and creatures: pelts, body feathers, bare skin, scutes, beaks, claws, talons and horns | Atlas |
| `leather`, `metal`, `wood`, `stone`, `plain` | Props and environments | Atlas |
| `feather` | Feather cards; one shared texture, tinted per material | Card |
| `eye` | Eyes, with a generated iris, clearcoat cornea and a soft glow | Card |

Common parameters: `color` and `color2` (linear RGB), `scale` (pattern size in metres), `roughness`, `metallic`, `variation`, `contrast`, `bump`, and `texel` (how much atlas area a material earns; 2 doubles its resolution). Each recipe's docstring lists its own extras, such as `belly` countershading for fur or a darker `tip` for keratin. `lab.configure(...)` sets per-creation options such as `atlas_size`, `card_size` and the texture budget.

When the builder runs, it bakes these materials automatically:

1. **Atlas materials** are unwrapped together (Smart UV Project, packed with texel weights) and Cycles bakes base colour, roughness, metallic, a tangent-space normal map and ambient occlusion from the whole creation into **one material** with three textures: a base-colour JPEG, an ORM PNG (R occlusion, G roughness, B metallic) and a normal PNG.
2. **Card materials** keep the UVs their geometry authored. Feathers share one feather atlas with four variants (plain, barred, pale-tipped, mottled) showing barbs, a rachis, vane splits and downy bases. Each feather's tint and its baked contact shadow go into vertex colours (`COLOR_0`), so every feather colour in a creation is one material.
3. **Rigid meshes** that share a bone and a material are merged, which cuts draw calls.

Sources that never call `lab.surface()` build exactly as before, with their own flat materials.

### Budget and checks

The builder prints a report after every build: draw calls, triangles, vertices, materials, and each texture's size, format and estimated GPU memory (mipmaps included). The build fails if a textured mesh has no UVs, a texture is larger than 2048 pixels, or textures need more than 64 MB of GPU memory. A creation can lower those limits with `lab.configure`. `npm test` checks the same contract on every committed creation.

The Griffon is the reference: 15 draw calls (down from 38), about 41,000 vertices, three materials and seven textures using about 32 MB of GPU memory. To look at the baked images, build with `--keep-textures <folder>`.

Textures are embedded as JPEG (base colour) and PNG (data maps). GPU texture compression (KTX2 with Basis Universal) would cut memory by roughly four to six times but needs the KTX-Software encoder, which this environment does not include; the contract above keeps uncompressed textures within budget instead.

## Lighting and inspection

The right column holds the review tools for materials:

- **Lighting**: presets for Studio HDR (default), Daylight, Raking detail (a low grazing light that reveals normal maps), Dramatic rim, Neutral flat (even light for judging colour), and Classic Lab (the original lighting). Exposure, environment strength and a light turn slider adjust any preset. Ground shadow and Show environment are switches.
- **Materials**: the View menu shows Lit, Base colour, Roughness, Metallic, Normals, Ambient occlusion, or a UV checker. The list shows each material with its colour, values, traits and texture thumbnails; pick one to show only the parts that use it. Feather contact shadows live in vertex colours, so they appear in the Base colour view rather than the Ambient occlusion view.

The studio HDR environment, `public/environments/lab-studio.hdr`, is rendered by Blender from `tools/make_studio_hdr.py`, so it carries no third-party licence. Rendering stays light: no post-processing, one shadow-casting light, and image-based lighting that is prepared once per preset.

Models without UVs or textures still display normally; their materials show flat values in each channel view, and the UV checker reports parts without UVs.

## Library and viewer

The left column lists every creation newest first, with a preview of each model. Search narrows it by name, and the Up and Down arrow keys move through the list. The stage shows the selected model; its animations appear under the stage, with a filter box when a model has many. The right column holds details, display options, scale and turn, and saving.

To add a creation to the library, add a manifest entry with an `updated` timestamp.

## Shortcut icon

`assets/blender-lab.ico` is the Blender Lab icon. To apply it to your desktop shortcut, run `tools\set-shortcut-icon.ps1` from PowerShell after pulling. It only changes shortcuts that point to `Start-Blender-Lab.bat`.

## Canvas tools

Orbit, pan, zoom, frame, front and side views; animation selection and playback; timeline scrubbing and speed; grid, wireframe, turntable, scale and yaw; lighting presets and material channel views; PNG snapshots; GLB export. Space toggles animation, F frames the model, L cycles lighting presets and V cycles material views.

The app does not upload files opened from the computer. Export creates a downloaded copy and does not overwrite source assets or commit to GitHub.

## Build and hosting

`npm run build` creates `dist/`; `npm run preview` serves that build. Static hosting remains supported for review, but automatic GitHub sync is provided by the local `npm run lab` workflow.
