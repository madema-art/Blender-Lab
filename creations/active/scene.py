"""Six-sided expression cube for Blender Lab's active creation."""

import bpy
import math
from mathutils import Matrix, Vector


# The frame columns map face-local X, Y, and Z to world-space right, up, and out.
FRAMES = {
    "Happy": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "Sad": ((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
    "Angry": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
    "Surprised": ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
    "Fear": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "Disgust": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
}


def material(name, color, roughness=0.58):
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = (*color, 1.0)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    return mat


body_mat = material("Violet enamel", (0.22, 0.14, 0.48))
skin_mats = [
    material("Warm peach skin", (0.82, 0.43, 0.26)),
    material("Rose skin", (0.77, 0.35, 0.32)),
    material("Golden skin", (0.76, 0.48, 0.24)),
    material("Apricot skin", (0.87, 0.52, 0.34)),
    material("Soft tan skin", (0.68, 0.36, 0.25)),
    material("Pale peach skin", (0.88, 0.57, 0.43)),
]

ink = material("Expression ink", (0.12, 0.045, 0.055))
white = material("Warm eye white", (0.96, 0.91, 0.78))
pupil = material("Deep brown", (0.10, 0.055, 0.045), 0.3)
inner_mouth = material("Mouth interior", (0.22, 0.025, 0.055))
teeth = material("Ivory teeth", (1.0, 0.91, 0.72))
tongue = material("Coral tongue", (0.90, 0.18, 0.30))
nose_blush = material("Nose shading", (0.68, 0.27, 0.22))


# Main rounded cube body.
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
cube = bpy.context.object
cube.name = "Six Expressions | Cube"
cube.data.materials.append(body_mat)
bevel = cube.modifiers.new("Soft cartoon corners", "BEVEL")
bevel.width = 0.055
bevel.segments = 3
bevel.profile = 0.5


def frame_parts(frame):
    u, v, n = (Vector(axis) for axis in frame)
    rot = Matrix((u, v, n)).transposed().to_4x4().to_quaternion()
    return u, v, n, rot


def position(frame, x, y, depth):
    u, v, n, _ = frame_parts(frame)
    return n * (1.0 + depth) + u * x + v * y


def ellipsoid(name, frame, x, y, depth, scale, mat, segments=24, rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=position(frame, x, y, depth))
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = frame_parts(frame)[3]
    obj.scale = scale
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def polygon(name, frame, points, depth, mat):
    area = sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))
    ordered = points if area > 0 else list(reversed(points))
    verts = [position(frame, x, y, depth) for x, y in ordered]
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(verts, [], [tuple(range(len(verts)))])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def stroke(name, frame, points, depth, mat, radius=0.035):
    curve = bpy.data.curves.new(name + " curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, (x, y) in zip(spline.points, points):
        p = position(frame, x, y, depth)
        point.co = (p.x, p.y, p.z, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def create_mouth(face, frame, expression):
    if expression == "Happy":
        polygon(face + " open smile", frame, [(-.42, -.20), (-.28, -.13), (0, -.10), (.28, -.13), (.42, -.20), (.31, -.37), (0, -.48), (-.31, -.37)], .205, inner_mouth)
        polygon(face + " smile teeth", frame, [(-.30, -.205), (-.18, -.17), (.18, -.17), (.30, -.205), (.24, -.28), (-.24, -.28)], .213, teeth)
        ellipsoid(face + " tongue", frame, 0, -.385, .218, (.16, .055, .025), tongue, 20, 12)
    elif expression == "Sad":
        stroke(face + " trembling frown", frame, [(-.39, -.42), (-.25, -.31), (0, -.23), (.25, -.31), (.39, -.42)], .205, inner_mouth, .045)
        stroke(face + " lower lip", frame, [(-.22, -.40), (0, -.43), (.22, -.40)], .208, nose_blush, .018)
    elif expression == "Angry":
        polygon(face + " clenched mouth", frame, [(-.37, -.28), (-.22, -.23), (0, -.25), (.22, -.23), (.37, -.28), (.32, -.40), (0, -.36), (-.32, -.40)], .205, inner_mouth)
        polygon(face + " bared teeth", frame, [(-.27, -.275), (-.13, -.27), (0, -.29), (.13, -.27), (.27, -.275), (.23, -.33), (0, -.32), (-.23, -.33)], .213, teeth)
        stroke(face + " lower lip", frame, [(-.28, -.42), (0, -.44), (.28, -.42)], .208, nose_blush, .025)
    elif expression == "Surprised":
        ellipsoid(face + " round O mouth", frame, 0, -.35, .205, (.22, .31, .075), inner_mouth)
        ellipsoid(face + " surprised tongue", frame, 0, -.52, .278, (.12, .07, .025), tongue)
    elif expression == "Fear":
        ellipsoid(face + " terrified open mouth", frame, 0, -.35, .205, (.31, .36, .085), inner_mouth)
        polygon(face + " chattering upper teeth", frame, [(-.18, -.11), (.18, -.11), (.14, -.20), (-.14, -.20)], .29, teeth)
        ellipsoid(face + " trembling tongue", frame, .03, -.57, .29, (.16, .07, .025), tongue)
    else:  # Disgust
        stroke(face + " crooked grimace", frame, [(-.40, -.34), (-.27, -.27), (-.10, -.31), (.08, -.39), (.27, -.36), (.40, -.27)], .205, inner_mouth, .052)
        stroke(face + " curled upper lip", frame, [(-.37, -.25), (-.20, -.20), (-.02, -.24), (.10, -.30)], .21, nose_blush, .035)


def build_face(expression, frame, skin, style):
    # Soft oval face and ears float just above this side of the cube.
    ellipsoid(expression + " face", frame, 0, 0, .025, (.74, .82, .105), skin, 32, 20)
    ellipsoid(expression + " left ear", frame, -.68, -.015, .04, (.13, .19, .11), skin)
    ellipsoid(expression + " right ear", frame, .68, -.015, .04, (.13, .19, .11), skin)
    ellipsoid(expression + " left ear inset", frame, -.70, -.015, .13, (.052, .095, .035), nose_blush, 20, 12)
    ellipsoid(expression + " right ear inset", frame, .70, -.015, .13, (.052, .095, .035), nose_blush, 20, 12)

    eye_y = .20
    if style == "happy":
        # Upturned closed eyes, like a delighted squint.
        stroke(expression + " left smiling eye", frame, [(-.49, eye_y), (-.39, eye_y - .06), (-.28, eye_y - .055), (-.19, eye_y)], .16, ink, .035)
        stroke(expression + " right smiling eye", frame, [(.19, eye_y), (.28, eye_y - .055), (.39, eye_y - .06), (.49, eye_y)], .16, ink, .035)
        stroke(expression + " left brow", frame, [(-.49, .43), (-.34, .48), (-.18, .43)], .16, ink, .035)
        stroke(expression + " right brow", frame, [(.18, .43), (.34, .48), (.49, .43)], .16, ink, .035)
    elif style == "sad":
        for x in (-.31, .31):
            ellipsoid(expression + " eye", frame, x, eye_y, .15, (.17, .16, .08), white)
            ellipsoid(expression + " downcast pupil", frame, x, eye_y - .045, .225, (.072, .082, .035), pupil)
        stroke(expression + " worried left brow", frame, [(-.49, .46), (-.33, .52), (-.16, .39)], .16, ink, .045)
        stroke(expression + " worried right brow", frame, [(.16, .39), (.33, .52), (.49, .46)], .16, ink, .045)
    elif style == "angry":
        for x in (-.31, .31):
            ellipsoid(expression + " narrowed eye", frame, x, eye_y, .15, (.19, .115, .08), white)
            ellipsoid(expression + " glare pupil", frame, x, eye_y - .01, .225, (.065, .08, .035), pupil)
        stroke(expression + " left angry brow", frame, [(-.51, .47), (-.33, .38), (-.13, .30)], .17, ink, .065)
        stroke(expression + " right angry brow", frame, [(.13, .30), (.33, .38), (.51, .47)], .17, ink, .065)
    elif style == "surprised":
        for x in (-.31, .31):
            ellipsoid(expression + " wide eye", frame, x, eye_y, .15, (.205, .22, .09), white)
            ellipsoid(expression + " centered pupil", frame, x, eye_y, .24, (.08, .10, .04), pupil)
        stroke(expression + " high left brow", frame, [(-.50, .52), (-.34, .59), (-.18, .52)], .16, ink, .04)
        stroke(expression + " high right brow", frame, [(.18, .52), (.34, .59), (.50, .52)], .16, ink, .04)
    elif style == "fear":
        for x in (-.31, .31):
            ellipsoid(expression + " frightened eye", frame, x, eye_y, .15, (.22, .23, .09), white)
            ellipsoid(expression + " tiny fearful pupil", frame, x, eye_y - .035, .24, (.055, .07, .035), pupil)
        stroke(expression + " raised left brow", frame, [(-.52, .52), (-.34, .65), (-.16, .52)], .16, ink, .055)
        stroke(expression + " raised right brow", frame, [(.16, .52), (.34, .65), (.52, .52)], .16, ink, .055)
    else:  # disgust
        ellipsoid(expression + " squinting eye", frame, -.31, eye_y, .15, (.19, .11, .075), white)
        ellipsoid(expression + " squint pupil", frame, -.31, eye_y, .22, (.06, .07, .03), pupil)
        ellipsoid(expression + " unimpressed eye", frame, .31, eye_y + .015, .15, (.17, .14, .075), white)
        ellipsoid(expression + " unimpressed pupil", frame, .34, eye_y, .22, (.055, .075, .03), pupil)
        stroke(expression + " lifted brow", frame, [(-.49, .49), (-.33, .55), (-.17, .48)], .16, ink, .045)
        stroke(expression + " lowered brow", frame, [(.16, .36), (.33, .40), (.50, .46)], .16, ink, .045)
        stroke(expression + " nose wrinkle", frame, [(-.11, .06), (0, .10), (.10, .05)], .22, nose_blush, .025)

    # A rounded bridge and tip make every expression read as a human face.
    ellipsoid(expression + " nose bridge", frame, 0, .015, .155, (.105, .20, .10), skin, 20, 12)
    ellipsoid(expression + " nose tip", frame, 0, -.09, .22, (.16, .11, .11), nose_blush, 20, 12)
    ellipsoid(expression + " left nostril", frame, -.075, -.13, .295, (.035, .028, .018), ink, 16, 10)
    ellipsoid(expression + " right nostril", frame, .075, -.13, .295, (.035, .028, .018), ink, 16, 10)
    create_mouth(expression, frame, expression)


for index, (expression, frame) in enumerate(FRAMES.items()):
    build_face(expression, frame, skin_mats[index], expression.lower())
