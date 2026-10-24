import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { makeDemo } from './demo.js';
import { PlayMode } from './play/mode.js';
import { readiness } from './play/profiles.js';
import { disposeObject } from './dispose.js';
import { defaultClipIndex, formatUpdated, matchesSearch, newestFirst, sourceLabel } from './library.js';
import { createThumbnails } from './thumbnails.js';
import { createLighting, LIGHTING_PRESETS } from './lighting.js';
import { CHANNELS, collectMaterials, createChannelView, describeMaterial, formatMegabytes, isolate, textureMemory } from './inspect.js';
import './style.css';

const $ = (id) => document.getElementById(id);
const PLAY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>';
const PAUSE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5.5h3.6v13H7zM13.4 5.5H17v13h-3.6z"/></svg>';
const viewport = $('viewport');
const shelf = $('shelf');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 10000);
let renderer;
try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true }); }
catch { status('WebGL is unavailable. Turn on hardware acceleration in your browser, then reload.', true); throw new Error('WebGL unavailable'); }
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
viewport.prepend(renderer.domElement);
const orbit = new OrbitControls(camera, renderer.domElement);
orbit.enableDamping = true;
const lighting = createLighting(renderer, scene, { hdrUrl: `${import.meta.env.BASE_URL}environments/lab-studio.hdr` });
const channelView = createChannelView();
const grid = new THREE.GridHelper(20, 40, 0x52675c, 0x344840); grid.material.transparent = true; grid.material.opacity = 0.32; scene.add(grid);

let root, mixer, action, clips = [], clipIndex = 0, playing = true, loadId = 0, current = null, statusTimer;
let materialEntries = [], isolated = null;
let savedInspection, lightingPending = false, modelLoading = false;
const playMode = new PlayMode({ scene, camera, orbit, renderer, grid, onExit() {
  if (savedInspection) {
    selectClip(savedInspection.clipIndex);
    if (action) { action.time = savedInspection.time; mixer.update(0); }
    playing = savedInspection.playing; updatePlay(); refreshView();
    savedInspection = null;
  }
} });
function updatePlayReadiness() {
  const reasons = modelLoading ? ['Wait for the creation to finish loading.'] : lightingPending ? ['Lighting is loading…'] : root ? readiness(current?.playProfile, clips, root) : ['Choose a playable creature.'];
  $('enter-play').disabled = reasons.length > 0;
  $('play-readiness').textContent = reasons.length ? reasons.join(' ') : 'WASD move · Shift run · Space takeoff · E/Q climb/descend · L land · G glide · R special · drag mouse to orbit · Esc return. Xbox: left/right sticks move/look; A takeoff, B land, X special, Y glide, RT speed/climb, LT descend, Menu return.';
  $('enter-play').title = reasons.join(' ') || 'Enter the starfield playground';
}
$('enter-play').onclick = () => {
  if (!root || playMode.active) return;
  savedInspection = { clipIndex, time: action?.time || 0, playing };
  showOriginal();
  try { playMode.enter(root, mixer, clips, current.playProfile); }
  catch (error) { savedInspection = null; refreshView(); status(error.message, true); }
};
const hiddenByIsolation = new Map();
const loader = new GLTFLoader();
const thumbnails = createThumbnails();
const assets = [];
const visible = [];
const originalWire = new WeakMap();
const thumbOwners = new WeakMap();
const demo = { id: 'demo', name: 'Studio moth', kind: 'demo', demo: true };
const thumbObserver = 'IntersectionObserver' in window ? new IntersectionObserver(onThumbVisible, { rootMargin: '0px 240px' }) : null;

function status(message, error = false) {
  const line = $('status');
  clearTimeout(statusTimer);
  line.textContent = message;
  line.classList.toggle('error', error);
  line.classList.add('show');
  if (!error) statusTimer = setTimeout(() => line.classList.remove('show'), 3200);
}

function frame(direction) {
  if (!root) return;
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) { camera.position.set(5, 4, 7); orbit.target.set(0, 0, 0); grid.position.y = 0; grid.scale.setScalar(1); orbit.update(); return; }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 0.1);
  const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.min(1, camera.aspect) * 1.15;
  const offset = direction || new THREE.Vector3(1.4, 0.85, 2);
  camera.position.copy(center).add(offset.clone().normalize().multiplyScalar(distance));
  orbit.target.copy(center); camera.near = Math.max(distance / 1000, .001); camera.far = Math.max(distance * 100, 100); camera.updateProjectionMatrix();
  orbit.minDistance = radius * .1; orbit.maxDistance = distance * 10;
  grid.position.y = box.min.y - radius * .015; grid.scale.setScalar(radius / 3); orbit.update();
  lighting.fit(box);
}

function setTransportEnabled(enabled) {
  for (const id of ['play', 'restart', 'timeline', 'speed']) $(id).disabled = !enabled;
}

function note(text) {
  const paragraph = document.createElement('p');
  paragraph.className = 'muted';
  paragraph.textContent = text;
  return paragraph;
}

// Long clip lists (some models carry well over a hundred) are narrowed by the filter box.
function renderClips() {
  const filter = $('clip-filter');
  filter.hidden = clips.length <= 12;
  if (!clips.length) {
    $('clips').replaceChildren(note(root ? 'No animations in this creation.' : 'Open a creation to see its motion.'));
    return;
  }
  const words = filter.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = clips.map((clip, index) => ({ clip, index, name: clip.name || `Animation ${index + 1}` }))
    .filter(({ name }) => words.every(word => name.toLowerCase().includes(word)));
  if (!matches.length) {
    $('clips').replaceChildren(note(`No animation matches “${filter.value.trim()}”.`));
    return;
  }
  $('clips').replaceChildren(...matches.map(({ index, name }) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'clip';
    button.textContent = name;
    button.setAttribute('aria-pressed', String(index === clipIndex));
    button.onclick = () => selectClip(index);
    return button;
  }));
}

function selectClip(index) {
  if (action) action.stop();
  clipIndex = index;
  action = clips[index] && mixer.clipAction(clips[index]);
  if (action) { action.reset().play(); mixer.update(0); }
  $('timeline').value = 0;
  setTransportEnabled(Boolean(action));
  renderClips();
  updatePlay();
}

function updatePlay() {
  const button = $('play');
  button.innerHTML = playing ? PAUSE_ICON : PLAY_ICON;
  const label = playing ? 'Pause animation' : 'Play animation';
  button.setAttribute('aria-label', label);
  button.title = label;
}

// Channel views and isolation swap materials and visibility; this puts the model back to its own state.
function showOriginal() {
  channelView.restore();
  isolate(root, null, hiddenByIsolation);
}

function refreshView() {
  channelView.restore();
  isolate(root, isolated, hiddenByIsolation);
  channelView.apply(root, $('channel').value, { wireframe: $('wire').checked });
}

function mapThumbnail(map) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  canvas.className = 'map-thumb';
  canvas.title = `${map.label} ${map.width}×${map.height}`;
  try { canvas.getContext('2d').drawImage(map.texture.image, 0, 0, 64, 64); }
  catch { canvas.classList.add('empty'); }
  return canvas;
}

function renderMaterials() {
  const list = $('materials');
  if (!root) { list.replaceChildren(); $('material-summary').textContent = 'Open a creation to inspect its materials.'; return; }
  const textures = materialEntries.flatMap(entry => describeMaterial(entry.material).maps.map(map => map.texture));
  const memory = textureMemory(textures);
  const unique = new Set(textures.map(texture => texture.image)).size;
  $('material-summary').textContent = unique
    ? `${materialEntries.length} material${materialEntries.length === 1 ? '' : 's'}, ${unique} texture${unique === 1 ? '' : 's'}, about ${formatMegabytes(memory)} of GPU memory. Pick one to show only its parts.`
    : `${materialEntries.length} material${materialEntries.length === 1 ? '' : 's'} using flat colours, with no textures.`;
  list.replaceChildren(...materialEntries.map(entry => {
    const info = describeMaterial(entry.material);
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'material';
    button.setAttribute('aria-pressed', String(isolated === entry.material));
    const swatch = document.createElement('span');
    swatch.className = 'swatch';
    swatch.style.background = info.color || 'transparent';
    const text = document.createElement('span');
    text.className = 'material-text';
    const name = document.createElement('span');
    name.className = 'material-name';
    name.textContent = info.name;
    const facts = document.createElement('span');
    facts.className = 'material-facts';
    const values = info.roughness === undefined ? [info.type] : [info.roughnessText, info.metalnessText];
    facts.textContent = [...values, ...info.traits, entry.hasUv ? null : 'no UVs'].filter(Boolean).join(' · ');
    text.append(name, facts);
    button.append(swatch, text);
    if (info.maps.length) {
      const maps = document.createElement('span');
      maps.className = 'maps';
      for (const map of info.maps) {
        const chip = document.createElement('span');
        chip.className = 'map';
        const label = document.createElement('span');
        label.textContent = `${map.label} ${map.width}`;
        chip.append(mapThumbnail(map), label);
        maps.append(chip);
      }
      button.append(maps);
    }
    button.onclick = () => {
      isolated = isolated === entry.material ? null : entry.material;
      refreshView();
      renderMaterials();
    };
    item.append(button);
    return item;
  }));
}

function install(model, animations, asset) {
  playMode.exit();
  modelLoading = false;
  if (root) { showOriginal(); mixer.stopAllAction(); mixer.uncacheRoot(root); scene.remove(root); disposeObject(root); }
  channelView.reset(); isolated = null; $('channel').value = 'lit';
  root = new THREE.Group(); root.name = 'LabTransform'; root.add(model); scene.add(root);
  clips = animations; mixer = new THREE.AnimationMixer(root); current = asset; playing = true;
  $('clip-filter').value = '';
  $('title').textContent = asset.name;
  $('metadata').textContent = sourceLabel(asset);
  $('empty-stage').hidden = true;
  $('scale').value = 1; $('yaw').value = 0; $('wire').checked = false;
  for (const id of ['scale', 'yaw', 'wire', 'reset', 'export']) $(id).disabled = false;
  let triangles = 0, meshes = 0;
  model.traverse(node => {
    if (!node.isMesh) return;
    node.castShadow = true;
    meshes++; triangles += (node.geometry.index?.count || node.geometry.attributes.position?.count || 0) / 3;
  });
  materialEntries = collectMaterials(model);
  const textures = materialEntries.flatMap(entry => describeMaterial(entry.material).maps.map(map => map.texture));
  const textureCount = new Set(textures.map(texture => texture.image)).size;
  $('about-source').textContent = sourceLabel(asset);
  $('about-updated').textContent = formatUpdated(asset.updated);
  $('about-size').textContent = `${meshes} parts, ${Math.round(triangles).toLocaleString()} triangles`;
  $('about-anims').textContent = clips.length ? `${clips.length} animation${clips.length === 1 ? '' : 's'}` : 'None. This is a still model.';
  $('about-textures').textContent = textureCount ? `${textureCount}, about ${formatMegabytes(textureMemory(textures))} on the GPU` : 'None. Flat material colours.';
  for (const id of ['channel']) $(id).disabled = false;
  renderMaterials();
  highlightCurrent();
  selectClip(defaultClipIndex(clips));
  frame();
  updatePlayReadiness();
  status(`Showing ${asset.name}`);
}

// Blob URLs from opened files cannot take a query string; repository files get a fresh version each open.
function freshUrl(url) {
  return url.startsWith('blob:') ? url : `${url}${url.includes('?') ? '&' : '?'}v=${Date.now()}`;
}

async function openAsset(asset) {
  playMode.exit();
  modelLoading = true; updatePlayReadiness();
  const ticket = ++loadId;
  current = asset;
  highlightCurrent();
  status(`Loading ${asset.name}…`);
  try {
    const gltf = asset.demo ? makeDemo() : await loader.loadAsync(freshUrl(asset.url));
    if (ticket !== loadId) { disposeObject(gltf.scene); return; }
    const animationSets = await Promise.all((asset.animationSources || []).map(url => loader.loadAsync(freshUrl(url))));
    if (ticket !== loadId) { disposeObject(gltf.scene); animationSets.forEach(set => disposeObject(set.scene)); return; }
    const clipList = [], names = new Set();
    for (const clip of [...gltf.animations, ...animationSets.flatMap(set => set.animations)]) {
      if (!names.has(clip.name)) { names.add(clip.name); clipList.push(clip); }
    }
    animationSets.forEach(set => disposeObject(set.scene));
    install(gltf.scene, clipList, asset);
  } catch (error) {
    if (ticket === loadId) status(`Could not open ${asset.name}. Export it from Blender as one self-contained .glb file, then try again.`, true);
    console.error(error);
  }
}

function highlightCurrent() {
  for (const card of shelf.querySelectorAll('.card')) {
    const selected = card.dataset.id === current?.id;
    card.classList.toggle('selected', selected);
    if (selected) card.setAttribute('aria-current', 'true');
    else card.removeAttribute('aria-current');
  }
}

function loadPreviewScene(asset) {
  if (asset.demo) return Promise.resolve(makeDemo().scene);
  return loader.loadAsync(asset.url).then(gltf => gltf.scene);
}

function showThumbnail(thumb, asset) {
  thumbnails.request(asset.id, () => loadPreviewScene(asset)).then(dataUrl => {
    if (!dataUrl || !thumb.isConnected) return;
    const image = new Image();
    image.alt = '';
    image.src = dataUrl;
    thumb.replaceChildren(image);
  });
}

function onThumbVisible(entries) {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    thumbObserver.unobserve(entry.target);
    showThumbnail(entry.target, thumbOwners.get(entry.target));
  }
}

function describe(asset) {
  if (asset.kind === 'active') return `Active, updated ${formatUpdated(asset.updated)}`;
  return asset.updated ? `Updated ${formatUpdated(asset.updated)}` : sourceLabel(asset);
}

function createCard(asset) {
  const item = document.createElement('li');
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'card';
  button.dataset.id = asset.id;
  const thumb = document.createElement('span');
  thumb.className = 'thumb';
  thumb.textContent = asset.name.trim().charAt(0).toUpperCase();
  const text = document.createElement('span');
  text.className = 'card-text';
  const name = document.createElement('span');
  name.className = 'card-name';
  name.textContent = asset.name;
  const meta = document.createElement('span');
  meta.className = 'card-meta';
  meta.textContent = describe(asset);
  text.append(name, meta);
  button.append(thumb, text);
  button.onclick = () => openAsset(asset);
  item.append(button);
  thumbOwners.set(thumb, asset);
  if (thumbObserver) thumbObserver.observe(thumb);
  else showThumbnail(thumb, asset);
  return item;
}

function renderShelf() {
  const query = $('search').value;
  visible.splice(0, visible.length, ...newestFirst(assets).filter(asset => matchesSearch(asset, query)));
  shelf.replaceChildren(...visible.map(createCard));
  $('count').textContent = query.trim() ? `${visible.length} of ${assets.length}` : `${assets.length}`;
  const empty = $('shelf-empty');
  empty.hidden = visible.length > 0;
  empty.textContent = assets.length ? `Nothing matches “${query.trim()}”.` : 'Loading creations…';
  highlightCurrent();
}

// Arrow keys move through the list in the order it is shown.
function step(direction) {
  if (!visible.length) return;
  const index = visible.findIndex(asset => asset.id === current?.id);
  const next = index < 0 ? visible[direction > 0 ? 0 : visible.length - 1] : visible[(index + direction + visible.length) % visible.length];
  openAsset(next);
  shelf.querySelector(`[data-id="${next.id}"]`)?.scrollIntoView({ block: 'nearest' });
}

function importFiles(files) {
  const added = [];
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith('.glb')) { status('That file is not a .glb. In Blender, use File > Export > glTF 2.0 and choose GLB.', true); continue; }
    added.push({ id: crypto.randomUUID(), name: file.name.replace(/\.glb$/i, ''), url: URL.createObjectURL(file), kind: 'local', updated: new Date().toISOString() });
  }
  if (!added.length) return;
  assets.push(...added);
  renderShelf();
  openAsset(added[0]);
}

function startNewCreation() {
  playMode.exit();
  modelLoading = false;
  ++loadId;
  if (root) { showOriginal(); mixer?.stopAllAction(); if (mixer) mixer.uncacheRoot(root); scene.remove(root); disposeObject(root); }
  root = undefined; mixer = undefined; action = undefined; clips = []; clipIndex = 0; current = null;
  channelView.reset(); isolated = null; materialEntries = []; $('channel').value = 'lit'; $('channel').disabled = true;
  renderMaterials();
  $('about-textures').textContent = '—';
  $('title').textContent = 'New creation';
  $('metadata').textContent = 'A blank Blender scene';
  $('empty-stage').hidden = false;
  $('about-source').textContent = 'Blank scene';
  $('about-updated').textContent = '—';
  $('about-size').textContent = '—';
  $('about-anims').textContent = '—';
  setTransportEnabled(false);
  renderClips();
  updatePlay();
  $('timeline').value = 0; $('time').textContent = '0.00 / 0.00 s';
  for (const id of ['scale', 'yaw', 'wire', 'reset', 'export']) $(id).disabled = true;
  $('scale').value = 1; $('yaw').value = 0; $('wire').checked = false;
  highlightCurrent();
  camera.position.set(5, 4, 7); orbit.target.set(0, 0, 0); camera.near = .01; camera.far = 10000; camera.updateProjectionMatrix(); orbit.update();
  grid.position.y = 0; grid.scale.setScalar(1);
  status('Blank scene ready. Ask Work to build it, and it will appear here.');
  updatePlayReadiness();
}

function download(blob, name) {
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$('new').onclick = startNewCreation;
$('open').onclick = () => $('file').click();
$('file').onchange = event => { importFiles(event.target.files); event.target.value = ''; };
$('search').addEventListener('input', renderShelf);
$('clip-filter').addEventListener('input', renderClips);

let dragDepth = 0;
viewport.addEventListener('dragenter', event => { event.preventDefault(); dragDepth++; viewport.classList.add('dragging'); });
viewport.addEventListener('dragover', event => event.preventDefault());
viewport.addEventListener('dragleave', () => { if (--dragDepth <= 0) viewport.classList.remove('dragging'); });
viewport.addEventListener('drop', event => { event.preventDefault(); dragDepth = 0; viewport.classList.remove('dragging'); importFiles(event.dataTransfer.files); });

$('play').onclick = () => { playing = !playing; updatePlay(); };
$('restart').onclick = () => { if (action) { action.reset().play(); mixer.update(0); } };
$('timeline').oninput = event => { if (action) { action.time = Number(event.target.value) * action.getClip().duration; mixer.update(0); } };
$('grid').onchange = event => { grid.visible = event.target.checked; };
$('wire').onchange = event => {
  channelView.restore();
  root?.traverse(node => {
    for (const material of node.material ? [node.material].flat() : []) {
      if (!originalWire.has(material)) originalWire.set(material, material.wireframe);
      material.wireframe = event.target.checked || originalWire.get(material);
    }
  });
  refreshView();
};
$('channel').onchange = () => {
  refreshView();
  const channel = CHANNELS.find(item => item.id === $('channel').value);
  const missingUv = $('channel').value === 'uv' && materialEntries.some(entry => !entry.hasUv);
  status(missingUv ? 'Some parts have no UVs, so the checker shows one flat colour on them' : `Showing ${channel.name}`);
};

function syncLightingControls() {
  const { preset, exposure, environmentIntensity, turn } = lighting.state;
  $('light-preset').value = preset.id;
  $('exposure').value = exposure; $('exposure-value').textContent = Number(exposure).toFixed(2);
  $('env-intensity').value = environmentIntensity; $('env-value').textContent = Number(environmentIntensity).toFixed(2);
  $('env-intensity').disabled = !preset.environment;
  $('light-turn').value = turn; $('turn-value').textContent = `${turn}°`;
}
async function useLighting(id) {
  playMode.exit();
  lightingPending=true; updatePlayReadiness();
  const preset = lighting.use(id);
  syncLightingControls();
  await preset;
  lightingPending=false; updatePlayReadiness();
  syncLightingControls();
}
$('light-preset').replaceChildren(...LIGHTING_PRESETS.map(preset => new Option(preset.name, preset.id)));
$('channel').replaceChildren(...CHANNELS.map(channel => new Option(channel.name, channel.id)));
$('light-preset').onchange = event => useLighting(event.target.value);
$('exposure').oninput = event => { lighting.setExposure(Number(event.target.value)); syncLightingControls(); };
$('env-intensity').oninput = event => { lighting.setEnvironmentIntensity(Number(event.target.value)); syncLightingControls(); };
$('light-turn').oninput = event => { lighting.setTurn(Number(event.target.value)); syncLightingControls(); };
$('shadows').onchange = event => lighting.setShadows(event.target.checked);
$('env-background').onchange = event => lighting.setBackground(event.target.checked);
function cycle(select, direction = 1) {
  if (select.disabled) return;
  select.selectedIndex = (select.selectedIndex + direction + select.options.length) % select.options.length;
  select.dispatchEvent(new Event('change'));
}
$('rotate').onchange = event => { orbit.autoRotate = event.target.checked; };
$('scale').onchange = event => {
  const value = Number(event.target.value);
  if (!root) return;
  if (value >= .01 && value <= 100) { root.scale.setScalar(value); frame(); }
  else event.target.value = root.scale.x;
};
$('yaw').onchange = event => {
  const value = Number(event.target.value);
  if (root && Number.isFinite(value)) root.rotation.y = THREE.MathUtils.degToRad(value);
};
$('reset').onclick = () => {
  if (!root) return;
  root.scale.setScalar(1); root.rotation.y = 0;
  $('scale').value = 1; $('yaw').value = 0;
  frame();
};
$('frame').onclick = () => frame();
$('front').onclick = () => frame(new THREE.Vector3(0, .25, 1));
$('side').onclick = () => frame(new THREE.Vector3(1, .25, 0));
$('shot').onclick = () => {
  renderer.render(scene, camera);
  renderer.domElement.toBlob(blob => { if (blob) download(blob, `${current?.name ?? 'Blender Lab'}.png`); });
};
$('export').onclick = async () => {
  if (!root) return;
  const button = $('export');
  button.disabled = true;
  status('Preparing the GLB download…');
  try {
    showOriginal();  // export the model's own materials, with every part visible
    const buffer = await new GLTFExporter().parseAsync(root, { binary: true, animations: clips }).finally(refreshView);
    download(new Blob([buffer], { type: 'model/gltf-binary' }), `${current?.name ?? 'creation'}-lab.glb`);
    status('Downloaded a GLB copy with its animations and transforms');
  } catch (error) {
    status('The download failed. Check the browser console for details.', true);
    console.error(error);
  } finally {
    button.disabled = false;
  }
};

window.addEventListener('keydown', event => {
  if (playMode.active) return;
  if (/INPUT|SELECT|TEXTAREA/.test(event.target.tagName) || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.code === 'Space' && event.target.tagName !== 'BUTTON') {
    if (action) { event.preventDefault(); $('play').click(); }
  } else if (event.key.toLowerCase() === 'f') {
    frame();
  } else if (event.key.toLowerCase() === 'l') {
    cycle($('light-preset'), event.shiftKey ? -1 : 1);
  } else if (event.key.toLowerCase() === 'v') {
    cycle($('channel'), event.shiftKey ? -1 : 1);
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    step(event.key === 'ArrowDown' ? 1 : -1);
  }
});

new ResizeObserver(() => {
  const width = viewport.clientWidth, height = viewport.clientHeight;
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}).observe(viewport);

const timer = new THREE.Timer();
function tick(delta, render = true) {
  if (playMode.active) playMode.update(delta);
  else {
    if (mixer && playing) mixer.update(delta * Number($('speed').value));
    orbit.update();
  }
  if (render) renderer.render(scene, camera);
  if (playMode.active) return;
  const duration = action?.getClip().duration || 0, time = action?.time || 0;
  $('timeline').value = duration ? time / duration : 0;
  $('time').textContent = `${time.toFixed(2)} / ${duration.toFixed(2)} s`;
}
let manualUntil = 0;
renderer.setAnimationLoop(() => {
  timer.update();
  const delta = Math.min(timer.getDelta(), .1);
  if (performance.now() >= manualUntil) tick(delta);
});
window.render_game_to_text = () => JSON.stringify({ ...playMode.describe(), model:current?.name, ready:root ? readiness(current?.playProfile,clips,root) : ['No model'], resources:{geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles} });
window.advanceTime = ms => {
  manualUntil=performance.now()+200;
  const steps=Math.max(1,Math.ceil(ms/(1000/60)));
  for(let n=0;n<steps;n++)tick(ms/1000/steps,false);
  renderer.render(scene,camera);
};

updatePlay();
renderClips();
renderMaterials();
updatePlayReadiness();
useLighting(LIGHTING_PRESETS[0].id);
fetch(`${import.meta.env.BASE_URL}models/manifest.json`)
  .then(response => { if (!response.ok) throw Error('Manifest unavailable'); return response.json(); })
  .then(entries => {
    if (!Array.isArray(entries)) throw Error('Manifest must be an array');
    const modelBase = new URL(`${import.meta.env.BASE_URL}models/`, location.href);
    const shelfAssets = entries.map(entry => {
      if (typeof entry.name !== 'string' || typeof entry.file !== 'string') throw Error('Each manifest entry needs name and file');
      const active = entry.file === 'active-creation.glb';
      return {
        id: active ? 'active-creation' : crypto.randomUUID(),
        name: entry.name,
        url: new URL(entry.file, modelBase).href,
        kind: active ? 'active' : 'repository',
        updated: typeof entry.updated === 'string' ? entry.updated : undefined,
        sourceRepository: entry.sourceRepository,
        playProfile: entry.playProfile,
        animationSources: Array.isArray(entry.animationSources) ? entry.animationSources.map(source => new URL(source.file, modelBase).href) : [],
      };
    });
    assets.push(...shelfAssets, demo);
    renderShelf();
    openAsset(shelfAssets.find(asset => asset.id === 'active-creation') || shelfAssets[0] || demo);
  })
  .catch(error => {
    assets.push(demo);
    renderShelf();
    $('shelf-empty').hidden = false;
    $('shelf-empty').textContent = `The creations list did not load: ${error.message}`;
    $('empty-stage').hidden = false;
    status(`Creations list: ${error.message}`, true);
    openAsset(demo);
  });
window.addEventListener('beforeunload', () => assets.filter(asset => asset.kind === 'local').forEach(asset => URL.revokeObjectURL(asset.url)));
