"""Mesh builders for Blender Lab creations, with UVs authored where the shape defines them.

Import from a creation source as `from tools import lab_shapes as shapes`. Every builder returns a
`Piece` (vertices, faces, per-face-corner UVs). Pieces are built in world space; `Batch` merges
many of them into one object, and `make_object` turns a piece into a mesh object with a "UVMap"
layer. UV conventions:

- `feather` maps u along the shaft (0 base, 1 tip) and v across the vane (0.5 is the rachis),
  inside one of four variant rows of a card atlas. Feather materials share that atlas.
- `ellipsoid` maps u around the local Z axis and v from the -Z pole (0) to the +Z pole (1). Rotate
  it so +Z points where a texture's pole belongs, for example an eye's gaze.
- `loft` maps u around the tube and v along its length.

Objects whose material is an atlas recipe are re-unwrapped by `lab_materials.finalize`, so their
authored UVs only matter for card and eye recipes.

For skinned creatures, `Batch.add` takes per-piece bone weights (see `envelope_weights`) and an
optional linear-RGB tint, stored as the "Tint" colour attribute that card materials use in place
of their material colour. `displace` sculpts organic forms with soft stamps, `scatter` places
pieces irregularly over a surface, and `eyelid` builds closed lid shells.
"""

from __future__ import annotations

from dataclasses import dataclass
import bisect
import math
import random

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


@dataclass
class Piece:
    verts: list
    faces: list
    uvs: list | None = None  # one tuple of (u, v) per face corner, matching `faces`

    def transformed(self, matrix):
        return Piece([matrix @ Vector(v) for v in self.verts], self.faces, self.uvs)

    def mirrored(self):
        """Mirror across X, keeping faces outward by reversing their winding."""
        uvs = [tuple(reversed(face)) for face in self.uvs] if self.uvs else None
        return Piece([Vector((-v.x, v.y, v.z)) for v in self.verts], [tuple(reversed(f)) for f in self.faces], uvs)


def make_object(name, mat, piece, smooth=True, collection=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in piece.verts], [], [tuple(f) for f in piece.faces])
    if piece.uvs:
        layer = mesh.uv_layers.new(name="UVMap")
        flat = [uv for face in piece.uvs for uv in face]
        layer.data.foreach_set("uv", [c for uv in flat for c in uv])
    mesh.validate()
    mesh.polygons.foreach_set("use_smooth", [smooth] * len(mesh.polygons))
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.collection).objects.link(obj)
    return obj


class Batch:
    """Collects many small pieces (feathers, scales, claws) into one mesh, optionally with a tint
    and bone weights per piece."""

    def __init__(self, name, mat):
        self.name, self.mat = name, mat
        self.verts, self.faces, self.uvs = [], [], []
        self.tints, self.weights = [], []
        self.count = 0

    def add(self, piece, tint=None, weights=None):
        """`weights` is {bone: weight} for the whole piece, or a list with one dict per vertex."""
        base = len(self.verts)
        self.verts.extend(piece.verts)
        self.faces.extend(tuple(i + base for i in face) for face in piece.faces)
        self.uvs.extend(piece.uvs or [tuple((0.0, 0.0) for _ in face) for face in piece.faces])
        self.tints.extend([tint] * len(piece.verts))
        self.weights.extend(weights if isinstance(weights, list) else [weights] * len(piece.verts))
        self.count += 1

    def variant(self, choices=4):
        """A repeatable pseudo-random pick for the next piece, so neighbours differ."""
        return (self.count * 2654435761 >> 7) % choices

    def build(self):
        if not self.faces:
            return None
        obj = make_object(self.name, self.mat, Piece(self.verts, self.faces, self.uvs))
        if any(t is not None for t in self.tints):
            fallback = tuple(self.mat.diffuse_color[:3])
            layer = obj.data.color_attributes.new("Tint", "FLOAT_COLOR", "POINT")
            for item, tint in zip(layer.data, self.tints):
                item.color = (*(tint if tint is not None else fallback), 1.0)
        if any(w for w in self.weights):
            assign_weights(obj, self.weights)
        return obj


def _ring_uv(k, ring):
    return k / ring


def circle(angle):
    return math.cos(angle), math.sin(angle)


def loft(points, ring=12, profile=circle):
    """Tube through (position, radius_side, radius_up) points, using parallel-transported frames.
    A zero radius at either end closes it into a point. `profile(angle)` returns the unit
    cross-section point (side, up); the default is a circle."""
    centres = [Vector(p[0]) for p in points]
    tangents = []
    for i in range(len(centres)):
        a = centres[max(i - 1, 0)]
        b = centres[min(i + 1, len(centres) - 1)]
        tangents.append((b - a).normalized())
    lengths = [0.0]
    for a, b in zip(centres, centres[1:]):
        lengths.append(lengths[-1] + (b - a).length)
    total = lengths[-1] or 1.0
    up = Vector((0, 0, 1)) if abs(tangents[0].z) < 0.9 else Vector((0, 1, 0))
    normal = (up - tangents[0] * up.dot(tangents[0])).normalized()
    verts, rings = [], []
    for i, (centre, tangent) in enumerate(zip(centres, tangents)):
        normal = (normal - tangent * normal.dot(tangent)).normalized()
        side = tangent.cross(normal).normalized()
        rs, ru = points[i][1], points[i][2]
        if rs == 0 and ru == 0:
            rings.append([len(verts)])
            verts.append(centre.copy())
            continue
        start = len(verts)
        for k in range(ring):
            cs, sn = profile(2 * math.pi * k / ring)
            verts.append(centre + side * (cs * rs) + normal * (sn * ru))
        rings.append(list(range(start, start + ring)))
    faces, uvs = [], []
    for i, (a, b) in enumerate(zip(rings, rings[1:])):
        va, vb = lengths[i] / total, lengths[i + 1] / total
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(ring):
            u0, u1 = _ring_uv(k, ring), _ring_uv(k + 1, ring)
            if len(a) == 1:
                faces.append((a[0], b[(k + 1) % ring], b[k]))
                uvs.append((((u0 + u1) / 2, va), (u1, vb), (u0, vb)))
            elif len(b) == 1:
                faces.append((a[k], a[(k + 1) % ring], b[0]))
                uvs.append(((u0, va), (u1, va), ((u0 + u1) / 2, vb)))
            else:
                faces.append((a[k], a[(k + 1) % ring], b[(k + 1) % ring], b[k]))
                uvs.append(((u0, va), (u1, va), (u1, vb), (u0, vb)))
    for cap, v in ((rings[0], 0.0), (rings[-1], 1.0)):
        if len(cap) > 1:
            ordered = tuple(reversed(cap)) if v == 0.0 else tuple(cap)
            faces.append(ordered)
            uvs.append(tuple((0.5 + 0.5 * math.cos(2 * math.pi * cap.index(i) / ring) * 0.1, v) for i in ordered))
    return Piece(verts, faces, uvs)


def ellipsoid(centre, radii, rotation=Matrix.Identity(3), segments=20, rings=12):
    centre = Vector(centre)
    verts = [centre + rotation @ Vector((0, 0, -radii[2]))]
    for r in range(1, rings):
        phi = math.pi * r / rings - math.pi / 2
        for s in range(segments):
            theta = 2 * math.pi * s / segments
            local = Vector((math.cos(phi) * math.cos(theta) * radii[0],
                            math.cos(phi) * math.sin(theta) * radii[1],
                            math.sin(phi) * radii[2]))
            verts.append(centre + rotation @ local)
    verts.append(centre + rotation @ Vector((0, 0, radii[2])))
    faces, uvs = [], []
    for s in range(segments):
        u0, u1 = s / segments, (s + 1) / segments
        faces.append((0, 1 + (s + 1) % segments, 1 + s))
        uvs.append((((u0 + u1) / 2, 0.0), (u1, 1 / rings), (u0, 1 / rings)))
    for r in range(rings - 2):
        a, b = 1 + r * segments, 1 + (r + 1) * segments
        v0, v1 = (r + 1) / rings, (r + 2) / rings
        for s in range(segments):
            u0, u1 = s / segments, (s + 1) / segments
            faces.append((a + s, a + (s + 1) % segments, b + (s + 1) % segments, b + s))
            uvs.append(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
    top, last = len(verts) - 1, 1 + (rings - 2) * segments
    for s in range(segments):
        u0, u1 = s / segments, (s + 1) / segments
        faces.append((last + s, last + (s + 1) % segments, top))
        uvs.append(((u0, (rings - 1) / rings), (u1, (rings - 1) / rings), ((u0 + u1) / 2, 1.0)))
    return Piece(verts, faces, uvs)


FLIGHT = (0.22, 0.8, 1.0, 1.0, 1.0, 0.97, 0.88, 0.66, 0.0)
PRIMARY = (0.2, 0.75, 0.95, 1.0, 0.95, 0.88, 0.75, 0.5, 0.0)
CONTOUR = (0.3, 0.85, 1.0, 1.0, 0.9, 0.7, 0.4, 0.0)
SECONDARY = (0.22, 0.82, 1.0, 1.0, 1.0, 1.0, 0.98, 0.9, 0.62, 0.0)        # broad, blunt tip
EMARGINATED = (0.2, 0.78, 1.0, 1.0, 0.92, 0.62, 0.5, 0.44, 0.34, 0.0)     # notched "finger" primary
SMALL = (0.35, 0.95, 0.8, 0.0)                                             # small contour, few rows
HACKLE = (0.3, 0.75, 0.8, 0.65, 0.42, 0.2, 0.0)                            # lanceolate nape feather
WISP = (0.25, 0.55, 0.5, 0.35, 0.0)                                        # narrow tapering tuft
FEATHER_VARIANTS = 4  # rows in the feather card atlas; see lab_materials feather recipe


def feather(matrix, length, width, profile=FLIGHT, curl=0.0, ridge=0.012, variant=0, sweep=0.0, twist=0.0):
    """A cambered feather card with a raised rachis, lying along local +X with its top facing +Z.
    `curl` bends the shaft up (+) or down (-), `sweep` bends it sideways, `twist` rotates the vane
    about the shaft towards the tip. Its UVs fill one variant row of the shared feather atlas."""
    verts, uv_of = [], []
    rows = len(profile)
    v_base, v_span = (variant % FEATHER_VARIANTS) / FEATHER_VARIANTS, 1 / FEATHER_VARIANTS
    inset = 0.04 * v_span

    def uv(t, across):
        return (0.01 + 0.98 * t, v_base + inset + (v_span - 2 * inset) * across)

    for i, w in enumerate(profile):
        t = i / (rows - 1)
        x = t * length
        z = curl * t * t * length
        y = sweep * t * t * length
        half = w * width * 0.5
        if i == rows - 1:
            verts.append(matrix @ Vector((x, y, z)))
            uv_of.append(uv(t, 0.5))
            continue
        droop = -0.25 * half
        ca, sa = math.cos(twist * t), math.sin(twist * t)
        verts += [matrix @ Vector((x, y - half * ca, z + droop - half * sa)),
                  matrix @ Vector((x, y, z + ridge * (1 - t))),
                  matrix @ Vector((x, y + half * ca, z + droop + half * sa))]
        # The vane texture is drawn at full width; narrow rows show its central part.
        uv_of += [uv(t, 0.5 - 0.5 * w), uv(t, 0.5), uv(t, 0.5 + 0.5 * w)]
    faces = []
    for i in range(rows - 2):
        a, b = 3 * i, 3 * (i + 1)
        faces += [(a, a + 1, b + 1, b), (a + 1, a + 2, b + 2, b + 1)]
    tip, a = len(verts) - 1, 3 * (rows - 2)
    faces += [(a, a + 1, tip), (a + 1, a + 2, tip)]
    return Piece(verts, faces, [tuple(uv_of[i] for i in face) for face in faces])


def frame(position, direction, up):
    """Matrix placing local +X along direction and +Z towards up."""
    x = Vector(direction).normalized()
    z = (Vector(up) - x * Vector(up).dot(x)).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(position)
    return m


def skin_body(name, mat, nodes, edges, levels=2):
    """Organic trunk from a skin-modifier skeleton: nodes are (position, radius_side, radius_up).
    The modifiers are applied, so the result is plain, game-ready geometry."""
    mesh = bpy.data.meshes.new(name + " skeleton")
    mesh.from_pydata([n[0] for n in nodes], edges, [])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.modifiers.new("Skin", "SKIN")
    for i, node in enumerate(nodes):
        mesh.skin_vertices[0].data[i].radius = (node[1], node[2])
    mesh.skin_vertices[0].data[0].use_root = True
    subsurf = obj.modifiers.new("Smooth", "SUBSURF")
    subsurf.levels = subsurf.render_levels = levels
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    obj.modifiers.clear()
    obj.data = baked
    baked.name = name
    baked.polygons.foreach_set("use_smooth", [True] * len(baked.polygons))
    baked.materials.append(mat)
    bpy.data.meshes.remove(mesh)
    return obj


def bvh_of(*objects):
    verts, faces = [], []
    for obj in objects:
        base = len(verts)
        verts += [obj.matrix_world @ v.co for v in obj.data.vertices]
        faces += [[i + base for i in p.vertices] for p in obj.data.polygons]
    return BVHTree.FromPolygons(verts, faces)


# ---------------------------------------------------------------- skinning

def envelope_weights(point, bones, power=4.0, influences=3):
    """Weights for `point` from bone segments [(name, head, tail)], falling off with distance."""
    point = Vector(point)
    scored = []
    for name, head, tail in bones:
        head, tail = Vector(head), Vector(tail)
        axis = tail - head
        t = max(0.0, min(1.0, (point - head).dot(axis) / max(axis.length_squared, 1e-9)))
        distance = (point - (head + axis * t)).length
        scored.append((1.0 / (distance + 0.03) ** power, name))
    scored.sort(reverse=True)
    top = scored[:influences]
    total = sum(w for w, _ in top)
    return {name: w / total for w, name in top if w / total > 0.02}


def assign_weights(obj, weights):
    """Create vertex groups from one {bone: weight} dict (or None) per vertex."""
    groups = {}
    for index, entry in enumerate(weights):
        for bone, weight in (entry or {}).items():
            if bone not in groups:
                groups[bone] = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
            groups[bone].add([index], weight, "REPLACE")


def skin_to(obj, armature):
    """Parent obj to an armature and deform it with its vertex groups."""
    obj.parent = armature
    obj.matrix_parent_inverse = armature.matrix_world.inverted()
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    return obj


# ---------------------------------------------------------------- sculpting and scattering

def _segment_distance(point, start, end):
    axis = end - start
    t = max(0.0, min(1.0, (point - start).dot(axis) / max(axis.length_squared, 1e-12)))
    return (point - (start + axis * t)).length


def displace(obj, stamps, snap=False):
    """Sculpt a mesh with soft strokes along vertex normals, falling off as exp(-(d / radius)^2):
    (centre, radius, amount) is a round stamp; (start, end, radius, amount) is a ridge or groove
    along a segment. Negative amounts carve hollows. With snap=True, stroke points are first moved
    to the nearest point of the surface, so they can be placed approximately."""
    mesh = obj.data
    mesh.update()
    normals = [Vector(n.vector) for n in mesh.vertex_normals]
    tree = BVHTree.FromPolygons([v.co for v in mesh.vertices], [p.vertices for p in mesh.polygons]) if snap else None

    def place(point):
        point = Vector(point)
        return tree.find_nearest(point)[0] if tree else point

    strokes = []
    for stamp in stamps:
        if len(stamp) == 3:
            centre = place(stamp[0])
            strokes.append((centre, centre, stamp[1], stamp[2]))
        else:
            strokes.append((place(stamp[0]), place(stamp[1]), stamp[2], stamp[3]))
    for vertex, normal in zip(mesh.vertices, normals):
        offset = 0.0
        for start, end, radius, amount in strokes:
            d2 = (_segment_distance(vertex.co, start, end) / radius) ** 2
            if d2 < 9.0:
                offset += amount * math.exp(-d2)
        if offset:
            vertex.co += normal * offset
    mesh.update()


def reshape(obj, function):
    """Move every vertex through function(co) -> new co, for broad proportional shaping."""
    for vertex in obj.data.vertices:
        vertex.co = function(vertex.co.copy())
    obj.data.update()


def scatter(objects, spacing, seed=1, candidates=20000, accept=None):
    """Irregular, non-overlapping points over the surfaces of `objects`. `spacing(location)` gives
    the minimum distance to neighbours there, or None to leave that spot bare; `accept(location)`
    may veto a candidate. Returns [(location, normal)] in the order they were accepted."""
    rng = random.Random(seed)
    triangles, cumulative, running = [], [], 0.0
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        world = obj.matrix_world
        for tri in mesh.loop_triangles:
            a, b, c = (world @ mesh.vertices[i].co for i in tri.vertices)
            area = (b - a).cross(c - a).length / 2
            if area > 0:
                running += area
                triangles.append((a, b, c))
                cumulative.append(running)
    cell = 0.1
    grid, points = {}, []
    for _ in range(candidates):
        a, b, c = triangles[min(bisect.bisect(cumulative, rng.random() * running), len(triangles) - 1)]
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        location = a + (b - a) * u + (c - a) * v
        gap = spacing(location)
        if gap is None or (accept and not accept(location)):
            continue
        key = tuple(int(math.floor(x / cell)) for x in location)
        reach = int(math.ceil(gap / cell))
        crowded = any((other - location).length < gap
                      for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1) for dz in range(-reach, reach + 1)
                      for other in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()))
        if crowded:
            continue
        grid.setdefault(key, []).append(location)
        points.append((location, (b - a).cross(c - a).normalized()))
    return points


# ---------------------------------------------------------------- eyelids

def eyelid(centre, radius, axis, angle, thickness=0.006, segments=20, rings=6):
    """A closed spherical lid shell around an eye: the cap about `axis` out to `angle` radians,
    `thickness` deep, with a rounded rim at its edge."""
    centre, axis = Vector(centre), Vector(axis).normalized()
    side = axis.orthogonal().normalized()
    other = axis.cross(side)
    outer_r, inner_r = radius + thickness, radius + 0.0015

    def point(polar, azimuth, r):
        direction = axis * math.cos(polar) + (side * math.cos(azimuth) + other * math.sin(azimuth)) * math.sin(polar)
        return centre + direction * r

    verts = [centre + axis * outer_r]
    for i in range(1, rings + 1):
        polar = angle * i / rings
        verts += [point(polar, 2 * math.pi * k / segments, outer_r) for k in range(segments)]
    rim = angle + thickness / radius * 0.6
    verts += [point(rim, 2 * math.pi * k / segments, (outer_r + inner_r) / 2) for k in range(segments)]
    for i in range(rings, 0, -1):
        polar = angle * i / rings
        verts += [point(polar, 2 * math.pi * k / segments, inner_r) for k in range(segments)]
    verts.append(centre + axis * inner_r)
    faces = [(0, 1 + k, 1 + (k + 1) % segments) for k in range(segments)]
    bands = 2 * rings + 1
    for band in range(bands - 1):
        a, b = 1 + band * segments, 1 + (band + 1) * segments
        faces += [(a + k, b + k, b + (k + 1) % segments, a + (k + 1) % segments) for k in range(segments)]
    last, top = 1 + (bands - 1) * segments, len(verts) - 1
    faces += [(last + k, top, last + (k + 1) % segments) for k in range(segments)]
    return Piece(verts, faces, None)
