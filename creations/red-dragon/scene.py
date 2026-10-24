"""Red Dragon: an ancient Western dragon - four legs, two great bat-wings - built as one skinned
game character for Blender Lab.

Blender is Z-up and the dragon faces -Y; the glTF exporter converts to Y-up. Units are metres:
about 8.6 m from snout to tail tip, 2 m at the shoulder, a 10 m wingspan.

Construction:
- One trunk surface runs from the back of the skull to the tail tip with all four legs, built from
  a skin-modifier skeleton and sculpted with muscle stamps (pectorals, the wing muscles over the
  shoulders, ribcage, flanks, glutes, quadriceps, hamstrings, calves, tail base).
- The skull and lower jaw are separate sculpted meshes with heavy brows, deep sockets, cheekbones
  and nostril mounds; individual teeth, a tongue, palate and throat sit inside the hinged mouth.
- Horns, cheek and jaw spikes, a cranial crest and dorsal spines are keratin pieces placed on the
  surfaces they grow from.
- Each wing is an arm, a thumb claw and four three-jointed fingers; the membrane is a set of
  Coons-patch panels between the fingers, the arm and the flank, skinned so it gathers when the
  fingers close.
- Scales are textures: a "Body" attribute (distance along the spine, angle around it, scale size)
  drives armoured dorsal scales, overlapping flank scales, small joint scales and belly plates.

Animation: forward kinematics from bone deltas plus analytic two-bone IK that keeps the feet planted
while the body crouches, bobs and rears. Clips: Idle, Perched, Wing beat, Roar and Flight.
"""

import math
import numpy
import random

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

from tools import lab_materials as lab
from tools import lab_shapes as shapes
from tools.lab_shapes import ellipsoid, eyelid, loft

lab.configure(name="Red Dragon", atlas_size=2048, atlas_data_size=2048, atlas_orm_size=1024, card_size=1024,
              card_data_size=512, eye_size=512, ao_distance=0.6, card_ao_distance=0.2, card_ao_strength=0.3)
rng = random.Random(11)


def jitter(amount):
    return rng.uniform(-amount, amount)


def smooth(lo, hi, x):
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


# ---------------------------------------------------------------- palette and materials (linear RGB)

CRIMSON, SCARLET, BURGUNDY = (0.19, 0.011, 0.011), (0.34, 0.024, 0.016), (0.055, 0.004, 0.006)
SOOT, BELLY, EMBER = (0.018, 0.007, 0.006), (0.16, 0.052, 0.03), (0.55, 0.11, 0.018)
hide_params = dict(color2=SCARLET, color3=BURGUNDY, soot=SOOT, belly=BELLY, ember=EMBER, roughness=0.44,
                   mottle=0.32, contrast=0.28, ember_amount=0.32)
hide = lab.surface("Dragon hide", "dragon", CRIMSON, scale=0.075, plate=0.17, bump=0.9, **hide_params)
face = lab.surface("Dragon face", "dragon", CRIMSON, scale=0.04, plate=0.07, bump=0.8, texel=2.4, dorsal_width=0.22,
                   **hide_params)
horn = lab.surface("Horn", "keratin", (0.022, 0.017, 0.015), along=True, tip_color=(0.26, 0.2, 0.15), tip_start=0.6,
                   grain="y", scale=0.02, roughness=0.56, variation=0.7, texel=1.4)
spine = lab.surface("Dorsal spines", "keratin", (0.07, 0.008, 0.008), along=True, tip_color=(0.02, 0.012, 0.01),
                    tip_start=0.3, grain="z", scale=0.015, roughness=0.5, texel=0.7)
teeth = lab.surface("Teeth", "keratin", (0.7, 0.6, 0.46), along=True, root_color=(0.3, 0.17, 0.11), root_end=0.3,
                    tip_color=(0.8, 0.74, 0.62), grain="z", roughness=0.32, texel=1.5)
claws = lab.surface("Claws", "keratin", (0.03, 0.022, 0.02), along=True, tip_color=(0.1, 0.085, 0.075), grain="y",
                    roughness=0.42, variation=0.8, texel=1.2)
mouth = lab.surface("Mouth", "skin", (0.2, 0.025, 0.03), scale=0.01, roughness=0.32, texel=0.9)
tongue_mat = lab.surface("Tongue", "skin", (0.32, 0.05, 0.055), scale=0.008, roughness=0.3, texel=1.0)
nostril = lab.surface("Nostrils", "skin", (0.012, 0.005, 0.005), scale=0.006, texel=0.3)
membrane = lab.surface("Wing membrane", "membrane", (0.3, 0.03, 0.02), jitter=0.02)
eye_mat = lab.surface("Dragon eyes", "eye", (0.95, 0.3, 0.02), color2=(0.16, 0.02, 0.004), pupil=0.14, iris_radius=0.45,
                      slit=0.16, glow=0.45, roughness=0.04)


# ---------------------------------------------------------------- skeleton landmarks

SIDES = ((1, "R"), (-1, "L"))
MIRROR = Matrix.Diagonal((-1, 1, 1, 1))
FLIP = MIRROR.to_3x3()

# The main chain from the nape to the tail tip: (position, side radius, up radius).
MAIN = [((0, -2.2, 3.12), 0.24, 0.25), ((0, -2.12, 2.97), 0.27, 0.29), ((0, -1.99, 2.72), 0.31, 0.34),
        ((0, -1.79, 2.42), 0.36, 0.4), ((0, -1.53, 2.12), 0.44, 0.5), ((0, -1.22, 1.87), 0.54, 0.62),
        ((0, -0.86, 1.73), 0.62, 0.7), ((0, -0.42, 1.67), 0.59, 0.65), ((0, 0.03, 1.63), 0.52, 0.56),
        ((0, 0.45, 1.66), 0.5, 0.52), ((0, 0.85, 1.72), 0.53, 0.55), ((0, 1.3, 1.66), 0.44, 0.44),
        ((0, 1.8, 1.48), 0.34, 0.34), ((0, 2.3, 1.24), 0.235, 0.235), ((0, 2.8, 0.98), 0.185, 0.185),
        ((0, 3.3, 0.72), 0.145, 0.145), ((0, 3.8, 0.5), 0.112, 0.112), ((0, 4.3, 0.34), 0.084, 0.084),
        ((0, 4.75, 0.24), 0.06, 0.06), ((0, 5.15, 0.18), 0.04, 0.04), ((0, 5.45, 0.15), 0.022, 0.022)]
NECK_END, CHEST, HIPS, TAIL_ROOT = 0, 6, 10, 11
FRONT = [((0.42, -0.95, 1.45), 0.34, 0.38), ((0.5, -0.86, 1.2), 0.28, 0.29), ((0.55, -0.74, 0.95), 0.215, 0.22),
         ((0.55, -0.78, 0.76), 0.18, 0.185), ((0.54, -0.9, 0.5), 0.15, 0.155), ((0.52, -1.0, 0.3), 0.12, 0.125),
         ((0.52, -1.07, 0.16), 0.13, 0.1), ((0.52, -1.16, 0.09), 0.15, 0.07)]
HIND = [((0.4, 0.95, 1.48), 0.44, 0.47), ((0.5, 0.78, 1.22), 0.39, 0.4), ((0.56, 0.58, 0.98), 0.3, 0.31),
        ((0.58, 0.47, 0.84), 0.23, 0.235), ((0.58, 0.64, 0.64), 0.19, 0.195), ((0.575, 0.85, 0.46), 0.155, 0.16),
        ((0.57, 0.98, 0.36), 0.13, 0.135), ((0.57, 0.92, 0.2), 0.11, 0.11), ((0.57, 0.83, 0.12), 0.14, 0.085),
        ((0.57, 0.72, 0.09), 0.16, 0.07)]

HEAD_POS = Vector((0, -2.3, 3.22))
HEAD_SCALE = 1.25
HEAD_M = Matrix.Translation(HEAD_POS) @ Matrix.Rotation(0.15, 4, "X") @ Matrix.Scale(HEAD_SCALE, 4)   # snout tilted down
WING_ROOT = Vector((0.38, -0.9, 2.12))
RAISE, SWEEP = 0.42, 0.1
WS = Matrix.Translation(WING_ROOT) @ Matrix.Rotation(-RAISE, 4, "Y") @ Matrix.Rotation(SWEEP, 4, "Z")
NORMAL = (WS.to_3x3() @ Vector((0, 0, 1))).normalized()
ELBOW, WRIST = Vector((1.0, 0.3, 0.04)), Vector((2.45, -0.22, 0.12))
# Fingers (digits II-V): angle from the span towards the tail, segment lengths, bend per joint.
FINGERS = {"d2": (9, (1.45, 1.1, 0.84), 4), "d3": (31, (1.5, 1.16, 0.88), 5),
           "d4": (56, (1.34, 1.04, 0.76), 5), "d5": (83, (1.1, 0.85, 0.6), 4)}


def finger_points(name):
    angle, lengths, bend = FINGERS[name]
    points, heading, at = [WRIST.copy()], angle, WRIST.copy()
    for length in lengths:
        at = at + Vector((math.cos(math.radians(heading)), math.sin(math.radians(heading)), -0.01)) * length
        points.append(at.copy())
        heading += bend
    return points


FINGER_POINTS = {name: finger_points(name) for name in FINGERS}

BONES = {}


def bone(name, head, tail, parent=None):
    BONES[name] = (Vector(head), Vector(tail), parent)


bone("root", (0, 0, 0), (0, 0.6, 0))
bone("pelvis", (0, 0.85, 1.72), (0, 0.4, 1.66), "root")
bone("spine1", (0, 0.4, 1.66), (0, -0.1, 1.64), "pelvis")
bone("spine2", (0, -0.1, 1.64), (0, -0.6, 1.68), "spine1")
bone("chest", (0, -0.6, 1.68), (0, -1.22, 1.87), "spine2")
neck_points = [Vector(MAIN[i][0]) for i in (5, 4, 3, 2, 1)]
for i in range(4):
    bone(f"neck{i + 1}", neck_points[i], neck_points[i + 1], f"neck{i}" if i else "chest")
bone("head", neck_points[-1], HEAD_M @ Vector((0, -0.75, 0.0)), "neck4")
bone("jaw", HEAD_M @ Vector((0, 0.08, -0.07)), HEAD_M @ Vector((0, -0.7, -0.12)), "head")
bone("throat", (0, -1.72, 2.2), (0, -1.95, 2.55), "neck2")
tail_points = [Vector(MAIN[i][0]) for i in range(TAIL_ROOT, len(MAIN))]
for i in range(len(tail_points) - 1):
    bone(f"tail{i + 1}", tail_points[i], tail_points[i + 1], f"tail{i}" if i else "pelvis")
TAILS = [f"tail{i + 1}" for i in range(len(tail_points) - 1)]
NECKS = ["neck1", "neck2", "neck3", "neck4"]
EYE_LOCAL = Vector((0.172, -0.192, 0.074))
for side, tag in SIDES:
    m = lambda p: Vector((p[0] * side, p[1], p[2]))
    eye = HEAD_M @ Vector((EYE_LOCAL.x * side, EYE_LOCAL.y, EYE_LOCAL.z))
    bone(f"lid.{tag}", eye, eye + Vector((0, 0, 0.08)), "head")
    bone(f"upperarm.{tag}", m(FRONT[0][0]), m(FRONT[2][0]), "chest")
    bone(f"forearm.{tag}", m(FRONT[2][0]), m(FRONT[5][0]), f"upperarm.{tag}")   # hand from the wrist
    bone(f"hand.{tag}", m(FRONT[5][0]), m((0.52, -1.3, 0.06)), f"forearm.{tag}")
    bone(f"thigh.{tag}", m(HIND[0][0]), m(HIND[3][0]), "pelvis")
    bone(f"shin.{tag}", m(HIND[3][0]), m(HIND[6][0]), f"thigh.{tag}")
    bone(f"foot.{tag}", m(HIND[6][0]), m(HIND[8][0]), f"shin.{tag}")
    bone(f"toes.{tag}", m(HIND[8][0]), m((0.57, 0.45, 0.05)), f"foot.{tag}")


def wing_world(point, side=1):
    world = WS @ Vector(point)
    return world if side > 0 else FLIP @ world


for side, tag in SIDES:
    bone(f"wup.{tag}", wing_world((0, 0, 0), side), wing_world(ELBOW, side), "chest")
    bone(f"wfore.{tag}", wing_world(ELBOW, side), wing_world(WRIST, side), f"wup.{tag}")
    for name, points in FINGER_POINTS.items():
        for k in range(3):
            bone(f"{name}_{k + 1}.{tag}", wing_world(points[k], side), wing_world(points[k + 1], side),
                 f"{name}_{k}.{tag}" if k else f"wfore.{tag}")
    # The membrane between the fifth finger and the flank follows a fitted affine map: the parent
    # turns and scales, the child turns back, so together they can squash the panel as it folds.
    for kind, centre in (("panel", wing_world((1.0, 1.2, 0.0), side)), ("pro", wing_world((1.0, -0.3, 0.0), side))):
        bone(f"{kind}.{tag}", centre, centre + Vector((0, 0.3, 0)), "chest")
        bone(f"{kind}_skin.{tag}", centre, centre + Vector((0, 0.25, 0)), f"{kind}.{tag}")


def weigh(point, names, influences=3, power=4.0):
    return shapes.envelope_weights(point, [(n, BONES[n][0], BONES[n][1]) for n in names], power, influences)


skinned = []


def build(batch):
    obj = batch.build()
    if obj:
        skinned.append(obj)
    return obj


# ---------------------------------------------------------------- trunk: nape to tail tip, four legs

LIMB_CHAINS, chains = [], [MAIN]
for side, _ in SIDES:
    for limb, joint in ((FRONT, CHEST), (HIND, HIPS)):
        mirrored = [((p[0] * side, p[1], p[2]), a, b) for p, a, b in limb]
        root = MAIN[joint]
        chains.append([(root[0], root[1] * 0.75, root[2] * 0.75)] + mirrored)
        LIMB_CHAINS.append([Vector(p) for p, a, b in mirrored])

# Muscle masses and hollows blended into the trunk: (centre, radii, rotation, negative).
masses = [((0, 0.05, 1.02), (0.4, 0.42, 0.16), None, True),            # belly drawn up between ribs and hips
          ((0, -1.05, 1.18), (0.22, 0.32, 0.18), None, False)]          # keel of the breastbone
for side, _ in SIDES:
    x = lambda v: v * side
    tilt = lambda a, b=0.0: Matrix.Rotation(a, 3, "X") @ Matrix.Rotation(b * side, 3, "Z")
    masses += [
        ((x(0.3), -0.92, 2.08), (0.22, 0.4, 0.18), tilt(-0.3, 0.2), False),     # wing muscles over the shoulders
        ((x(0.36), -1.25, 1.42), (0.22, 0.2, 0.3), tilt(0.5), False),           # pectorals
        ((x(0.52), -0.95, 1.36), (0.18, 0.22, 0.24), tilt(0.2), False),         # deltoid
        ((x(0.45), -0.4, 1.62), (0.2, 0.55, 0.42), None, False),                # ribcage
        ((x(0.53), 0.28, 1.4), (0.12, 0.25, 0.22), None, True),                 # flank hollow before the haunch
        ((x(0.3), 0.92, 1.95), (0.24, 0.38, 0.2), tilt(0.15), False),           # croup and glutes
        ((x(0.6), 0.66, 1.15), (0.2, 0.3, 0.38), tilt(0.5), False),             # quadriceps
        ((x(0.48), 1.06, 1.12), (0.2, 0.26, 0.4), tilt(-0.25), False),          # hamstrings
        ((x(0.6), 0.8, 0.6), (0.12, 0.16, 0.2), tilt(-0.6), False),             # calf
        ((x(0.6), -0.82, 1.08), (0.15, 0.2, 0.26), tilt(-0.3), False),          # triceps
        ((x(0.58), -0.88, 0.66), (0.12, 0.14, 0.2), tilt(0.4), False),          # forearm flexors
        ((x(0.22), 1.42, 1.72), (0.2, 0.42, 0.24), tilt(0.25), False),          # tail-base muscles
        ((x(0.17), -1.72, 2.35), (0.17, 0.25, 0.28), tilt(-0.9), False),        # neck muscles
    ]
trunk = shapes.blob_body("Dragon | Trunk", hide, chains, masses, resolution=0.028, decimate=None)
TRI_TARGET = 21000
faces = len(trunk.data.polygons)
shapes.apply_modifier(trunk, "DECIMATE", ratio=min(1.0, TRI_TARGET / max(1, faces * 2)))
TRUNK_BONES = ["pelvis", "spine1", "spine2", "chest", "throat", "head"] + NECKS + TAILS + \
    [f"{b}.{t}" for t in "RL" for b in ("upperarm", "forearm", "hand", "thigh", "shin", "foot")]
shapes.assign_weights(trunk, [weigh(v.co, TRUNK_BONES) for v in trunk.data.vertices])
skinned.append(trunk)

MAIN_POINTS = [Vector(p[0]) for p in MAIN]
MAIN_RADII = [p[2] for p in MAIN]
MAIN_ARC = [0.0]
for a, b in zip(MAIN_POINTS, MAIN_POINTS[1:]):
    MAIN_ARC.append(MAIN_ARC[-1] + (b - a).length)


def nearest_on(points, p):
    best = (1e9, 0, 0.0)
    for i, (a, b) in enumerate(zip(points, points[1:])):
        axis = b - a
        t = max(0.0, min(1.0, (p - a).dot(axis) / max(axis.length_squared, 1e-9)))
        d = (p - (a + axis * t)).length
        if d < best[0]:
            best = (d, i, t)
    return best


def trunk_body(p):
    """Body attribute for the trunk: arc length along the spine, angle around it, scale size."""
    d, i, t = nearest_on(MAIN_POINTS, p)
    for chain in LIMB_CHAINS:
        dl, il, tl = nearest_on(chain, p)
        if dl < d * 0.85 and p.z < 1.55:
            depth = (il + tl) / (len(chain) - 1)
            return (0.0, 0.42, 0.62 - 0.32 * depth)
    a, b = MAIN_POINTS[i], MAIN_POINTS[i + 1]
    tangent = (b - a).normalized()
    up = Vector((0, 0, 1)) - tangent * tangent.z
    up = up.normalized() if up.length > 1e-4 else Vector((0, 1, 0))
    side = tangent.cross(up)
    offset = p - (a + (b - a) * t)
    around = math.atan2(offset.dot(side), offset.dot(up)) / math.pi
    radius = MAIN_RADII[i] + (MAIN_RADII[i + 1] - MAIN_RADII[i]) * t
    size = max(0.4, min(1.0, radius / 0.55))
    return (MAIN_ARC[i] + (MAIN_ARC[i + 1] - MAIN_ARC[i]) * t, abs(around), size)


shapes.set_attribute(trunk, "Body", trunk_body)
trunk_tree = BVHTree.FromObject(trunk, bpy.context.evaluated_depsgraph_get())


# ---------------------------------------------------------------- feet: pads, knuckled toes, talons

def talon_profile(angle):
    return 0.58 * math.cos(angle), math.sin(angle) * (1.0 if math.sin(angle) > 0 else 0.75)


def claw(base, direction, size, drop=None):
    """A curved, keeled talon from `base` along `direction`, hooking down to the ground (or by
    `drop` metres)."""
    direction = Vector(direction).normalized()
    drop = max(base.z - 0.004, 0.02) if drop is None else drop
    pts = [(base + direction * -0.02 * size + Vector((0, 0, 0.02 * size)), 0.034 * size, 0.04 * size),
           (base + direction * 0.05 * size + Vector((0, 0, 0.022 * size)), 0.025 * size, 0.032 * size),
           (base + direction * 0.11 * size + Vector((0, 0, 0.0)), 0.016 * size, 0.02 * size),
           (base + direction * 0.145 * size + Vector((0, 0, -drop * 0.55)), 0.009 * size, 0.011 * size),
           (base + direction * 0.15 * size + Vector((0, 0, -drop)), 0, 0)]
    piece = loft(pts, ring=10, profile=talon_profile)
    return piece, shapes.along(piece, pts[0][0], pts[-1][0])


FOOT_BODY = (0.0, 0.4, 0.3)
for side, tag in SIDES:
    for kind, centre, toes_spec, foot_bone in (
            ("front", Vector((0.52 * side, -1.2, 0.08)), ((-0.5, 0.24), (-0.16, 0.29), (0.18, 0.29), (0.52, 0.25), (2.5, 0.14)), f"hand.{tag}"),
            ("hind", Vector((0.57 * side, 0.68, 0.08)), ((-0.4, 0.3), (-0.12, 0.36), (0.18, 0.35), (0.52, 0.28), (2.9, 0.18)), f"toes.{tag}")):
        foot = shapes.Batch(f"Dragon | {kind} foot {tag}", hide)
        nails = shapes.Batch(f"Dragon | {kind} claws {tag}", claws)
        pad_radii = (0.13, 0.12, 0.06) if kind == "front" else (0.14, 0.13, 0.065)
        foot.add(ellipsoid(centre + Vector((0, 0, -0.01)), pad_radii, segments=16, rings=10), weights={foot_bone: 1.0}, body=FOOT_BODY)
        for yaw, length in toes_spec:
            direction = Vector((math.sin(yaw) * side, -math.cos(yaw), 0))
            base = centre + direction * 0.06 + Vector((0, 0, 0.01))
            scale = 1.3 if kind == "hind" else 1.15
            if yaw > 2:   # the dewclaw or hind spur, set higher up the foot
                base = centre + direction * 0.1 + Vector((0, 0, 0.12))
            ring = []
            for t, r, lift in ((0.0, 0.07, 0.0), (0.3, 0.058, 0.012), (0.42, 0.065, 0.012), (0.68, 0.05, 0.0),
                               (0.78, 0.054, -0.004), (1.0, 0.042, -0.025)):
                drop = 0.0 if yaw > 2 else -0.035 * t * t
                ring.append((base + direction * length * t + Vector((0, 0, lift + drop)), r * scale * 0.85, r * scale * 0.8))
            foot.add(loft(ring, ring=12), weights={foot_bone: 1.0}, body=FOOT_BODY)
            piece, values = claw(ring[-1][0], direction + Vector((0, 0, -0.1)), 1.15 * scale if yaw < 2 else 0.8 * scale)
            nails.add(piece, weights={foot_bone: 1.0}, body=values)
        build(foot)
        build(nails)


# ---------------------------------------------------------------- tail spines and dorsal crest

spikes = shapes.Batch("Dragon | Dorsal spines", spine)
SPINE_BONES = ["pelvis", "spine1", "spine2", "chest"] + NECKS + TAILS


def spine_size(arc):
    """Spine height along the body: small on the neck, tallest over the shoulders, dwindling down the tail."""
    shoulder = MAIN_ARC[CHEST]
    if arc < shoulder:
        return 0.07 + 0.11 * smooth(0.0, shoulder, arc)
    return 0.18 * (1 - smooth(shoulder, MAIN_ARC[-1] - 0.2, arc)) ** 1.2 + 0.02


arc = 0.25
while arc < MAIN_ARC[-1] - 0.25:
    i = max(k for k in range(len(MAIN_ARC) - 1) if MAIN_ARC[k] <= arc)
    t = (arc - MAIN_ARC[i]) / (MAIN_ARC[i + 1] - MAIN_ARC[i])
    centre = MAIN_POINTS[i].lerp(MAIN_POINTS[i + 1], t)
    tangent = (MAIN_POINTS[i + 1] - MAIN_POINTS[i]).normalized()
    up = (Vector((0, 0, 1)) - tangent * tangent.z).normalized()
    hit = trunk_tree.ray_cast(centre + up * 1.5, -up)[0]
    size = spine_size(arc) * rng.uniform(0.9, 1.08)
    if hit is not None:
        base = hit - up * size * 0.25
        lean = (up + tangent * 0.9).normalized()
        pts = [(base - tangent * size * 0.18, size * 0.13, size * 0.4), (base + lean * size * 0.45, size * 0.09, size * 0.22),
               (base + lean * size * 0.85 + tangent * size * 0.1, size * 0.04, size * 0.08), (base + lean * size * 1.08 + tangent * size * 0.2, 0, 0)]
        piece = loft(pts, ring=8, profile=lambda a: (0.5 * math.cos(a), math.sin(a)))
        spikes.add(piece, weights=weigh(base, SPINE_BONES, 1), body=shapes.along(piece, base, pts[-1][0]))
    arc += max(0.12, size * 1.25)
build(spikes)


# ---------------------------------------------------------------- head: skull, jaw, mouth, eyes, horns

head_objects = []


def local_obj(name, mat, piece):
    obj = shapes.make_object(name, mat, piece)
    head_objects.append(obj)
    return obj


def lip(y):
    """The mouth line: level along the snout, rising behind the last teeth towards the jaw hinge."""
    return -0.07 + 0.035 * smooth(-0.2, 0.08, y)


def shut(obj, upper):
    """Flatten a jaw against the lip line so the mouth closes cleanly."""
    def press(co):
        limit = lip(co.y) - (0.0 if upper else 0.004)
        if co.y < 0.1 and ((upper and co.z < limit) or (not upper and co.z > limit)):
            co.z = limit + (co.z - limit) * 0.1
        return co
    shapes.reshape(obj, press)


# The skull, sculpted from blended masses: cranium, a tapering muzzle, brow ridges that run back
# into the horn bosses, cheekbones, jaw muscles and nostril mounds, with the eye sockets carved out.
skull_chains = [[((0, -0.12, 0.02), 0.2, 0.15), ((0, -0.45, 0.0), 0.165, 0.12), ((0, -0.72, -0.01), 0.125, 0.1),
                 ((0, -0.84, -0.02), 0.1, 0.085)],
                [((0, -0.6, 0.085), 0.03, 0.025), ((0, -0.25, 0.15), 0.035, 0.03)]]
skull_masses = [((0, 0.03, 0.04), (0.24, 0.25, 0.165), None, False), ((0, 0.16, 0.0), (0.19, 0.14, 0.15), None, False)]
for side, _ in SIDES:
    x = lambda v: v * side
    skull_chains += [[((x(0.09), -0.44, 0.1), 0.028, 0.026), ((x(0.19), -0.15, 0.15), 0.045, 0.04),
                      ((x(0.17), 0.07, 0.18), 0.05, 0.045)],                        # brow ridge into the horn boss
                     [((x(0.19), -0.36, -0.025), 0.035, 0.035), ((x(0.255), -0.02, -0.01), 0.055, 0.05),
                      ((x(0.25), 0.1, -0.02), 0.05, 0.05)]]                        # cheekbone
    skull_masses += [((x(0.235), 0.06, -0.05), (0.08, 0.12, 0.1), None, False),       # jaw muscle
                     ((x(0.085), -0.76, 0.045), (0.042, 0.065, 0.035), None, False),  # nostril mound
                     ((x(0.205), -0.2, 0.075), (0.045, 0.055, 0.04), None, True)]     # eye socket
skull = shapes.blob_body("Dragon | Skull", face, skull_chains, skull_masses, resolution=0.011)
head_objects.append(skull)
shut(skull, True)
face_stamps = []
for side, _ in SIDES:
    face_stamps += [((0.093 * side, -0.79, 0.06), 0.016, -0.022),                      # nostril
                    ((0.13 * side, -0.6, -0.055), 0.04, 0.012)]                         # lip over the fang
shapes.displace(skull, face_stamps, snap=True)

jaw_chains = [[((0, -0.3, -0.13), 0.13, 0.04), ((0, -0.62, -0.115), 0.08, 0.035)]]
for side, _ in SIDES:
    x = lambda v: v * side
    jaw_chains.append([((x(0.2), 0.1, -0.055), 0.055, 0.07), ((x(0.19), -0.15, -0.115), 0.06, 0.06),
                       ((x(0.13), -0.5, -0.11), 0.05, 0.045), ((x(0.05), -0.78, -0.105), 0.045, 0.04)])
jaw = shapes.blob_body("Dragon | Jaw", face, jaw_chains, [((0, -0.8, -0.105), (0.06, 0.05, 0.045), None, False)],
                       resolution=0.011)
head_objects.append(jaw)
shut(jaw, False)
for obj in (skull, jaw):
    shapes.apply_modifier(obj, "DECIMATE", ratio=min(1.0, 2600 / max(1, len(obj.data.polygons))))


def lip_edge(obj, y, top):
    """Half-width of a jaw's lip line at local y (top=True for the skull's lower edge)."""
    best = 0.0
    for v in obj.data.vertices:
        if abs(v.co.y - y) < 0.025 and (v.co.z < lip(y) + 0.015 if top else v.co.z > lip(y) - 0.02):
            best = max(best, abs(v.co.x))
    return best


inner = shapes.Batch("Dragon | Mouth", mouth)
inner.add(ellipsoid((0, -0.34, -0.068), (0.17, 0.44, 0.012), segments=24, rings=10), weights={"head": 1.0})
inner.add(ellipsoid((0, -0.32, -0.07), (0.15, 0.4, 0.01), segments=24, rings=10), weights={"jaw": 1.0})
inner.add(ellipsoid((0, 0.04, -0.1), (0.16, 0.12, 0.09), segments=16, rings=10), weights={"head": 0.5, "jaw": 0.5})
head_objects.append(build(inner))
tongue = shapes.Batch("Dragon | Tongue", tongue_mat)
tongue.add(loft([((0, 0.02, -0.08), 0.065, 0.02), ((0, -0.22, -0.075), 0.062, 0.02), ((0, -0.42, -0.076), 0.045, 0.015),
                 ((0, -0.53, -0.078), 0.022, 0.009), ((0, -0.56, -0.079), 0, 0)], ring=12), weights={"jaw": 1.0})
head_objects.append(build(tongue))

fangs = shapes.Batch("Dragon | Teeth", teeth)
for upper_row in (True, False):
    count = 12 if upper_row else 10
    for side, _ in SIDES:
        for k in range(count):
            t = (k + jitter(0.2)) / (count - 1)
            y = -0.8 + 0.74 * t if upper_row else -0.77 + 0.64 * t
            width = lip_edge(skull if upper_row else jaw, y, upper_row)
            canine = (k == 2) if upper_row else (k == 1)
            length = (0.085 if canine else (0.045 - 0.018 * t) * rng.uniform(0.75, 1.2)) * (1 if upper_row else 0.85)
            radius = 0.022 if canine else 0.012 + 0.006 * (1 - t)
            if upper_row:
                root = Vector((side * width * 0.94, y, lip(y) + 0.004))
                down = Vector((side * 0.12, 0.08, -1)).normalized()
            else:
                root = Vector((side * width * 0.9, y, lip(y) - 0.008))
                down = Vector((side * 0.06, 0.1, 1)).normalized()
            tip = root + down * length + Vector((0, 0.012, 0))
            pts = [(root - down * 0.02, radius, radius * 1.1), (root + down * length * 0.35, radius * 0.85, radius),
                   (root + down * length * 0.75 + Vector((0, 0.006, 0)), radius * 0.45, radius * 0.5), (tip, 0, 0)]
            piece = loft(pts, ring=7, profile=lambda a: (0.75 * math.cos(a), math.sin(a)))
            fangs.add(piece, weights={("head" if upper_row else "jaw"): 1.0}, body=shapes.along(piece, root, tip))
head_objects.append(build(fangs))

horns = shapes.Batch("Dragon | Horns", horn)


def horn_piece(path, radius, owner="head", ring=12):
    points = shapes.polyline(path)
    count = max(6, int(sum((Vector(b) - Vector(a)).length for a, b in zip(path, path[1:])) / 0.06))
    pts = []
    for k in range(count + 1):
        t = k / count
        r = radius * (1 - t) ** 0.85 * (1.0 if k % 2 else 1.035)
        pts.append((points(t), r, r * 1.06))
    pts[-1] = (pts[-1][0], 0, 0)
    piece = loft(pts, ring=ring)
    horns.add(piece, weights={owner: 1.0}, body=[(max(0.0, min(1.0, ((Vector(v) - Vector(path[0])).length) /
                                                              max((Vector(path[-1]) - Vector(path[0])).length, 1e-6))), 0, 0)
                                                 for v in piece.verts])


for side, _ in SIDES:
    s = side
    # The great horns sweep back from the brow bosses in one long, slightly outward curve.
    horn_piece([(0.14 * s, 0.04, 0.15), (0.19 * s, 0.28, 0.25), (0.25 * s, 0.54, 0.29), (0.3 * s, 0.8, 0.26),
                (0.34 * s, 1.02, 0.17), (0.36 * s, 1.2, 0.04)], 0.09, ring=14)
    horn_piece([(0.18 * s, -0.14, 0.17), (0.2 * s, -0.05, 0.23), (0.21 * s, 0.02, 0.26)], 0.022, ring=8)
    for k, (y, length) in enumerate(((0.0, 0.2), (0.12, 0.16))):
        base = Vector((0.25 * s, y, -0.035 - 0.015 * k))
        direction = Vector((0.45 * s, 1.0, -0.25)).normalized()
        horn_piece([base, base + direction * length * 0.5 + Vector((0, 0, 0.01)), base + direction * length], 0.03, ring=8)
    base = Vector((0.18 * s, -0.08, -0.17))
    horn_piece([base, base + Vector((0.05 * s, 0.07, -0.05)), base + Vector((0.07 * s, 0.14, -0.08))], 0.026, owner="jaw", ring=8)
for k in range(4):
    y = -0.06 + 0.09 * k
    base = Vector((0, y, 0.17 + 0.02 * smooth(-0.16, 0.2, y)))
    h = 0.03 + 0.01 * k
    horn_piece([base, base + Vector((0, 0.03, h * 0.6)), base + Vector((0, 0.06, h))], 0.022, ring=8)
head_objects.append(build(horns))

nostrils = shapes.Batch("Dragon | Nostrils", nostril)
eyes = shapes.Batch("Dragon | Eyes", eye_mat)
lids = shapes.Batch("Dragon | Eyelids", face)
skull_tree = BVHTree.FromPolygons([v.co for v in skull.data.vertices], [p.vertices for p in skull.data.polygons])
for side, tag in SIDES:
    spot, normal = skull_tree.find_nearest(Vector((0.093 * side, -0.79, 0.06)))[:2]
    nostrils.add(ellipsoid(spot - normal * 0.006, (0.013, 0.024, 0.009), Vector((0, 0, 1)).rotation_difference(normal).to_matrix()
                           @ Matrix.Rotation(0.5 * side, 3, "Z"), 10, 6), weights={"head": 1.0})
    centre = Vector((EYE_LOCAL.x * side, EYE_LOCAL.y, EYE_LOCAL.z))
    gaze = Vector((0.72 * side, -0.68, 0.06)).normalized()
    up = (Vector((0, 0, 1)) - gaze * gaze.z).normalized()
    axes = Matrix((up, gaze.cross(up), gaze)).transposed()   # local X = up, so the slit pupil stands upright
    eyes.add(ellipsoid(centre, (0.054, 0.054, 0.05), axes, segments=24, rings=16), weights={"head": 1.0})
    brow = up.copy()
    brow.rotate(Matrix.Rotation(0.25 * side, 3, gaze))   # the lid drops towards the snout: a hard, level glare
    lids.add(eyelid(centre, 0.054, brow, math.radians(70), 0.004), weights={f"lid.{tag}": 1.0})
    lids.add(eyelid(centre, 0.054, -up, math.radians(66), 0.0035), weights={"head": 1.0})
head_objects += [build(nostrils), build(eyes), build(lids)]
for obj in (skull, jaw):
    shapes.assign_weights(obj, [{"head" if obj is skull else "jaw": 1.0}] * len(obj.data.vertices))
    skinned.append(obj)
for obj in head_objects:
    if obj:
        obj.data.transform(HEAD_M)

HEAD_AXIS = (HEAD_M @ Vector((0, 0.25, 0)), HEAD_M @ Vector((0, -0.95, 0)))


def head_body(p):
    a, b = HEAD_AXIS
    tangent = (b - a).normalized()
    up = (Vector((0, 0, 1)) - tangent * tangent.z).normalized()
    offset = p - a
    offset -= tangent * offset.dot(tangent)
    around = math.atan2(offset.dot(tangent.cross(up)), offset.dot(up)) / math.pi
    return ((p - a).dot(tangent), abs(around), 0.55)


for obj in head_objects:
    if obj and obj.data.materials[0] is face:
        shapes.set_attribute(obj, "Body", head_body)


# ---------------------------------------------------------------- wings: arm, thumb, fingers, membrane

def body_edge_world():
    return [Vector(p) for p in ((0.42, -0.72, 2.12), (0.56, -0.28, 2.02), (0.6, 0.25, 1.92), (0.62, 0.62, 1.74))]


WS_INV = WS.inverted()


def on_flank(point):
    spot, normal = trunk_tree.find_nearest(point)[:2]
    return spot + normal * 0.02


BODY_EDGE = [WS_INV @ on_flank(p) for p in body_edge_world()]   # in wing space, just outside the flank
ARM_PATH = [Vector((0, 0, 0)), ELBOW, WRIST]
FINGER_ORDER = ["d2", "d3", "d4", "d5"]


def segment_weights(name, u, tag):
    """Weights along a finger at fraction u of its length, blending across the knuckles."""
    lengths = FINGERS[name][1]
    total = sum(lengths)
    marks = [0.0, lengths[0] / total, (lengths[0] + lengths[1]) / total, 1.0]
    weights = {}
    for k in range(3):
        centre = (marks[k] + marks[k + 1]) / 2
        half = (marks[k + 1] - marks[k]) / 2 + 0.05
        w = max(0.0, 1 - abs(u - centre) / half)
        if w > 0:
            weights[f"{name}_{k + 1}.{tag}"] = w
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def arm_weights(v_along, tag):
    """Weights at fraction v_along of the arm path from the wrist (0) back to the shoulder (1)."""
    split = (WRIST - ELBOW).length / ((WRIST - ELBOW).length + ELBOW.length)
    if v_along < split - 0.06:
        return {f"wfore.{tag}": 1.0}
    if v_along > split + 0.06:
        return {f"wup.{tag}": 0.7, "chest": 0.3} if v_along > 0.9 else {f"wup.{tag}": 1.0}
    w = (v_along - (split - 0.06)) / 0.12
    return {f"wfore.{tag}": 1 - w, f"wup.{tag}": w}


def combine(parts, limit=4):
    total = {}
    for weight, weights in parts:
        for k, v in weights.items():
            total[k] = total.get(k, 0.0) + weight * v
    best = sorted(total.items(), key=lambda kv: -kv[1])[:limit]
    norm = sum(v for k, v in best) or 1.0
    return {k: v / norm for k, v in best if v / norm > 0.01}


def catenary(p, q, sag, toward):
    """A trailing edge scalloped between two attachment points, drawn in towards `toward`."""
    def at(t):
        base = p.lerp(q, t)
        pull = (toward - base)
        pull.z = 0
        return base + pull.normalized() * sag * math.sin(math.pi * t) * (q - p).length
    return at


def billow(depth):
    return lambda u, v: Vector((0, 0, -depth * math.sin(math.pi * min(u * 1.1, 1.0)) * math.sin(math.pi * v)))


panels = []   # (piece in wing space, weights per vertex as function(tag) -> list, tints)
tips = {name: FINGER_POINTS[name][-1] for name in FINGERS}
for a, b in zip(FINGER_ORDER, FINGER_ORDER[1:]):
    fa, fb = shapes.polyline(FINGER_POINTS[a]), shapes.polyline(FINGER_POINTS[b])
    edge = catenary(tips[a], tips[b], 0.2, WRIST)
    piece = shapes.coons_patch(fa, fb, lambda v: WRIST.copy(), edge, 22, 12, billow(0.07 * (tips[a] - tips[b]).length))
    panels.append((piece, lambda tag, a=a, b=b, piece=piece: [
        combine([(1 - uv[1], segment_weights(a, uv[0], tag)), (uv[1], segment_weights(b, uv[0], tag))])
        for uv in [(i / 22, j / 12) for j in range(13) for i in range(23)]]))

d5, edge_body = shapes.polyline(FINGER_POINTS["d5"]), shapes.polyline(BODY_EDGE)
arm_back = shapes.polyline([WRIST, ELBOW, Vector((0, 0, 0))])
trailing = catenary(tips["d5"], BODY_EDGE[-1], 0.16, (ELBOW + BODY_EDGE[1]) / 2)
body_patch = shapes.coons_patch(d5, edge_body, arm_back, trailing, 22, 16, billow(0.12))
BODY_EDGE_BONES = ["chest", "spine2", "spine1", "pelvis", "thigh.{tag}"]
panels.append((body_patch, lambda tag: [
    combine([((1 - v) ** 3, segment_weights("d5", u, tag)),
             (v ** 3, weigh(wing_world(edge_body(u), 1 if tag == "R" else -1),
                            [n.format(tag=tag) for n in BODY_EDGE_BONES], 2)),
             ((1 - u) ** 3, arm_weights(v, tag)),
             (max(0.0, 1 - (1 - v) ** 3 - v ** 3 - (1 - u) ** 3), {f"panel_skin.{tag}": 1.0})])
    for v, u in [(j / 16, i / 22) for j in range(17) for i in range(23)]]))

front_edge = shapes.polyline([Vector((0.05, -0.32, 0.04)), WRIST * 0.55 + Vector((0, -0.28, 0.03)), WRIST])
arm_front = shapes.polyline([Vector((0, 0, 0)), ELBOW, WRIST])
pro_patch = shapes.coons_patch(arm_front, front_edge, shapes.polyline([Vector((0, 0, 0)), Vector((0.05, -0.32, 0.04))]),
                               lambda v: WRIST.copy(), 16, 3)
panels.append((pro_patch, lambda tag: [combine([((1 - j / 3) ** 2, arm_weights(1 - i / 16, tag)),
                                                  (1 - (1 - j / 3) ** 2, {f"pro_skin.{tag}": 1.0})])
                                        for j in range(4) for i in range(17)]))


def membrane_tint(point):
    """Darker by the bones and body, brighter and warmer where the membrane is thinnest."""
    nearest = min((point - p).length for name in FINGERS for p in FINGER_POINTS[name])
    root = smooth(0.0, 3.0, (point - WRIST).length)
    thin = smooth(0.05, 0.6, nearest)
    colour = lerp((0.08, 0.005, 0.007), (0.28, 0.026, 0.015), thin)
    return lerp(colour, (0.5, 0.09, 0.018), 0.32 * thin * root)


wing_batches = {tag: shapes.Batch(f"Dragon | Membrane {tag}", membrane) for _, tag in SIDES}
for piece, weights_for in panels:
    world = piece.transformed(WS)
    tints = [membrane_tint(Vector(v)) for v in piece.verts]
    for side, tag in SIDES:
        wing_batches[tag].add(world if side > 0 else world.mirrored(), tint=None, weights=weights_for(tag))
        start = len(wing_batches[tag].tints) - len(piece.verts)
        wing_batches[tag].tints[start:] = tints
for batch in wing_batches.values():
    build(batch)

bones_batch = {tag: shapes.Batch(f"Dragon | Wing bones {tag}", hide) for _, tag in SIDES}
claw_batch = {tag: shapes.Batch(f"Dragon | Wing claws {tag}", claws) for _, tag in SIDES}
WING_BODY = (0.0, 0.45, 0.42)


def add_wing_piece(batches, piece, names, body=None, influences=2, power=8.0):
    world = piece.transformed(WS)
    for side, tag in SIDES:
        oriented = world if side > 0 else world.mirrored()
        batches[tag].add(oriented, weights=[weigh(v, [n.format(tag=tag) for n in names], influences, power)
                                            for v in oriented.verts], body=body)


arm = loft([((-0.18, 0.02, -0.02), 0, 0), ((-0.1, 0.02, -0.02), 0.16, 0.15), ((0, 0, 0), 0.19, 0.17),
            (ELBOW * 0.5, 0.15, 0.13), (ELBOW, 0.115, 0.1), (ELBOW.lerp(WRIST, 0.35), 0.1, 0.085),
            (ELBOW.lerp(WRIST, 0.8), 0.08, 0.07), (WRIST, 0.095, 0.085), (WRIST + Vector((0.08, 0.0, 0.0)), 0, 0)], ring=14)
add_wing_piece(bones_batch, arm, ["wup.{tag}", "wfore.{tag}", "chest"], WING_BODY)
for name, points in FINGER_POINTS.items():
    pts = []
    for k, p in enumerate(points):
        r = 0.07 - 0.016 * k
        pts.append((p, r * 1.15, r))
        if k < 3:
            pts.append((p.lerp(points[k + 1], 0.5), r * 0.75, r * 0.65))
    pts[-1] = (pts[-1][0], 0.016, 0.014)
    pts.append((points[-1] + (points[-1] - points[-2]).normalized() * 0.08, 0, 0))
    add_wing_piece(bones_batch, loft(pts, ring=10), [f"{name}_{k}.{{tag}}" for k in (1, 2, 3)] + ["wfore.{tag}"], WING_BODY)
thumb_dir = Vector((0.3, -1.0, 0.25)).normalized()
thumb_base = WRIST + Vector((0.0, -0.06, 0.04))
thumb = loft([(thumb_base, 0.06, 0.055), (thumb_base + thumb_dir * 0.12, 0.05, 0.045), (thumb_base + thumb_dir * 0.2, 0.045, 0.04)], ring=10)
add_wing_piece(bones_batch, thumb, ["wfore.{tag}"], WING_BODY, 1)
thumb_claw, thumb_values = claw(thumb_base + thumb_dir * 0.2, thumb_dir, 1.4, drop=0.12)
add_wing_piece(claw_batch, thumb_claw, ["wfore.{tag}"], thumb_values, 1)
for batch in list(bones_batch.values()) + list(claw_batch.values()):
    build(batch)


# ---------------------------------------------------------------- rig

bpy.ops.object.armature_add(location=(0, 0, 0))
rig = bpy.context.object
rig.name = "Dragon | Rig"
rig.data.name = "Dragon rig"
bpy.ops.object.mode_set(mode="EDIT")
edit = rig.data.edit_bones
edit.remove(edit[0])
for name, (head, tail, parent) in BONES.items():
    b = edit.new(name)
    b.head, b.tail, b.roll = head, tail, 0
    if parent:
        b.parent = edit[parent]
bpy.ops.object.mode_set(mode="OBJECT")
for obj in skinned:
    shapes.skin_to(obj, rig)
REST = {name: rig.data.bones[name].matrix_local.copy() for name in BONES}


# ---------------------------------------------------------------- animation: FK deltas, two-bone IK, keys

AXES = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}


def about(pivot, axis, angle):
    pivot = Vector(pivot)
    axis = AXES[axis] if isinstance(axis, str) else axis
    return Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-pivot)


def head_of(name):
    return BONES[name][0]


def chain(names, axis, angles):
    return {n: about(head_of(n), axis, a) for n, a in zip(names, angles)}


def frame(direction, normal):
    d = direction.normalized()
    n = (normal - d * normal.dot(d)).normalized()
    return Matrix((d, n.cross(d), n)).transposed()


def turn_onto(rest_dir, target_dir, target_normal):
    """The rotation carrying a rest wing bone (lying in the wing plane) onto a folded direction,
    with the wing's upper surface turned towards target_normal."""
    return (frame(target_dir, target_normal) @ frame(rest_dir, NORMAL).transposed()).to_quaternion()


# The folded right wing, in body space: the elbow tucked back and high, the wrist forward at the
# base of the neck, the fingers lying back and down along the flank with the membrane between them.
W_SHOULDER, W_ELBOW, W_WRIST = WS @ Vector((0, 0, 0)), WS @ ELBOW, WS @ WRIST
FOLD_ELBOW = Vector((0.64, 0.06, 2.42))
FOLD_WRIST = Vector((0.74, -1.46, 2.28))
FOLD_TIPS = {"d2": Vector((1.0, 1.85, 1.62)), "d3": Vector((0.97, 1.95, 1.4)),
             "d4": Vector((1.0, 1.5, 1.2)), "d5": Vector((1.0, 0.8, 1.12))}
FOLD_IN = Vector((-1, 0, -0.3))   # the folded membrane's upper surface faces the flank, so it hangs below the arm
FOLD_TURN = {"wup": turn_onto(W_ELBOW - W_SHOULDER, FOLD_ELBOW - W_SHOULDER, FOLD_IN),
             "wfore": turn_onto(W_WRIST - W_ELBOW, FOLD_WRIST - FOLD_ELBOW, FOLD_IN)}
for _name in FINGERS:
    FOLD_TURN[_name] = turn_onto(WS @ FINGER_POINTS[_name][-1] - W_WRIST, FOLD_TIPS[_name] - FOLD_WRIST, FOLD_IN)


def right_wing(fold=0.0, lower=0.0, flap=0.0, tip_flap=0.0, spread=0.0, curl=0.0):
    """Wing deltas: fold (0-1) turns each wing bone from its spread rest towards the folded pose,
    lower swings the whole wing down about the body's long axis, flap raises it, tip_flap lags the
    hand behind, spread fans the fingers, curl flexes their joints."""
    s, e, w = W_SHOULDER, W_ELBOW, W_WRIST
    turn = lambda name, pivot, at: Matrix.Translation(at) @ Quaternion().slerp(FOLD_TURN[name], fold).to_matrix().to_4x4() @ Matrix.Translation(-pivot)
    swing = about(s, "Y", lower - flap)
    upper = turn("wup", s, s)
    fore = turn("wfore", e, upper @ e)
    absolute = {"wup": swing @ upper, "wfore": swing @ fore}
    deltas = {"wup": absolute["wup"], "wfore": absolute["wup"].inverted() @ absolute["wfore"]}
    chord = (WS.to_3x3() @ Vector((0, 1, 0))).normalized()
    for k, name in enumerate(FINGER_ORDER):
        fan = spread * (k - 1.5) * 0.08
        finger = swing @ turn(name, w, fore @ w)
        deltas[f"{name}_1"] = absolute["wfore"].inverted() @ finger @ about(w, chord, -tip_flap) @ about(w, NORMAL, fan)
        for j in (2, 3):
            joint = WS @ FINGER_POINTS[name][j - 1]
            deltas[f"{name}_{j}"] = about(joint, NORMAL, curl * 0.12) @ about(joint, chord, -tip_flap * 0.35)
    return deltas


def wings(**kwargs):
    deltas = {}
    for name, delta in right_wing(**kwargs).items():
        deltas[f"{name}.R"] = delta
        deltas[f"{name}.L"] = MIRROR @ delta @ MIRROR
    return deltas


ORDER = list(BONES)
LEGS = []   # (upper, lower, end, extra child or None)
for _, tag in SIDES:
    LEGS += [(f"upperarm.{tag}", f"forearm.{tag}", f"hand.{tag}", None), (f"thigh.{tag}", f"shin.{tag}", f"foot.{tag}", f"toes.{tag}")]


def solve(deltas, ik=True, plant=None):
    """Armature-space pose matrices from FK deltas, then two-bone IK keeping each foot planted."""
    poses = {}
    for name in ORDER:
        parent = BONES[name][2]
        delta = deltas.get(name, Matrix.Identity(4))
        poses[name] = (poses[parent] @ REST[parent].inverted() @ delta @ REST[name]) if parent else delta @ REST[name]
    if not ik:
        return poses
    for upper, lower, end, child in LEGS:
        hip = poses[upper].translation
        target = (plant or {}).get(end, REST[end].translation)
        l1 = (REST[lower].translation - REST[upper].translation).length
        l2 = (REST[end].translation - REST[lower].translation).length
        reach = target - hip
        d = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, reach.length))
        n = reach.normalized()
        rest_hip, rest_knee, rest_end = REST[upper].translation, REST[lower].translation, REST[end].translation
        pole = rest_knee - (rest_hip + (rest_end - rest_hip).normalized() * (rest_knee - rest_hip).dot((rest_end - rest_hip).normalized()))
        parent_rot = (poses[BONES[upper][2]] @ REST[BONES[upper][2]].inverted()).to_3x3()
        pole = parent_rot @ pole
        pole = (pole - n * pole.dot(n)).normalized()
        a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
        knee = hip + n * a + pole * math.sqrt(max(l1 * l1 - a * a, 0.0))
        target = hip + n * d
        for name, start, finish in ((upper, hip, knee), (lower, knee, target)):
            current = poses[name].to_3x3() @ Vector((0, 1, 0))
            if name == lower:
                current = (poses[upper] @ REST[upper].inverted() @ REST[lower]).to_3x3() @ Vector((0, 1, 0))
                base = (poses[upper] @ REST[upper].inverted() @ REST[lower]).to_3x3()
            else:
                base = poses[name].to_3x3()
            turn = current.rotation_difference((finish - start).normalized()).to_matrix()
            poses[name] = Matrix.Translation(start) @ (turn @ base).to_4x4()
        rotation = REST[end].to_3x3().to_4x4()
        poses[end] = Matrix.Translation(target) @ rotation
        if child:
            poses[child] = poses[end] @ REST[end].inverted() @ REST[child]
    return poses


def key(frame, poses):
    for name in ORDER:
        parent = BONES[name][2]
        local = REST[parent].inverted() @ REST[name] if parent else REST[name]
        relative = poses[parent].inverted() @ poses[name] if parent else poses[name]
        basis = local.inverted() @ relative
        location, rotation, scale = basis.decompose()
        pose_bone = rig.pose.bones[name]
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.location, pose_bone.rotation_quaternion, pose_bone.scale = location, rotation, scale
        for path in ("location", "rotation_quaternion", "scale"):
            pose_bone.keyframe_insert(path, frame=frame)


def motion(poses, name):
    return poses[name] @ REST[name].inverted()


def panel_samples(side, tag, kind):
    """Points of a panel's border with the bone each one rides on."""
    w = lambda p: wing_world(p, side)
    if kind == "pro":
        return [(w((0, 0, 0)), f"wup.{tag}"), (w(ELBOW * 0.5), f"wup.{tag}"), (w(ELBOW), f"wup.{tag}"),
                (w(ELBOW.lerp(WRIST, 0.5)), f"wfore.{tag}"), (w(WRIST), f"wfore.{tag}")]
    d5 = FINGER_POINTS["d5"]
    samples = [(w(d5[k]), f"d5_{min(k, 2) + 1}.{tag}") for k in range(4)]
    samples += [(w((0, 0, 0)), f"wup.{tag}"), (w(ELBOW), f"wup.{tag}"), (w(ELBOW.lerp(WRIST, 0.5)), f"wfore.{tag}")]
    for p in BODY_EDGE:
        world = w(p)
        samples.append((world, min(("chest", "spine2", "spine1", "pelvis"), key=lambda n: abs(BONES[n][0].y - world.y))))
    return samples


PANEL_SAMPLES = {(kind, tag): panel_samples(side, tag, kind) for side, tag in SIDES for kind in ("panel", "pro")}


def fit_panels(poses):
    """Pose each panel bone pair so the panel interior follows the best affine fit of its border."""
    for (kind, tag), samples in PANEL_SAMPLES.items():
        normal = FLIP @ NORMAL if tag == "L" else NORMAL
        rest, posed = [], []
        for point, name in samples:
            m = motion(poses, name)
            for offset in (0.0, 0.4, -0.4):
                rest.append(list(point + normal * offset) + [1.0])
                posed.append(list(m @ (point + normal * offset)))
        solution = numpy.linalg.lstsq(numpy.array(rest), numpy.array(posed), rcond=None)[0].T   # 3x4
        linear, shift = solution[:, :3], solution[:, 3]
        u, sigma, vt = numpy.linalg.svd(linear)
        if numpy.linalg.det(u) < 0:
            u[:, 2] *= -1
            sigma[2] *= -1
        if numpy.linalg.det(vt) < 0:
            vt[2] *= -1
            sigma[2] *= -1
        sigma = numpy.maximum(sigma, 0.05)
        head = BONES[f"{kind}.{tag}"][0]
        to = Matrix([list(r) for r in linear]) @ head + Vector(shift)
        scaled = Matrix([list(r) for r in u]) @ Matrix.Diagonal(Vector(sigma))
        poses[f"{kind}.{tag}"] = Matrix.Translation(to) @ scaled.to_4x4()
        poses[f"{kind}_skin.{tag}"] = poses[f"{kind}.{tag}"] @ Matrix([list(r) for r in vt]).to_4x4()
    return poses


def clip(name, frames, pose, ik=True, step=2):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    for f in range(0, frames + 1, step):
        deltas, plant = pose(f / frames)
        key(f, fit_panels(solve(deltas, ik, plant)))
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, 0, action)
    rig.animation_data.action = None


def blink(t, *moments):
    return max([max(0.0, 1 - abs(t - m) / 0.02) for m in moments] + [0.0])


def lids(amount):
    deltas = {}
    for side, tag in SIDES:
        centre = head_of(f"lid.{tag}")
        across = (HEAD_M.to_3x3() @ Vector((1, 0, 0)))
        deltas[f"lid.{tag}"] = about(centre, across, -0.75 * amount)
    return deltas


def look(phase, yaw=0.2, pitch=0.06, raise_neck=0.0):
    weights = (0.15, 0.22, 0.28, 0.35)
    deltas = {}
    for n, w in zip(NECKS, weights):
        deltas[n] = about(head_of(n), "Z", yaw * w * math.sin(phase)) @ about(head_of(n), "X", -raise_neck * w)
    deltas["head"] = about(head_of("head"), "Z", yaw * 0.6 * math.sin(phase - 0.4)) @ \
        about(head_of("head"), "X", pitch * math.sin(phase * 0.5 + 0.7) + raise_neck * 0.9)
    return deltas


def tail(phase, side=0.08, lift=0.03, curl=0.0, raise_tail=0.0):
    deltas = {}
    for i, n in enumerate(TAILS):
        k = (i + 1) / len(TAILS)
        deltas[n] = about(head_of(n), "Z", side * (0.4 + k) * math.sin(phase - 0.75 * i) + curl * (0.3 + k)) @ \
            about(head_of(n), "X", lift * math.sin(2 * phase - 0.5 * i) + raise_tail * (1.2 - k))
    return deltas


def lift_body(dz=0.0, pitch=0.0, front_dz=0.0):
    """Move the hips and chest (the feet stay planted by IK): dz for the pelvis, front_dz extra at
    the chest, pitch rotates the spine about the hips."""
    deltas = {"pelvis": Matrix.Translation((0, 0, dz)) @ about(head_of("pelvis"), "X", pitch)}
    deltas["chest"] = about(head_of("chest"), "X", -math.atan2(front_dz, 0.9))
    return deltas


def merge(*parts):
    out = {}
    for part in parts:
        for name, delta in part.items():
            out[name] = out[name] @ delta if name in out else delta
    return out


def idle(t):
    phase = 2 * math.pi * t
    breath = math.sin(2 * phase)
    deltas = merge(wings(fold=0.96 + 0.02 * math.sin(phase * 2 + 1), flap=0.015 * breath),
                   lift_body(0.01 * breath),
                   chain(["spine1", "spine2"], "X", [0.004 * breath, 0.006 * breath]),
                   {"throat": about(head_of("throat"), "X", 0) @ Matrix.Diagonal((1 + 0.03 * breath, 1, 1 + 0.03 * breath, 1))},
                   look(phase, 0.32, 0.07), lids(blink(t, 0.18, 0.62, 0.66)), tail(phase, 0.09, 0.03))
    return deltas, None


def perched(t):
    phase = 2 * math.pi * t
    breath = math.sin(2 * phase)
    deltas = merge(wings(fold=1.0, flap=0.01 * breath),
                   lift_body(-0.36 + 0.008 * breath, -0.05, 0.18),
                   look(phase, 0.22, 0.05, raise_neck=0.18),
                   lids(blink(t, 0.3, 0.78)), tail(phase, 0.04, 0.02, curl=0.16))
    return deltas, None


def wing_beat(t):
    phase = 2 * math.pi * t
    upstroke = max(0.0, -math.sin(phase))
    deltas = merge(wings(fold=0.42 * upstroke, flap=0.3 + 0.65 * math.cos(phase), tip_flap=0.35 * math.cos(phase - 1.1),
                         curl=upstroke),
                   lift_body(0.05 * math.sin(phase + 0.6), 0.02 * math.cos(phase)),
                   chain(NECKS, "X", [-0.012 * math.cos(phase)] * 4),
                   {"head": about(head_of("head"), "X", 0.04 * math.sin(phase))},
                   tail(phase, 0.04, 0.08))
    return deltas, None


def roar(t):
    gather = smooth(0.0, 0.25, t) * (1 - smooth(0.25, 0.38, t))
    open_ = smooth(0.26, 0.4, t) * (1 - smooth(0.78, 0.95, t))
    shake = math.sin(t * 2 * math.pi * 9) * open_ * 0.015
    spread = smooth(0.18, 0.36, t) * (1 - smooth(0.82, 0.98, t))
    neck = [-0.1 * gather + 0.05 * open_ for _ in NECKS]
    deltas = merge(wings(fold=0.96 * (1 - spread), flap=0.45 * spread, spread=0.6 * spread),
                   lift_body(-0.06 * gather + 0.06 * open_, 0.0, -0.08 * gather + 0.16 * open_),
                   chain(NECKS, "X", neck),
                   {"head": about(head_of("head"), "X", 0.28 * gather - 0.32 * open_ + shake) @ about(head_of("head"), "Z", shake),
                    "jaw": about(head_of("jaw"), HEAD_M.to_3x3() @ Vector((1, 0, 0)), 0.6 * open_),
                    "throat": Matrix.Translation(head_of("throat")) @ Matrix.Diagonal((1 + 0.2 * open_, 1, 1 + 0.25 * open_, 1)) @ Matrix.Translation(-head_of("throat"))},
                   lids(0.25 * open_), tail(t * 2 * math.pi * 1.5, 0.06 + 0.12 * open_, 0.05))
    return deltas, None


def flight(t):
    phase = 2 * math.pi * t
    upstroke = max(0.0, -math.sin(phase))
    deltas = merge({"root": Matrix.Translation((0, 0, 2.3 - 0.12 * math.cos(phase + 0.3)))},
                   wings(fold=0.45 * upstroke, flap=-0.1 + 0.95 * math.cos(phase), tip_flap=0.4 * math.cos(phase - 1.1),
                         curl=upstroke, spread=0.5),
                   {"pelvis": about(head_of("pelvis"), "X", 0.04 * math.cos(phase))},
                   chain(NECKS, "X", [0.14, 0.1, 0.06, 0.03]),
                   {"head": about(head_of("head"), "X", -0.28 + 0.03 * math.sin(phase))},
                   tail(phase, 0.05, 0.06, raise_tail=0.07))
    for side, tag in SIDES:
        deltas[f"thigh.{tag}"] = about(head_of(f"thigh.{tag}"), "X", 0.85)
        deltas[f"shin.{tag}"] = about(head_of(f"shin.{tag}"), "X", -0.5)
        deltas[f"foot.{tag}"] = about(head_of(f"foot.{tag}"), "X", 0.9)
        deltas[f"upperarm.{tag}"] = about(head_of(f"upperarm.{tag}"), "X", 0.55)
        deltas[f"forearm.{tag}"] = about(head_of(f"forearm.{tag}"), "X", -1.1)
        deltas[f"hand.{tag}"] = about(head_of(f"hand.{tag}"), "X", 0.7)
    return deltas, None


bpy.context.scene.render.fps = 24
clip("Idle", 120, idle)
clip("Perched", 120, perched)
clip("Wing beat", 36, wing_beat)
clip("Roar", 96, roar)
clip("Flight", 48, flight, ik=False)
for pose_bone in rig.pose.bones:
    pose_bone.rotation_quaternion = (1, 0, 0, 0)
    pose_bone.location = (0, 0, 0)
    pose_bone.scale = (1, 1, 1)
