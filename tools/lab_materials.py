"""Blender Lab material pipeline: stylised-PBR recipes, UV layout, texture baking, export prep.

A creation source declares materials with `surface()` and builds its meshes as usual:

    from tools import lab_materials as lab
    fur = lab.surface("Lion fur", "fur", color=(0.5, 0.32, 0.13), belly=(0.9, 1.3))

The builder (tools/build_active_creation.py) then calls `finalize()` before exporting. Sources
that never call `surface()` are exported untouched, so older creations build exactly as before.

`finalize()` turns every lab material into glTF-ready PBR textures:

* Atlas recipes (fur, plumage, skin, scales, keratin, leather, metal, wood, stone, plain) are
  procedural node trees evaluated in world space. All objects using them are unwrapped together
  into one shared UV atlas (Smart UV Project, packed with per-material texel weights), and Cycles
  bakes base colour, roughness, metallic, a tangent-space normal map from the recipe's height,
  and ambient occlusion from the whole creation. The result is ONE atlas material: a base-colour
  JPEG, an ORM PNG (R occlusion, G roughness, B metallic), and a normal PNG.
* Card recipes (feather, eye) keep the UVs their geometry authored (see tools/lab_shapes.py) and
  get generated textures. Feather materials share one card atlas with four variants; each feather
  material's colour and the creation's baked ambient occlusion go into the COLOR_0 vertex colour,
  so every feather colour is one material and one draw call per bone.
* Rigid, unanimated meshes that share a parent bone and material are merged to cut draw calls.

Colours are linear RGB, sizes are metres, and textures follow glTF conventions (sRGB base colour,
linear data maps, OpenGL-style +Y normal maps).
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np


DEFAULTS = {
    "name": "Creation",
    "atlas_size": 1024,       # body atlas base colour
    "atlas_data_size": None,  # body atlas normal map; None matches atlas_size
    "atlas_orm_size": None,   # body atlas ORM map; None matches atlas_data_size
    "card_size": 1024,        # feather and membrane card base colour
    "card_data_size": None,   # card normal and ORM maps; None matches card_size
    "eye_size": 512,
    "ao_distance": 0.35,      # metres; how far baked ambient occlusion looks
    "ao_samples": 48,
    "card_ao_distance": 0.06, # metres; shorter, so only overlapping feather layers shade each other
    "card_ao_strength": 0.45, # how much that occlusion darkens feather vertex colours
    "texture_budget_mb": 64,  # estimated GPU memory for all textures, mipmaps included
    "max_texture_size": 2048,
    "merge": True,
    "jpeg_quality": 90,
}

ATLAS_RECIPES = ("plain", "fur", "plumage", "skin", "scales", "dragon", "keratin", "leather", "metal", "wood", "stone", "blend")
CARD_RECIPES = ("feather", "membrane", "eye")


# ---------------------------------------------------------------- public API

def configure(**settings):
    """Override pipeline settings for this creation (see DEFAULTS)."""
    unknown = set(settings) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown lab material settings: {sorted(unknown)}")
    current = _settings()
    current.update(settings)
    bpy.context.scene["lab_settings"] = json.dumps(current)


def surface(name, recipe, color, **params):
    """Create a lab material. `color` is linear RGB. Common params: color2, scale (pattern size in
    metres), roughness, metallic, variation (0-1 tonal variation), bump (normal strength) and
    texel (atlas area weight; 2 doubles a part's texture resolution). Recipe-specific params are
    documented on each recipe below. The "blend" recipe crossfades two atlas recipes across the
    body: a=(recipe, params), b=(recipe, params), axis ("x", "y" or "z"), start and end positions
    along it in metres, and `noise` (metres of ragged edge) - for transitions such as feathers into
    fur. Card recipes accept `jitter` (0-0.2): per-piece random variation of value and warmth."""
    if recipe not in ATLAS_RECIPES + CARD_RECIPES:
        raise ValueError(f"unknown recipe '{recipe}'; choose from {ATLAS_RECIPES + CARD_RECIPES}")
    mat = bpy.data.materials.new(name=name)
    mat["lab_recipe"] = recipe
    mat["lab_params"] = json.dumps({"color": list(color), **{k: list(v) if isinstance(v, tuple) else v for k, v in params.items()}})
    # A flat preview so the scene reads correctly in Blender before finalize() bakes it.
    mat.diffuse_color = (*color, 1.0)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = params.get("roughness", 0.6)
    shader.inputs["Metallic"].default_value = params.get("metallic", 0.0)
    return mat


def finalize(workdir):
    """Bake every lab material into glTF PBR textures. Returns a report dict, or None when the
    creation uses no lab materials. Image files are written under `workdir`."""
    scene = bpy.context.scene
    lab_mats = [m for m in bpy.data.materials if m.get("lab_recipe")]
    if not lab_mats:
        return None
    settings = _settings()
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    meshes = [o for o in scene.objects if o.type == "MESH" and any(s.material in lab_mats for s in o.material_slots)]
    report = {"objects_before": len(meshes), "textures": []}

    restore = _rest_pose()
    try:
        _prepare_cycles(scene, settings)
        atlas_objects = [o for o in meshes if _recipe(o) in ATLAS_RECIPES]
        card_objects = [o for o in meshes if _recipe(o) in CARD_RECIPES]
        mixed = [o.name for o in meshes if o not in atlas_objects and o not in card_objects]
        if mixed:
            raise ValueError(f"objects mixing lab and other materials are not supported: {mixed}")

        replacements = {}
        if atlas_objects:
            replacements.update(_bake_atlas(atlas_objects, settings, workdir, report))
        if card_objects:
            replacements.update(_finish_cards(card_objects, settings, workdir, report))
        for obj in meshes:
            for slot in obj.material_slots:
                if slot.material in replacements:
                    slot.material = replacements[slot.material]
        wanted = {new: old.name for old, new in replacements.items()}
        for mat in lab_mats:
            bpy.data.materials.remove(mat)
        for new, name in wanted.items():
            if new.name.startswith(name + "."):
                new.name = name
    finally:
        restore()

    survivors = [o for o in scene.objects if o.type == "MESH"]
    if settings["merge"]:
        survivors = _merge_rigid(survivors)
    report["objects_after"] = len([o for o in survivors if o.type == "MESH"])
    report["texture_mb"] = round(sum(t["mb"] for t in report["textures"]), 1)
    return report


# ---------------------------------------------------------------- settings and scene helpers

def _settings():
    stored = bpy.context.scene.get("lab_settings")
    return {**DEFAULTS, **(json.loads(stored) if stored else {})}


def _params(mat):
    return json.loads(mat["lab_params"])


def _recipe(obj):
    recipes = {s.material.get("lab_recipe") for s in obj.material_slots if s.material}
    if len(recipes) != 1 or None in recipes:
        return None
    return recipes.pop()


def _rest_pose():
    """Bake in the rest pose; returns a function restoring each armature's pose setting."""
    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    previous = [(a, a.data.pose_position) for a in armatures]
    for armature in armatures:
        armature.data.pose_position = "REST"
    bpy.context.view_layer.update()

    def restore():
        for armature, position in previous:
            armature.data.pose_position = position
    return restore


def _prepare_cycles(scene, settings):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.use_denoising = False
    scene.cycles.seed = 7
    if scene.world is None:
        scene.world = bpy.data.worlds.new("Lab bake world")
    scene.world.light_settings.distance = settings["ao_distance"]
    scene.render.bake.margin_type = "EXTEND"


def _select(objects, active=None):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or objects[0]


def _bake(kind, objects, samples, margin, **options):
    bpy.context.scene.cycles.samples = samples
    _select(objects)
    result = bpy.ops.object.bake(type=kind, margin=margin, use_clear=True, **options)
    if "FINISHED" not in result:
        raise RuntimeError(f"Cycles {kind} bake did not finish: {result}")


# ---------------------------------------------------------------- node-graph helpers for recipes

class Graph:
    """Small helper for building recipe node trees."""

    def __init__(self, tree):
        self.tree = tree
        self.position = self.new("ShaderNodeNewGeometry").outputs["Position"]

    def new(self, kind, **attrs):
        node = self.tree.nodes.new(kind)
        for key, value in attrs.items():
            setattr(node, key, value)
        return node

    def put(self, socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.tree.links.new(value, socket)
        elif socket.type in ("RGBA",) and len(value) == 3:
            socket.default_value = (*value, 1.0)
        else:
            socket.default_value = value

    def _io(self, sockets, identifier):
        return next(s for s in sockets if s.identifier == identifier)

    def coords(self, scale, stretch=None):
        """World position divided by `scale`, optionally stretched along axes (x, y, z) factors."""
        vec = self.new("ShaderNodeVectorMath", operation="SCALE")
        self.put(vec.inputs[0], self.position)
        self.put(vec.inputs["Scale"], 1.0 / scale)
        out = vec.outputs[0]
        if stretch:
            mul = self.new("ShaderNodeVectorMath", operation="MULTIPLY")
            self.put(mul.inputs[0], out)
            mul.inputs[1].default_value = stretch
            out = mul.outputs[0]
        return out

    def noise(self, vec, scale=1.0, detail=4.0, roughness=0.55, distortion=0.0):
        node = self.new("ShaderNodeTexNoise")
        self.put(node.inputs["Vector"], vec)
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        node.inputs["Roughness"].default_value = roughness
        node.inputs["Distortion"].default_value = distortion
        return node.outputs["Fac"]

    def voronoi(self, vec, scale=1.0, feature="F1", randomness=1.0):
        node = self.new("ShaderNodeTexVoronoi", feature=feature)
        self.put(node.inputs["Vector"], vec)
        node.inputs["Scale"].default_value = scale
        node.inputs["Randomness"].default_value = randomness
        return node

    def wave(self, vec, scale=1.0, kind="BANDS", direction="X", distortion=0.0, detail=2.0):
        node = self.new("ShaderNodeTexWave", wave_type=kind)
        if kind == "BANDS":
            node.bands_direction = direction
        else:
            node.rings_direction = direction
        self.put(node.inputs["Vector"], vec)
        node.inputs["Scale"].default_value = scale
        node.inputs["Distortion"].default_value = distortion
        node.inputs["Detail"].default_value = detail
        return node.outputs["Fac"]

    def math(self, operation, a, b=0.0, clamp=False):
        node = self.new("ShaderNodeMath", operation=operation, use_clamp=clamp)
        self.put(node.inputs[0], a)
        self.put(node.inputs[1], b)
        return node.outputs[0]

    def add(self, *terms):
        total = terms[0]
        for term in terms[1:]:
            total = self.math("ADD", total, term)
        return total

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def lin(self, value, scale, offset):
        """value * scale + offset"""
        node = self.new("ShaderNodeMath", operation="MULTIPLY_ADD")
        self.put(node.inputs[0], value)
        self.put(node.inputs[1], scale)
        self.put(node.inputs[2], offset)
        return node.outputs[0]

    def smooth(self, value, lo, hi, to_lo=0.0, to_hi=1.0):
        node = self.new("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        self.put(node.inputs["Value"], value)
        node.inputs["From Min"].default_value = lo
        node.inputs["From Max"].default_value = hi
        node.inputs["To Min"].default_value = to_lo
        node.inputs["To Max"].default_value = to_hi
        return node.outputs["Result"]

    def mix(self, factor, a, b, blend="MIX"):
        node = self.new("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self.put(self._io(node.inputs, "Factor_Float"), factor)
        self.put(self._io(node.inputs, "A_Color"), a)
        self.put(self._io(node.inputs, "B_Color"), b)
        return self._io(node.outputs, "Result_Color")

    def shade(self, color, k):
        """color multiplied by a grey value k."""
        return self.mix(1.0, color, (k, k, k), "MULTIPLY") if not isinstance(k, bpy.types.NodeSocket) else \
            self.mix(1.0, color, self.grey(k), "MULTIPLY")

    def grey(self, value):
        node = self.new("ShaderNodeCombineColor")
        for i in range(3):
            self.put(node.inputs[i], value)
        return node.outputs[0]

    def axis(self, name):
        node = self.new("ShaderNodeSeparateXYZ")
        self.put(node.inputs[0], self.position)
        return node.outputs["XYZ".index(name.upper())]

    def body(self):
        """(x, y, z) outputs of the "Body" vector attribute a creation stores on its meshes."""
        attribute = self.new("ShaderNodeAttribute", attribute_name="Body", attribute_type="GEOMETRY")
        split = self.new("ShaderNodeSeparateXYZ")
        self.put(split.inputs[0], attribute.outputs["Vector"])
        return split.outputs[0], split.outputs[1], split.outputs[2]

    def distance_to(self, point):
        node = self.new("ShaderNodeVectorMath", operation="DISTANCE")
        self.put(node.inputs[0], self.position)
        node.inputs[1].default_value = point
        return node.outputs["Value"]


def _stretch(flow, amount):
    """Scale factors that elongate a pattern along the named axis."""
    factors = [1.0, 1.0, 1.0]
    factors["xyz".index(flow.lower())] = 1.0 / amount
    return factors


# ---------------------------------------------------------------- atlas recipes
# Each returns base (colour), tone (0-1, 0.5 neutral), height (0-1), rough, metal, occl (or None).

def _recipe_plain(g, p):
    """Barely-there surface variation for painted or synthetic surfaces."""
    n = g.noise(g.coords(p.get("scale", 0.2)), detail=3)
    return dict(base=p["color"], tone=n, height=g.mul(n, 0.3), rough=g.lin(n, 0.1, p.get("roughness", 0.5) - 0.05),
                metal=p.get("metallic", 0.0), occl=None)


def _recipe_fur(g, p):
    """Short pelt: streaks along `flow` ("x", "y" or "z"), soft clumps, optional countershading
    with `belly=(low_z, high_z)` blending from color2 below to color above. `leg_flow` with
    `legs=(low_z, high_z)` turns the streaks to run along the legs below that height, `dorsal`
    =(low_z, high_z) darkens towards color3 along the back, and `mottle` (0-0.3) adds broad,
    soft colour variation."""
    scale = p.get("scale", 0.05)
    streak = g.noise(g.coords(scale, _stretch(p.get("flow", "y"), 7.0)), scale=6.0, detail=8, roughness=0.62)
    if "legs" in p:
        leg_streak = g.noise(g.coords(scale, _stretch(p.get("leg_flow", "z"), 7.0)), scale=6.0, detail=8, roughness=0.62)
        weight = g.smooth(g.axis("z"), *p["legs"])
        streak = g.add(leg_streak, g.mul(g.math("SUBTRACT", streak, leg_streak), weight))
    clumps = g.voronoi(g.coords(scale * 2.5), scale=1.0, feature="SMOOTH_F1").outputs["Distance"]
    base = p["color"]
    if "belly" in p:
        low, high = p["belly"]
        base = g.mix(g.smooth(g.axis("z"), low, high), p.get("color2", p["color"]), p["color"])
    if "dorsal" in p:
        base = g.mix(g.smooth(g.axis("z"), *p["dorsal"]), base, p.get("color3", [c * 0.7 for c in p["color"]]))
    if p.get("mottle"):
        broad = g.noise(g.coords(scale * 14), detail=2, roughness=0.4)
        base = g.mix(g.mul(g.smooth(broad, 0.35, 0.75), p["mottle"] * 2), base, g.shade(base, 0.78))
    tone = g.add(g.mul(streak, 0.75), g.lin(clumps, -0.35, 0.3))
    return dict(base=base, tone=tone, height=g.add(g.mul(streak, 0.7), g.lin(clumps, -0.3, 0.3)),
                rough=g.lin(streak, 0.16, p.get("roughness", 0.82) - 0.08), metal=0.0,
                occl=g.smooth(clumps, 0.0, 0.6, 0.8, 1.0))


def _recipe_plumage(g, p):
    """Close-lying contour feathers: overlapping rounded scales with fine barbs."""
    scale = p.get("scale", 0.025)
    cells = g.voronoi(g.coords(scale), feature="F1", randomness=0.8)
    edges = g.voronoi(g.coords(scale), feature="DISTANCE_TO_EDGE", randomness=0.8).outputs["Distance"]
    barbs = g.noise(g.coords(scale * 0.12, _stretch(p.get("flow", "z"), 4.0)), scale=1.0, detail=3)
    cell_tone = g.new("ShaderNodeSeparateColor")
    g.put(cell_tone.inputs[0], cells.outputs["Color"])
    lift = g.smooth(edges, 0.0, 0.3)
    tone = g.add(g.lin(cell_tone.outputs[0], p.get("variation", 0.3), 0.5 - p.get("variation", 0.3) / 2),
                 g.lin(barbs, 0.25, -0.12), g.lin(lift, 0.15, -0.1))
    return dict(base=p["color"], tone=tone, height=g.add(g.mul(lift, 0.7), g.mul(barbs, 0.3)),
                rough=g.lin(barbs, 0.1, p.get("roughness", 0.6) - 0.05), metal=0.0,
                occl=g.smooth(edges, 0.0, 0.18, 0.72, 1.0))


def _recipe_skin(g, p):
    """Bare skin such as a cere, paw pads or a snout: pores and soft wrinkles."""
    scale = p.get("scale", 0.006)
    pores = g.voronoi(g.coords(scale), feature="F1").outputs["Distance"]
    pit = g.smooth(pores, 0.25, 0.0)
    wrinkle = g.noise(g.coords(scale * 6), scale=1.0, detail=2, distortion=1.5)
    blotch = g.noise(g.coords(scale * 20), scale=1.0, detail=2)
    tone = g.add(g.lin(blotch, p.get("variation", 0.35), 0.5 - p.get("variation", 0.35) / 2), g.mul(pit, -0.15))
    return dict(base=p["color"], tone=tone, height=g.add(g.mul(wrinkle, 0.5), g.mul(pit, -0.4)),
                rough=g.lin(pit, 0.12, p.get("roughness", 0.5)), metal=0.0, occl=g.lin(pit, -0.25, 1.0))


def _recipe_scales(g, p):
    """Reptilian or avian scutes: domed cells with dark creases."""
    scale = p.get("scale", 0.022)
    cells = g.voronoi(g.coords(scale), feature="F1", randomness=0.85)
    edge = g.voronoi(g.coords(scale), feature="DISTANCE_TO_EDGE", randomness=0.85).outputs["Distance"]
    crease = g.smooth(edge, 0.09, 0.0)
    dome = g.smooth(edge, 0.0, 0.32)
    cell_tone = g.new("ShaderNodeSeparateColor")
    g.put(cell_tone.inputs[0], cells.outputs["Color"])
    variation = p.get("variation", 0.3)
    tone = g.add(g.lin(cell_tone.outputs[1], variation, 0.55 - variation / 2), g.mul(crease, -0.45))
    return dict(base=p["color"], tone=tone, height=g.add(g.mul(dome, 0.8), g.mul(crease, -0.3)),
                rough=g.lin(crease, 0.32, p.get("roughness", 0.42)), metal=0.0, occl=g.lin(crease, -0.5, 1.0))


def _recipe_dragon(g, p):
    """Dragon hide: a hierarchy of overlapping scales driven by the mesh's "Body" attribute - x is
    metres along the spine, y is the angle around it from 0 on top to 1 underneath (store it unsigned:
    a signed -1..1 value interpolates through 0 across the belly seam), z is a local scale
    size factor (1 on the body, lower at joints, limbs and face). Large armoured scales along the
    back, imbricate flank scales that shrink with z, and transverse belly plates underneath.
    Colours: color (crimson), color2 (scarlet highlights), color3 (burgundy creases), soot (dorsal
    ridges), belly (plates) and ember (a band where flank meets belly)."""
    arc, around, size = g.body()
    side = g.math("ABSOLUTE", around)
    belly = g.smooth(side, p.get("belly_start", 0.62), p.get("belly_end", 0.74))
    dorsal = g.smooth(side, p.get("dorsal_width", 0.3), 0.05)
    size = g.math("MAXIMUM", size, 0.2)
    density = g.math("DIVIDE", 1.0 / p.get("scale", 0.05), size)
    coords = g.new("ShaderNodeVectorMath", operation="SCALE")
    g.put(coords.inputs[0], g.position)
    g.put(coords.inputs["Scale"], density)
    coords = coords.outputs[0]

    def scale_layer(vec, randomness):
        cells = g.voronoi(vec, feature="F1", randomness=randomness)
        edge = g.voronoi(vec, feature="DISTANCE_TO_EDGE", randomness=randomness).outputs["Distance"]
        offset = g.new("ShaderNodeVectorMath", operation="SUBTRACT")
        g.put(offset.inputs[0], cells.outputs["Position"])
        g.put(offset.inputs[1], vec)
        lean = g.new("ShaderNodeSeparateXYZ")
        g.put(lean.inputs[0], offset.outputs[0])
        tone = g.new("ShaderNodeSeparateColor")
        g.put(tone.inputs[0], cells.outputs["Color"])
        # Scales overlap towards the tail: the leading edge of each one sits higher.
        imbricate = g.smooth(lean.outputs[1], -0.55, 0.55)
        return g.smooth(edge, 0.085, 0.0), g.smooth(edge, 0.0, 0.34), imbricate, tone.outputs[0]

    big = g.new("ShaderNodeVectorMath", operation="SCALE")
    g.put(big.inputs[0], coords)
    big.inputs["Scale"].default_value = 0.5
    crease_f, dome_f, lean_f, tone_f = scale_layer(coords, 0.9)
    crease_d, dome_d, lean_d, tone_d = scale_layer(big.outputs[0], 0.75)

    plate_len = g.mul(size, p.get("plate", 0.12))
    phase = g.math("DIVIDE", arc, plate_len)
    frac = g.math("FRACT", phase)
    plate_crease = g.add(g.smooth(frac, 0.1, 0.0), g.smooth(frac, 0.9, 1.0))
    plate_dome = g.math("SINE", g.mul(frac, math.pi))
    plate_tone = g.noise(g.math("FLOOR", phase), scale=3.1, detail=1)

    def lerp(a, b, m):
        return g.add(a, g.mul(g.math("SUBTRACT", b, a), m))

    crease = lerp(lerp(crease_f, crease_d, dorsal), plate_crease, belly)
    dome = lerp(lerp(dome_f, dome_d, dorsal), plate_dome, belly)
    lean = lerp(lerp(lean_f, lean_d, dorsal), g.mul(frac, 0.0), belly)
    cell = lerp(tone_f, tone_d, dorsal)
    micro = g.noise(coords, scale=7.0, detail=3)
    broad = g.noise(g.coords(p.get("mottle_scale", 0.9)), detail=3, roughness=0.5)

    colour = g.mix(g.smooth(cell, 0.2, 0.9), p["color"], p.get("color2", p["color"]))
    colour = g.mix(g.mul(dome, 0.35), colour, p.get("color2", p["color"]))
    colour = g.mix(crease, colour, p.get("color3", [c * 0.4 for c in p["color"]]))
    colour = g.mix(g.mul(dorsal, g.lin(crease_d, 0.35, 0.55)), colour, p.get("soot", [c * 0.2 for c in p["color"]]))
    band = g.mul(g.smooth(side, 0.42, 0.56), g.smooth(side, 0.74, 0.6))
    colour = g.mix(g.mul(band, p.get("ember_amount", 0.55)), colour, p.get("ember", p["color"]))
    plate_colour = g.mix(g.lin(plate_tone, 0.3, 0.0), p.get("belly", p["color"]), [c * 0.85 for c in p.get("belly", p["color"])])
    plate_colour = g.mix(plate_crease, plate_colour, [c * 0.5 for c in p.get("belly", p["color"])])
    colour = g.mix(belly, colour, plate_colour)
    colour = g.mix(g.mul(g.smooth(broad, 0.42, 0.72), p.get("mottle", 0.3)), colour, g.shade(colour, 0.68))
    return dict(base=colour, tone=g.add(g.lin(micro, 0.2, 0.4), g.mul(lean, 0.12)),
                height=g.add(g.mul(dome, 0.7), g.mul(crease, -0.45), g.mul(lean, 0.35), g.mul(micro, 0.08)),
                rough=g.add(g.lin(crease, 0.28, p.get("roughness", 0.42)), g.mul(dorsal, 0.1), g.mul(belly, 0.06)),
                metal=0.0, occl=g.lin(crease, -0.55, 1.0))


def _recipe_keratin(g, p):
    """Beaks, claws, talons and horns: glossy, with growth striations along `grain` and an optional
    darker `tip` point (x, y, z) fading out over `tip_radius` into `tip_color`."""
    scale = p.get("scale", 0.01)
    streak = g.noise(g.coords(scale, _stretch(p.get("grain", "y"), 6.0)), scale=4.0, detail=6, roughness=0.55)
    base = p["color"]
    if "tip" in p:
        fade = g.smooth(g.distance_to(p["tip"]), p.get("tip_radius", 0.1), 0.0)
        base = g.mix(fade, base, p.get("tip_color", [c * 0.25 for c in p["color"]]))
    if "root" in p:
        fade = g.smooth(g.distance_to(p["root"]), p.get("root_radius", 0.08), 0.0)
        base = g.mix(fade, base, p.get("root_color", p["color"]))
    if p.get("along"):
        # Per-piece gradient from the "Body" attribute's x (0 at the root, 1 at the tip).
        t = g.body()[0]
        base = g.mix(g.smooth(t, p.get("tip_start", 0.55), 1.0), base, p.get("tip_color", [c * 0.25 for c in p["color"]]))
        base = g.mix(g.smooth(t, p.get("root_end", 0.25), 0.0), base, p.get("root_color", p["color"]))
    return dict(base=base, tone=g.lin(streak, p.get("variation", 0.5), 0.5 - p.get("variation", 0.5) / 2),
                height=g.mul(streak, 0.4), rough=g.lin(streak, 0.12, p.get("roughness", 0.28) - 0.06),
                metal=p.get("metallic", 0.0), occl=None)


def _recipe_leather(g, p):
    """Tanned hide: pebbled grain, creases and wear."""
    scale = p.get("scale", 0.01)
    grain = g.voronoi(g.coords(scale), feature="DISTANCE_TO_EDGE").outputs["Distance"]
    crease = g.smooth(grain, 0.08, 0.0)
    wear = g.noise(g.coords(scale * 25), detail=3)
    tone = g.add(g.lin(wear, 0.5, 0.25), g.mul(crease, -0.3))
    return dict(base=p["color"], tone=tone, height=g.lin(crease, -0.6, 0.6), rough=g.lin(wear, -0.2, p.get("roughness", 0.7)),
                metal=0.0, occl=g.lin(crease, -0.3, 1.0))


def _recipe_metal(g, p):
    """Bare or painted metal: directional scratches along `grain`, optional `rust` (0-1) in color2."""
    scale = p.get("scale", 0.05)
    scratch = g.smooth(g.noise(g.coords(scale * 0.3, _stretch(p.get("grain", "x"), 30.0)), scale=3.0, detail=4), 0.62, 0.72)
    smudge = g.noise(g.coords(scale * 4), detail=3)
    rough = g.add(g.lin(smudge, 0.2, p.get("roughness", 0.32) - 0.1), g.mul(scratch, -0.15))
    base, metal, occl = p["color"], p.get("metallic", 1.0), None
    if p.get("rust", 0) > 0:
        rust = g.smooth(g.noise(g.coords(scale * 3), detail=6, roughness=0.65), 0.75 - 0.35 * p["rust"], 0.8 - 0.35 * p["rust"])
        base = g.mix(rust, base, p.get("color2", (0.25, 0.09, 0.03)))
        metal = g.lin(rust, -metal, metal)
        rough = g.mix(rust, g.grey(rough), (0.88, 0.88, 0.88))
        occl = g.lin(rust, -0.15, 1.0)
    return dict(base=base, tone=g.lin(smudge, 0.4, 0.3), height=g.add(g.mul(scratch, -0.3), g.mul(smudge, 0.2)),
                rough=rough, metal=metal, occl=occl)


def _recipe_wood(g, p):
    """Wood: growth rings around `grain` axis plus fine grain; color2 is the late-wood colour."""
    scale = p.get("scale", 0.03)
    axis = p.get("grain", "z").upper()
    rings = g.wave(g.coords(scale, _stretch(axis, 8.0)), scale=1.0, kind="RINGS", direction=axis, distortion=3.0, detail=3)
    fibre = g.noise(g.coords(scale * 0.1, _stretch(axis, 20.0)), detail=5)
    base = g.mix(g.smooth(rings, 0.3, 0.8), p["color"], p.get("color2", [c * 0.55 for c in p["color"]]))
    return dict(base=base, tone=g.lin(fibre, 0.6, 0.2), height=g.add(g.mul(fibre, 0.5), g.mul(rings, 0.2)),
                rough=g.lin(fibre, 0.15, p.get("roughness", 0.6)), metal=0.0, occl=None)


def _recipe_stone(g, p):
    """Rock and masonry: mottled colour between color and color2 with cracks."""
    scale = p.get("scale", 0.15)
    mottle = g.noise(g.coords(scale), detail=8, roughness=0.6)
    crack = g.smooth(g.voronoi(g.coords(scale * 2), feature="DISTANCE_TO_EDGE").outputs["Distance"], 0.04, 0.0)
    base = g.mix(mottle, p["color"], p.get("color2", [c * 0.7 for c in p["color"]]))
    return dict(base=base, tone=g.lin(crack, -0.4, 0.5), height=g.add(g.mul(mottle, 0.6), g.mul(crack, -0.6)),
                rough=g.lin(mottle, 0.1, p.get("roughness", 0.85) - 0.05), metal=0.0, occl=g.lin(crack, -0.6, 1.0))


RECIPE_GRAPHS = {name: globals()[f"_recipe_{name}"] for name in ATLAS_RECIPES if name != "blend"}


def _channels(g, recipe, p):
    """Final colour, roughness, metallic, occlusion and height (in metres) for a recipe."""
    if recipe == "blend":
        return _blend(g, p)
    out = RECIPE_GRAPHS[recipe](g, p)
    contrast = p.get("contrast", 0.35)
    base = out["base"] if isinstance(out["base"], bpy.types.NodeSocket) else tuple(out["base"])
    tone = g.math("MAXIMUM", g.math("MINIMUM", out["tone"], 1.0), 0.0)
    color = g.mix(tone, g.shade(base, 1.0 - contrast), g.shade(base, 1.0 + contrast * 0.5))
    rough = out["rough"]
    if isinstance(rough, bpy.types.NodeSocket) and rough.type == "RGBA":
        rough = g.new("ShaderNodeSeparateColor")
        g.put(rough.inputs[0], out["rough"])
        rough = rough.outputs[0]
    height = g.mul(out["height"], p.get("bump", 0.5) * p.get("scale", 0.02) * 0.15)
    return dict(color=color, rough=rough, metal=out["metal"], occl=out["occl"] if out["occl"] is not None else 1.0, height=height)


def _blend(g, p):
    (recipe_a, params_a), (recipe_b, params_b) = p["a"], p["b"]
    a, b = _channels(g, recipe_a, params_a), _channels(g, recipe_b, params_b)
    position = g.axis(p.get("axis", "y"))
    if p.get("noise"):
        ragged = g.noise(g.coords(p.get("noise_scale", 0.12)), detail=4, roughness=0.6)
        position = g.add(position, g.lin(ragged, 2 * p["noise"], -p["noise"]))
    mask = g.smooth(position, p["start"], p["end"])

    def lerp(x, y):
        return g.add(x, g.mul(g.math("SUBTRACT", y, x), mask))

    return dict(color=g.mix(mask, a["color"], b["color"]), rough=lerp(a["rough"], b["rough"]),
                metal=lerp(a["metal"], b["metal"]), occl=lerp(a["occl"], b["occl"]), height=lerp(a["height"], b["height"]))


def _build_bake_material(mat, image):
    """Replace mat's nodes with its recipe plus switchable outputs for each bake pass."""
    p = _params(mat)
    tree = mat.node_tree
    tree.nodes.clear()
    g = Graph(tree)
    out = _channels(g, mat["lab_recipe"], p)
    color, rough = out["color"], out["rough"]
    bump = g.new("ShaderNodeBump")
    g.put(bump.inputs["Height"], out["height"])
    bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = 1.0
    bsdf = g.new("ShaderNodeBsdfPrincipled")
    g.put(bsdf.inputs["Normal"], bump.outputs["Normal"])
    emit = g.new("ShaderNodeEmission")
    output = g.new("ShaderNodeOutputMaterial")
    target = g.new("ShaderNodeTexImage")
    target.image = image
    tree.nodes.active = target
    channels = {"color": color, "rough": rough, "metal": out["metal"], "occl": out["occl"]}

    def show(channel):
        for link in list(output.inputs["Surface"].links):
            tree.links.remove(link)
        if channel == "normal":
            tree.links.new(bsdf.outputs[0], output.inputs["Surface"])
            return
        for link in list(emit.inputs["Color"].links):
            tree.links.remove(link)
        value = channels[channel]
        if isinstance(value, bpy.types.NodeSocket):
            g.put(emit.inputs["Color"], value if value.type == "RGBA" else g.grey(value))
        else:
            emit.inputs["Color"].default_value = (*value, 1.0) if isinstance(value, (list, tuple)) else (value, value, value, 1.0)
        tree.links.new(emit.outputs[0], output.inputs["Surface"])

    return target, show


# ---------------------------------------------------------------- atlas: unwrap, bake, compose

def _closed(mesh):
    return all(len(e.link_faces) == 2 for e in mesh.edges)


def _clean_normals(objects):
    """Closed meshes get consistent outward normals, so they can be back-face culled safely."""
    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        if bm.faces and _closed(bm):
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(obj.data)
        bm.free()


def _unwrap(objects, size, weights=None):
    """Unwrap objects together into one 0-1 UV space with uniform texel density scaled by weights."""
    for obj in objects:
        for layer in list(obj.data.uv_layers):
            obj.data.uv_layers.remove(layer)
        obj.data.uv_layers.new(name="UVMap")
    _select(objects)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, area_weight=0.0, correct_aspect=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    if weights:
        for obj in objects:
            factor = math.sqrt(weights.get(obj.name, 1.0))
            uv = np.empty(len(obj.data.uv_layers[0].data) * 2, np.float32)
            obj.data.uv_layers[0].data.foreach_get("uv", uv)
            obj.data.uv_layers[0].data.foreach_set("uv", uv * factor)
            obj.data.update()
    _select(objects)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=6.0 / size, rotate=True, scale=True)
    bpy.ops.object.mode_set(mode="OBJECT")


def _downsample(array, factor):
    """Box-filter an (H, W, C) array down by an integer factor."""
    h, w, c = array.shape
    return array.reshape(h // factor, factor, w // factor, factor, c).mean(axis=(1, 3))


def _float_image(name, size):
    image = bpy.data.images.new(name, size, size, alpha=False, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    return image


def _pixels(image):
    data = np.empty(image.size[0] * image.size[1] * 4, np.float32)
    image.pixels.foreach_get(data)
    return data.reshape(image.size[1], image.size[0], 4)


def _bake_atlas(objects, settings, workdir, report):
    size = settings["atlas_size"]
    margin = max(4, size // 128)
    _clean_normals(objects)
    weights = {o.name: float(_params(o.material_slots[0].material).get("texel", 1.0)) for o in objects}
    _unwrap(objects, size, weights)

    buffers = {k: _float_image(f"lab bake {k}", size) for k in ("color", "rough", "metal", "occl", "normal", "ao")}
    switches = []
    for mat in {s.material for o in objects for s in o.material_slots}:
        switches.append(_build_bake_material(mat, buffers["color"]))
    for channel in ("color", "rough", "metal", "occl"):
        for target, show in switches:
            target.image = buffers[channel]
            show(channel)
        _bake("EMIT", objects, 4, margin)
    for target, show in switches:
        target.image = buffers["normal"]
        show("normal")
    _bake("NORMAL", objects, 4, margin, normal_space="TANGENT")
    for target, _ in switches:
        target.image = buffers["ao"]
    _bake("AO", objects, settings["ao_samples"], margin)

    px = {k: _pixels(img) for k, img in buffers.items()}
    name = settings["name"]
    color = _write(f"{name} atlas color", _to_srgb(px["color"][..., :3]), workdir / "atlas_color.jpg", "JPEG", "sRGB", settings)
    ao = np.clip(px["ao"][..., 0] * 0.8 + 0.2, 0, 1) * np.clip(px["occl"][..., 0], 0, 1)
    orm = np.stack([ao, np.clip(px["rough"][..., 0], 0.04, 1), np.clip(px["metal"][..., 0], 0, 1)], axis=-1)
    data_size = settings["atlas_data_size"] or size
    orm_size = settings["atlas_orm_size"] or data_size
    normal = px["normal"][..., :3]
    if orm_size < size:
        orm = _downsample(orm, size // orm_size)
    if data_size < size:
        normal = _downsample(normal, size // data_size) * 2 - 1
        normal = normal / np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-6) * 0.5 + 0.5
    orm = _write(f"{name} atlas ORM", orm, workdir / "atlas_orm.png", "PNG", "Non-Color", settings)
    normal = _write(f"{name} atlas normal", np.clip(normal, 0, 1), workdir / "atlas_normal.png", "PNG", "Non-Color", settings)
    for image in buffers.values():
        bpy.data.images.remove(image)
    for image, role in ((color, "atlas base colour"), (orm, "atlas ORM"), (normal, "atlas normal")):
        report["textures"].append(_texture_entry(image, role))

    atlas = _pbr_material(f"{name} atlas", color, orm, normal, double_sided=False)
    return {s.material: atlas for o in objects for s in o.material_slots}


# ---------------------------------------------------------------- card textures (numpy)

def _value_noise(height, width, cells_y, cells_x, seed, wrap_x=False):
    rng = np.random.default_rng(seed)
    grid = rng.random((cells_y + 2, cells_x + 2))
    if wrap_x:
        grid[:, cells_x] = grid[:, 0]
        grid[:, cells_x + 1] = grid[:, 1]
    y = (np.arange(height) + 0.5) / height * cells_y
    x = (np.arange(width) + 0.5) / width * cells_x
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    a = grid[y0][:, x0]
    b = grid[y0][:, x0 + 1]
    c = grid[y0 + 1][:, x0]
    d = grid[y0 + 1][:, x0 + 1]
    top = a + (b - a) * fx[None, :]
    bottom = c + (d - c) * fx[None, :]
    return top + (bottom - top) * fy[:, None]


def _fbm(height, width, cells_y, cells_x, seed, octaves=4, wrap_x=False):
    total, amplitude, norm = 0.0, 1.0, 0.0
    for octave in range(octaves):
        scale = 2 ** octave
        total = total + amplitude * _value_noise(height, width, cells_y * scale, cells_x * scale, seed + octave, wrap_x)
        norm += amplitude
        amplitude *= 0.5
    return total / norm


def _smoothstep(lo, hi, x):
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def _hash(values):
    return np.modf(np.sin(values * 12.9898 + 78.233) * 43758.5453)[0] % 1.0


def _normal_from_height(height, strength):
    dy, dx = np.gradient(height)
    normal = np.stack([-dx * strength, -dy * strength, np.ones_like(height)], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return normal * 0.5 + 0.5


def feather_card(size, rows=4, seed=11):
    """Neutral feather atlas: `rows` variants stacked in v - plain with a soft darker margin,
    irregularly barred, pale-fringed with a dark shaft streak, and finely vermiculated. u runs
    base to tip and each row's centre line is the rachis. Barbs sweep towards the tip with slight
    waviness and the odd split; the base is downy. Returns linear colour, roughness, metallic,
    occlusion and an encoded normal map, all shaped (H, W, ...)."""
    tile = size // rows
    t = np.broadcast_to((np.arange(size) + 0.5) / size, (tile, size))
    t = np.clip((t - 0.01) / 0.98, 0, 1)
    inset = 0.04
    across = ((np.arange(tile) + 0.5) / tile - inset) / (1 - 2 * inset)
    across = np.broadcast_to(np.clip(across, 0, 1)[:, None], (tile, size))
    d = np.abs(across - 0.5) * 2
    side = np.sign(across - 0.5)
    parts = {k: [] for k in ("color", "rough", "occl", "height")}
    for variant in range(rows):
        s = seed + variant * 17
        wobble = _fbm(tile, size, 4, 24, s + 1, 3) - 0.5
        shaft = 0.03 * (1 - 0.7 * t) + 0.007
        rachis = _smoothstep(shaft, shaft * 0.4, d)
        phase = t * 50 - d * 6.5 + wobble * 1.2
        index = np.floor(phase) + side * 1000 + variant * 7
        frac = phase - np.floor(phase)
        barb = (0.5 + 0.5 * np.cos(2 * np.pi * phase)) ** 1.4
        barb_tone = 0.93 + 0.07 * _hash(index)
        split = (_hash(index * 1.37) > 0.955) * _smoothstep(0.35, 0.65, d) * _smoothstep(0.2, 0.0, frac)
        down = _smoothstep(0.14, 0.02, t)
        fluff = _fbm(tile, size, 8, 64, s, 3)
        broad = _fbm(tile, size, 2, 5, s + 3, 3) - 0.5
        # Natural transitions: a paler base, a slightly deeper distal half and a soft dark margin.
        tone = 0.9 + 0.1 * broad + 0.06 * (1 - _smoothstep(0.1, 0.5, t)) - 0.05 * _smoothstep(0.5, 1.0, t)
        tone = tone * (1 - 0.1 * _smoothstep(0.7, 1.0, d))
        if variant == 1:
            spacing = 5.2 + 0.8 * broad
            bands = 0.5 + 0.5 * np.sin(2 * np.pi * (t * spacing + d * 0.35 + wobble * 0.5))
            tone = tone * (1 - 0.24 * _smoothstep(0.55, 0.9, bands) * _smoothstep(0.12, 0.3, t))
        elif variant == 2:
            fringe = _smoothstep(0.86, 0.97, t) + 0.6 * _smoothstep(0.82, 0.98, d) * _smoothstep(0.3, 0.6, t)
            streak = _smoothstep(0.22, 0.04, d + 0.04 * wobble) * _smoothstep(0.15, 0.35, t)
            tone = tone + 0.1 * np.clip(fringe, 0, 1) - 0.28 * streak
        elif variant == 3:
            vermiculation = _fbm(tile, size, 6, 30, s + 9, 4)
            tone = tone * (1 - 0.16 * _smoothstep(0.52, 0.66, vermiculation))
        tone = tone * barb_tone * (0.88 + 0.12 * barb) * (1 - 0.3 * split)
        tone = tone * (1 - rachis) + (0.95 - 0.12 * t) * rachis
        tone = tone * (1 - down) + (0.86 + 0.1 * fluff) * down
        height = (barb * 0.45 * (1 - rachis) + rachis * 0.9 - split * 0.5) * (1 - down) + fluff * 0.25 * down
        rough = 0.62 + 0.08 * (1 - barb) - 0.22 * rachis + 0.15 * split + 0.2 * down
        occl = 1 - 0.16 * (1 - barb) * (1 - rachis) - 0.25 * split - 0.1 * down
        parts["color"].append(tone)
        parts["rough"].append(rough)
        parts["occl"].append(occl)
        parts["height"].append(height)
    tone = np.concatenate(parts["color"], axis=0)
    warm = np.array([1.0, 0.975, 0.94])
    color = np.clip(tone[..., None] * warm, 0, 1)
    height = np.concatenate(parts["height"], axis=0)
    return dict(color=color, rough=np.clip(np.concatenate(parts["rough"]), 0.05, 1),
                metal=np.zeros_like(tone), occl=np.clip(np.concatenate(parts["occl"]), 0, 1),
                normal=_normal_from_height(height, 1.3))


def membrane_card(size, seed=23):
    """Neutral wing-membrane texture: u runs from the membrane's root to its trailing edge and v
    across the panel between two finger bones. Branching veins, a capillary web, thicker margins
    along the bones, a darker trailing rim and fine tension wrinkles."""
    u = np.broadcast_to((np.arange(size) + 0.5) / size, (size, size))
    v = np.broadcast_to(((np.arange(size) + 0.5) / size)[:, None], (size, size))
    wobble = _fbm(size, size, 6, 3, seed, 3) - 0.5
    veins = np.zeros((size, size))
    for k, centre in enumerate((0.17, 0.36, 0.55, 0.74, 0.88)):
        path = centre + 0.05 * np.sin(u * (3 + k) + k) + 0.06 * wobble
        width = 0.006 + 0.007 * (1 - u)
        veins = np.maximum(veins, _smoothstep(width, width * 0.25, np.abs(v - path)))
        # Side branches angling out towards the trailing edge.
        for b in range(3):
            start = 0.2 + 0.25 * b + 0.05 * k
            branch = path + (u - start) * (0.5 if (k + b) % 2 else -0.5)
            reach = _smoothstep(start - 0.01, start + 0.02, u) * _smoothstep(start + 0.32, start + 0.18, u)
            veins = np.maximum(veins, 0.7 * reach * _smoothstep(0.0045, 0.001, np.abs(v - branch)))
    web = 1 - np.abs(2 * _fbm(size, size, 18, 10, seed + 3, 4) - 1)
    capillary = _smoothstep(0.86, 0.96, web)
    margin = _smoothstep(0.1, 0.0, v) + _smoothstep(0.9, 1.0, v)
    rim = _smoothstep(0.93, 1.0, u)
    wrinkle = 0.5 + 0.5 * np.sin(2 * np.pi * (v * 46 + 3 * wobble))
    broad = _fbm(size, size, 3, 3, seed + 7, 3) - 0.5
    tone = 0.9 + 0.12 * broad - 0.3 * veins - 0.1 * capillary - 0.2 * margin - 0.15 * rim
    color = np.clip(tone[..., None] * np.array([1.0, 0.95, 0.92]), 0, 1)
    height = 0.6 * veins + 0.25 * capillary + 0.12 * wrinkle + 0.3 * margin
    return dict(color=color, rough=np.clip(0.55 + 0.1 * veins + 0.08 * margin, 0, 1), metal=np.zeros_like(tone),
                occl=np.clip(1 - 0.2 * veins - 0.15 * margin, 0, 1), normal=_normal_from_height(height, 1.2))


CARD_TEXTURES = {"feather": feather_card, "membrane": membrane_card}


def eye_card(size, iris, outer, pupil=0.1, iris_radius=0.3, seed=5, slit=1.0):
    """Iris texture for an ellipsoid whose +Z pole is the gaze: v=1 is the pupil centre and u wraps
    around it. A gold-to-bronze gradient, fine radial fibres, a wavy collarette, darker crypts,
    sparse flecks, a soft limbal ring and a slightly irregular pupil. `slit` below 1 narrows the
    pupil across u = 0.25/0.75 into a vertical slit, so u = 0 must point up the eye."""
    v = (np.arange(size) + 0.5) / size
    r = np.broadcast_to((1 - v)[:, None], (size, size))
    angle = np.broadcast_to(((np.arange(size) + 0.5) / size * 2 * np.pi)[None, :], (size, size))
    fibres = _fbm(size, size, 8, 128, seed, 3, wrap_x=True)
    coarse = _fbm(size, size, 6, 32, seed + 2, 3, wrap_x=True)
    crypts = _fbm(size, size, 12, 40, seed + 4, 2, wrap_x=True)
    flecks = _fbm(size, size, 40, 160, seed + 6, 1, wrap_x=True)
    iris, outer = np.array(iris), np.array(outer)
    a, b = pupil, pupil * slit
    shape = a * b / np.sqrt((b * np.cos(angle)) ** 2 + (a * np.sin(angle)) ** 2)
    edge = shape + 0.006 * np.sin(angle * 5 + 1.3) + 0.004 * (coarse - 0.5)
    radial = np.clip((r - edge) / (iris_radius - edge), 0, 1)
    inner_color, outer_color = np.clip(iris * 1.3 + 0.05, 0, 1), iris * 0.55
    color = inner_color[None, None, :] + (outer_color - inner_color)[None, None, :] * _smoothstep(0.1, 0.95, radial)[..., None]
    light = 0.8 + 0.35 * fibres + 0.12 * (coarse - 0.5)
    collarette = 0.33 + 0.04 * np.sin(angle * 11 + 3 * coarse)
    light = light + 0.22 * _smoothstep(0.07, 0.0, np.abs(radial - collarette))
    light = light - 0.22 * _smoothstep(0.58, 0.72, crypts) * _smoothstep(0.38, 0.5, radial)
    light = light - 0.35 * _smoothstep(0.8, 0.86, flecks)
    color = color * light[..., None] * (1 - 0.7 * _smoothstep(0.78, 1.0, radial))[..., None]
    color = np.where((r > iris_radius)[..., None], outer[None, None, :] * (0.75 + 0.35 * coarse[..., None]), color)
    hole = _smoothstep(edge + 0.006, edge - 0.006, r)[..., None]
    color = color * (1 - hole) + 0.003 * hole
    return dict(color=np.clip(color, 0, 1))


# ---------------------------------------------------------------- cards: textures, vertex AO, materials

def _finish_cards(objects, settings, workdir, report):
    replacements = {}
    eyes = [o for o in objects if _recipe(o) == "eye"]
    for obj in objects:
        if not obj.data.uv_layers:
            _unwrap([obj], settings["card_size"])

    for kind, generate in CARD_TEXTURES.items():
        cards = [o for o in objects if _recipe(o) == kind]
        if not cards:
            continue
        size = settings["card_size"]
        data = settings["card_data_size"] or size
        card = generate(size)
        orm, normal = np.stack([card["occl"], card["rough"], card["metal"]], -1), card["normal"]
        if data < size:
            orm, normal = _downsample(orm, size // data), _downsample(normal, size // data)
        name = settings["name"]
        color = _write(f"{name} {kind} color", _to_srgb(card["color"]), workdir / f"{kind}_color.jpg", "JPEG", "sRGB", settings)
        orm = _write(f"{name} {kind} ORM", orm, workdir / f"{kind}_orm.png", "PNG", "Non-Color", settings)
        normal = _write(f"{name} {kind} normal", normal, workdir / f"{kind}_normal.png", "PNG", "Non-Color", settings)
        for image, role in ((color, f"{kind} base colour"), (orm, f"{kind} ORM"), (normal, f"{kind} normal")):
            report["textures"].append(_texture_entry(image, role))
        shared = _pbr_material(f"{name} {kind}s", color, orm, normal, vertex_color=True, double_sided=True)
        _bake_vertex_tint(cards, settings)
        for obj in cards:
            replacements[obj.material_slots[0].material] = shared

    for mat in {o.material_slots[0].material for o in eyes}:
        p = _params(mat)
        card = eye_card(settings["eye_size"], p["color"], p.get("color2", [c * 0.35 for c in p["color"]]),
                        p.get("pupil", 0.1), p.get("iris_radius", 0.3), slit=p.get("slit", 1.0))
        color = _write(f"{mat.name} iris", _to_srgb(card["color"]), workdir / f"eye_{len(replacements)}.png", "PNG", "sRGB", settings)
        report["textures"].append(_texture_entry(color, "eye base colour"))
        replacements[mat] = _pbr_material(mat.name, color, None, None, roughness=p.get("roughness", 0.06),
                                          emission=p.get("glow", 0.0), coat=1.0, double_sided=False)
    return replacements


def _bake_vertex_tint(objects, settings):
    """Bake the creation's ambient occlusion into each card's vertex colours, tinted by its colour."""
    for obj in objects:
        attrs = obj.data.color_attributes
        # Per-vertex (not per-corner) colour, so the exporter does not split vertices.
        layer = attrs.get("Color") or attrs.new("Color", "FLOAT_COLOR", "POINT")
        attrs.active_color = layer
    world = bpy.context.scene.world.light_settings
    world.distance = settings["card_ao_distance"]
    _bake("AO", objects, settings["ao_samples"], 0, target="VERTEX_COLORS")
    world.distance = settings["ao_distance"]
    strength = settings["card_ao_strength"]
    for obj in objects:
        params = _params(obj.material_slots[0].material)
        layer = obj.data.color_attributes["Color"]
        count = len(layer.data)
        values = np.empty(count * 4, np.float32)
        layer.data.foreach_get("color", values)
        shade = 1 - strength + strength * values.reshape(-1, 4)[:, :1]
        tint = np.tile(np.array(params["color"] + [1.0], np.float32), (count, 1))
        authored = obj.data.color_attributes.get("Tint")
        if authored is not None:
            authored.data.foreach_get("color", tint.ravel())
            obj.data.color_attributes.remove(authored)
            layer = obj.data.color_attributes["Color"]
        jitter = params.get("jitter", 0.0)
        if jitter:
            # One random value and warmth shift per piece, so neighbouring feathers differ subtly.
            piece = _pieces(obj.data)
            rng = np.random.default_rng(len(piece) + count)
            value = 1 + rng.uniform(-jitter, jitter, piece.max() + 1)[piece]
            warm = rng.uniform(-jitter, jitter, piece.max() + 1)[piece] * 0.5
            tint[:, 0] *= value * (1 + warm)
            tint[:, 1] *= value
            tint[:, 2] *= value * (1 - warm)
        tint[:, :3] *= shade
        tint[:, 3] = 1.0
        layer.data.foreach_set("color", np.clip(tint, 0, None).ravel())


def _pieces(mesh):
    """Connected-component index per vertex (each feather card is its own component)."""
    parent = np.arange(len(mesh.vertices))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = np.empty(len(mesh.edges) * 2, np.int64)
    mesh.edges.foreach_get("vertices", edges)
    for a, b in edges.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots = np.array([find(i) for i in range(len(parent))])
    return np.unique(roots, return_inverse=True)[1]


# ---------------------------------------------------------------- images and final materials

def _to_srgb(linear):
    linear = np.clip(linear, 0, 1)
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)


def _write(name, array, path, file_format, colorspace, settings):
    """Save an (H, W, 3) array (already in the target colour encoding) and load it as a file image."""
    height, width = array.shape[:2]
    if max(height, width) > settings["max_texture_size"]:
        raise ValueError(f"{name} is {width}x{height}; the limit is {settings['max_texture_size']}")
    rgba = np.concatenate([array.reshape(height, width, -1)[..., :3], np.ones((height, width, 1))], axis=-1)
    image = bpy.data.images.new(name, width, height, alpha=False, float_buffer=False)
    image.colorspace_settings.name = "sRGB"  # byte pixels are stored as given; we encoded them already
    image.pixels.foreach_set(rgba.astype(np.float32).ravel())
    image.filepath_raw = str(path)
    image.file_format = file_format
    scene = bpy.context.scene
    scene.render.image_settings.quality = settings["jpeg_quality"]
    image.save(filepath=str(path), quality=settings["jpeg_quality"])
    bpy.data.images.remove(image)
    loaded = bpy.data.images.load(str(path))
    loaded.name = name
    loaded.colorspace_settings.name = colorspace
    return loaded


def _texture_entry(image, role):
    width, height = image.size
    return {"name": image.name, "role": role, "size": [width, height], "mb": round(width * height * 4 * 4 / 3 / 2 ** 20, 2)}


def _gltf_output_group():
    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        group.interface.new_socket(name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return group


def _pbr_material(name, color, orm, normal, vertex_color=False, roughness=1.0, emission=0.0, coat=0.0, double_sided=False):
    """A Principled material laid out the way the glTF exporter maps to core PBR + ORM textures."""
    mat = bpy.data.materials.new(name)
    mat.use_backface_culling = not double_sided
    tree = mat.node_tree
    g = Graph(tree)
    bsdf = tree.nodes.get("Principled BSDF")
    base = g.new("ShaderNodeTexImage")
    base.image = color
    base_out = base.outputs["Color"]
    if vertex_color:
        attr = g.new("ShaderNodeVertexColor", layer_name="Color")
        base_out = g.mix(1.0, base_out, attr.outputs["Color"], "MULTIPLY")
    g.put(bsdf.inputs["Base Color"], base_out)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if orm is not None:
        orm_node = g.new("ShaderNodeTexImage")
        orm_node.image = orm
        split = g.new("ShaderNodeSeparateColor")
        g.put(split.inputs[0], orm_node.outputs["Color"])
        g.put(bsdf.inputs["Roughness"], split.outputs["Green"])
        g.put(bsdf.inputs["Metallic"], split.outputs["Blue"])
        occlusion = g.new("ShaderNodeGroup")
        occlusion.node_tree = _gltf_output_group()
        g.put(occlusion.inputs["Occlusion"], split.outputs["Red"])
    if normal is not None:
        normal_node = g.new("ShaderNodeTexImage")
        normal_node.image = normal
        normal_map = g.new("ShaderNodeNormalMap")
        g.put(normal_map.inputs["Color"], normal_node.outputs["Color"])
        g.put(bsdf.inputs["Normal"], normal_map.outputs["Normal"])
    if emission:
        g.put(bsdf.inputs["Emission Color"], base.outputs["Color"])
        bsdf.inputs["Emission Strength"].default_value = emission
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.03
    return mat


# ---------------------------------------------------------------- draw-call reduction

def _merge_rigid(objects):
    """Join unanimated meshes that share a parent, parent bone, materials and (for skinned meshes)
    armature into one object."""
    groups = defaultdict(list)
    for obj in objects:
        armatures = [m.object for m in obj.modifiers if m.type == "ARMATURE"]
        if obj.animation_data or len(obj.modifiers) != len(armatures) or len(armatures) > 1 \
                or obj.data.shape_keys or obj.children or obj.data.users > 1:
            continue
        key = (obj.parent.name if obj.parent else "", obj.parent_type, obj.parent_bone,
               tuple(s.material.name if s.material else "" for s in obj.material_slots),
               armatures[0].name if armatures else "")
        groups[key].append(obj)
    for (parent, _, bone, materials, armature), members in groups.items():
        if len(members) < 2:
            continue
        prefix = members[0].name.split(" | ")[0]
        with bpy.context.temp_override(active_object=members[0], object=members[0], selected_objects=members,
                                       selected_editable_objects=members):
            bpy.ops.object.join()
        members[0].name = f"{prefix} | {'skinned' if armature else bone or parent or 'root'} | {materials[0]}"
        members[0].data.name = members[0].name
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]
