import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const modelsRoot = resolve(repoRoot, 'public', 'models');

test('repository model manifest lists valid, self-contained GLB files', async () => {
  const entries = JSON.parse(await readFile(resolve(modelsRoot, 'manifest.json'), 'utf8'));
  assert.ok(Array.isArray(entries), 'manifest must be an array');
  assert.ok(entries.length > 0, 'manifest should include a review model');

  for (const entry of entries) {
    assert.equal(typeof entry.name, 'string');
    assert.ok(entry.name.trim());
    assert.equal(typeof entry.file, 'string');
    assert.match(entry.file, /^[\w.-]+\.glb$/i, 'model paths must be simple GLB filenames');
    const modelPath = resolve(modelsRoot, entry.file);
    assert.ok(modelPath.startsWith(modelsRoot + sep), 'model must stay inside public/models');
    const bytes = await readFile(modelPath);
    assert.equal(bytes.toString('ascii', 0, 4), 'glTF', `${entry.file} must have GLB magic`);
    assert.equal(bytes.readUInt32LE(4), 2, `${entry.file} must use GLB version 2`);
    assert.equal(bytes.readUInt32LE(8), bytes.length, `${entry.file} must have a valid length header`);
    assert.equal(bytes.readUInt32LE(16), 0x4e4f534a, `${entry.file} must begin with a JSON chunk`);
    const jsonLength = bytes.readUInt32LE(12);
    const gltf = JSON.parse(bytes.toString('utf8', 20, 20 + jsonLength).trim());
    assert.ok(!(gltf.buffers || []).some(buffer => buffer.uri), `${entry.file} must be self-contained`);
    assert.ok(!(gltf.images || []).some(image => image.uri && !image.uri.startsWith('data:')), `${entry.file} must embed its textures`);
  }
});
