import * as THREE from 'three';
export function makeDemo() {
  const moth = new THREE.Group(); moth.name = 'Moth';
  const bodyMat = new THREE.MeshStandardMaterial({color:0xcce2a9,roughness:.65});
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(.14,.7,8,16),bodyMat); body.rotation.x = Math.PI / 2; moth.add(body);
  const head = new THREE.Mesh(new THREE.SphereGeometry(.2,20,12),bodyMat); head.position.z=.58; moth.add(head);
  for(const side of [-1,1]) {
    const wing = new THREE.Group(); wing.name = side < 0 ? 'LeftWing' : 'RightWing'; wing.position.x = side * .12;
    const shape = new THREE.Shape(); shape.moveTo(0,.32); shape.bezierCurveTo(.6,.85,1.65,.8,1.45,.1); shape.bezierCurveTo(1.25,-.2,.95,-.32,1.05,-.65); shape.bezierCurveTo(.65,-1,.2,-.65,0,-.3);
    const mesh = new THREE.Mesh(new THREE.ExtrudeGeometry(shape,{depth:.035,bevelEnabled:true,bevelThickness:.025,bevelSize:.025,bevelSegments:2,steps:1}),new THREE.MeshStandardMaterial({color:side<0?0xe0a25c:0xeac17e,roughness:.6,side:THREE.DoubleSide}));
    mesh.rotation.x=-Math.PI/2; mesh.scale.x=side; wing.add(mesh);
    const spot = new THREE.Mesh(new THREE.CircleGeometry(.19,32),new THREE.MeshStandardMaterial({color:0x485e51,side:THREE.DoubleSide})); spot.rotation.x=-Math.PI/2; spot.position.set(side*.95,.07,.0); wing.add(spot);
    moth.add(wing);
    const antenna = new THREE.Mesh(new THREE.CylinderGeometry(.012,.018,.55,8),bodyMat); antenna.position.set(side*.18,.12,.84); antenna.rotation.set(.8,0,side*-.5); moth.add(antenna);
  }
  const quaternionTrack = (name, times, angles) => new THREE.QuaternionKeyframeTrack(`${name}.quaternion`,times,angles.flatMap(angle => new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),angle).toArray()));
  const flutter = new THREE.AnimationClip('Flutter',1.6,[quaternionTrack('LeftWing',[0,.4,.8,1.2,1.6],[.12,.65,.12,.65,.12]),quaternionTrack('RightWing',[0,.4,.8,1.2,1.6],[-.12,-.65,-.12,-.65,-.12]),new THREE.VectorKeyframeTrack('Moth.position',[0,.8,1.6],[0,.05,0,0,.16,0,0,.05,0])]);
  const glide = new THREE.AnimationClip('Glide',4,[quaternionTrack('Moth',[0,1,2,3,4],[0,.13,0,-.13,0])]);
  return {scene:moth,animations:[flutter,glide]};
}
