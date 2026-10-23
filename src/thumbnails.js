import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { disposeObject } from './dispose.js';

const SIZE = 256;

// Draws one still image per creation. Jobs run one at a time so a long shelf never floods the GPU.
export function createThumbnails() {
  const results = new Map();
  let renderer, environment;
  let queue = Promise.resolve();

  function getRenderer() {
    if (!renderer) {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(1);
      renderer.setSize(SIZE, SIZE);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.NeutralToneMapping;
      // A soft studio environment, so metals and glossy textures read correctly in previews.
      const pmrem = new THREE.PMREMGenerator(renderer);
      environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
      pmrem.dispose();
    }
    return renderer;
  }

  function snapshot(model) {
    const target = getRenderer();
    const scene = new THREE.Scene();
    scene.environment = environment;
    scene.environmentIntensity = 0.6;
    scene.add(new THREE.HemisphereLight(0xe7f6ff, 0x526252, 0.8));
    const key = new THREE.DirectionalLight(0xffe9cc, 2.4);
    key.position.set(3, 5, 4);
    scene.add(key, model);
    const box = new THREE.Box3().setFromObject(model);
    if (box.isEmpty()) return null;
    const center = box.getCenter(new THREE.Vector3());
    const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.01);
    model.position.sub(center);
    const distance = radius / Math.sin(THREE.MathUtils.degToRad(15)) * 1.08;
    const camera = new THREE.PerspectiveCamera(30, 1, radius / 100, radius * 100);
    camera.position.set(0.9, 0.55, 1).normalize().multiplyScalar(distance);
    camera.lookAt(0, 0, 0);
    target.render(scene, camera);
    return target.domElement.toDataURL('image/png');
  }

  // `loadScene` returns a Promise for a model's root object. Results are remembered by `key`.
  function request(key, loadScene) {
    if (!results.has(key)) {
      const job = queue.then(async () => {
        const model = await loadScene();
        try { return snapshot(model); }
        finally { model.removeFromParent(); disposeObject(model); }
      }).catch(error => { console.warn('Thumbnail unavailable', error); return null; });
      queue = job;
      results.set(key, job);
    }
    return results.get(key);
  }

  return { request };
}
