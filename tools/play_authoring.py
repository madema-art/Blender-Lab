"""Rig-specific locomotion templates. Run inside Blender, after the original generator.

These templates support ONLY griffon-v2 and red-dragon. In-place stride distances
and stance durations are shared with the capability profiles; analytic IK plants
the contact feet, while the original wing and membrane solvers remain in use.
"""
import math
import bpy
from mathutils import Matrix, Vector

TEMPLATES = {
    'griffon-v2': dict(walk=(.55,.65,1.2), run=(.76,.46,.72), takeoff=1.8, flight=1., land=1.8, size=1.5),
    'red-dragon': dict(walk=(.75,.68,1.8), run=(1.3,.48,1.12), takeoff=2.8, flight=2., land=2.6, size=2.1),
}
SEMANTICS = dict(idle='Idle',walk='Walk',run='Run',turnLeft='Turn Left',turnRight='Turn Right',takeoff='Takeoff',flight='Flight',glide='Glide',bankLeft='Bank Left',bankRight='Bank Right',land='Land')

def profile(kind):
    t=TEMPLATES[kind]
    speed=lambda gait: t[gait][0]/(t[gait][1]*t[gait][2])
    return dict(version=1,category='quadruped',flight=True,jump=False,swimming=False,scale=1,forwardYaw=math.pi,
        animations={key:'Play '+name for key,name in SEMANTICS.items()},
        specials={'roar':'Roar'} if kind=='red-dragon' else {},
        motion=dict(walk=speed('walk'),run=speed('run'),fly=6 if kind=='griffon-v2' else 5,
                    acceleration=5 if kind=='griffon-v2' else 2.8,turnRate=2.8 if kind=='griffon-v2' else 1.8,
                    climb=2.2,descend=2,takeoffHeight=2.5 if kind=='griffon-v2' else 3),
        camera=dict(size=t['size'],height=1.25 if kind=='griffon-v2' else 1.8,distance=8 if kind=='griffon-v2' else 14),blend=.2 if kind=='griffon-v2' else .28)

def author(ns, kind):
    if kind not in TEMPLATES: raise ValueError('No compatible animation template for '+kind)
    rig=ns['rig']; bones=ns['BONES']; about=ns['about']; wing=ns['wings']; t=TEMPLATES[kind]
    dragon=kind=='red-dragon'
    rest={name:rig.data.bones[name].matrix_local.copy() for name in bones}
    legs=ns['LEGS'] if dragon else [(f'arm.{s}',f'tarsus.{s}',f'ffoot.{s}',None) for s in 'RL']+[(f'thigh.{s}',f'shin.{s}',f'hfoot.{s}',None) for s in 'RL']

    def solve(deltas, plant=None, ik=True):
        if dragon: return ns['fit_panels'](ns['solve'](deltas,ik,plant))
        poses={}
        for name in bones:
            parent=bones[name][2]; delta=deltas.get(name,Matrix.Identity(4))
            poses[name]=poses[parent]@rest[parent].inverted()@delta@rest[name] if parent else delta@rest[name]
        if not ik: return poses
        for upper,lower,end,child in legs:
            hip=poses[upper].translation; target=(plant or {}).get(end,rest[end].translation)
            a=(rest[lower].translation-rest[upper].translation).length; b=(rest[end].translation-rest[lower].translation).length
            n=target-hip; d=max(abs(a-b)+.001,min(a+b-.001,n.length)); n.normalize()
            axis=(rest[end].translation-rest[upper].translation).normalized()
            pole=rest[lower].translation-rest[upper].translation
            pole-=axis*pole.dot(axis)
            pole=(poses[bones[upper][2]]@rest[bones[upper][2]].inverted()).to_3x3()@pole
            pole=(pole-n*pole.dot(n)).normalized()
            distance=(a*a-b*b+d*d)/(2*d)
            knee=hip+n*distance+pole*math.sqrt(max(a*a-distance*distance,0))
            target=hip+n*d
            for name,start,finish in [(upper,hip,knee),(lower,knee,target)]:
                base=poses[name].to_3x3() if name==upper else (poses[upper]@rest[upper].inverted()@rest[lower]).to_3x3()
                turn=(base@Vector((0,1,0))).rotation_difference((finish-start).normalized()).to_matrix()
                poses[name]=Matrix.Translation(start)@(turn@base).to_4x4()
            poses[end]=Matrix.Translation(target)@rest[end].to_3x3().to_4x4()
        return poses

    def grounded(phase):
        if dragon:
            delta,_=ns['idle'](phase); return delta
        delta=ns['perched'](phase); return delta

    def gait(u, running=False, turning=0):
        stride,duty,period=t['run' if running else 'walk']; phase=u*math.tau
        delta=grounded(u)
        body='pelvis'; dz=((- .22 if running else -.13) if not dragon else -.05)+(.028 if running else .012)*math.cos(phase*2)
        delta[body]=Matrix.Translation((0,0,dz))@about(bones[body][0],'Y',.018*math.sin(phase))
        plant={}
        for upper,lower,end,_ in legs:
            fore=upper.startswith('arm.') or upper.startswith('upperarm.')
            side=end.endswith('.R')
            # Four-beat walk; diagonal pairs converge into a powerful trot at speed.
            offset=(0 if side else .5)+(0 if fore else (.5 if running else .25))
            q=(u+offset)%1
            if q<duty: y=-stride*.5+stride*q/duty; z=0
            else:
                swing=(q-duty)/(1-duty); smooth=swing*swing*(3-2*swing)
                y=stride*.5-stride*smooth; z=(.20 if running else .105)*(1.4 if dragon else 1)*math.sin(math.pi*swing)
            target=rest[end].translation.copy(); target.y+=y; target.z+=z
            target.x+=turning*.08*math.sin(phase+offset*math.tau)
            plant[end]=target
        tails=ns['tail'](phase,.04,.025) if dragon else ns['tail_wave'](phase,.06,.025)
        delta.update(tails)
        necks=ns['NECKS'] if dragon else ns['NECK']
        for n in necks: delta[n]=about(bones[n][0],'Z',turning*.07)
        return solve(delta,plant)

    def flying(u, glide=False, bank=0):
        phase=u*math.tau
        if dragon:
            delta,_=ns['flight'](u); delta.pop('root',None)
            if glide: delta.update(wing(fold=.04,flap=.1,tip_flap=.04*math.sin(phase),spread=.5))
        else:
            delta=ns['wing_beat'](u)
            if glide: delta.update(wing(fold=.02,flap=.08,hand_flap=.03*math.sin(phase)))
            for upper,lower,end,_ in legs:
                delta[upper]=about(bones[upper][0],'X',.65)
                delta[lower]=about(bones[lower][0],'X',-1.05)
                delta[end]=about(bones[end][0],'X',.6)
        # Actual asymmetric wing/neck/tail articulation complements world banking.
        if bank:
            root='wup' if dragon else 'up'
            for side,sign in [('R',1),('L',-1)]:
                n=f'{root}.{side}'; delta[n]=about(bones[n][0],'Y',bank*sign*.13)@delta[n]
            delta['head']=about(bones['head'][0],'Z',bank*.08)@delta.get('head',Matrix.Identity(4))
        return solve(delta,ik=False)

    def lerp_poses(a,b,t):
        out={}
        for n in a:
            x,q,s=a[n].decompose(); y,r,z=b[n].decompose()
            out[n]=Matrix.LocRotScale(x.lerp(y,t),q.slerp(r,t),s.lerp(z,t))
        # Refit the membrane after interpolation as well as on every source pose.
        return ns['fit_panels'](out) if dragon else out

    def takeoff(u):
        base=grounded(0)
        if u<.3:
            base['pelvis']=Matrix.Translation((0,0,-.14*math.sin(math.pi*u/.6)))
            return solve(base)
        smooth=(u-.3)/.7; smooth=smooth*smooth*(3-2*smooth)
        return lerp_poses(solve(grounded(0)),flying(0),smooth)

    def land(u):
        if u<.5:
            v=u*2; v=v*v*(3-2*v)
            return lerp_poses(flying(0,True),solve(grounded(0)),v)
        base=grounded(0); base['pelvis']=Matrix.Translation((0,0,-.12*math.sin((u-.5)*math.tau)))
        return solve(base)

    recipes=[('Idle',4,lambda u:solve(grounded(u)),True),
      ('Walk',t['walk'][2],lambda u:gait(u),True),('Run',t['run'][2],lambda u:gait(u,True),True),
      ('Turn Left',t['walk'][2],lambda u:gait(u,turning=1),True),('Turn Right',t['walk'][2],lambda u:gait(u,turning=-1),True),
      ('Takeoff',t['takeoff'],takeoff,False),('Flight',t['flight'],lambda u:flying(u),True),
      ('Glide',2.4,lambda u:flying(u,True),True),('Bank Left',t['flight'],lambda u:flying(u,bank=-1),True),
      ('Bank Right',t['flight'],lambda u:flying(u,bank=1),True),('Land',t['land'],land,False)]
    # Animation-only export includes only new tracks, plus the preserved Dragon Roar.
    for track in list(rig.animation_data.nla_tracks):
        rig.animation_data.nla_tracks.remove(track)
    rig.animation_data.action=None
    for label,seconds,pose,loop in recipes:
        name='Play '+label; action=bpy.data.actions.new(name); action.use_fake_user=True
        rig.animation_data.action=action; count=round(seconds*24); first=pose(0)
        for frame in range(count+1):
            poses=first if loop and frame==count else pose(frame/count)
            for n in bones:
                parent=bones[n][2]
                local=rest[parent].inverted()@rest[n] if parent else rest[n]
                relative=poses[parent].inverted()@poses[n] if parent else poses[n]
                loc,rot,scale=(local.inverted()@relative).decompose()
                pb=rig.pose.bones[n]; pb.rotation_mode='QUATERNION'
                # Choose quaternion hemisphere continuously to prevent 360-degree interpolation.
                if frame and pb.rotation_quaternion.dot(rot)<0: rot.negate()
                pb.location=loc; pb.rotation_quaternion=rot; pb.scale=scale
                for path in ['location','rotation_quaternion','scale']: pb.keyframe_insert(path,frame=frame)
        for slot in action.slots:
            for layer in action.layers:
                for strip in layer.strips:
                    bag=strip.channelbag(slot)
                    if bag:
                        for curve in bag.fcurves:
                            for point in curve.keyframe_points: point.interpolation='LINEAR'
        track=rig.animation_data.nla_tracks.new(); track.name=name; track.strips.new(name,0,action)
        rig.animation_data.action=None
        print('[Play authoring]',kind,name,count+1,'keyed frames',flush=True)
    for pb in rig.pose.bones:
        pb.location=(0,0,0); pb.rotation_quaternion=(1,0,0,0); pb.scale=(1,1,1)
    return profile(kind)
