import * as THREE from 'three';
import { disposeObject } from './dispose.js';

const SIZE = 256;

// Draws one still image per creation. Jobs run one at a time so a long shelf never floods the GPU.
export function createThumbnails() {
  const results = new Map();
  let renderer;
  let queue = Promise.resolve();

  function getRenderer() {
    if (!renderer) {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(1);
      renderer.setSize(SIZE, SIZE);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
    }
    return renderer;
  }

  function snapshot(model) {
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xe7f6ff, 0x526252, 2.5));
    const key = new THREE.DirectionalLight(0xffe9cc, 3);
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
    const target = getRenderer();
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
