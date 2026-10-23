import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const models = resolve(repoRoot, 'public', 'models');
const TEXTURE_BUDGET_MB = 64;
const MAX_TEXTURE = 2048;

function parseGlb(data) {
  assert.equal(data.toString('ascii', 0, 4), 'glTF');
  const jsonLength = data.readUInt32LE(12);
  const json = JSON.parse(data.toString('utf8', 20, 20 + jsonLength));
  const binStart = 20 + jsonLength + 8;
  return { json, bin: data.subarray(binStart) };
}

function imageSize(blob) {
  if (blob.readUInt32BE(0) === 0x89504e47) return [blob.readUInt32BE(16), blob.readUInt32BE(20)];
  assert.equal(blob.readUInt16BE(0), 0xffd8, 'embedded images must be PNG or JPEG');
  for (let offset = 2; offset + 9 < blob.length;) {
    const marker = blob[offset + 1];
    if (marker >= 0xc0 && marker <= 0xc2) return [blob.readUInt16BE(offset + 7), blob.readUInt16BE(offset + 5)];
    offset += 2 + blob.readUInt16BE(offset + 2);
  }
  throw new Error('JPEG without a frame header');
}

// The game-ready contract for Blender-built creations (see README "Materials and textures").
async function checkCreation(file) {
  const { json, bin } = parseGlb(await readFile(resolve(models, file)));
  let megabytes = 0;
  for (const image of json.images ?? []) {
    assert.ok(Number.isInteger(image.bufferView), `${file}: images are embedded, not referenced`);
    assert.ok(['image/png', 'image/jpeg'].includes(image.mimeType), `${file}: ${image.mimeType} is portable`);
    const view = json.bufferViews[image.bufferView];
    const [width, height] = imageSize(bin.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength));
    assert.ok(Math.max(width, height) <= MAX_TEXTURE, `${file}: ${image.name} is ${width}x${height}`);
    assert.equal(width & (width - 1), 0, `${file}: ${image.name} width is a power of two for mipmapping`);
    megabytes += width * height * 4 * 4 / 3 / 2 ** 20;
  }
  assert.ok(megabytes <= TEXTURE_BUDGET_MB, `${file}: about ${megabytes.toFixed(1)} MB of textures`);
  for (const mesh of json.meshes ?? []) {
    for (const primitive of mesh.primitives) {
      const material = json.materials?.[primitive.material] ?? {};
      const textured = material.normalTexture || material.occlusionTexture || material.pbrMetallicRoughness?.baseColorTexture;
      if (textured) assert.ok(primitive.attributes.TEXCOORD_0 !== undefined, `${file}: ${mesh.name} is textured but has no UVs`);
    }
  }
  return { json, megabytes };
}

test('Blender-built creations meet the texture and UV contract', async () => {
  const entries = JSON.parse(await readFile(resolve(models, 'manifest.json'), 'utf8'));
  const built = entries.filter(entry => entry.file === 'active-creation.glb' || entry.creationSource);
  assert.ok(built.length > 0);
  for (const entry of built) await checkCreation(entry.file);
});

test('lab materials export as core glTF PBR with packed ORM textures', async () => {
  const { json } = await checkCreation('active-creation.glb');
  for (const material of (json.materials ?? []).filter(item => item.occlusionTexture)) {
    // Occlusion, roughness and metalness share one ORM texture, as glTF intends.
    assert.equal(material.occlusionTexture.index, material.pbrMetallicRoughness.metallicRoughnessTexture.index, material.name);
  }
});
