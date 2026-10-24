"""Build repeatable animation-only GLBs, retaining every original creation byte.

Blender Python: python tools/build_play_animations.py [griffon-v2|red-dragon]
Requires bpy 4.5+ and the original generation sources. Sidecar tracks bind by the
same node names and rest matrices as their original self-contained model GLBs.
"""
import sys, os, json, runpy, argparse
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.play_authoring import author

def build(kind):
    os.chdir(ROOT); bpy.ops.wm.read_factory_settings(use_empty=True)
    ns=runpy.run_path(str(ROOT/'creations'/kind/'scene.py'),run_name='__main__')
    profile=author(ns,kind)
    # glTF does not emit skin joints for an armature without a selected mesh.
    # Export the already-generated rig with geometry then strip the mesh payload
    # from the sidecar, keeping node names, animation samplers and bind transforms.
    final_path=ROOT/'public/models'/f'{kind}-play-animations.glb'
    path=final_path.with_name('.active-creation-'+final_path.name)
    bpy.ops.object.select_all(action='DESELECT')
    rig=ns['rig']; rig.select_set(True); bpy.context.view_layer.objects.active=rig
    for obj in bpy.context.scene.objects:
        if obj.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in obj.modifiers): obj.select_set(True)
    result=bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,
        export_animations=True,export_animation_mode='NLA_TRACKS',export_cameras=False,export_lights=False,
        export_materials='NONE',export_force_sampling=True)
    if 'FINISHED' not in result: raise RuntimeError('Animation export failed')
    strip_geometry(path)
    from tools.play_retarget import retarget
    retarget(path,ROOT/'public/models'/f'{kind}.glb')
    from tools.play_validation import validate
    import struct
    raw=path.read_bytes(); length=struct.unpack_from('<I',raw,12)[0]
    document=json.loads(raw[20:20+length])
    # Roar is preserved in the original Dragon GLB, not duplicated in the sidecar.
    p={**profile,'specials':{}}
    validate(document,p,raw[28+length:])
    os.replace(path,final_path)
    path=final_path
    entries=json.loads((ROOT/'public/models/manifest.json').read_text(encoding='utf-8'))
    is_active=(ROOT/'public/models/active-creation.glb').read_bytes()==(ROOT/'public/models'/f'{kind}.glb').read_bytes()
    for entry in entries:
        if entry['file']==f'{kind}.glb' or (is_active and entry['file']=='active-creation.glb'):
            entry['playProfile']=profile
            sources=[s for s in entry.get('animationSources',[]) if s['file']!=path.name]
            entry['animationSources']=sources+[{'file':path.name}]
    (ROOT/'public/models/manifest.json').write_text(json.dumps(entries,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def strip_geometry(path):
    import struct
    raw=path.read_bytes(); n=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+n]); binary=raw[28+n:]
    # Compact the buffer to animation accessors alone. No duplicated textures/meshes.
    indices={s[k] for a in doc.get('animations',[]) for s in a['samplers'] for k in ('input','output')}
    remap={old:i for i,old in enumerate(sorted(indices))}; access=[]; views=[]; data=bytearray()
    for old in sorted(indices):
        acc=doc['accessors'][old].copy(); view=doc['bufferViews'][acc['bufferView']]
        start=view.get('byteOffset',0); payload=binary[start:start+view['byteLength']]
        while len(data)%4:data.append(0)
        new_view={'buffer':0,'byteOffset':len(data),'byteLength':len(payload)}
        if 'byteStride' in view:new_view['byteStride']=view['byteStride']
        acc['bufferView']=len(views); views.append(new_view); access.append(acc); data.extend(payload)
    for anim in doc.get('animations',[]):
        for sampler in anim['samplers']:
            for key in ['input','output']:sampler[key]=remap[sampler[key]]
    for node in doc.get('nodes',[]):
        node.pop('mesh',None); node.pop('skin',None)
    for key in ['meshes','skins','materials','images','textures','samplers','extensionsUsed','extensionsRequired']:doc.pop(key,None)
    doc['accessors']=access; doc['bufferViews']=views; doc['buffers']=[{'byteLength':len(data)}]
    encoded=json.dumps(doc,separators=(',',':')).encode(); encoded+=b' '*((-len(encoded))%4); data.extend(b'\0'*((-len(data))%4))
    path.write_bytes(struct.pack('<III',0x46546C67,2,28+len(encoded)+len(data))+struct.pack('<II',len(encoded),0x4E4F534A)+encoded+struct.pack('<II',len(data),0x004E4942)+data)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rigs',nargs='*',metavar='RIG',help='Compatible templates: griffon-v2, red-dragon (default: both)')
    args=parser.parse_args()
    if any(kind not in ('griffon-v2','red-dragon') for kind in args.rigs):
        parser.error('No compatible authoring template. Supported rigs: griffon-v2, red-dragon')
    for kind in args.rigs or ['griffon-v2','red-dragon']:build(kind)
