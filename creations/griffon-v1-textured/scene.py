"""Griffon: an eagle-headed, lion-bodied mythical beast with layered feathered wings, rigged with
two animations (Wing beat and Idle) for Blender Lab's active creation.

Blender is Z-up and the griffon faces -Y; the glTF exporter converts to Y-up. Units are metres.
Every mesh is built directly in world space, then rigidly parented to a bone of one armature, so
both animations live on a single rig.

Materials are Blender Lab recipes (tools/lab_materials.py). The builder bakes the fur, plumage,
skin, scales and keratin into one UV atlas with ambient occlusion, gives every feather a shared
feather-card texture tinted per feather tract, and paints the eyes with a generated iris.
"""

import math

import bpy
from mathutils import Matrix, Vector

from tools import lab_materials as lab
from tools import lab_shapes as shapes
from tools.lab_shapes import CONTOUR, FLIGHT, PRIMARY, ellipsoid, feather, frame, loft

lab.configure(name="Griffon", atlas_size=1024, card_size=1024, ao_distance=0.3)

# Atlas recipes: baked together into one texture set. `texel` weights where resolution is spent.
fur = lab.surface("Tawny lion fur", "fur", (0.50, 0.31, 0.12), color2=(0.56, 0.38, 0.18), belly=(0.5, 1.1),
                  flow="y", scale=0.045, roughness=0.84, bump=0.6)
fur_dark = lab.surface("Dark tail tuft", "fur", (0.09, 0.055, 0.03), flow="y", scale=0.03, roughness=0.88, texel=0.8)
plumage = lab.surface("Cream breast plumage", "plumage", (0.86, 0.8, 0.68), scale=0.018, bump=0.35, texel=0.6)
face = lab.surface("Cream face plumage", "plumage", (0.88, 0.83, 0.72), scale=0.012, variation=0.2, bump=0.3, texel=2.2)
wing_plumage = lab.surface("Gilded wing plumage", "plumage", (0.62, 0.4, 0.13), scale=0.02, texel=0.4)
beak_mat = lab.surface("Polished gold beak", "keratin", (0.92, 0.56, 0.07), tip=(0, -1.2, 1.87), tip_radius=0.16,
                       tip_color=(0.16, 0.09, 0.03), root=(0, -0.97, 2.05), root_color=(0.98, 0.72, 0.2),
                       grain="y", roughness=0.24, variation=0.9, contrast=0.5, bump=0.8, texel=2.5)
cere_mat = lab.surface("Yellow cere", "skin", (0.85, 0.6, 0.11), scale=0.005, roughness=0.45, texel=2.5)
nostril = lab.surface("Nostrils", "skin", (0.03, 0.02, 0.015), scale=0.004, texel=0.5)
leg_scales = lab.surface("Yellow leg scales", "scales", (0.82, 0.58, 0.11), scale=0.02, roughness=0.42, texel=1.6)
talon_mat = lab.surface("Black talons", "keratin", (0.035, 0.032, 0.03), grain="z", roughness=0.2, variation=0.8, texel=1.4)

# Card recipes: every feather shares one feather texture, tinted by its tract's colour.
cream = lab.surface("Cream head feathers", "feather", (0.88, 0.82, 0.70))
gold = lab.surface("Golden mantle feathers", "feather", (0.72, 0.48, 0.16))
bronze = lab.surface("Bronze secondaries", "feather", (0.36, 0.20, 0.08))
umber = lab.surface("Umber primaries", "feather", (0.13, 0.08, 0.045))
covert = lab.surface("Gilded coverts", "feather", (0.62, 0.40, 0.13))
iris = lab.surface("Amber eyes", "eye", (1.0, 0.46, 0.03), color2=(0.3, 0.14, 0.03), pupil=0.1, iris_radius=0.32, glow=0.35)

parts = []  # (object, bone name)

# Feather-card variants: 0 plain, 1 barred, 2 pale tip with a shaft streak, 3 mottled.
PLAIN, ALL = (0, 2), (0, 1, 2, 3)


def part(name, mat, piece, bone):
    obj = shapes.make_object(name, mat, piece)
    parts.append((obj, bone))
    return obj


class Batch(shapes.Batch):
    """A shapes.Batch that remembers the bone its object rides on."""

    def __init__(self, name, mat, bone):
        super().__init__(name, mat)
        self.bone = bone

    def pick(self, options=ALL):
        return options[self.variant(len(options))]

    def build(self):
        obj = super().build()
        if obj:
            parts.append((obj, self.bone))
        return obj


def skin_body(name, mat, bone, nodes, edges):
    obj = shapes.skin_body(name, mat, nodes, edges)
    parts.append((obj, bone))
    return obj


# ---------------------------------------------------------------- anatomy landmarks

HEAD = Vector((0, -0.84, 2.06))          # skull centre
SHOULDER = Vector((0.27, -0.33, 1.5))    # right wing root; the left wing mirrors it
SIDES = ((1, "R"), (-1, "L"))


# ---------------------------------------------------------------- lion hindquarters

lion_nodes = [
    ((0, -0.32, 1.14), 0.36, 0.38),      # 0 chest (hidden under the feathered front)
    ((0, 0.12, 1.08), 0.30, 0.31),       # 1 lean waist
    ((0, 0.58, 1.12), 0.32, 0.33),       # 2 rump
    ((0, 0.86, 1.16), 0.11, 0.11),       # 3 tail root
]
lion_edges = [(0, 1), (1, 2), (2, 3)]
for side, _ in SIDES:
    start = len(lion_nodes)
    lion_nodes += [
        ((0.2 * side, 0.6, 0.95), 0.21, 0.22),    # hip
        ((0.25 * side, 0.42, 0.62), 0.15, 0.15),  # stifle, forward like a cat's
        ((0.25 * side, 0.74, 0.34), 0.09, 0.09),  # hock
        ((0.25 * side, 0.67, 0.12), 0.08, 0.08),  # ankle, buried in the paw
    ]
    lion_edges += [(2, start), (start, start + 1), (start + 1, start + 2), (start + 2, start + 3)]
lion = skin_body("Griffon | Lion body", fur, "body", lion_nodes, lion_edges)

toes = Batch("Griffon | Hind paws", fur, "body")
claws = Batch("Griffon | Hind claws", talon_mat, "body")
for side, _ in SIDES:
    toes.add(ellipsoid((0.25 * side, 0.6, 0.075), (0.09, 0.13, 0.07), segments=16, rings=10))
    for k, dx in enumerate((-0.06, -0.02, 0.02, 0.06)):
        centre = Vector((0.25 * side + dx * side, 0.5 - 0.015 * (k in (1, 2)), 0.05))
        toes.add(ellipsoid(centre, (0.032, 0.045, 0.04), segments=12, rings=8))
        claws.add(loft([(centre + Vector((0, -0.03, 0.01)), 0.012, 0.014),
                         (centre + Vector((0, -0.065, 0.0)), 0.006, 0.008),
                         (centre + Vector((0, -0.08, -0.03)), 0, 0)], ring=6))
toes.build()
claws.build()


# ---------------------------------------------------------------- lion tail with a dark tuft

tail_path = [((0, 0.84, 1.15), 0.075, 0.075), ((0, 1.08, 1.24), 0.062, 0.062), ((0, 1.32, 1.17), 0.052, 0.052),
             ((0, 1.48, 0.98), 0.046, 0.046), ((0, 1.58, 0.76), 0.042, 0.042), ((0, 1.72, 0.6), 0.04, 0.04),
             ((0, 1.9, 0.6), 0.038, 0.038), ((0, 2.02, 0.7), 0.03, 0.03), ((0, 2.06, 0.76), 0, 0)]
part("Griffon | Tail", fur, loft(tail_path, ring=12), "tail")
tuft = Batch("Griffon | Tail tuft", fur_dark, "tail")
end, along = Vector((0, 2.0, 0.69)), Vector((0, 0.5, 0.86)).normalized()
for k in range(18):
    angle = 2 * math.pi * k / 18
    spread = Vector((math.cos(angle), 0, math.sin(angle))) * (0.35 + 0.25 * (k % 3) / 2)
    direction = (along + spread).normalized()
    length = 0.2 + 0.06 * ((k * 7) % 4) / 3
    tuft.add(loft([(end, 0.035, 0.035), (end + direction * length * 0.5, 0.03, 0.03), (end + direction * length, 0, 0)], ring=6))
tuft.build()


# ---------------------------------------------------------------- feathered eagle front: chest, neck, forelegs

front_nodes = [
    ((0, -0.36, 1.12), 0.39, 0.41),      # 0 deep chest
    ((0, -0.6, 1.38), 0.29, 0.3),        # 1 breast
    ((0, -0.72, 1.64), 0.2, 0.21),       # 2 neck
    ((0, -0.78, 1.86), 0.16, 0.17),      # 3 throat
    ((0, -0.82, 2.0), 0.13, 0.13),       # 4 nape, inside the skull
]
front_edges = [(0, 1), (1, 2), (2, 3), (3, 4)]
for side, _ in SIDES:
    start = len(front_nodes)
    front_nodes += [((0.21 * side, -0.44, 0.92), 0.15, 0.16), ((0.25 * side, -0.5, 0.6), 0.1, 0.1)]
    front_edges += [(0, start), (start, start + 1)]
front = skin_body("Griffon | Feathered breast", plumage, "body", front_nodes, front_edges)


# Eagle forelegs: ridged yellow scales over the tarsus, four toes, and hooked black talons.
scales = Batch("Griffon | Scaled forelegs", leg_scales, "body")
talons = Batch("Griffon | Talons", talon_mat, "body")
for side, _ in SIDES:
    top, ankle = Vector((0.25 * side, -0.5, 0.62)), Vector((0.25 * side, -0.58, 0.1))
    ridges = []
    for i in range(15):
        t = i / 14
        radius = (0.064 - 0.014 * t) * (1.0 if i % 2 else 1.1)
        ridges.append((top.lerp(ankle, t), radius, radius))
    scales.add(loft(ridges, ring=10))
    scales.add(ellipsoid(ankle + Vector((0, 0, -0.02)), (0.06, 0.06, 0.045), segments=12, rings=8))
    for yaw, length in ((-0.45, 0.2), (0.0, 0.24), (0.45, 0.2), (math.pi, 0.12)):
        direction = Vector((math.sin(yaw) * side, -math.cos(yaw), 0))
        base = ankle + Vector((0, 0, -0.03))
        knuckle = base + direction * (length * 0.55) + Vector((0, 0, 0.0))
        tip = base + direction * length + Vector((0, 0, -0.035))
        scales.add(loft([(base, 0.035, 0.03), (knuckle, 0.03, 0.03), (tip, 0.024, 0.022)], ring=8))
        talons.add(loft([(tip + direction * -0.01 + Vector((0, 0, 0.012)), 0.02, 0.022),
                          (tip + direction * 0.04 + Vector((0, 0, 0.0)), 0.013, 0.015),
                          (tip + direction * 0.075 + Vector((0, 0, -0.025)), 0.007, 0.008),
                          (tip + direction * 0.085 + Vector((0, 0, -0.055)), 0, 0)], ring=8))
scales.build()
talons.build()


# ---------------------------------------------------------------- eagle head

skull_rot = Matrix.Rotation(-0.12, 3, "X")
part("Griffon | Skull", face, ellipsoid(HEAD, (0.15, 0.2, 0.155), skull_rot, 28, 16), "head")
part("Griffon | Cheeks", face, ellipsoid(HEAD + Vector((0, -0.07, -0.07)), (0.135, 0.15, 0.11), segments=24, rings=12), "head")

for side, _ in SIDES:
    # A heavy brow ridge gives the eagle's stern glare.
    brow = Matrix.Rotation(-0.35 * side, 3, "Y") @ Matrix.Rotation(0.25, 3, "X")
    part(f"Griffon | Brow {side:+d}", face, ellipsoid(HEAD + Vector((0.085 * side, -0.13, 0.05)), (0.06, 0.1, 0.026), brow, 16, 10), "head")
    # The eye's +Z pole looks out and forward; its generated iris centres on that pole.
    eye = HEAD + Vector((0.114 * side, -0.132, 0.02))
    gaze = Vector((0, 0, 1)).rotation_difference(Vector((0.85 * side, -0.5, 0.04))).to_matrix()
    part(f"Griffon | Eye {side:+d}", iris, ellipsoid(eye, (0.034, 0.034, 0.031), gaze, segments=20, rings=14), "head")

# Hooked upper mandible, lower mandible on its own jaw bone, cere and nostrils.
beak = [((0, -0.98, 2.05), 0.085, 0.085), ((0, -1.05, 2.05), 0.07, 0.075), ((0, -1.12, 2.03), 0.055, 0.062),
        ((0, -1.18, 1.99), 0.042, 0.05), ((0, -1.21, 1.93), 0.03, 0.036), ((0, -1.21, 1.87), 0.017, 0.02),
        ((0, -1.185, 1.83), 0, 0)]
part("Griffon | Upper beak", beak_mat, loft(beak, ring=16), "head")
mandible = [((0, -0.95, 1.975), 0.072, 0.04), ((0, -1.04, 1.962), 0.056, 0.032), ((0, -1.11, 1.958), 0.038, 0.022),
            ((0, -1.15, 1.962), 0, 0)]
part("Griffon | Lower beak", beak_mat, loft(mandible, ring=14), "jaw")
part("Griffon | Cere", cere_mat, loft([((0, -0.955, 2.06), 0.092, 0.092), ((0, -1.0, 2.07), 0.08, 0.075), ((0, -1.02, 2.075), 0, 0)], ring=16), "head")
for side, _ in SIDES:
    part(f"Griffon | Nostril {side:+d}", nostril, ellipsoid((0.045 * side, -1.0, 2.085), (0.008, 0.016, 0.009), segments=8, rings=6), "head")


# ---------------------------------------------------------------- feather coat over the head, neck and breast
# Feathers flow away from the beak, snapped onto the real surface, shading from cream to gold.

surface = shapes.bvh_of(front, *[obj for obj, bone in parts if obj.name in ("Griffon | Skull", "Griffon | Cheeks")])
coat_cream = Batch("Griffon | Hackles cream", cream, "body")
coat_gold = Batch("Griffon | Mantle gold", gold, "body")
coat_head = Batch("Griffon | Crown feathers", cream, "head")
flow_origin = HEAD + Vector((0, -0.25, 0.0))
rows = 34
for r in range(rows):
    v = r / (rows - 1)
    # Sample the coat along the neck and breast axis, from the crown down to mid-body.
    if v < 0.625:
        a, b, u = Vector((0, -0.8, 2.12)), Vector((0, -0.62, 1.42)), v / 0.625
    else:
        a, b, u = Vector((0, -0.62, 1.42)), Vector((0, -0.12, 1.1)), (v - 0.625) / 0.375
    axis_point, axis = a.lerp(b, u), (b - a).normalized()
    across = Vector((1, 0, 0)).cross(axis).normalized()
    count = 18 + int(10 * v)
    for k in range(count):
        angle = 2 * math.pi * (k + 0.5 * (r % 2)) / count
        probe = axis_point + (Vector((math.cos(angle), 0, 0)) + across * math.sin(angle)) * 0.6
        location, normal, _, _ = surface.find_nearest(probe)
        if location is None or (location.y < -0.9 and location.z < 2.12):  # keep the face smooth
            continue
        flow = (location - flow_origin)
        flow = (flow - normal * flow.dot(normal)).normalized()
        if flow.length == 0:
            continue
        size = 0.09 + 0.12 * v + 0.03 * ((k * 5 + r) % 3) / 2
        place = frame(location + normal * 0.006, flow + normal * 0.18, normal)
        batch = coat_head if location.z > 1.96 and location.y > -0.95 else coat_cream if v < 0.5 else coat_gold
        batch.add(feather(place, size, size * 0.62, CONTOUR, curl=-0.12, ridge=0.006,
                          variant=batch.pick(ALL if batch is coat_gold else PLAIN)))

# Feathered trousers over the upper forelegs, falling towards the scales.
for side, _ in SIDES:
    for i in range(5):
        for k in range(10):
            angle = 2 * math.pi * (k + 0.5 * (i % 2)) / 10
            centre = Vector((0.23 * side, -0.47, 0.98 - i * 0.08))
            probe = centre + Vector((math.cos(angle), math.sin(angle), 0)) * 0.5
            location, normal, _, _ = surface.find_nearest(probe)
            place = frame(location + normal * 0.005, Vector((0, 0, -1)) + normal * 0.25, normal)
            coat_gold.add(feather(place, 0.15 + 0.02 * i, 0.09, CONTOUR, curl=-0.1, ridge=0.005, variant=coat_gold.pick()))

# Feathered ear tufts sweeping back from the crown.
for side, _ in SIDES:
    for k, (lift, length) in enumerate(((0.0, 0.28), (0.12, 0.22), (-0.1, 0.2))):
        base = HEAD + Vector((0.085 * side, 0.04 + 0.03 * k, 0.1))
        direction = Vector((0.25 * side, 1.0, 0.45 + lift))
        coat_head.add(feather(frame(base, direction, Vector((0.5 * side, 0, 1))), length, 0.05, CONTOUR, curl=0.2, ridge=0.008, variant=2))

for batch in (coat_cream, coat_gold, coat_head):
    batch.build()


# ---------------------------------------------------------------- wings
# Built in wing space (X out along the span, Y back along the chord, Z up), raised and swept,
# then mirrored for the left wing. The arm and its feathers ride the wing bone; the hand,
# primaries and primary coverts ride the hand bone so the tip can lag in the wing beat.

RAISE, SWEEP = 0.5, 0.18
ELBOW, WRIST, TIP = Vector((0.62, 0.22, 0.0)), Vector((1.3, -0.04, 0.05)), Vector((2.05, 0.1, 0.02))


wing_batches = {}
for side, tag in SIDES:
    for key, mat, bone in (("arm", wing_plumage, "wing"), ("secondaries", bronze, "wing"), ("coverts", covert, "wing"),
                           ("lesser", gold, "wing"), ("hand", wing_plumage, "hand"), ("primaries", umber, "hand"),
                           ("primary coverts", bronze, "hand")):
        wing_batches[(tag, key)] = Batch(f"Griffon | {tag} wing {key}", mat, f"{bone}.{tag}")

ws = Matrix.Translation(SHOULDER) @ Matrix.Rotation(-RAISE, 4, "Y") @ Matrix.Rotation(SWEEP, 4, "Z")


def add_wing(key, piece):
    for side, tag in SIDES:
        wing_batches[(tag, key)].add(piece if side == 1 else piece.mirrored())


def on_arm(x):
    """Point on the leading-edge bone line at span x (wing space)."""
    if x <= ELBOW.x:
        return Vector((0, 0, 0)).lerp(ELBOW, x / ELBOW.x)
    if x <= WRIST.x:
        return ELBOW.lerp(WRIST, (x - ELBOW.x) / (WRIST.x - ELBOW.x))
    return WRIST.lerp(TIP, min((x - WRIST.x) / (TIP.x - WRIST.x), 1.0))


def add_wing_bone(key, piece):
    add_wing(key, piece.transformed(ws))


add_wing_bone("arm", loft([((-0.14, 0, 0), 0, 0), ((-0.08, 0, 0), 0.09, 0.08), ((0, 0, 0), 0.11, 0.09), (ELBOW, 0.065, 0.055), (WRIST, 0.05, 0.045)], ring=14))
add_wing_bone("arm", ellipsoid(WRIST, (0.058, 0.058, 0.05), segments=14, rings=8))
add_wing_bone("hand", loft([(WRIST, 0.048, 0.042), (WRIST.lerp(TIP, 0.5), 0.036, 0.03), (TIP, 0.02, 0.017), (TIP + Vector((0.06, 0.02, 0)), 0, 0)], ring=12))


def wing_feather(key, x, angle, length, width, lift, profile=FLIGHT, curl=-0.05, roll=0.0, back=0.0):
    base = on_arm(x) + Vector((0, 0.03 + back, lift))
    local = Matrix.Translation(base) @ Matrix.Rotation(angle, 4, "Z") @ Matrix.Rotation(roll, 4, "X") @ Matrix.Rotation(-0.03, 4, "Y")
    add_wing(key, feather(ws @ local, length, width, profile, curl=curl, variant=wing_batches[("R", key)].pick()))


# Tertials and secondaries along the arm, fanning slightly outwards.
for i in range(16):
    t = i / 15
    x = 0.02 + t * (WRIST.x - 0.04)
    wing_feather("secondaries", x, math.radians(98 - 16 * t), 1.0 - 0.12 * t + 0.08 * (i < 3), 0.2, -0.01 + 0.004 * i, roll=0.12)
# Ten fingered primaries splaying from the hand, longest in the middle.
for i in range(10):
    t = i / 9
    x = WRIST.x + 0.02 + t * (TIP.x - WRIST.x - 0.05)
    length = 1.05 + 0.4 * math.sin(math.pi * min(t * 1.25, 1.0)) - 0.12 * t
    wing_feather("primaries", x, math.radians(76 - 66 * t), length, 0.19 - 0.04 * t, 0.012 * i - 0.02, PRIMARY, curl=-0.04, roll=0.15)
# Greater coverts over the flight feathers, then median and lesser coverts towards the leading edge.
for i in range(18):
    t = i / 17
    wing_feather("coverts", 0.02 + t * (WRIST.x - 0.03), math.radians(97 - 14 * t), 0.5 - 0.06 * t, 0.18, 0.035 + 0.002 * i, CONTOUR, curl=-0.1, roll=0.1)
for i in range(9):
    t = i / 8
    wing_feather("primary coverts", WRIST.x + t * (TIP.x - WRIST.x - 0.2), math.radians(72 - 40 * t), 0.55 - 0.15 * t, 0.16, 0.05, CONTOUR, curl=-0.08, roll=0.1)
for row, (length, lift, back) in enumerate(((0.32, 0.065, -0.04), (0.22, 0.085, -0.08), (0.15, 0.1, -0.11))):
    count = 22 - row * 2
    for i in range(count):
        t = i / (count - 1)
        wing_feather("lesser", 0.04 + t * (WRIST.x - 0.04), math.radians(95 - 20 * t), length, 0.16 - 0.02 * row, lift, CONTOUR, curl=-0.15, back=back)
# Underwing coverts hide the arm from below.
for row, (length, lift, back) in enumerate(((0.36, -0.035, 0.0), (0.24, -0.055, -0.05))):
    for i in range(18):
        t = i / 17
        wing_feather("lesser", 0.04 + t * (WRIST.x - 0.04), math.radians(95 - 20 * t), length, 0.16, lift, CONTOUR, curl=0.15, roll=math.pi, back=back)
# Marginal coverts wrap the leading edge, flowing back over and under the arm.
for i in range(26):
    x = 0.05 + (WRIST.x + 0.3) * i / 25
    centre = on_arm(x)
    radius = 0.11 + (0.05 - 0.11) * min(x / WRIST.x, 1.0) + 0.012
    for theta in (-1.2, -0.75, -0.3, 0.15, 0.6, 1.05):
        theta += 0.2 * (i % 2)
        outward = Vector((0, -math.cos(theta), math.sin(theta)))
        flow = Vector((0, math.sin(abs(theta)) * 0.3 + 0.7, math.copysign(math.cos(theta), theta)))
        add_wing("lesser", feather(ws @ frame(centre + outward * radius, flow, outward), 0.13, 0.085, CONTOUR, curl=-0.2,
                                   ridge=0.004, variant=wing_batches[("R", "lesser")].pick(PLAIN)))
# Small scale-like feathers sheathing the hand's leading edge.
for i in range(10):
    t = i / 9
    wing_feather("primary coverts", WRIST.x + t * (TIP.x - WRIST.x - 0.1), math.radians(60 - 35 * t), 0.2 - 0.08 * t, 0.11, 0.07, CONTOUR, curl=-0.15, back=-0.06)

for batch in wing_batches.values():
    batch.build()


# ---------------------------------------------------------------- rig

def wing_point(side, point):
    world = ws @ Vector(point)
    return Vector((world.x * side, world.y, world.z))


bpy.ops.object.armature_add(location=(0, 0, 0))
rig = bpy.context.object
rig.name = "Griffon | Rig"
rig.data.name = "Griffon rig"
bpy.ops.object.mode_set(mode="EDIT")
edit = rig.data.edit_bones
edit.remove(edit[0])


def bone(name, head, tail, parent=None):
    b = edit.new(name)
    b.head, b.tail = Vector(head), Vector(tail)
    b.roll = 0
    if parent:
        b.parent = edit[parent]
    return b


bone("body", (0, 0.6, 1.1), (0, -0.34, 1.16))
bone("neck", (0, -0.5, 1.25), (0, -0.76, 1.86), "body")
bone("head", (0, -0.78, 1.92), (0, -0.98, 2.06), "neck")
bone("jaw", (0, -0.93, 1.99), (0, -1.12, 1.96), "head")
bone("tail", (0, 0.84, 1.15), (0, 1.35, 1.17), "body")
for side, tag in SIDES:
    bone(f"wing.{tag}", wing_point(side, (0, 0, 0)), wing_point(side, WRIST), "body")
    bone(f"hand.{tag}", wing_point(side, WRIST), wing_point(side, TIP), f"wing.{tag}")
bpy.ops.object.mode_set(mode="OBJECT")

bpy.context.view_layer.update()
for obj, bone_name in parts:
    obj.parent = rig
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    bpy.context.view_layer.update()
    obj.matrix_world = Matrix.Identity(4)


# ---------------------------------------------------------------- animation

def about(pivot, axis, angle):
    pivot = Vector(pivot)
    return Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-pivot)


def key_pose(frame_number, deltas):
    """deltas maps bone name -> armature-space rest-frame delta matrix relative to its parent."""
    for name, delta in deltas.items():
        rest = rig.data.bones[name].matrix_local
        basis = rest.inverted() @ delta @ rest
        pose_bone = rig.pose.bones[name]
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.rotation_quaternion = basis.to_quaternion()
        pose_bone.location = basis.translation
        pose_bone.keyframe_insert("rotation_quaternion", frame=frame_number)
        pose_bone.keyframe_insert("location", frame=frame_number)


def clip(name, frames, pose):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    for f in range(0, frames + 1, 2):
        key_pose(f, pose(f / frames))
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, 0, action)
    rig.animation_data.action = None


def wings(shoulder_up, hand_up, hand_back):
    deltas = {}
    for side, tag in SIDES:
        root, wrist = wing_point(side, (0, 0, 0)), wing_point(side, WRIST)
        deltas[f"wing.{tag}"] = about(root, "Y", -side * shoulder_up)
        deltas[f"hand.{tag}"] = about(wrist, "Y", -side * hand_up) @ about(wrist, "Z", side * hand_back)
    return deltas


def wing_beat(t):
    phase = 2 * math.pi * t
    deltas = wings(-0.25 + 0.8 * math.cos(phase), 0.35 * math.cos(phase - 1.1), 0.22 * max(0.0, math.sin(phase)))
    deltas["body"] = Matrix.Translation((0, 0, 0.03 * math.sin(phase))) @ about((0, 0.6, 1.1), "X", 0.03 * math.cos(phase))
    deltas["neck"] = about((0, -0.5, 1.25), "X", -0.03 * math.cos(phase))
    deltas["head"] = about((0, -0.78, 1.92), "X", 0.05 * math.sin(phase))
    deltas["jaw"] = Matrix.Identity(4)
    deltas["tail"] = about((0, 0.84, 1.15), "X", 0.12 * math.sin(phase - 0.8))
    return deltas


def idle(t):
    phase = 2 * math.pi * t
    breath = math.sin(2 * phase)
    deltas = wings(0.04 * breath, 0.03 * breath, 0.0)
    deltas["body"] = about((0, 0.6, 1.1), "X", 0.012 * breath)
    deltas["neck"] = about((0, -0.5, 1.25), "Z", 0.12 * math.sin(phase))
    deltas["head"] = about((0, -0.78, 1.92), "Z", 0.28 * math.sin(phase)) @ about((0, -0.78, 1.92), "Y", 0.12 * math.sin(phase + 0.6))
    screech = max(0.0, math.sin(math.pi * (t - 0.4) / 0.25)) if 0.4 <= t <= 0.65 else 0.0
    deltas["jaw"] = about((0, -0.93, 1.99), "X", 0.32 * screech)
    deltas["tail"] = about((0, 0.84, 1.15), "Z", 0.3 * math.sin(phase)) @ about((0, 0.84, 1.15), "X", 0.08 * math.sin(2 * phase))
    return deltas


bpy.context.scene.render.fps = 24
clip("Wing beat", 24, wing_beat)
clip("Idle", 96, idle)
for pose_bone in rig.pose.bones:
    pose_bone.rotation_quaternion = (1, 0, 0, 0)
    pose_bone.location = (0, 0, 0)
