"""Preserve exact original bind frames across Blender exporter versions.

Blender 4.5 and 5.x choose slightly different feather-bone rolls. Preserve the
authored armature-space deformation D = posed * inverse(bind), then apply D to
the original model's bind frames. This is not a generic anatomy retargeter.
"""
import bisect, json, struct
from mathutils import Matrix, Vector, Quaternion

def read(path):
    b=path.read_bytes();n=struct.unpack_from('<I',b,12)[0]
    return json.loads(b[20:20+n]),b[28+n:]

def matrix(node):
    if 'matrix' in node:return Matrix([node['matrix'][i::4] for i in range(4)])
    q=node.get('rotation',[0,0,0,1])
    return Matrix.LocRotScale(Vector(node.get('translation',[0,0,0])),Quaternion((q[3],*q[:3])),Vector(node.get('scale',[1,1,1])))

def retarget(sidecar, original):
    doc,raw=read(sidecar);base,_=read(original);nodes=doc['nodes'];names={n.get('name'):n for n in base['nodes']}
    parents={c:i for i,n in enumerate(nodes) for c in n.get('children',[])}
    ordered=[]
    def order(i):
        if i in ordered:return
        if i in parents:order(parents[i])
        ordered.append(i)
    for i in range(len(nodes)):order(i)
    rest_new={};rest_old={}
    for i in ordered:
        parent=parents.get(i);rest_new[i]=rest_new.get(parent,Matrix.Identity(4))@matrix(nodes[i])
        rest_old[i]=rest_old.get(parent,Matrix.Identity(4))@matrix(names.get(nodes[i].get('name'),nodes[i]))
    def values(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];w={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']]
        offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',w*4)
        return [struct.unpack_from('<'+'f'*w,raw,offset+k*stride) for k in range(a['count'])]
    accessors=[];views=[];binary=bytearray()
    def store(rows,typ):
        while len(binary)%4:binary.append(0)
        offset=len(binary)
        for row in rows:binary.extend(struct.pack('<'+'f'*len(row),*row))
        vi=len(views);views.append(dict(buffer=0,byteOffset=offset,byteLength=len(binary)-offset))
        ai=len(accessors);a=dict(bufferView=vi,componentType=5126,count=len(rows),type=typ)
        if typ=='SCALAR':a['min']=[min(r[0] for r in rows)];a['max']=[max(r[0] for r in rows)]
        accessors.append(a);return ai
    for anim in doc['animations']:
        channels={};times=set()
        for c in anim['channels']:
            s=anim['samplers'][c['sampler']];ts=[r[0] for r in values(s['input'])];vs=values(s['output'])
            channels[(c['target']['node'],c['target']['path'])]=(ts,vs);times.update(ts)
        times=sorted(times);affected=sorted({key[0] for key in channels});result={(i,k):[] for i in affected for k in ('translation','rotation','scale')}
        def sample(i,k,t):
            if (i,k) not in channels:return nodes[i].get(k,{'translation':[0,0,0],'rotation':[0,0,0,1],'scale':[1,1,1]}[k])
            ts,vs=channels[(i,k)];j=max(0,bisect.bisect_right(ts,t)-1)
            if j==len(ts)-1:return vs[j]
            f=(t-ts[j])/(ts[j+1]-ts[j])
            if k=='rotation':
                a,b=vs[j],vs[j+1];q=Quaternion((a[3],*a[:3])).slerp(Quaternion((b[3],*b[:3])),f)
                return(q.x,q.y,q.z,q.w)
            return [a+(b-a)*f for a,b in zip(vs[j],vs[j+1])]
        previous={}
        for t in times:
            new={};target={}
            for i in ordered:
                parent=parents.get(i)
                local=matrix({k:sample(i,k,t) for k in ('translation','rotation','scale')})
                new[i]=new.get(parent,Matrix.Identity(4))@local
                target[i]=new[i]@rest_new[i].inverted()@rest_old[i]
                if i not in affected:continue
                local=target.get(parent,Matrix.Identity(4)).inverted()@target[i]
                loc,rot,scale=local.decompose()
                if i in previous and rot.dot(previous[i])<0:rot.negate()
                previous[i]=rot.copy()
                result[(i,'translation')].append(tuple(loc));result[(i,'rotation')].append((rot.x,rot.y,rot.z,rot.w));result[(i,'scale')].append(tuple(scale))
        time_index=store([(t,) for t in times],'SCALAR');anim['channels']=[];anim['samplers']=[]
        for (i,k),rows in result.items():
            output=store(rows,'VEC4' if k=='rotation' else 'VEC3');si=len(anim['samplers'])
            anim['samplers'].append(dict(input=time_index,output=output,interpolation='LINEAR'))
            anim['channels'].append(dict(sampler=si,target=dict(node=i,path=k)))
    for n in nodes:
        old=names.get(n.get('name'))
        if old:
            for key in ('translation','rotation','scale','matrix'):
                n.pop(key,None)
                if key in old:n[key]=old[key]
    doc['accessors']=accessors;doc['bufferViews']=views;doc['buffers']=[dict(byteLength=len(binary))]
    encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
    binary.extend(b'\0'*((-len(binary))%4))
    sidecar.write_bytes(struct.pack('<III',0x46546C67,2,28+len(encoded)+len(binary))+struct.pack('<II',len(encoded),0x4E4F534A)+encoded+struct.pack('<II',len(binary),0x004E4942)+binary)
