import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { channelMaterial, collectMaterials, createChannelView, describeMaterial, isolate, textureMemory } from '../src/inspect.js';

const texture = (width, height, image = { width, height }) => new THREE.Texture(image);

test('describeMaterial lists a packed occlusion-roughness-metal texture once', () => {
  const orm = texture(1024, 1024);
  const material = new THREE.MeshStandardMaterial({ name: 'Atlas', map: texture(1024, 1024), roughnessMap: orm, metalnessMap: orm, aoMap: orm, normalMap: texture(512, 512) });
  const info = describeMaterial(material);
  assert.deepEqual(info.maps.map(map => map.label), ['Colour', 'Normal', 'ORM']);
  assert.equal(info.maps[2].width, 1024);
  assert.match(info.roughnessText, /map/);
});

test('describeMaterial reports flat materials and their traits', () => {
  const info = describeMaterial(new THREE.MeshPhysicalMaterial({ color: 0xff8800, side: THREE.DoubleSide, clearcoat: 1, vertexColors: true }));
  assert.equal(info.maps.length, 0);
  assert.equal(info.color, '#ff8800');
  assert.deepEqual(info.traits, ['vertex colour', 'double-sided', 'clearcoat']);
});

test('textureMemory counts each image once, with mipmaps', () => {
  const image = { width: 1024, height: 1024 };
  const bytes = textureMemory([texture(0, 0, image), texture(0, 0, image), texture(256, 256)]);
  assert.ok(Math.abs(bytes - (1024 * 1024 + 256 * 256) * 4 * 4 / 3) < 1);
});

test('channel views swap every mesh material and restore the originals', () => {
  const rough = texture(64, 64);
  const original = new THREE.MeshStandardMaterial({ roughnessMap: rough, normalMap: texture(64, 64) });
  const group = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(), original);
  group.add(mesh);
  const view = createChannelView();
  view.apply(group, 'roughness');
  assert.ok(mesh.material.isMeshBasicMaterial);
  assert.equal(mesh.material.map, rough);
  view.apply(group, 'normal', { wireframe: true });
  assert.ok(mesh.material.isMeshNormalMaterial);
  assert.equal(mesh.material.normalMap, original.normalMap);
  assert.equal(mesh.material.wireframe, true);
  view.apply(group, 'lit');
  assert.equal(mesh.material, original);
  view.apply(group, 'color');
  view.reset();
  assert.equal(mesh.material, original);
  assert.equal(view.channel, 'lit');
});

test('channel materials fall back to factors when a map is missing', () => {
  const material = channelMaterial(new THREE.MeshStandardMaterial({ metalness: 0.25 }), 'metalness');
  assert.equal(material.map, null);
  const shader = { uniforms: {}, fragmentShader: '#include <common>\n#include <map_fragment>' };
  material.onBeforeCompile(shader);
  assert.equal(shader.uniforms.labFactor.value, 0.25);
  assert.match(shader.fragmentShader, /labFactor, 0.0, 1.0/);
});

test('collectMaterials flags meshes without UVs, and isolate shows one material', () => {
  const a = new THREE.MeshStandardMaterial(), b = new THREE.MeshStandardMaterial();
  const withUv = new THREE.Mesh(new THREE.BoxGeometry(), a);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3));
  const withoutUv = new THREE.Mesh(geometry, b);
  const root = new THREE.Group().add(withUv, withoutUv);
  const entries = collectMaterials(root);
  assert.deepEqual(entries.map(entry => entry.hasUv), [true, false]);
  const hidden = isolate(root, b);
  assert.equal(withUv.visible, false);
  assert.equal(withoutUv.visible, true);
  isolate(root, null, hidden);
  assert.equal(withUv.visible, true);
});
