import { makeDemo } from './demo.js';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import './style.css';

const $ = (id) => document.getElementById(id);
$('app').innerHTML = `
<header><div class="brand"><span class="logo">⬡</span><div><h1>Blender Lab</h1><div class="subtitle">A little space for your creations.</div></div><span class="version">v0.1</span></div><button id="open" class="primary">＋ Open GLB</button><input id="file" class="hidden" type="file" accept=".glb" multiple></header>
<div class="workspace"><aside><div class="eyebrow">YOUR MODEL SHELF</div><div class="shelf" id="shelf"></div><p class="hint">Drop a Blender export into the studio. Pick an animation. See it come to life.</p><div class="aside-bottom"><div class="eyebrow">MADE FOR EXPLORING</div><p class="hint">Orbit, inspect, and try ideas.<br>One model. A clear view.</p><a href="https://github.com/madema-art/Blender-Lab" target="_blank" rel="noopener" class="hint">View project on GitHub ↗</a></div></aside>
<main class="studio"><div class="scene-top"><div><h2 id="title">Studio moth</h2><p id="metadata">Built-in animation study</p></div><span class="badge">THREE.JS STUDIO</span></div><div class="viewport" id="viewport"><div class="toolbar"><div><button id="frame" title="Frame model (F)">Frame model</button><button id="front">Front</button><button id="side">Side</button></div><div><button id="shot">Snapshot ↓</button></div></div><div class="view-hint">DRAG to orbit · SCROLL to zoom · RIGHT DRAG to pan</div><div class="axis">Y ↑</div><div class="drop-overlay">Drop .glb models here</div></div>
<div class="controls"><div class="playback"><button id="play" class="primary" aria-label="Pause animation">Ⅱ</button><button id="restart" aria-label="Restart animation">↺</button><select id="clips" aria-label="Animation"></select><input id="timeline" type="range" min="0" max="1" step="0.001" value="0" aria-label="Animation timeline"><span class="time" id="time">0.00 / 0.00 s</span><select id="speed" class="speed" aria-label="Playback speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></div><div class="details"><label><input id="grid" type="checkbox" checked> Grid</label><label><input id="wire" type="checkbox"> Wireframe</label><label><input id="rotate" type="checkbox"> Turntable</label><label>Scale <input id="scale" type="number" min="0.01" max="100" step="0.1" value="1"></label><label>Yaw <input id="yaw" type="number" step="15" value="0">°</label><button id="export">Export GLB ↓</button><span id="status" class="status" role="status">Ready to explore</span></div></div><footer><span>BLENDER → GLB → LAB</span><span>Local files stay in your browser</span></footer></main></div>`;
const viewport = $('viewport');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 10000);
let renderer;
try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true }); }
catch { $('status').textContent = 'WebGL is unavailable. Enable hardware acceleration and reload.'; throw new Error('WebGL unavailable'); }
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
viewport.prepend(renderer.domElement);
const orbit = new OrbitControls(camera, renderer.domElement);
orbit.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xe7f6ff, 0x526252, 2.5));
const key = new THREE.DirectionalLight(0xffe9cc, 3); key.position.set(3, 5, 4); scene.add(key);
const rim = new THREE.DirectionalLight(0xb6e6ff, 2); rim.position.set(-4, 2, -3); scene.add(rim);
const grid = new THREE.GridHelper(20, 40, 0x52675c, 0x344840); grid.material.transparent = true; grid.material.opacity = 0.32; scene.add(grid);
let root, mixer, action, clips = [], playing = true, loadId = 0, currentName = 'Studio moth';
const loader = new GLTFLoader();
const assets = [];
const originalWire = new WeakMap();
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function frame(direction) {
  if (!root) return;
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root), center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 0.1);
  const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.min(1, camera.aspect) * 1.15;
  const offset = direction || new THREE.Vector3(1.4, 0.85, 2);
  camera.position.copy(center).add(offset.clone().normalize().multiplyScalar(distance));
  orbit.target.copy(center); camera.near = Math.max(distance / 1000, .001); camera.far = Math.max(distance * 100, 100); camera.updateProjectionMatrix();
  orbit.minDistance = radius * .1; orbit.maxDistance = distance * 10;
  grid.position.y = box.min.y - radius * .015; grid.scale.setScalar(radius / 3); orbit.update();
}
function selectClip(index) {
  if (action) action.stop();
  action = clips[index] && mixer.clipAction(clips[index]);
  if (action) { action.reset().play(); mixer.update(0); }
  $('timeline').value = 0;
  for (const id of ['play','restart','timeline','speed']) $(id).disabled = !action;
  $('clips').disabled = !clips.length;
  updatePlay();
}
function updatePlay() { $('play').textContent = playing ? 'Ⅱ' : '▶'; $('play').setAttribute('aria-label', playing ? 'Pause animation' : 'Play animation'); }
function dispose(model) {
  const textures = new Set(), materials = new Set(), geometries = new Set();
  model.traverse(o => { if (o.geometry) geometries.add(o.geometry); for (const m of o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : []) { materials.add(m); for (const v of Object.values(m)) if (v?.isTexture) textures.add(v); } });
  textures.forEach(t => t.dispose()); materials.forEach(m => m.dispose()); geometries.forEach(g => g.dispose());
}
function install(model, animations, name, selected) {
  if (root) { mixer.stopAllAction(); mixer.uncacheRoot(root); scene.remove(root); dispose(root); }
  root = new THREE.Group(); root.name = 'LabTransform'; root.add(model); scene.add(root);
  clips = animations; mixer = new THREE.AnimationMixer(root); currentName = name;
  $('title').textContent = name; $('scale').value = 1; $('yaw').value = 0; $('wire').checked = false;
  $('clips').replaceChildren(...(clips.length ? clips.map((clip,i) => new Option(clip.name || `Animation ${i+1}`, i)) : [new Option('No animations', '')]));
  let triangles = 0, meshes = 0;
  model.traverse(o => { if(o.isMesh) { meshes++; triangles += (o.geometry.index?.count || o.geometry.attributes.position?.count || 0) / 3; } });
  $('metadata').textContent = `${meshes} meshes · ${Math.round(triangles).toLocaleString()} triangles · ${clips.length} animations`;
  document.querySelectorAll('.asset').forEach(b => b.classList.toggle('selected', b.dataset.id === selected));
  playing = true; selectClip(0); frame(); status('Ready to explore');
}
async function openAsset(asset) {
  const ticket = ++loadId; status(`Loading ${asset.name}…`);
  try { const gltf = asset.demo ? makeDemo() : await loader.loadAsync(asset.url); if(ticket !== loadId) {dispose(gltf.scene);return;} install(gltf.scene,gltf.animations,asset.name,asset.id); }
  catch(error) { if(ticket === loadId) status(`Could not load ${asset.name}. Use a self-contained GLB export.`,true); console.error(error); }
}
function addAsset(asset) {
  assets.push(asset); const button = document.createElement('button'); button.className='asset'; button.dataset.id=asset.id;
  const icon=document.createElement('span'); icon.className='asset-icon'; icon.textContent='⬡';
  const title=document.createElement('span'); title.textContent=asset.name; const sub=document.createElement('small'); sub.textContent=asset.demo?'ANIMATION STUDY':asset.local?'LOCAL GLB':'REPOSITORY GLB'; title.append(sub); button.append(icon,title); button.onclick=()=>openAsset(asset); $('shelf').append(button);
}
function importFiles(files) {
  for(const file of files) { if(!file.name.toLowerCase().endsWith('.glb')) {status('Please choose a .glb file. Export glTF Binary from Blender.',true);continue;} const asset={id:crypto.randomUUID(),name:file.name.replace(/\.glb$/i,''),url:URL.createObjectURL(file),local:true}; addAsset(asset); openAsset(asset); }
}
$('open').onclick=()=>$('file').click(); $('file').onchange=e=>{importFiles(e.target.files); e.target.value='';};
let dragDepth=0;
viewport.addEventListener('dragenter',e=>{e.preventDefault();dragDepth++;viewport.classList.add('dragging');});
viewport.addEventListener('dragover',e=>e.preventDefault());
viewport.addEventListener('dragleave',()=>{if(--dragDepth<=0)viewport.classList.remove('dragging');});
viewport.addEventListener('drop',e=>{e.preventDefault();dragDepth=0;viewport.classList.remove('dragging');importFiles(e.dataTransfer.files);});
$('play').onclick=()=>{playing=!playing;updatePlay();}; $('restart').onclick=()=>{if(action){action.reset().play();mixer.update(0);}};
$('clips').onchange=e=>selectClip(Number(e.target.value));
$('timeline').oninput=e=>{if(action){action.time=Number(e.target.value)*action.getClip().duration;mixer.update(0);}};
$('grid').onchange=e=>grid.visible=e.target.checked;
$('wire').onchange=e=>root?.traverse(o=>{for(const material of o.material?(Array.isArray(o.material)?o.material:[o.material]):[]){if(!originalWire.has(material))originalWire.set(material,material.wireframe);material.wireframe=e.target.checked||originalWire.get(material);}});
$('rotate').onchange=e=>orbit.autoRotate=e.target.checked;
$('scale').onchange=e=>{const n=Number(e.target.value);if(n>=.01&&n<=100){root.scale.setScalar(n);frame();}else e.target.value=root.scale.x;};
$('yaw').onchange=e=>{const n=Number(e.target.value);if(Number.isFinite(n))root.rotation.y=THREE.MathUtils.degToRad(n);};
$('frame').onclick=()=>frame(); $('front').onclick=()=>frame(new THREE.Vector3(0,.25,1)); $('side').onclick=()=>frame(new THREE.Vector3(1,.25,0));
function download(blob,name) { const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
$('shot').onclick=()=>{renderer.render(scene,camera);renderer.domElement.toBlob(blob=>{if(blob)download(blob,`${currentName}.png`);});};
$('export').onclick=async()=>{if(!root)return;const button=$('export');button.disabled=true;status('Exporting GLB…');try{const buffer=await new GLTFExporter().parseAsync(root,{binary:true,animations:clips});download(new Blob([buffer],{type:'model/gltf-binary'}),`${currentName}-lab.glb`);status('GLB exported with animations and transforms');}catch(error){status('Export failed. See browser console for details.',true);console.error(error);}finally{button.disabled=false;}};
window.addEventListener('keydown',e=>{if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;if(e.code==='Space'){e.preventDefault();if(action)$('play').click();}if(e.key.toLowerCase()==='f')frame();});
new ResizeObserver(()=>{const w=viewport.clientWidth,h=viewport.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}).observe(viewport);
const clock=new THREE.Clock();
renderer.setAnimationLoop(()=>{const delta=Math.min(clock.getDelta(),.1);if(mixer&&playing)mixer.update(delta*Number($('speed').value));orbit.update();renderer.render(scene,camera);const duration=action?.getClip().duration||0,time=action?.time||0;$('timeline').value=duration?time/duration:0;$('time').textContent=`${time.toFixed(2)} / ${duration.toFixed(2)} s`;});
addAsset({id:'demo',name:'Studio moth',demo:true});openAsset(assets[0]);
fetch(`${import.meta.env.BASE_URL}models/manifest.json`).then(r=>{if(!r.ok)throw Error('Manifest unavailable');return r.json();}).then(entries=>{if(!Array.isArray(entries))throw Error('Manifest must be an array');for(const entry of entries){if(typeof entry.name!=='string'||typeof entry.file!=='string')throw Error('Each manifest entry needs name and file');addAsset({id:crypto.randomUUID(),name:entry.name,url:new URL(entry.file,new URL(`${import.meta.env.BASE_URL}models/`,location.href)).href});}}).catch(error=>status(`Model shelf: ${error.message}`,true));
window.addEventListener('beforeunload',()=>assets.filter(a=>a.local).forEach(a=>URL.revokeObjectURL(a.url)));
