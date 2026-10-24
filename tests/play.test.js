import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { CreatureController, LocomotionAnimator } from '../src/play/controller.js';
import { analog, readPad } from '../src/play/input.js';
import { readiness } from '../src/play/profiles.js';

const manifest=JSON.parse(readFileSync(new URL('../public/models/manifest.json',import.meta.url)));
const profile=manifest.find(e=>e.file==='red-dragon.glb').playProfile;
const input={x:0,y:0,sprint:false,vertical:0};
const documentOf=file=>{const b=readFileSync(new URL(`../public/models/${file}`,import.meta.url));return JSON.parse(b.toString('utf8',20,20+b.readUInt32LE(12)));};

test('controller accelerates, turns, takes off, climbs, glides, lands and returns to idle',()=>{
  const c=new CreatureController(profile), dur={takeoff:2.8,land:2.6};
  for(let n=0;n<90;n++)c.update(1/60,{...input,y:1},0,dur);
  assert.equal(c.state,'walk'); assert.ok(c.position.z<-.5);
  const slow=c.speed;
  for(let n=0;n<90;n++)c.update(1/60,{...input,y:1,sprint:true},0,dur);
  assert.equal(c.state,'run'); assert.ok(c.speed>slow*2);
  c.update(1/60,{...input,jump:true},0,dur);assert.equal(c.state,'takeoff');
  for(let n=0;n<190;n++)c.update(1/60,input,0,dur);
  assert.equal(c.state,'flight'); assert.ok(c.position.y>2);
  let peakBank=0;
  for(let n=0;n<60;n++){c.update(1/60,{...input,x:1,y:1,vertical:1},0,dur);peakBank=Math.max(peakBank,Math.abs(c.bank));}
  assert.ok(c.position.y>3);assert.ok(Math.abs(c.yaw)>.2);assert.ok(peakBank>.01);
  c.update(1/60,{...input,glide:true},0,dur);assert.equal(c.state,'glide');
  c.update(1/60,{...input,land:true},0,dur);assert.equal(c.state,'land');
  for(let n=0;n<600;n++)c.update(1/60,input,0,dur);
  assert.equal(c.state,'idle');assert.equal(c.position.y,0);
  c.update(1/60,{...input,special:true},0,dur);assert.equal(c.special.name,'roar');
  for(let n=0;n<180;n++)c.update(1/60,input,0,dur);assert.equal(c.special,null);
});
test('analog input removes stick noise, keeps fractional travel and maps standard Xbox controls',()=>{
  assert.equal(analog(.1),0);assert.ok(analog(.5)>0&&analog(.5)<.5);assert.equal(analog(-1),-1);
  const buttons=Array.from({length:16},()=>({value:0}));buttons[0].value=1;buttons[6].value=.7;buttons[2].value=1;
  const f=readPad({axes:[.5,-1,.3,-.4],buttons},{});
  assert.ok(f.x>0&&f.x<1);assert.equal(f.y,1);assert.ok(f.lookX>0);assert.equal(f.vertical,-.7);assert.equal(f.jump,true);assert.equal(f.special,true);
  assert.equal(readPad(null,{}).jump,false);
});
test('shared world controller supports aquatic, slithering and jumping-biped profiles without using a quadruped gait',()=>{
  const fish=new CreatureController({category:'aquatic',motion:{swim:1,sprint:3,vertical:2,acceleration:4,turnRate:2}});
  for(let n=0;n<90;n++)fish.update(1/60,{...input,y:1,vertical:1},0);
  assert.equal(fish.state,'ascend');assert.ok(fish.position.y>2);assert.ok(fish.position.z<-.5);
  const snake=new CreatureController({category:'slither',motion:{slither:.4,sprint:1.2,acceleration:4,turnRate:2}});
  for(let n=0;n<90;n++)snake.update(1/60,{...input,y:1},0);
  assert.equal(snake.state,'slither');assert.equal(snake.position.y,0);
  const biped=new CreatureController({category:'biped',jump:true,motion:{walk:1,run:2,jump:3,acceleration:4,turnRate:2}});
  biped.update(1/60,{...input,jump:true},0);assert.equal(biped.state,'jump');
  for(let n=0;n<120;n++)biped.update(1/60,input,0);
  assert.equal(biped.state,'idle');assert.equal(biped.position.y,0);
});
test('readiness rejects missing clips, invalid profiles and incompatible targets',()=>{
  assert.match(readiness(null,[]).join(),/No creature/);
  assert.match(readiness(profile,[]).join(),/Missing keyed walk/);
  assert.match(readiness({...profile,version:99},[]).join(),/Unsupported/);
});
for(const kind of ['griffon-v2','red-dragon'])test(`${kind}: real sidecar tracks bind to original rig; loops close; base geometry is not duplicated`,async()=>{
  const entry=manifest.find(e=>e.file===`${kind}.glb`), base=documentOf(entry.file), side=documentOf(`${kind}-play-animations.glb`);
  assert.equal(side.meshes,undefined);assert.equal(side.images,undefined);
  assert.equal(side.animations.length,11);
  const names=new Set(base.nodes.map(n=>n.name));
  const originalByName=new Map(base.nodes.map(n=>[n.name,n]));
  for(const n of side.nodes){
    const original=originalByName.get(n.name);if(!original)continue;
    for(const key of ['translation','rotation','scale','matrix'])assert.deepEqual(n[key],original[key],`${n.name} retains the original bind frame`);
  }
  for(const a of side.animations)for(const channel of a.channels)assert.ok(names.has(side.nodes[channel.target.node].name),'sidecar targets original bone');
  // Load only the original node hierarchy, allowing the real GLTFLoader binding conventions
  // to run in Node without browser image decoders.
  const hierarchy=structuredClone(base); delete hierarchy.meshes;delete hierarchy.skins;
  delete hierarchy.images;delete hierarchy.textures;delete hierarchy.materials;delete hierarchy.animations;
  for(const node of hierarchy.nodes){delete node.mesh;delete node.skin;}
  delete hierarchy.buffers;delete hierarchy.bufferViews;delete hierarchy.accessors;
  const model=await new GLTFLoader().parseAsync(JSON.stringify(hierarchy),'');
  const bytes=readFileSync(new URL(`../public/models/${kind}-play-animations.glb`,import.meta.url));
  const anim=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  const all=[...anim.animations];
  if(kind==='red-dragon')all.push(new THREE.AnimationClip('Roar',4,[new THREE.NumberKeyframeTrack('head.position[x]',[0,4],[0,1])]));
  assert.deepEqual(readiness(entry.playProfile,all,model.scene),[]);
  for(const clip of anim.animations){
    assert.ok(clip.tracks.length>40);
    assert.ok(clip.tracks.some(track=>track.values.some((v,i)=>Math.abs(v-track.values[i%track.getValueSize()])>1e-4)),`${clip.name} must change bones`);
    if(!/Takeoff|Land/.test(clip.name))for(const track of clip.tracks){
      const width=track.getValueSize();
      const start=Array.from(track.values.slice(0,width)),end=Array.from(track.values.slice(-width));
      // q and -q are the same rotation; hemisphere continuity can choose either at a loop end.
      const sign=track.name.endsWith('.quaternion')&&start.reduce((sum,v,i)=>sum+v*end[i],0)<0?-1:1;
      for(let i=0;i<width;i++)assert.ok(Math.abs(start[i]-end[i]*sign)<1e-4,`${clip.name}/${track.name} closes`);
    }
  }
  const mixer=new THREE.AnimationMixer(model.scene), animator=new LocomotionAnimator(mixer,all,entry.playProfile);
  const c=new CreatureController(entry.playProfile);
  for(let i=0;i<120;i++){c.update(1/60,{...input,y:1},0,animator.durations);animator.update(1/60,c);}
  assert.equal(animator.primary,'walk');assert.ok(animator.actions.walk.time>.01);
  assert.ok(model.scene.getObjectByName('head'));
  animator.dispose();
});
