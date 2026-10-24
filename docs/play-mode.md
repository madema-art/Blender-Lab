# Universal Play Mode

Launch **Blender Lab** from the desktop, choose **Griffon V2**, **Red Dragon**, or the current **Active Creation** (Dragon), then click **Enter Play Mode**. The inspection UI disappears completely. Escape restores the previous model transform, camera, material isolation/channel, lighting, selected clip, playback time and paused/running state.

## Controls

| Keyboard / mouse | Action |
| --- | --- |
| WASD | Camera-relative movement; smooth steering |
| Shift | Run / sprint |
| Space | Takeoff for these two flyers; jump only for profiles with a jump clip |
| E / Q | Climb / descend during flight (or swim vertically for aquatic profiles) |
| Hold G | Glide; release for powered flight |
| L | Descend, approach, land, settle, then return to walking |
| R | Special action while idle: Dragon Roar |
| Drag mouse | Orbit freely; wheel adjusts distance |
| Double-click canvas | Optional captured mouse look; Escape still returns to viewer |
| Escape | Exit and restore inspection |

| Standard Xbox-compatible gamepad | Action |
| --- | --- |
| Left stick | Analog movement, with dead zone and curved response |
| Right stick | Orbit camera |
| RT | Run on ground; climb in flight |
| LT | Descend in flight |
| A | Takeoff / jump when supported |
| B | Land |
| X | Special action |
| Hold Y | Glide |
| Menu / Start | Return to viewer |

Keyboard and standard-mapped Gamepad API devices work together. Focus loss clears held keyboard input. Non-standard gamepads need an explicit mapping. Hardware gamepad testing is separate from the automated standard-API simulation.

## Assets and animations

Original GLBs, source generators, all earlier Griffons, textures and existing clips remain unchanged. Animation-only sidecars extend the **same** library entries, without duplicating geometry or textures:

- `griffon-v2-play-animations.glb`
- `red-dragon-play-animations.glb`

Both contain **Play Idle, Play Walk, Play Run, Play Turn Left, Play Turn Right, Play Takeoff, Play Flight, Play Glide, Play Bank Left, Play Bank Right, Play Land**. The `Play ` prefix prevents replacing existing Idle / Perched / Wing beat / Flight / Roar clips. All clips remain available individually in the viewer.

`tools/play_authoring.py` builds actual keyed skeletal animation for these two specific rigs. The original wing-fold and feather functions remain in use. The Dragon's original finger and two-bone membrane-panel affine fitting runs on every new pose, including interpolated transitions. Its original Roar is used directly. Walk foot trajectories use a four-beat sequence and analytic two-bone IK; running converges to diagonal pairs. Contact feet sweep backwards relative to forward travel during stance, then lift and return during swing. Profile speed is stride distance divided by stance fraction and cycle duration. The heavier Dragon has a slower gait, acceleration, turns, takeoff and wingbeats. The Griffon's foreleg stride and crouch respect its shorter reach.

Movement is in-place, without accumulating horizontal root translation. Takeoff begins with compression and wing spreading; the world controller supplies smooth ascent. Landing descends before the timed approach/touchdown/absorption clip. Loop endpoints are explicitly identical. Blend weights decay smoothly; walk/run phases remain synchronized rather than restarting each frame. Bank clips articulate asymmetrical wings and head, alongside the controller's world bank.

Blender exporter versions can choose different feather-bone rolls. `tools/play_retarget.py` preserves armature-space deformation (`posed * inverse(bind)`) and converts it to the **original GLB's exact bind frames**. It does not alter the source model or attempt to retarget arbitrary anatomy.

Rebuild with a Python environment containing Blender's `bpy` (tested here with Python 3.11 / bpy 4.5.3; the original pipeline uses bpy 5.2):

```powershell
python tools/build_play_animations.py
# Or just one compatible rig:
python tools/build_play_animations.py griffon-v2
```

The tool executes the original rig generator, keys new actions, exports and strips the temporary GLB to animation data only, converts bind frames, validates required clips, and atomically publishes the sidecar. It then updates the existing manifest entries. It never bakes or replaces the original model textures.

## Capability profiles and future creations

`playProfile` is explicit metadata in `public/models/manifest.json`. There are no model-name guesses in the runtime. The same profile can also be embedded in a self-contained new creature build using scene metadata.

```python
import json
bpy.context.scene['lab_controllable'] = True
bpy.context.scene['lab_play_profile'] = json.dumps({
    'version': 1, 'category': 'quadruped',
    'flight': False, 'jump': False, 'swimming': False,
    'scale': 1, 'forwardYaw': 3.141592653589793,
    'animations': {'idle':'Idle','walk':'Walk','run':'Run',
                   'turnLeft':'Turn Left','turnRight':'Turn Right'},
    'specials': {},
    'motion': {'walk':1,'run':3,'acceleration':4,'turnRate':2},
    'camera': {'size':1.5,'height':1.2,'distance':8}, 'blend':.2,
})
```

This declaration does **not** create animation. Author the actual actions first. `tools/play_validation.py` rejects a declared controllable export missing its profile or required keyed clips **before** the active GLB is replaced. Saving a creation preserves its profile and any sidecar references. Rebuilding a different active creation clears stale former profile/sidecar metadata.

Required semantics depend on anatomy:

| Category / capability | Required clips |
| --- | --- |
| quadruped, biped | idle, walk, run, turnLeft, turnRight |
| flight | takeoff, flight, glide, bankLeft, bankRight, land |
| jump | jump |
| aquatic | idle, swim, turnLeft, turnRight, ascend, descend |
| slither | idle, slither, turnLeft, turnRight |
| specials | Every explicitly mapped special action |

Aquatic profiles use `motion.swim`, `motion.sprint` and `motion.vertical`; slithering profiles use `motion.slither` and `motion.sprint`. Both still supply acceleration, turn rate and camera framing. The aquatic controller allows vertical movement without a ground plane; terrestrial controllers remain grounded except supported jumps/flight. New categories require an explicit controller/template extension, not unrelated clip substitutions.

To add a creature:

1. Design its anatomy and stable rig, preserving weighted geometry and PBR assets.
2. Author an appropriate rig-specific template. Only Griffon V2 and Red Dragon currently have supplied authoring templates. Unsupported anatomy must fail authoring clearly until a compatible template exists.
3. Create real, sampled skeletal tracks with stable orientation, in-place movement, clean loop boundaries, compatible transitions and calibrated speeds.
4. Declare the profile, build with `tools/build_active_creation.py`, inspect actual exported playback from several views and check planted feet, feathers/membranes, takeoff and landing.
5. Save a new library entry with `tools/save_creation.py --name "New creature name"`; run validation, tests and browser QA before committing source and assets together.

Legacy/static props remain viewable without a profile. The disabled Play button and adjacent explanation list missing capabilities rather than offering fake locomotion.

## Runtime and performance

One existing renderer, animation loop and mixer are reused. Play input listeners are scoped to an AbortController and removed on exit; GPU star/ground/light resources are disposed. The sky uses 6,000 points in one draw call, three distance shells, per-star GPU twinkle, and very small parallax. The ground follows the camera and fades into black; stars are never obstacles. Soft key/rim/hemisphere lighting and the existing IBL reveal PBR surfaces. Only the Play key light casts a shadow (1024 map); the inspection lighting rig is hidden during play.

The two sidecars contain animation accessors and bone nodes only, so model draw calls, triangles, bones, textures and GPU texture memory stay unchanged. They add CPU animation tracks and a small download, plus one star draw and one ground draw in play (and the single shadow pass). No bloom or post-processing. Actual frame rate depends on hardware; automated software-rendered checks are not a hardware FPS benchmark.

The playground has a level ground and open air, without obstacles, terrain physics, combat, multiplayer or sound effects. The preserved Roar animates the creature; no roar audio was present in the original. Arbitrary legacy animals are not automatically made playable. Precise foot contacts through blends still need artistic evaluation on any new rig.

## Verification

```powershell
npm ci # stop the running Lab server first on Windows so esbuild.exe is not locked
npm test
npm run build
# Start a local dev server, then (requires Playwright and Chromium):
node tools/check_play_browser.mjs http://127.0.0.1:5174 path/to/evidence
```

`PLAYWRIGHT_MODULE` can point to an installed Playwright ESM entry. The browser check exercises both creatures, keyboard and simulated standard gamepad input, the full walk/run/takeoff/flight/glide/bank/land/roar sequence, mouse orbit/zoom, paused inspection restoration, repeated switching, model changes and missing-profile behavior. `render_game_to_text()` reports controller state; `advanceTime(ms)` advances the same simulation in fixed substeps and renders once for deterministic browser checks. Production rendering continues through the original single animation loop.
