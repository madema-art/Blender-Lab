import { test } from 'node:test';
import assert from 'node:assert/strict';
import { defaultClipIndex, formatUpdated, matchesSearch, newestFirst, sourceLabel } from '../src/library.js';

test('newestFirst lists the latest update first and keeps undated items last in shelf order', () => {
  const shelf = [
    { name: 'Old', updated: '2026-10-01T00:00:00Z' },
    { name: 'Moth' },
    { name: 'Newest', updated: '2026-10-18T09:00:00Z' },
    { name: 'Middle', updated: '2026-10-10T00:00:00Z' },
    { name: 'Other moth' },
  ];
  assert.deepEqual(newestFirst(shelf).map(item => item.name), ['Newest', 'Middle', 'Old', 'Moth', 'Other moth']);
});

test('newestFirst keeps shelf order for items updated at the same time', () => {
  const same = '2026-10-17T16:24:06Z';
  const shelf = [{ name: 'A', updated: same }, { name: 'B', updated: same }, { name: 'C', updated: same }];
  assert.deepEqual(newestFirst(shelf).map(item => item.name), ['A', 'B', 'C']);
});

test('matchesSearch requires every typed word and ignores case and extra spaces', () => {
  const item = { name: 'Silver Gull — Adult' };
  assert.equal(matchesSearch(item, ''), true);
  assert.equal(matchesSearch(item, '  SILVER   adult '), true);
  assert.equal(matchesSearch(item, 'silver juvenile'), false);
});

test('formatUpdated and sourceLabel use plain language', () => {
  assert.equal(formatUpdated(undefined), 'Date not recorded');
  assert.match(formatUpdated('2026-10-18T21:32:24Z'), /2026/);
  assert.equal(sourceLabel({ kind: 'active' }), 'Made in Blender for this lab');
  assert.equal(sourceLabel({ kind: 'repository', sourceRepository: 'madema-art/Paradise-island' }), 'From madema-art/Paradise-island');
  assert.equal(sourceLabel({ kind: 'local' }), 'Opened from this computer');
});

test('defaultClipIndex prefers an Idle clip and otherwise plays the first', () => {
  assert.equal(defaultClipIndex([{ name: 'Flight' }, { name: 'Idle' }, { name: 'Roar' }]), 1);
  assert.equal(defaultClipIndex([{ name: 'idle breathing' }]), 0);
  assert.equal(defaultClipIndex([{ name: 'Walk' }, { name: 'Idler' }]), 0);
  assert.equal(defaultClipIndex([]), 0);
});
