import * as THREE from 'three';

// Material inspection: channel views that swap each mesh's material for an unlit view of one
// PBR input, a material summary for the inspector, and a texture-memory estimate.
export const CHANNELS = [
  { id: 'lit', name: 'Lit (full PBR)' },
  { id: 'color', name: 'Base colour' },
  { id: 'roughness', name: 'Roughness' },
  { id: 'metalness', name: 'Metallic' },
  { id: 'normal', name: 'Normals' },
  { id: 'ao', name: 'Ambient occlusion' },
  { id: 'uv', name: 'UV checker' },
];

const MAP_SLOTS = [
  ['map', 'Colour'], ['normalMap', 'Normal'], ['roughnessMap', 'Rough'], ['metalnessMap', 'Metal'],
  ['aoMap', 'AO'], ['emissiveMap', 'Emissive'], ['alphaMap', 'Alpha'], ['clearcoatMap', 'Coat'],
];

function imageSize(texture) {
  const image = texture?.image;
  return image ? { width: image.width || 0, height: image.height || 0 } : { width: 0, height: 0 };
}

// GPU bytes for a set of textures, counting each image once and including its mipmap chain.
export function textureMemory(textures) {
  const images = new Set();
  let bytes = 0;
  for (const texture of textures) {
    const image = texture?.image;
    if (!image || images.has(image)) continue;
    images.add(image);
    const { width, height } = imageSize(texture);
    bytes += width * height * 4 * (texture.generateMipmaps === false ? 1 : 4 / 3);
  }
  return bytes;
}

export function formatMegabytes(bytes) {
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// Plain facts about one material, for display and tests.
export function describeMaterial(material) {
  // Textures shared between slots (glTF packs occlusion, roughness and metalness) are listed once.
  const byTexture = new Map();
  for (const [slot, label] of MAP_SLOTS) {
    const texture = material[slot];
    if (!texture?.isTexture) continue;
    if (byTexture.has(texture)) byTexture.get(texture).slots.push(slot);
    else byTexture.set(texture, { slots: [slot], label, texture, ...imageSize(texture) });
  }
  const maps = [...byTexture.values()].map(map => {
    const packed = map.slots.includes('roughnessMap') && map.slots.length > 1;
    return { ...map, label: packed ? (map.slots.includes('aoMap') ? 'ORM' : 'Rough/Metal') : map.label };
  });
  const traits = [];
  if (material.vertexColors) traits.push('vertex colour');
  if (material.side === THREE.DoubleSide) traits.push('double-sided');
  if (material.transparent || material.alphaTest > 0) traits.push(material.alphaTest > 0 ? 'alpha cut' : 'transparent');
  if (material.clearcoat > 0) traits.push('clearcoat');
  if (material.transmission > 0) traits.push('transmission');
  if (material.emissive && (material.emissive.r + material.emissive.g + material.emissive.b) > 0) traits.push('emissive');
  return {
    name: material.name || material.type,
    type: material.type,
    color: material.color ? `#${material.color.getHexString()}` : null,
    roughness: material.roughness,
    metalness: material.metalness,
    // A map multiplies its factor, so the text says where the value really comes from.
    roughnessText: material.roughnessMap ? `rough map × ${material.roughness?.toFixed(2)}` : `rough ${material.roughness?.toFixed(2)}`,
    metalnessText: material.metalnessMap ? `metal map × ${material.metalness?.toFixed(2)}` : `metal ${material.metalness?.toFixed(2)}`,
    maps,
    traits,
  };
}

export function collectMaterials(root) {
  const found = new Map();
  root?.traverse(node => {
    if (!node.isMesh) return;
    for (const material of [node.material].flat()) {
      if (!found.has(material)) found.set(material, { material, meshes: [], hasUv: true });
      const entry = found.get(material);
      entry.meshes.push(node);
      if (!node.geometry.attributes.uv) entry.hasUv = false;
    }
  });
  return [...found.values()];
}

let checker;
function checkerTexture() {
  if (checker || typeof document === 'undefined') return checker;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 512;
  const context = canvas.getContext('2d');
  const cells = 8, size = 512 / cells;
  for (let y = 0; y < cells; y++) for (let x = 0; x < cells; x++) {
    context.fillStyle = `hsl(${(x * 45 + y * 12) % 360} 55% ${(x + y) % 2 ? 58 : 34}%)`;
    context.fillRect(x * size, y * size, size, size);
    context.fillStyle = 'rgba(255,255,255,.85)';
    context.font = '600 16px system-ui, sans-serif';
    context.fillText(`${String.fromCharCode(65 + x)}${cells - y}`, x * size + 6, y * size + 20);
  }
  checker = new THREE.CanvasTexture(canvas);
  checker.colorSpace = THREE.SRGBColorSpace;
  checker.anisotropy = 4;
  return checker;
}

// An unlit material showing one scalar channel of `texture` (times `factor`) as grey.
function scalarMaterial(source, texture, expression, factor) {
  const material = new THREE.MeshBasicMaterial({ map: texture || null, side: source.side, toneMapped: false });
  material.onBeforeCompile = shader => {
    shader.uniforms.labFactor = { value: factor };
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float labFactor;')
      .replace('#include <map_fragment>', `float labValue = clamp(${texture ? expression : 'labFactor'}, 0.0, 1.0);
        diffuseColor.rgb = vec3(pow(labValue, 2.2));`);
  };
  material.customProgramCacheKey = () => `lab-scalar-${expression}-${Boolean(texture)}`;
  return material;
}

export function channelMaterial(source, channel) {
  switch (channel) {
    case 'color':
      return new THREE.MeshBasicMaterial({
        map: source.map || null, color: source.color?.clone() ?? new THREE.Color(1, 1, 1), vertexColors: source.vertexColors,
        side: source.side, transparent: source.transparent, opacity: source.opacity, alphaTest: source.alphaTest, toneMapped: false,
      });
    case 'roughness':
      return scalarMaterial(source, source.roughnessMap, 'texture2D(map, vMapUv).g * labFactor', source.roughness ?? 1);
    case 'metalness':
      return scalarMaterial(source, source.metalnessMap, 'texture2D(map, vMapUv).b * labFactor', source.metalness ?? 0);
    case 'ao':
      return scalarMaterial(source, source.aoMap, '1.0 - labFactor * (1.0 - texture2D(map, vMapUv).r)', source.aoMapIntensity ?? 1);
    case 'normal':
      return new THREE.MeshNormalMaterial({
        normalMap: source.normalMap || null, normalScale: source.normalScale?.clone() ?? new THREE.Vector2(1, 1), side: source.side,
      });
    case 'uv':
      return new THREE.MeshBasicMaterial({ map: checkerTexture() || null, side: source.side, toneMapped: false });
    default:
      return source;
  }
}

// Swaps materials for a channel view and back, remembering each mesh's own material.
export function createChannelView() {
  const originals = new Map();
  const cache = new Map();
  let channel = 'lit';

  function override(material) {
    const key = `${channel}:${material.uuid}`;
    if (!cache.has(key)) cache.set(key, channelMaterial(material, channel));
    return cache.get(key);
  }

  function restore() {
    for (const [mesh, material] of originals) mesh.material = material;
    originals.clear();
  }

  return {
    get channel() { return channel; },
    apply(root, next, { wireframe = false } = {}) {
      restore();
      channel = next;
      if (channel === 'lit' || !root) return;
      root.traverse(node => {
        if (!node.isMesh) return;
        originals.set(node, node.material);
        const swapped = Array.isArray(node.material) ? node.material.map(override) : override(node.material);
        for (const material of [swapped].flat()) material.wireframe = wireframe;
        node.material = swapped;
      });
    },
    restore,
    // Forget the cached view materials, for example when another model is opened.
    reset() {
      restore();
      for (const material of cache.values()) material.dispose();
      cache.clear();
      channel = 'lit';
    },
  };
}

// Shows only meshes that use `material`; pass null to show everything again.
export function isolate(root, material, hidden = new Map()) {
  for (const [mesh, visible] of hidden) mesh.visible = visible;
  hidden.clear();
  if (!material || !root) return hidden;
  root.traverse(node => {
    if (!node.isMesh) return;
    const uses = [node.material].flat().includes(material);
    hidden.set(node, node.visible);
    node.visible = node.visible && uses;
  });
  return hidden;
}
