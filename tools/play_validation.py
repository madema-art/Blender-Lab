"""Export-time semantic readiness validation. No Blender dependency.

Legacy creations with no controllable-creature declaration remain viewer assets.
Declared controllable creatures fail before publication if their contract is false.
"""
import json,struct,math

REQUIRED = {
    'quadruped':['idle','walk','run','turnLeft','turnRight'],
    'biped':['idle','walk','run','turnLeft','turnRight'],
    'aquatic':['idle','swim','turnLeft','turnRight','ascend','descend'],
    'slither':['idle','slither','turnLeft','turnRight'],
}

def validate(document, profile, binary=None):
    if not isinstance(profile,dict) or profile.get('version')!=1 or profile.get('category') not in REQUIRED:
        raise ValueError('Controllable creature requires a version 1 capability profile with a supported anatomy')
    gait={'aquatic':'swim','slither':'slither'}.get(profile['category'],'walk')
    for key in (gait,'run' if gait=='walk' else 'sprint','acceleration','turnRate'):
        value=profile.get('motion',{}).get(key)
        if not isinstance(value,(float,int)) or not math.isfinite(value) or value<=0:raise ValueError('Invalid Play Mode motion setting: '+key)
    for key in ('size','height','distance'):
        value=profile.get('camera',{}).get(key)
        if not isinstance(value,(float,int)) or not math.isfinite(value) or (key!='height' and value<=0):raise ValueError('Invalid Play Mode camera setting: '+key)
    if profile.get('flight') and not profile.get('motion',{}).get('fly',0)>0:raise ValueError('Missing flight speed')
    required=list(REQUIRED[profile['category']])
    if profile.get('flight'):required+=['takeoff','flight','glide','bankLeft','bankRight','land']
    if profile.get('jump'):required+=['jump']
    required+=list(profile.get('specials',{}))
    names={a.get('name'):a for a in document.get('animations',[])}
    mappings={**profile.get('animations',{}),**profile.get('specials',{})}
    failures=[]
    for semantic in required:
        name=mappings.get(semantic); anim=names.get(name)
        if not anim or not anim.get('channels') or not anim.get('samplers'):
            failures.append(f'{semantic}: missing keyed clip {name!r}');continue
        if not any(document['accessors'][s['input']]['count']>1 for s in anim['samplers']):
            failures.append(f'{semantic}: clip has no motion samples')
        if binary is not None:
            changes=False
            for sampler in anim['samplers']:
                a=document['accessors'][sampler['output']];v=document['bufferViews'][a['bufferView']]
                width={'SCALAR':1,'VEC3':3,'VEC4':4}.get(a['type'],1)
                offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',width*4)
                first=struct.unpack_from('<'+'f'*width,binary,offset)
                for i in range(1,a['count']):
                    row=struct.unpack_from('<'+'f'*width,binary,offset+i*stride)
                    if any(abs(x-y)>1e-5 for x,y in zip(first,row)):changes=True;break
                if changes:break
            if not changes:failures.append(f'{semantic}: samples are all constant; author actual motion')
        for channel in anim['channels']:
            node=channel.get('target',{}).get('node')
            if node is None or node>=len(document.get('nodes',[])):failures.append(f'{semantic}: invalid target bone')
    if failures:raise ValueError('Play Mode readiness failed: '+'; '.join(failures))
    return True

def declared_profile(scene):
    profile=scene.get('lab_play_profile')
    if isinstance(profile,str):profile=json.loads(profile)
    if scene.get('lab_controllable') and not profile:
        raise ValueError('Controllable creature has no lab_play_profile; author a compatible rig-specific template first')
    return profile
