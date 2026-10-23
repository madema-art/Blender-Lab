import * as THREE from 'three';
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

// Studio lighting for inspecting materials. Every preset pairs an image-based environment with
// up to three directional lights; angles are degrees, azimuth 0 is in front of the model.
// Only the key light casts a shadow, onto an invisible ground that catches nothing else.
export const LIGHTING_PRESETS = [
  {
    id: 'studio', name: 'Studio HDR', environment: 'hdr', environmentIntensity: 0.55, exposure: 1, toneMapping: 'neutral',
    key: { color: 0xfff0dc, intensity: 2.2, azimuth: 40, elevation: 42 },
    fill: { color: 0xdbe7ff, intensity: 0.35, azimuth: -65, elevation: 15 },
    rim: { color: 0xffffff, intensity: 1.6, azimuth: 165, elevation: 30 },
  },
  {
    id: 'daylight', name: 'Daylight', environment: 'sky', environmentIntensity: 0.8, exposure: 1, toneMapping: 'neutral',
    key: { color: 0xfff4e2, intensity: 3.2, azimuth: 55, elevation: 58 },
    fill: null,
    rim: { color: 0xbfd8ff, intensity: 0.6, azimuth: 200, elevation: 20 },
  },
  {
    id: 'raking', name: 'Raking detail', environment: 'room', environmentIntensity: 0.18, exposure: 1.1, toneMapping: 'neutral',
    key: { color: 0xffffff, intensity: 4.2, azimuth: 80, elevation: 9 },
    fill: null,
    rim: null,
  },
  {
    id: 'rim', name: 'Dramatic rim', environment: 'room', environmentIntensity: 0.12, exposure: 1.05, toneMapping: 'neutral',
    key: { color: 0xffe2c0, intensity: 1.1, azimuth: 30, elevation: 25 },
    fill: { color: 0x9ec8ff, intensity: 3.2, azimuth: -150, elevation: 25 },
    rim: { color: 0xffd9a6, intensity: 4, azimuth: 150, elevation: 35 },
  },
  {
    id: 'neutral', name: 'Neutral flat', environment: 'room', environmentIntensity: 1, exposure: 1, toneMapping: 'neutral',
    key: null, fill: null, rim: null,
  },
  {
    id: 'classic', name: 'Classic Lab', environment: null, environmentIntensity: 0, exposure: 1, toneMapping: 'aces', hemisphere: 2.5,
    key: { color: 0xffe9cc, intensity: 3, azimuth: 37, elevation: 44 },
    fill: null,
    rim: { color: 0xb6e6ff, intensity: 2, azimuth: -127, elevation: 21 },
  },
];

export const ENVIRONMENTS = ['hdr', 'sky', 'room'];
const TONE_MAPPING = { neutral: THREE.NeutralToneMapping, aces: THREE.ACESFilmicToneMapping };

// A blue-sky dome with a warm horizon and a bright sun, as a PMREM-ready scene.
function skyScene() {
  const scene = new THREE.Scene();
  const dome = new THREE.Mesh(new THREE.SphereGeometry(10, 48, 24), new THREE.ShaderMaterial({
    side: THREE.BackSide,
    uniforms: { sun: { value: new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(32), THREE.MathUtils.degToRad(55)) } },
    vertexShader: 'varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: `
      uniform vec3 sun; varying vec3 vDir;
      void main() {
        float h = vDir.y;
        vec3 sky = mix(vec3(0.9, 0.85, 0.75), vec3(0.25, 0.45, 0.9), smoothstep(0.0, 0.5, h));
        vec3 ground = mix(vec3(0.35, 0.3, 0.24), vec3(0.18, 0.16, 0.13), smoothstep(0.0, -0.4, h));
        vec3 color = h > 0.0 ? sky : ground;
        color += vec3(1.0, 0.92, 0.8) * 60.0 * pow(max(dot(vDir, normalize(sun)), 0.0), 900.0);
        gl_FragColor = vec4(color, 1.0);
      }`,
  }));
  scene.add(dome);
  return scene;
}

function direction(azimuth, elevation, distance = 1) {
  const az = THREE.MathUtils.degToRad(azimuth), el = THREE.MathUtils.degToRad(elevation);
  return new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)).multiplyScalar(distance);
}

export function createLighting(renderer, scene, { hdrUrl } = {}) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environments = new Map();
  const rig = new THREE.Group();
  rig.name = 'LabLighting';
  scene.add(rig);
  const lights = {
    key: new THREE.DirectionalLight(), fill: new THREE.DirectionalLight(), rim: new THREE.DirectionalLight(),
  };
  const hemisphere = new THREE.HemisphereLight(0xe7f6ff, 0x526252, 0);
  rig.add(lights.key, lights.fill, lights.rim, lights.key.target, lights.fill.target, lights.rim.target, hemisphere);
  const key = lights.key;
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.02;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.32 }));
  ground.name = 'LabShadowCatcher';
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  const state = { preset: LIGHTING_PRESETS[0], exposure: 1, environmentIntensity: 1, turn: 0, background: false, shadows: true, radius: 2, center: new THREE.Vector3() };
  let pending = 0;

  async function environment(kind) {
    if (!kind) return null;
    if (!environments.has(kind)) {
      let job;
      if (kind === 'room') job = Promise.resolve(pmrem.fromScene(new RoomEnvironment(), 0.04).texture);
      else if (kind === 'sky') job = Promise.resolve(pmrem.fromScene(skyScene(), 0).texture);
      else job = new HDRLoader().loadAsync(hdrUrl).then(texture => {
        const result = pmrem.fromEquirectangular(texture).texture;
        texture.dispose();
        return result;
      });
      environments.set(kind, job.catch(error => { environments.delete(kind); throw error; }));
    }
    return environments.get(kind);
  }

  function placeLights() {
    const preset = state.preset;
    for (const [name, light] of Object.entries(lights)) {
      const spec = preset[name];
      light.visible = Boolean(spec);
      if (!spec) continue;
      light.color.setHex(spec.color);
      light.intensity = spec.intensity;
      light.position.copy(state.center).add(direction(spec.azimuth + state.turn, spec.elevation, state.radius * 4));
      light.target.position.copy(state.center);
    }
    hemisphere.intensity = preset.hemisphere || 0;
    key.castShadow = state.shadows && key.visible;
    ground.visible = key.castShadow;
    const shadow = key.shadow.camera;
    shadow.left = shadow.bottom = -state.radius * 1.6;
    shadow.right = shadow.top = state.radius * 1.6;
    shadow.near = state.radius * 0.5;
    shadow.far = state.radius * 9;
    shadow.updateProjectionMatrix();
  }

  function applyEnvironment(texture) {
    scene.environment = texture;
    scene.environmentIntensity = state.environmentIntensity;
    scene.environmentRotation.set(0, THREE.MathUtils.degToRad(state.turn), 0);
    scene.background = state.background ? texture : null;
    scene.backgroundBlurriness = 0.35;
    scene.backgroundIntensity = state.environmentIntensity;
    scene.backgroundRotation.copy(scene.environmentRotation);
  }

  return {
    presets: LIGHTING_PRESETS,
    get state() { return state; },
    async use(id) {
      const preset = LIGHTING_PRESETS.find(item => item.id === id) || LIGHTING_PRESETS[0];
      const ticket = ++pending;
      state.preset = preset;
      state.exposure = preset.exposure;
      state.environmentIntensity = preset.environmentIntensity;
      renderer.toneMapping = TONE_MAPPING[preset.toneMapping] ?? THREE.NeutralToneMapping;
      renderer.toneMappingExposure = state.exposure;
      placeLights();
      try {
        const texture = await environment(preset.environment);
        if (ticket === pending) applyEnvironment(texture);
      } catch (error) {
        // An environment that cannot load falls back to the procedural studio room.
        console.warn('Environment unavailable, using the studio room instead', error);
        if (ticket === pending) applyEnvironment(await environment('room'));
      }
      return preset;
    },
    setExposure(value) { state.exposure = value; renderer.toneMappingExposure = value; },
    setEnvironmentIntensity(value) {
      state.environmentIntensity = value;
      scene.environmentIntensity = value;
      scene.backgroundIntensity = value;
    },
    setTurn(degrees) {
      state.turn = degrees;
      placeLights();
      scene.environmentRotation.set(0, THREE.MathUtils.degToRad(degrees), 0);
      scene.backgroundRotation.copy(scene.environmentRotation);
    },
    setBackground(show) { state.background = show; scene.background = show ? scene.environment : null; },
    setShadows(show) { state.shadows = show; placeLights(); },
    // Fit lights, the shadow camera and the ground to a model's bounds.
    fit(box) {
      if (box.isEmpty()) return;
      box.getCenter(state.center);
      state.radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.05);
      ground.position.set(state.center.x, box.min.y - state.radius * 0.002, state.center.z);
      ground.scale.setScalar(state.radius * 6);
      placeLights();
    },
  };
}
