"""Griffon V2: an eagle-headed, lion-bodied griffon built as one skinned game character.

Blender is Z-up and the griffon faces -Y; the glTF exporter converts to Y-up. Units are metres.

What changed from V1:
- One armature deforms everything by skin weights: a spine, a three-bone neck, a five-bone tail,
  leg chains, eyelids, a jaw, three-bone wings and one bone per flight feather, so wings fold the
  way a bird's do and bodies bend smoothly instead of hinging between rigid parts.
- The trunk is one sculpted surface (shoulders, ribcage, tucked belly, haunches, hamstrings) whose
  hide crossfades from plumage to lion fur; feathers thin out into wisps over that transition.
- The head is sculpted around a brow shelf, eye sockets and cheeks, with a hooked, D-section beak,
  cere and nostrils, eyelids, and a detailed iris.
- Feathers are scattered irregularly along a flow field from the beak instead of in rows, and the
  wings are rebuilt as primaries (notched "fingers"), secondaries, tertials, greater, median,
  lesser and marginal coverts, an alula and scapulars, each tinted and varied per feather.

Three clips share the rig: Idle (wings raised), Wing beat, and Perched (wings folded).
"""

import math
import random

import bpy
from mathutils import Matrix, Vector, noise

from tools import lab_materials as lab
from tools import lab_shapes as shapes
from tools.lab_shapes import (CONTOUR, EMARGINATED, HACKLE, PRIMARY, SECONDARY, SMALL, WISP, ellipsoid, eyelid,
                              feather, frame, loft)

lab.configure(name="Griffon V2", atlas_size=2048, atlas_data_size=1024, card_size=1024, ao_distance=0.3,
              card_ao_strength=0.35)
rng = random.Random(7)


def jitter(amount):
    return rng.uniform(-amount, amount)


def smooth(lo, hi, x):
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


# ---------------------------------------------------------------- materials

FUR = (0.44, 0.25, 0.085)
fur_params = dict(color=FUR, color2=(0.58, 0.4, 0.2), color3=(0.28, 0.15, 0.05), belly=(0.5, 0.86),
                  dorsal=(1.18, 1.42), legs=(0.45, 0.8), flow="y", leg_flow="z", mottle=0.22,
                  scale=0.04, roughness=0.84, bump=0.7, contrast=0.42)
hide = lab.surface("Griffon hide", "blend", (0.62, 0.44, 0.2),
                   a=("plumage", dict(color=(0.56, 0.39, 0.17), scale=0.02, variation=0.3, bump=0.45, roughness=0.62)),
                   b=("fur", fur_params), axis="y", start=-0.24, end=0.0, noise=0.08, noise_scale=0.1)
paws = lab.surface("Lion paws", "fur", FUR, **{k: v for k, v in fur_params.items() if k not in ("color", "dorsal")})
tuft_fur = lab.surface("Dark tail tuft", "fur", (0.07, 0.045, 0.025), flow="z", scale=0.02, roughness=0.9, texel=0.6)
face = lab.surface("Face plumage", "plumage", (0.9, 0.82, 0.62), scale=0.009, variation=0.22, bump=0.35, texel=2.6)
wing_flesh = lab.surface("Wing leading edge", "plumage", (0.66, 0.46, 0.18), scale=0.015, texel=0.35)
beak = lab.surface("Beak", "keratin", (0.84, 0.6, 0.17), tip=(0, -1.205, 1.875), tip_radius=0.13,
                   tip_color=(0.12, 0.09, 0.06), root=(0, -0.96, 2.02), root_radius=0.08, root_color=(0.95, 0.78, 0.36),
                   grain="y", roughness=0.3, variation=0.7, contrast=0.4, bump=0.7, texel=3.0)
cere = lab.surface("Cere and gape", "skin", (0.86, 0.63, 0.13), scale=0.004, roughness=0.5, texel=2.5)
nostril = lab.surface("Nostrils", "skin", (0.02, 0.015, 0.012), scale=0.003, texel=0.3)
scales = lab.surface("Leg scales", "scales", (0.8, 0.56, 0.13), scale=0.016, roughness=0.42, variation=0.35, texel=1.6)
talon = lab.surface("Talons", "keratin", (0.03, 0.028, 0.026), grain="z", roughness=0.24, variation=0.8, texel=1.4)
lion_claw = lab.surface("Lion claws", "keratin", (0.42, 0.37, 0.3), grain="y", roughness=0.35, texel=0.8)
plumes = lab.surface("Griffon feathers", "feather", (0.6, 0.42, 0.18), jitter=0.07)
iris = lab.surface("Griffon eyes", "eye", (0.95, 0.52, 0.07), color2=(0.22, 0.11, 0.03), pupil=0.105,
                   iris_radius=0.34, glow=0.12, roughness=0.04)


# ---------------------------------------------------------------- landmarks and bones

HEAD = Vector((0, -0.84, 2.06))
BEAK_BASE = Vector((0, -0.985, 2.035))
SHOULDER = Vector((0.27, -0.33, 1.5))   # right wing root; left mirrors
SIDES = ((1, "R"), (-1, "L"))
MIRROR = Matrix.Diagonal((-1, 1, 1, 1))

RAISE, SWEEP = 0.5, 0.18
WS = Matrix.Translation(SHOULDER) @ Matrix.Rotation(-RAISE, 4, "Y") @ Matrix.Rotation(SWEEP, 4, "Z")
ELBOW, WRIST, TIP = Vector((0.56, 0.2, 0.0)), Vector((1.28, -0.04, 0.04)), Vector((2.05, 0.1, 0.02))
NORMAL = (WS.to_3x3() @ Vector((0, 0, 1))).normalized()   # right wing's upper surface at rest

EYE_OFFSET = Vector((0.066, -0.118, 0.03))
GAZE = Vector((0.76, -0.65, 0.02)).normalized()

TAIL = [Vector(p) for p in ((0, 0.84, 1.15), (0, 1.08, 1.24), (0, 1.32, 1.17), (0, 1.48, 0.98), (0, 1.58, 0.76),
                            (0, 1.72, 0.6), (0, 1.9, 0.6), (0, 2.02, 0.7))]

BONES = {}  # name -> (head, tail, parent)


def bone(name, head, tail, parent=None):
    BONES[name] = (Vector(head), Vector(tail), parent)


bone("pelvis", (0, 0.55, 1.12), (0, 0.2, 1.08))
bone("spine", (0, 0.2, 1.08), (0, -0.2, 1.12), "pelvis")
bone("chest", (0, -0.2, 1.12), (0, -0.5, 1.3), "spine")
bone("neck1", (0, -0.5, 1.3), (0, -0.68, 1.56), "chest")
bone("neck2", (0, -0.68, 1.56), (0, -0.76, 1.78), "neck1")
bone("neck3", (0, -0.76, 1.78), (0, -0.8, 1.94), "neck2")
bone("head", (0, -0.8, 1.94), (0, -0.98, 2.08), "neck3")
bone("jaw", (0, -0.92, 1.99), (0, -1.12, 1.96), "head")
for i, (a, b) in enumerate(zip([TAIL[0], TAIL[2], TAIL[3], TAIL[5], TAIL[6]], [TAIL[2], TAIL[3], TAIL[5], TAIL[6], TAIL[7]])):
    bone(f"tail{i + 1}", a, b, f"tail{i}" if i else "pelvis")
for side, tag in SIDES:
    m = lambda x, y, z: (x * side, y, z)
    eye = HEAD + Vector((EYE_OFFSET.x * side, EYE_OFFSET.y, EYE_OFFSET.z))
    bone(f"lid.{tag}", eye, eye + Vector((0, 0, 0.05)), "head")
    bone(f"thigh.{tag}", m(0.2, 0.6, 0.98), m(0.25, 0.42, 0.62), "pelvis")
    bone(f"shin.{tag}", m(0.25, 0.42, 0.62), m(0.25, 0.74, 0.34), f"thigh.{tag}")
    bone(f"hfoot.{tag}", m(0.25, 0.74, 0.34), m(0.25, 0.62, 0.07), f"shin.{tag}")
    bone(f"arm.{tag}", m(0.2, -0.42, 0.96), m(0.25, -0.5, 0.62), "chest")
    bone(f"tarsus.{tag}", m(0.25, -0.5, 0.62), m(0.25, -0.58, 0.12), f"arm.{tag}")
    bone(f"ffoot.{tag}", m(0.25, -0.58, 0.12), m(0.25, -0.78, 0.05), f"tarsus.{tag}")


def wing_world(point, side=1):
    world = WS @ Vector(point)
    return Vector((world.x * side, world.y, world.z))


for side, tag in SIDES:
    bone(f"up.{tag}", wing_world((0, 0, 0), side), wing_world(ELBOW, side), "chest")
    bone(f"fore.{tag}", wing_world(ELBOW, side), wing_world(WRIST, side), f"up.{tag}")
    bone(f"hand.{tag}", wing_world(WRIST, side), wing_world(TIP, side), f"fore.{tag}")


def weigh(point, names, influences=3, power=4.0):
    return shapes.envelope_weights(point, [(n, BONES[n][0], BONES[n][1]) for n in names], power, influences)


skinned = []  # every deforming object


def part(name, mat, piece, weights):
    """weights: a bone name (rigid), or a function point -> {bone: weight}."""
    obj = shapes.make_object(name, mat, piece)
    if isinstance(weights, str):
        shapes.assign_weights(obj, [{weights: 1.0}] * len(piece.verts))
    else:
        shapes.assign_weights(obj, [weights(v) for v in piece.verts])
    skinned.append(obj)
    return obj


def batch_build(batch):
    obj = batch.build()
    if obj:
        skinned.append(obj)
    return obj


# ---------------------------------------------------------------- trunk: one sculpted surface

trunk_nodes = [
    ((0, 0.62, 1.13), 0.29, 0.30),      # 0 rump
    ((0, 0.36, 1.1), 0.26, 0.27),       # 1 loin
    ((0, 0.12, 1.09), 0.25, 0.25),      # 2 waist, tucked
    ((0, -0.15, 1.1), 0.31, 0.34),      # 3 ribcage
    ((0, -0.38, 1.14), 0.34, 0.38),     # 4 deep chest
    ((0, -0.6, 1.38), 0.27, 0.28),      # 5 breast
    ((0, -0.71, 1.62), 0.18, 0.19),     # 6 neck
    ((0, -0.78, 1.83), 0.15, 0.155),    # 7 throat
    ((0, -0.82, 1.99), 0.12, 0.12),     # 8 nape, inside the skull
    ((0, 0.86, 1.16), 0.1, 0.1),        # 9 tail root
]
trunk_edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (0, 9)]
for side, _ in SIDES:
    s = len(trunk_nodes)
    trunk_nodes += [((0.19 * side, 0.6, 0.97), 0.23, 0.24), ((0.25 * side, 0.42, 0.62), 0.155, 0.165),
                    ((0.25 * side, 0.75, 0.34), 0.092, 0.1), ((0.25 * side, 0.69, 0.16), 0.078, 0.08),
                    ((0.25 * side, 0.63, 0.08), 0.085, 0.064)]   # down into the paw
    trunk_edges += [(0, s), (s, s + 1), (s + 1, s + 2), (s + 2, s + 3), (s + 3, s + 4)]
    s = len(trunk_nodes)
    trunk_nodes += [((0.19 * side, -0.42, 0.94), 0.15, 0.16), ((0.24 * side, -0.5, 0.62), 0.095, 0.1)]
    trunk_edges += [(4, s), (s, s + 1)]
trunk = shapes.skin_body("Griffon | Trunk", hide, trunk_nodes, trunk_edges)

# Procedural sculpting: muscle masses, bony landmarks and hollows (centre, radius, push).
stamps = [((0, 0.15, 0.84), 0.2, -0.045), ((0, -0.05, 1.42), 0.1, -0.01), ((0, 0.3, 1.38), 0.1, -0.012)]
for side, _ in SIDES:
    x = lambda v: v * side
    stamps += [
        ((x(0.27), -0.3, 1.3), 0.14, 0.03),      # scapula and shoulder mass
        ((x(0.3), -0.08, 1.04), 0.17, 0.016),    # ribcage
        ((x(0.25), 0.27, 0.98), 0.1, -0.022),    # flank hollow before the haunch
        ((x(0.19), 0.55, 1.28), 0.09, 0.02),     # point of the hip
        ((x(0.12), 0.74, 1.3), 0.12, 0.018),     # croup
        ((x(0.3), 0.44, 0.84), 0.13, 0.035),     # quadriceps
        ((x(0.24), 0.77, 0.86), 0.13, 0.042),    # hamstrings
        ((x(0.27), 0.67, 0.5), 0.07, 0.022),     # gastrocnemius
        ((x(0.25), 0.82, 0.36), 0.04, 0.008),    # point of the hock
        ((x(0.17), -0.52, 1.0), 0.1, 0.02),      # pectoral, where the foreleg meets the breast
    ]
shapes.displace(trunk, stamps)
TRUNK_BONES = ["pelvis", "spine", "chest", "neck1", "neck2", "neck3", "head", "tail1"] + \
    [f"{b}.{t}" for t in "RL" for b in ("thigh", "shin", "hfoot", "arm", "tarsus")]
shapes.assign_weights(trunk, [weigh(v.co, TRUNK_BONES) for v in trunk.data.vertices])
skinned.append(trunk)


# ---------------------------------------------------------------- tail with a tufted tip

tail_points = []
for i, (a, b) in enumerate(zip(TAIL, TAIL[1:])):
    for k in range(2):
        t = (i * 2 + k) / ((len(TAIL) - 1) * 2)
        tail_points.append((a.lerp(b, k / 2), 0.078 - 0.042 * t, 0.078 - 0.042 * t))
tail_points.append((TAIL[-1] + Vector((0, 0.02, 0.04)), 0, 0))
TAIL_BONES = ["pelvis"] + [f"tail{i}" for i in range(1, 6)]
part("Griffon | Tail", paws, loft(tail_points, ring=12), lambda p: weigh(p, TAIL_BONES))
tuft = shapes.Batch("Griffon | Tail tuft", tuft_fur)
end, along = TAIL[-1] + Vector((0, -0.04, -0.02)), (TAIL[-1] - TAIL[-2]).normalized()
for k in range(30):
    angle = rng.uniform(0, 2 * math.pi)
    spread = rng.uniform(0.15, 0.7)
    sideways = along.orthogonal().normalized()
    sideways.rotate(Matrix.Rotation(angle, 3, along))
    direction = (along + sideways * spread).normalized()
    length = rng.uniform(0.13, 0.27)
    bend = Vector((0, 0, -0.04 * rng.random()))
    start = end + sideways * rng.uniform(0.0, 0.03)
    tuft.add(loft([(start, 0.022, 0.022), (start + direction * length * 0.45 + bend * 0.5, 0.018, 0.016),
                   (start + direction * length + bend, 0, 0)], ring=5), weights={"tail5": 1.0})
batch_build(tuft)


# ---------------------------------------------------------------- hind paws: pad, four toes, sheathed claws

for side, tag in SIDES:
    foot = f"hfoot.{tag}"
    paw = shapes.Batch(f"Griffon | Hind paw {tag}", paws)
    claws = shapes.Batch(f"Griffon | Hind claws {tag}", lion_claw)
    paw.add(ellipsoid((0.25 * side, 0.6, 0.072), (0.092, 0.13, 0.068), segments=18, rings=10), weights={foot: 1.0})
    for dx, dy, r in ((-0.066, 0.508, 0.029), (-0.023, 0.482, 0.034), (0.022, 0.482, 0.034), (0.064, 0.508, 0.029)):
        centre = Vector((0.25 * side + dx * side, dy, 0.05))
        paw.add(ellipsoid(centre, (r, r * 1.35, r * 1.15), Matrix.Rotation(0.25, 3, "X"), segments=12, rings=8), weights={foot: 1.0})
        tip = centre + Vector((0, -r * 1.2, 0.0))
        claws.add(loft([(tip + Vector((0, 0.012, 0.012)), 0.008, 0.011), (tip + Vector((0, -0.012, 0.002)), 0.005, 0.007),
                        (tip + Vector((0, -0.026, -0.022)), 0, 0)], ring=6), weights={foot: 1.0})
    batch_build(paw)
    batch_build(claws)


# ---------------------------------------------------------------- eagle forelegs: scutes, knuckled toes, talons

def talon_profile(angle):
    """Laterally compressed, keeled cross-section for talons."""
    return 0.62 * math.cos(angle), math.sin(angle) * (1.0 if math.sin(angle) > 0 else 0.8)


for side, tag in SIDES:
    legs = shapes.Batch(f"Griffon | Foreleg {tag}", scales)
    claws = shapes.Batch(f"Griffon | Talons {tag}", talon)
    top, ankle = Vector((0.25 * side, -0.5, 0.64)), Vector((0.25 * side, -0.58, 0.115))
    ridges = []
    for i in range(17):
        t = i / 16
        radius = (0.068 - 0.016 * t) * (1.0 if i % 2 else 1.07)
        ridges.append((top.lerp(ankle, t), radius, radius * 1.05))
    leg_names = [f"tarsus.{tag}", f"ffoot.{tag}", f"arm.{tag}"]
    tarsus = loft(ridges, ring=12)
    legs.add(tarsus, weights=[weigh(v, leg_names, 2) for v in tarsus.verts])
    legs.add(ellipsoid(ankle + Vector((0, -0.01, -0.04)), (0.058, 0.064, 0.04), segments=14, rings=8), weights={f"ffoot.{tag}": 1.0})
    for yaw, length, talon_size in ((-0.44, 0.2, 1.0), (0.0, 0.245, 1.1), (0.44, 0.2, 1.0), (math.pi, 0.13, 1.25)):
        direction = Vector((math.sin(yaw) * side, -math.cos(yaw), 0))
        base = ankle + Vector((0, 0, -0.045))
        points = []
        for t, r, lift in ((0.0, 0.034, 0.0), (0.3, 0.03, 0.004), (0.45, 0.034, 0.004), (0.7, 0.027, -0.004), (0.82, 0.029, -0.004), (1.0, 0.023, -0.012)):
            points.append((base + direction * length * t + Vector((0, 0, lift - 0.018 * t * t)), r, r * 0.95))
        legs.add(loft(points, ring=10), weights={f"ffoot.{tag}": 1.0})
        tip = points[-1][0]
        k = talon_size
        drop = tip.z - 0.002   # the talon's point just reaches the ground
        claw = [(tip + direction * -0.012 + Vector((0, 0, 0.012)), 0.02 * k, 0.023 * k),
                (tip + direction * 0.026 * k + Vector((0, 0, 0.012)), 0.014 * k, 0.018 * k),
                (tip + direction * 0.055 * k + Vector((0, 0, 0.0)), 0.0095 * k, 0.012 * k),
                (tip + direction * 0.072 * k + Vector((0, 0, -drop * 0.55)), 0.0055 * k, 0.0068 * k),
                (tip + direction * 0.074 * k + Vector((0, 0, -drop)), 0, 0)]
        claws.add(loft(claw, ring=10, profile=talon_profile), weights={f"ffoot.{tag}": 1.0})
    batch_build(legs)
    batch_build(claws)


# ---------------------------------------------------------------- head: sculpted skull, beak, eyes, lids

skull = shapes.make_object("Griffon | Head", face, ellipsoid(HEAD, (0.13, 0.2, 0.135), Matrix.Rotation(-0.12, 3, "X"), 44, 28))
H = lambda x, y, z: HEAD + Vector((x, y, z))


def head_profile(co):
    """Eagle proportions: the crown slopes down into the culmen and the face narrows to the cere."""
    local = co - HEAD
    front = smooth(0.0, -0.21, local.y)
    if local.z > -0.02:
        local.z = -0.02 + (local.z + 0.02) * (1 - 0.42 * front)
    local.x *= 1 - 0.28 * front
    local.z -= 0.025 * front
    return HEAD + local


shapes.reshape(skull, head_profile)
head_stamps = [(H(0, 0.02, 0.13), 0.07, -0.016),         # flat crown between the brows
               (H(0, -0.08, -0.12), 0.08, 0.012),        # throat
               (H(0, 0.14, 0.04), 0.1, 0.012)]           # occiput
for side, _ in SIDES:
    head_stamps += [
        # The supraorbital ridge: a straight shelf from above the cere back over the eye.
        (H(0.05 * side, -0.19, 0.06), H(0.085 * side, -0.06, 0.09), 0.022, 0.04),
        (H(0.075 * side, -0.15, 0.07), H(0.09 * side, -0.1, 0.08), 0.018, 0.02),
        (H(0.094 * side, -0.118, 0.025), 0.024, -0.011),  # eye socket under the shelf
        (H(0.096 * side, -0.05, -0.05), 0.055, 0.02),     # cheek behind and below the eye
        (H(0.11 * side, 0.03, 0.0), 0.08, 0.008),         # ear coverts, widening the back of the head
    ]
shapes.displace(skull, head_stamps, snap=True)
shapes.assign_weights(skull, [{"head": 1.0}] * len(skull.data.vertices))
skinned.append(skull)


def upper_beak(angle):
    """D-section upper mandible: rounded culmen, flattened palate, keen tomial edges."""
    c, s = math.cos(angle), math.sin(angle)
    if s >= 0:
        return math.copysign(abs(c) ** 0.75, c), s
    return math.copysign(abs(c) ** 0.55, c), -0.38 * abs(s) ** 0.8


def lower_beak(angle):
    c, s = math.cos(angle), math.sin(angle)
    if s >= 0:
        return math.copysign(abs(c) ** 0.55, c), 0.3 * s ** 0.8
    return math.copysign(abs(c) ** 0.8, c), s


# A deep base and a culmen that arches from the cere to the hook, rather than a straight bill.
upper = [((0, -0.94, 2.0), 0.07, 0.088), ((0, -1.0, 1.998), 0.061, 0.082), ((0, -1.06, 1.99), 0.051, 0.073),
         ((0, -1.115, 1.972), 0.041, 0.061), ((0, -1.155, 1.942), 0.032, 0.048), ((0, -1.18, 1.902), 0.023, 0.034),
         ((0, -1.184, 1.864), 0.013, 0.02), ((0, -1.172, 1.834), 0, 0)]
part("Griffon | Upper beak", beak, loft(upper, ring=28, profile=upper_beak), "head")
lower = [((0, -0.9, 1.955), 0.046, 0.026), ((0, -0.98, 1.957), 0.043, 0.024), ((0, -1.05, 1.96), 0.035, 0.019),
         ((0, -1.1, 1.963), 0.024, 0.014), ((0, -1.13, 1.966), 0, 0)]
part("Griffon | Lower beak", beak, loft(lower, ring=20, profile=lower_beak), "jaw")
part("Griffon | Cere", cere, loft([((0, -0.925, 2.002), 0.078, 0.096), ((0, -0.975, 2.0), 0.071, 0.092),
                                   ((0, -1.012, 1.998), 0.065, 0.087), ((0, -1.02, 1.998), 0, 0)], ring=28, profile=upper_beak), "head")
features = shapes.Batch("Griffon | Nostrils", nostril)
for side, tag in SIDES:
    features.add(ellipsoid((0.052 * side, -0.995, 2.04), (0.008, 0.016, 0.007), Matrix.Rotation(0.4 * side, 3, "Z"), 10, 6),
                 weights={"head": 1.0})
batch_build(features)

eyes = shapes.Batch("Griffon | Eyes", iris)
lids = shapes.Batch("Griffon | Eyelids", face)   # feathered lids that read as the brow's edge
for side, tag in SIDES:
    centre = HEAD + Vector((EYE_OFFSET.x * side, EYE_OFFSET.y, EYE_OFFSET.z))
    gaze = Vector((GAZE.x * side, GAZE.y, GAZE.z))
    aim = Vector((0, 0, 1)).rotation_difference(gaze).to_matrix()
    eyes.add(ellipsoid(centre, (0.03, 0.03, 0.031), aim, segments=24, rings=16), weights={"head": 1.0})
    # Lids are caps about "up"; the upper one tilts down towards the beak for the eagle's stern look.
    up = (Vector((0, 0, 1)) - gaze * gaze.z).normalized()
    up.rotate(Matrix.Rotation(-0.2 * side, 3, gaze))
    lids.add(eyelid(centre, 0.03, up, math.radians(66), 0.0025), weights={f"lid.{tag}": 1.0})
    lids.add(eyelid(centre, 0.03, -up, math.radians(64), 0.0022), weights={"head": 1.0})
batch_build(eyes)
batch_build(lids)


# ---------------------------------------------------------------- feather coat over head, neck, breast and shoulders

coat = shapes.Batch("Griffon | Coat", plumes)
CREAM, GOLD, TAWNY, BRONZE = (0.95, 0.85, 0.62), (0.86, 0.52, 0.12), (0.72, 0.44, 0.14), (0.4, 0.23, 0.075)
COAT_BONES = ["head", "neck3", "neck2", "neck1", "chest", "spine", "arm.R", "arm.L"]


def transition_edge(p):
    """Where plumage gives way to fur: a ragged line around the ribs."""
    return -0.05 + 0.09 * noise.noise(p * 4.0)


def coat_size(p):
    d = (p - BEAK_BASE).length
    size = 0.03 + 0.21 * smooth(0.13, 0.85, d)
    if p.z < 1.0 and abs(p.x) > 0.1 and p.y < -0.3:
        size = 0.13 + 0.05 * smooth(1.0, 0.7, p.z)     # trousers over the forelegs
    return min(size, 0.26)


def coat_spacing(p):
    d = (p - BEAK_BASE).length
    if d < 0.13 or p.z < 0.62:
        return None
    edge = transition_edge(p)
    if p.y > edge + 0.24:
        return None
    gap = 0.4 * coat_size(p)
    if p.y > edge:
        gap *= 1 + 3.5 * (p.y - edge) / 0.24       # thinning out into the fur
    return gap


def coat_flow(p, normal):
    flow = p - BEAK_BASE
    for side, _ in SIDES:
        eye = HEAD + Vector((EYE_OFFSET.x * side, EYE_OFFSET.y, EYE_OFFSET.z))
        weight = math.exp(-((p - eye).length / 0.06) ** 2)
        flow = flow.normalized() + (p - eye).normalized() * 1.5 * weight
    if p.z < 1.05 and abs(p.x) > 0.1 and p.y < -0.3:
        flow = Vector((0, 0.15, -1))
    flow = flow - normal * flow.dot(normal)
    return flow.normalized()


def coat_tint(p, normal):
    d = (p - BEAK_BASE).length
    back = normal.y > 0.15 or normal.z > 0.6
    colour = lerp(CREAM, GOLD if back else TAWNY, smooth(0.16, 0.62, d))
    if p.z > 1.25 and p.y > -0.62:
        colour = lerp(colour, BRONZE, smooth(-0.62, -0.3, p.y))
    if p.z < 1.05 and abs(p.x) > 0.1 and p.y < -0.3:
        colour = lerp(colour, (0.62, 0.43, 0.2), 0.7)
    return lerp(colour, FUR, smooth(transition_edge(p) - 0.12, transition_edge(p) + 0.12, p.y))


for location, normal in shapes.scatter([skull, trunk], coat_spacing, seed=3, candidates=90000):
    size = coat_size(location) * rng.uniform(0.88, 1.12)
    flow = coat_flow(location, normal)
    flow.rotate(Matrix.Rotation(jitter(0.14), 3, normal))
    edge = transition_edge(location)
    nape = location.y > -0.88 and 1.5 < location.z < 2.05 and normal.y > 0.3
    if location.y > edge:
        profile, width, length, variant = WISP, 0.32, size * 1.15, rng.choice((0, 3))
    elif nape:
        profile, width, length, variant = HACKLE, 0.34, size * 1.35, 0
    else:
        profile, width, length = (SMALL if size < 0.08 else CONTOUR), rng.uniform(0.58, 0.7), size
        variant = rng.choice((0, 2, 2)) if normal.y < -0.2 else rng.choice((0, 0, 3))
    lift = rng.uniform(0.1, 0.2)
    direction = flow * math.cos(lift) + normal * math.sin(lift)
    piece = feather(frame(location + normal * 0.004, direction, normal), length, length * width, profile,
                    curl=rng.uniform(-0.18, -0.08), ridge=0.004 + 0.02 * size, variant=variant, twist=jitter(0.15))
    coat.add(piece, tint=coat_tint(location, normal), weights=weigh(location, COAT_BONES, 2))
batch_build(coat)


# ---------------------------------------------------------------- wings
# Built for the right wing in wing space (X out along the span, Y back along the chord, Z up),
# then mirrored. Flight feathers each get a bone so the fan can close when the wing folds.

def on_arm(x):
    if x <= ELBOW.x:
        return Vector((0, 0, 0)).lerp(ELBOW, x / ELBOW.x)
    if x <= WRIST.x:
        return ELBOW.lerp(WRIST, (x - ELBOW.x) / (WRIST.x - ELBOW.x))
    return WRIST.lerp(TIP, min((x - WRIST.x) / (TIP.x - WRIST.x), 1.0))


def arm_radius(x):
    return 0.1 + (0.045 - 0.1) * min(x / WRIST.x, 1.0) if x <= WRIST.x else 0.045 - 0.025 * (x - WRIST.x) / (TIP.x - WRIST.x)


def segment(x):
    return "up" if x < ELBOW.x else "fore" if x < WRIST.x else "hand"


wing = {tag: shapes.Batch(f"Griffon | Wing {tag}", plumes) for _, tag in SIDES}
flesh = {tag: shapes.Batch(f"Griffon | Wing arm {tag}", wing_flesh) for _, tag in SIDES}
FEATHER_BONES = []   # (name without side, wing-space root, rest angle in degrees, parent segment)
# Small coverts ride a few group bones along the leading edge, which swing them back when folding.
COVERT_GROUPS = [(f"cov{i + 1}", x, segment) for i, (x, segment) in enumerate(
    [(0.14, "up"), (0.4, "up")] + [(ELBOW.x + 0.06 + (WRIST.x - ELBOW.x - 0.12) * k / 4, "fore") for k in range(5)])]


def covert_bone(x):
    seg = "up" if x < ELBOW.x else "fore"
    return min((g for g in COVERT_GROUPS if g[2] == seg), key=lambda g: abs(g[1] - x))[0]


def add_wing(piece, tint, bone_for):
    """Add a wing-space piece to both wings. bone_for(tag) -> weights dict."""
    world = piece.transformed(WS)
    for side, tag in SIDES:
        wing[tag].add(world if side == 1 else world.mirrored(), tint=tint, weights=bone_for(tag))


def wing_feather(x, angle, length, width, lift, tint, profile=CONTOUR, curl=-0.06, roll=0.0, back=0.0,
                 variant=0, sweep=0.0, bone_name=None, twist=0.0, covert=False):
    root = on_arm(x) + Vector((0, 0.03 + back, lift))
    local = Matrix.Translation(root) @ Matrix.Rotation(math.radians(angle), 4, "Z") @ Matrix.Rotation(roll, 4, "X") \
        @ Matrix.Rotation(-0.03, 4, "Y")
    piece = feather(local, length, width, profile, curl=curl, variant=variant, sweep=sweep, twist=twist,
                    ridge=0.006 + 0.008 * length)
    world_root = WS @ root
    if covert and x <= WRIST.x:
        bone_name = covert_bone(x)
    if bone_name:
        def weights(tag):
            return {f"{bone_name}.{tag}": 1.0}
    else:
        def weights(tag):
            point = world_root if tag == "R" else MIRROR.to_3x3() @ world_root
            # Feathers are rigid: one bone each, so large folds never shear them.
            return weigh(point, [f"{n}.{tag}" for n in ("up", "fore", "hand")], 1)
    add_wing(piece, tint, weights)
    return root


def wing_tint(base, amount=0.0):
    return tuple(c * (1 + amount) for c in base)


# Primaries: ten, the outer six notched into "fingers" that spread and turn up at the tips.
PRIMARY_LENGTHS = (1.0, 1.07, 1.15, 1.24, 1.32, 1.37, 1.38, 1.33, 1.21, 1.02)
for i, length in enumerate(PRIMARY_LENGTHS):
    t = i / 9
    x = WRIST.x + 0.02 + (TIP.x - WRIST.x - 0.06) * (t ** 0.85)
    angle = 76 - 68 * t + jitter(1.5)
    name = f"pri{i + 1}"
    root = wing_feather(x, angle, length * rng.uniform(0.98, 1.02), 0.19 - 0.05 * t, 0.012 * i - 0.025,
                        wing_tint((0.105, 0.068, 0.04), 0.25 * (1 - t) + jitter(0.05)),
                        EMARGINATED if i >= 4 else PRIMARY, curl=0.03 + 0.05 * t if i >= 4 else -0.03,
                        roll=0.14 + 0.06 * t, variant=rng.choice((0, 1)), sweep=-0.02 * t, bone_name=name, twist=0.08 * t)
    FEATHER_BONES.append((name, root, angle, "hand"))

# Secondaries: broad, blunt and slightly scalloped along the trailing edge.
for i in range(15):
    t = i / 14
    x = ELBOW.x - 0.04 + (WRIST.x - ELBOW.x + 0.02) * t
    angle = 97 - 15 * t + jitter(1.2)
    name = f"sec{i + 1}"
    root = wing_feather(x, angle, (1.0 - 0.06 * t) * rng.uniform(0.97, 1.03), 0.2, -0.012 + 0.0045 * i,
                        wing_tint((0.2, 0.125, 0.06), -0.12 * t + jitter(0.06)), SECONDARY, curl=-0.05,
                        roll=0.12, variant=rng.choice((1, 1, 0)), bone_name=name)
    FEATHER_BONES.append((name, root, angle, "fore"))

# Tertials lie over the elbow on the upper arm, each on its own bone so they lie flat when folded.
for i in range(4):
    t = i / 3
    angle = 106 - 4 * t + jitter(2)
    name = f"ter{i + 1}"
    root = wing_feather(0.1 + 0.36 * t, angle, 0.92 - 0.06 * t, 0.2, 0.04 - 0.008 * i,
                        wing_tint((0.32, 0.2, 0.09), jitter(0.06)), SECONDARY, curl=-0.06, roll=0.1,
                        variant=rng.choice((1, 3)), bone_name=name)
    FEATHER_BONES.append((name, root, angle, "up"))

# Greater and median coverts over each secondary, and primary coverts over the hand; they share
# their flight feather's bone so coverts and flight feathers close together.
for name, root, angle, parent in list(FEATHER_BONES):
    if parent == "up" or name == "alula":
        continue
    index = int(name[3:]) - 1
    if parent == "fore":
        x = ELBOW.x - 0.04 + (WRIST.x - ELBOW.x + 0.02) * index / 14
        wing_feather(x, angle + 2, rng.uniform(0.44, 0.5) - 0.04 * index / 14, 0.18, 0.04 + 0.002 * index,
                     wing_tint((0.44, 0.28, 0.11), jitter(0.06)), CONTOUR, curl=-0.1, roll=0.1, back=0.005,
                     variant=rng.choice((0, 2)), bone_name=name)
        wing_feather(x, angle + 8, rng.uniform(0.24, 0.29), 0.16, 0.065, wing_tint((0.6, 0.4, 0.15), jitter(0.06)),
                     CONTOUR, curl=-0.14, roll=0.08, back=-0.04, variant=rng.choice((0, 2)), bone_name=name)
    else:
        t = index / 9
        x = WRIST.x + 0.02 + (TIP.x - WRIST.x - 0.06) * (t ** 0.85)
        wing_feather(x, angle + 4, 0.5 - 0.2 * t, 0.16, 0.05, wing_tint((0.3, 0.19, 0.08), jitter(0.05)),
                     CONTOUR, curl=-0.08, roll=0.1, variant=rng.choice((0, 2)), bone_name=name)

# Lesser coverts point back and slightly towards the body, in loose overlapping rows.
for row, (length, lift, back, count) in enumerate(((0.2, 0.085, -0.075, 20), (0.15, 0.098, -0.1, 17), (0.11, 0.108, -0.12, 14))):
    for i in range(count):
        t = (i + rng.uniform(-0.3, 0.3)) / (count - 1)
        x = 0.06 + (WRIST.x - 0.06) * max(0.0, min(1.0, t))
        wing_feather(x, 118 - 6 * t + jitter(5), length * rng.uniform(0.9, 1.1), 0.15 - 0.02 * row, lift,
                     wing_tint((0.72, 0.5, 0.19), jitter(0.07)), SMALL, curl=-0.2, back=back, variant=rng.choice((0, 2)),
                     covert=True)

# Underwing coverts, paler, hide the arm from below.
for row, (length, lift, back) in enumerate(((0.38, -0.04, 0.0), (0.24, -0.06, -0.05))):
    for i in range(16):
        t = i / 15
        wing_feather(0.06 + (WRIST.x - 0.06) * t, 104 - 18 * t + jitter(3), length * rng.uniform(0.92, 1.08), 0.16, lift,
                     wing_tint((0.66, 0.5, 0.29), jitter(0.06)), SMALL if row else CONTOUR, curl=0.14, roll=math.pi,
                     back=back, variant=0, covert=True)

# Marginal coverts wrap the leading edge from the shoulder past the wrist.
for i in range(30):
    x = 0.05 + (WRIST.x + 0.42) * i / 29 + jitter(0.01)
    centre, radius = on_arm(x), arm_radius(x) + 0.01
    for theta in (-1.0, -0.35, 0.3, 0.95):
        theta += 0.25 * (i % 2) + jitter(0.08)
        outward = Vector((0, -math.cos(theta), math.sin(theta)))
        flow = Vector((-0.25, 0.7 + 0.3 * math.sin(abs(theta)), math.copysign(math.cos(theta), theta)))
        piece = feather(frame(centre + outward * radius, flow, outward), 0.13 * rng.uniform(0.9, 1.15), 0.085, SMALL,
                        curl=-0.25, ridge=0.003, variant=0)
        owner = covert_bone(x) if x < WRIST.x else "hand"
        add_wing(piece, wing_tint((0.74, 0.54, 0.24), jitter(0.06)), lambda tag, o=owner: {f"{o}.{tag}": 1.0})

# The alula: a little thumb of stiff feathers at the wrist, folding back on its own bone.
for i in range(4):
    root = wing_feather(WRIST.x - 0.02 + 0.03 * i, -12 + 8 * i, 0.3 - 0.04 * i, 0.08, 0.05 + 0.004 * i,
                        wing_tint((0.28, 0.17, 0.07), jitter(0.05)), CONTOUR, curl=0.02, roll=0.1, back=-0.07,
                        bone_name="alula")
FEATHER_BONES.append(("alula", root, 0.0, "hand"))

# The arm itself, under the coverts: smooth through the elbow and wrist by skin weights.
arm_piece = loft([((-0.14, 0, 0), 0, 0), ((-0.07, 0, 0), 0.085, 0.075), ((0, 0, 0), 0.1, 0.085), (ELBOW * 0.5, 0.08, 0.068),
                  (ELBOW, 0.066, 0.056), (ELBOW.lerp(WRIST, 0.5), 0.055, 0.048), (WRIST, 0.048, 0.044),
                  (WRIST.lerp(TIP, 0.5), 0.036, 0.03), (TIP, 0.02, 0.016), (TIP + Vector((0.06, 0.02, 0)), 0, 0)], ring=12)
arm_world = arm_piece.transformed(WS)
for side, tag in SIDES:
    piece = arm_world if side == 1 else arm_world.mirrored()
    names = [f"up.{tag}", f"fore.{tag}", f"hand.{tag}", "chest"]
    flesh[tag].add(piece, weights=[weigh(v, names, 2, 5.0) for v in piece.verts])

# Scapulars: long body feathers that cover the wing root and lie back along the spine.
scapular = shapes.Batch("Griffon | Scapulars", plumes)
for i in range(16):
    side = 1 if i % 2 == 0 else -1
    k = i // 2
    root = Vector((side * (0.12 + 0.03 * (k % 3) + jitter(0.015)), -0.42 + 0.06 * k + jitter(0.02), 1.47 - 0.01 * k))
    direction = Vector((side * 0.15, 1.0, -0.25 - 0.02 * k)).normalized()
    up = Vector((side * 0.3, 0, 1)).normalized()
    length = rng.uniform(0.34, 0.46) - 0.01 * k
    scapular.add(feather(frame(root, direction, up), length, length * 0.42, CONTOUR, curl=-0.1, ridge=0.01,
                         variant=rng.choice((0, 3))),
                 tint=lerp(BRONZE, (0.36, 0.22, 0.08), rng.random()), weights={"chest": 1.0})

for batch in list(wing.values()) + list(flesh.values()) + [scapular]:
    batch_build(batch)

for side, tag in SIDES:
    for name, x, parent in COVERT_GROUPS:
        head, tail = WS @ on_arm(x), WS @ (on_arm(x) + Vector((0, 0.15, 0)))
        if side < 0:
            head, tail = MIRROR.to_3x3() @ head, MIRROR.to_3x3() @ tail
        bone(f"{name}.{tag}", head, tail, f"{parent}.{tag}")
    for name, root, angle, parent in FEATHER_BONES:
        head = WS @ root
        tail = WS @ (root + Vector((math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0)) * 0.25)
        if side < 0:
            head, tail = MIRROR.to_3x3() @ head, MIRROR.to_3x3() @ tail
        bone(f"{name}.{tag}", head, tail, f"{parent}.{tag}")


# ---------------------------------------------------------------- rig

bpy.ops.object.armature_add(location=(0, 0, 0))
rig = bpy.context.object
rig.name = "Griffon | Rig"
rig.data.name = "Griffon rig"
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


# ---------------------------------------------------------------- animation

AXES = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}


def about(pivot, axis, angle):
    pivot = Vector(pivot)
    return Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, AXES[axis] if isinstance(axis, str) else axis) @ Matrix.Translation(-pivot)


def head_of(name):
    return BONES[name][0]


def wing_angles():
    """Planar fold targets (degrees about the wing normal) from the wing's own geometry."""
    deg = lambda v: math.degrees(math.atan2(v.y, v.x))
    humerus = 76 - deg(ELBOW)
    forearm_total = -96 - deg(WRIST - ELBOW)
    hand_total = 86 - deg(TIP - WRIST)
    feathers = {}
    for name, root, angle, parent in FEATHER_BONES:
        if name == "alula":
            feathers[name] = (95 - angle - hand_total, 0.02)
            continue
        number = int(name[3:])
        if parent == "up":
            target, total, stack = 104 - number, humerus, 0.08 + 0.006 * number
        elif parent == "fore":
            target, total, stack = 99 - 0.6 * number, forearm_total, 0.0045 * (16 - number)
        else:
            target, total, stack = 92 - 0.5 * number, hand_total, -0.035 - 0.0035 * number
        feathers[name] = (target - angle - total, stack)
    for name, x, parent in COVERT_GROUPS:
        feathers[name] = (-58 if parent == "up" else 62, 0.03)
    return humerus, forearm_total - humerus, hand_total - forearm_total, feathers


HUMERUS, FOREARM, HAND, FEATHERS = wing_angles()


def right_wing(fold, lower, flap, hand_flap):
    """Deltas for the right wing: fold (0-1) closes it in its own plane, lower (radians) swings the
    folded wing down onto the body, flap raises it about the body's long axis."""
    s, e, w = WS @ Vector((0, 0, 0)), WS @ ELBOW, WS @ WRIST
    rad = math.radians
    deltas = {
        "up": about(s, "Y", -flap) @ about(s, "Y", lower) @ about(s, NORMAL, rad(HUMERUS) * fold),
        "fore": about(e, NORMAL, rad(FOREARM) * fold),
        "hand": about(w, "Y", -hand_flap) @ about(w, NORMAL, rad(HAND) * fold),
    }
    pivots = [(n, WS @ r) for n, r, a, p in FEATHER_BONES] + [(n, WS @ on_arm(x)) for n, x, p in COVERT_GROUPS]
    for name, pivot in pivots:
        turn, stack = FEATHERS[name]
        deltas[name] = Matrix.Translation(NORMAL * stack * fold) @ about(pivot, NORMAL, rad(turn) * fold)
    return deltas


def wings(fold=0.0, lower=0.0, flap=0.0, hand_flap=0.0):
    deltas = {}
    for name, delta in right_wing(fold, lower, flap, hand_flap).items():
        deltas[f"{name}.R"] = delta
        deltas[f"{name}.L"] = MIRROR @ delta @ MIRROR
    return deltas


def chain(names, axis, angles):
    return {n: about(head_of(n), axis, a) for n, a in zip(names, angles)}


NECK = ["neck1", "neck2", "neck3"]
TAILS = [f"tail{i}" for i in range(1, 6)]


def key_pose(frame_number, deltas):
    for name in BONES:
        delta = deltas.get(name, Matrix.Identity(4))
        rest = rig.data.bones[name].matrix_local
        basis = rest.inverted() @ delta @ rest
        pose_bone = rig.pose.bones[name]
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.rotation_quaternion = basis.to_quaternion()
        pose_bone.location = basis.translation
        pose_bone.keyframe_insert("rotation_quaternion", frame=frame_number)
        pose_bone.keyframe_insert("location", frame=frame_number)


def clip(name, frames, pose, step=2):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    for f in range(0, frames + 1, step):
        key_pose(f, pose(f / frames))
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, 0, action)
    rig.animation_data.action = None


def blink(t, *moments):
    return max([max(0.0, 1 - abs(t - m) / 0.025) for m in moments] + [0.0])


def lids(amount):
    deltas = {}
    for side, tag in SIDES:
        gaze = Vector((GAZE.x * side, GAZE.y, GAZE.z))
        across = gaze.cross(Vector((0, 0, 1))).normalized()
        deltas[f"lid.{tag}"] = about(head_of(f"lid.{tag}"), across, -0.62 * amount)
    return deltas


def look(phase, turn=0.25, tilt=0.1):
    deltas = chain(NECK, "Z", [0.05 * math.sin(phase), 0.07 * math.sin(phase - 0.2), 0.09 * math.sin(phase - 0.4)])
    deltas["head"] = about(head_of("head"), "Z", turn * math.sin(phase - 0.6)) @ about(head_of("head"), "Y", tilt * math.sin(phase + 0.6))
    return deltas


def tail_wave(phase, amplitude=0.12, lift=0.04):
    return {n: about(head_of(n), "Z", amplitude * (0.4 + 0.25 * i) * math.sin(phase - 0.7 * i))
            @ about(head_of(n), "X", lift * math.sin(2 * phase - 0.5 * i)) for i, n in enumerate(TAILS)}


def idle(t):
    phase = 2 * math.pi * t
    breath = math.sin(2 * phase)
    deltas = wings(fold=0.04 + 0.03 * breath, flap=0.03 * breath)
    deltas.update(chain(["spine", "chest"], "X", [0.008 * breath, 0.012 * breath]))
    deltas.update(look(phase))
    screech = max(0.0, math.sin(math.pi * (t - 0.42) / 0.22)) if 0.42 <= t <= 0.64 else 0.0
    deltas["jaw"] = about(head_of("jaw"), "X", 0.36 * screech)
    deltas["head"] = deltas["head"] @ about(head_of("head"), "X", -0.12 * screech)
    deltas.update(lids(blink(t, 0.18, 0.8)))
    deltas.update(tail_wave(phase))
    return deltas


def wing_beat(t):
    phase = 2 * math.pi * t
    upstroke = max(0.0, -math.sin(phase))
    deltas = wings(fold=0.38 * upstroke, flap=-0.3 + 0.85 * math.cos(phase), hand_flap=0.3 * math.cos(phase - 1.0))
    deltas.update(chain(["spine", "chest"], "X", [0.02 * math.cos(phase), 0.03 * math.cos(phase)]))
    # The neck counters the body's pitch so the head stays steady, as a bird's does.
    deltas.update(chain(NECK, "X", [-0.02 * math.cos(phase), -0.015 * math.cos(phase), -0.01 * math.cos(phase)]))
    deltas["head"] = about(head_of("head"), "X", 0.03 * math.sin(phase))
    deltas.update(tail_wave(phase, 0.04, 0.1))
    return deltas


def perched(t):
    phase = 2 * math.pi * t
    breath = math.sin(2 * phase)
    deltas = wings(fold=1.0, lower=1.29 - 0.01 * breath)
    deltas.update(chain(["spine", "chest"], "X", [0.008 * breath, 0.012 * breath]))
    deltas.update(look(phase, 0.35, 0.14))
    deltas.update(lids(blink(t, 0.35, 0.72)))
    deltas.update(tail_wave(phase, 0.08, 0.03))
    return deltas


bpy.context.scene.render.fps = 24
clip("Idle", 96, idle)
clip("Wing beat", 24, wing_beat)
clip("Perched", 96, perched)
for pose_bone in rig.pose.bones:
    pose_bone.rotation_quaternion = (1, 0, 0, 0)
    pose_bone.location = (0, 0, 0)
