import { test } from 'node:test';
import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));

test('library entries have unique files, and saved creations keep their source', async () => {
  const entries = JSON.parse(await readFile(resolve(repoRoot, 'public', 'models', 'manifest.json'), 'utf8'));
  const files = entries.map(entry => entry.file);
  assert.equal(new Set(files).size, files.length, 'each library entry needs its own GLB file');
  for (const entry of entries.filter(entry => entry.creationSource)) {
    await access(resolve(repoRoot, entry.creationSource));
  }
});
