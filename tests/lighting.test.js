import { test } from 'node:test';
import assert from 'node:assert/strict';
import { access } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ENVIRONMENTS, LIGHTING_PRESETS } from '../src/lighting.js';

const repoRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));

test('lighting presets are complete and distinct', () => {
  const ids = LIGHTING_PRESETS.map(preset => preset.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(ids.includes('classic'), 'the original Blender Lab lighting stays available');
  for (const preset of LIGHTING_PRESETS) {
    assert.ok(preset.environment === null || ENVIRONMENTS.includes(preset.environment), preset.id);
    assert.ok(preset.exposure > 0 && preset.environmentIntensity >= 0, preset.id);
    for (const light of [preset.key, preset.fill, preset.rim].filter(Boolean)) {
      assert.ok(light.intensity > 0 && light.elevation > 0 && light.elevation < 90, preset.id);
    }
  }
});

test('the default studio preset ships its HDR environment', async () => {
  assert.equal(LIGHTING_PRESETS[0].environment, 'hdr');
  await access(resolve(repoRoot, 'public', 'environments', 'lab-studio.hdr'));
});
