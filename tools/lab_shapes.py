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
"""

from __future__ import annotations

from dataclasses import dataclass
import math

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
    """Collects many small pieces (feathers, scales, claws) into one mesh."""

    def __init__(self, name, mat):
        self.name, self.mat = name, mat
        self.verts, self.faces, self.uvs = [], [], []
        self.count = 0

    def add(self, piece):
        base = len(self.verts)
        self.verts.extend(piece.verts)
        self.faces.extend(tuple(i + base for i in face) for face in piece.faces)
        self.uvs.extend(piece.uvs or [tuple((0.0, 0.0) for _ in face) for face in piece.faces])
        self.count += 1

    def variant(self, choices=4):
        """A repeatable pseudo-random pick for the next piece, so neighbours differ."""
        return (self.count * 2654435761 >> 7) % choices

    def build(self):
        if self.faces:
            return make_object(self.name, self.mat, Piece(self.verts, self.faces, self.uvs))


def _ring_uv(k, ring):
    return k / ring


def loft(points, ring=12):
    """Tube through (position, radius_side, radius_up) points, using parallel-transported frames.
    A zero radius at either end closes it into a point."""
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
            angle = 2 * math.pi * k / ring
            verts.append(centre + side * (math.cos(angle) * rs) + normal * (math.sin(angle) * ru))
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
FEATHER_VARIANTS = 4  # rows in the feather card atlas; see lab_materials feather recipe


def feather(matrix, length, width, profile=FLIGHT, curl=0.0, ridge=0.012, variant=0):
    """A cambered feather card with a raised rachis, lying along local +X with its top facing +Z.
    Its UVs fill one variant row of the shared feather atlas."""
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
        half = w * width * 0.5
        if i == rows - 1:
            verts.append(matrix @ Vector((x, 0, z)))
            uv_of.append(uv(t, 0.5))
            continue
        droop = -0.25 * half
        verts += [matrix @ Vector((x, -half, z + droop)),
                  matrix @ Vector((x, 0, z + ridge * (1 - t))),
                  matrix @ Vector((x, half, z + droop))]
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
