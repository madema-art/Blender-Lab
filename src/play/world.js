import * as THREE from 'three';

export function createPlayWorld(scene, size, aquatic = false) {
  const group = new THREE.Group(); group.name = 'Black starfield playground';
  let seed = 7819; const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
  const positions = [], data = [];
  for (let i = 0; i < 6000; i++) {
    const az = random() * Math.PI * 2, y = random() * 2-1, r = (700 + (i % 3) * 700) * size;
    const xz = Math.sqrt(1-y*y); positions.push(Math.cos(az)*xz*r, y*r, Math.sin(az)*xz*r);
    data.push(random()*6.28, .3 + random()*.65, .6 + random()*1.1);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('star', new THREE.Float32BufferAttribute(data, 3));
  const material = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, toneMapped: false,
    uniforms: { time: { value: 0 }, pixelRatio: { value: Math.min(devicePixelRatio, 2) } },
    vertexShader: `attribute vec3 star; varying float brightness; uniform float time; uniform float pixelRatio;
      void main(){ brightness=star.y*(.88+.12*sin(time*(.25+star.y*.2)+star.x));
      gl_PointSize=star.z*pixelRatio; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
    fragmentShader: `varying float brightness; void main(){ float d=length(gl_PointCoord-.5)*2.;
      float a=(1.-smoothstep(.05,1.,d))*brightness; gl_FragColor=vec4(vec3(.78,.84,.9)*brightness,a); }`,
  });
  const stars = new THREE.Points(geometry, material); stars.frustumCulled = false; group.add(stars);
  // Lambert has no broad specular lobe to turn the black ground into a grey horizon.
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(size*20000,size*20000), new THREE.MeshLambertMaterial({ color: 0x010102 }));
  ground.rotation.x = -Math.PI/2; ground.position.y = -.005 * size; ground.receiveShadow = true; group.add(ground);
  ground.visible = !aquatic;
  const ambient = new THREE.HemisphereLight(0xcddcff, 0x24252b, .7);
  const key = new THREE.DirectionalLight(0xffeddb, 2.4), rim = new THREE.DirectionalLight(0xb4caff, 2.1);
  key.castShadow = true; key.shadow.mapSize.set(1024,1024); key.shadow.normalBias = .015 * size;
  key.shadow.camera.left = key.shadow.camera.bottom = -size*4;
  key.shadow.camera.right = key.shadow.camera.top = size*4;
  key.shadow.camera.near = .1 * size; key.shadow.camera.far = size*40;
  group.add(ambient,key,key.target,rim,rim.target); scene.add(group);
  const groundTarget = new THREE.Vector3();
  const keyOffset = new THREE.Vector3(.7,1,.8).multiplyScalar(size*10);
  const rimOffset = new THREE.Vector3(-.8,.6,-1).multiplyScalar(size*10);
  return {
    update(dt, position, camera) {
      material.uniforms.time.value += dt;
      stars.position.copy(camera.position).multiplyScalar(.998);
      ground.position.x = camera.position.x; ground.position.z = camera.position.z;
      groundTarget.copy(position); key.target.position.copy(groundTarget); rim.target.position.copy(groundTarget);
      key.position.copy(groundTarget).add(keyOffset);
      rim.position.copy(groundTarget).add(rimOffset);
    },
    dispose() { scene.remove(group); geometry.dispose(); material.dispose(); ground.geometry.dispose(); ground.material.dispose(); key.shadow.map?.dispose(); key.dispose(); rim.dispose(); },
  };
}
