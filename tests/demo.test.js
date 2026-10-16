import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { makeDemo } from '../src/demo.js';
// Browser-compatible FileReader implementation for exercising GLB serialization in Node.
globalThis.FileReader = class {
  async readAsArrayBuffer(blob) { this.result = await blob.arrayBuffer(); this.onloadend?.(); }
  async readAsDataURL(blob) { this.result = `data:${blob.type};base64,${Buffer.from(await blob.arrayBuffer()).toString('base64')}`; this.onloadend?.(); }
};
test('demo animation changes wing poses and returns to its starting pose', () => {
  const {scene, animations} = makeDemo();
  const mixer = new THREE.AnimationMixer(scene);
  const action = mixer.clipAction(animations[0]).play();
  mixer.update(0);
  const wing = scene.getObjectByName('LeftWing');
  const start = wing.rotation.z;
  mixer.update(.4); assert.ok(wing.rotation.z > start + .4);
  action.time = 0; mixer.update(0); assert.ok(Math.abs(wing.rotation.z - start) < 1e-6);
  action.stop(); mixer.clipAction(animations[1]).play(); mixer.update(1);
  assert.ok(scene.rotation.z > .1);
});
test('GLB round trip retains both clips and editable wrapper transforms', async () => {
  const {scene,animations} = makeDemo();
  const wrapper = new THREE.Group(); wrapper.name = 'LabTransform'; wrapper.scale.setScalar(2); wrapper.rotation.y = .5; wrapper.add(scene);
  const result = await new GLTFExporter().parseAsync(wrapper,{binary:true,animations});
  assert.equal(new DataView(result).getUint32(0,true),0x46546c67);
  const loaded = await new GLTFLoader().parseAsync(result,'');
  assert.equal(loaded.animations.length,2);
  const transform = loaded.scene.getObjectByName('LabTransform');
  assert.equal(transform.scale.x,2); assert.ok(Math.abs(transform.rotation.y-.5)<1e-6);
  const mixer = new THREE.AnimationMixer(loaded.scene); mixer.clipAction(loaded.animations[0]).play(); mixer.update(.4);
  assert.ok(loaded.scene.getObjectByName('LeftWing').rotation.z>.5);
});
