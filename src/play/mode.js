import * as THREE from 'three';
import { PlayInput } from './input.js';
import { CreatureController, LocomotionAnimator } from './controller.js';
import { createPlayWorld } from './world.js';
import { readiness } from './profiles.js';

export class PlayMode {
  constructor({scene,camera,orbit,renderer,grid,onExit}) { Object.assign(this,{scene,camera,orbit,renderer,grid,onExit}); this.active = false; this.target = new THREE.Vector3(); this.desired = new THREE.Vector3(); this.offset = new THREE.Vector3(); }
  enter(root,mixer,clips,profile) {
    const errors = readiness(profile,clips,root); if (errors.length) throw Error(errors.join(' '));
    const {scene,camera,orbit,grid} = this;
    this.root=root; this.mixer=mixer; this.profile=profile;
    this.saved = {
      rootPosition:root.position.clone(), rootQuaternion:root.quaternion.clone(), rootScale:root.scale.clone(),
      cameraPosition:camera.position.clone(), cameraQuaternion:camera.quaternion.clone(), target:orbit.target.clone(),
      near:camera.near, far:camera.far, autoRotate:orbit.autoRotate, min:orbit.minDistance, max:orbit.maxDistance,
      background:scene.background, fog:scene.fog, intensity:scene.environmentIntensity,
      exposure:this.renderer.toneMappingExposure,
      visibility: scene.children.filter(o=>o.name==='LabLighting'||o.name==='LabShadowCatcher'||o===grid).map(o=>[o,o.visible]),
    };
    this.saved.visibility.forEach(([o])=>o.visible=false);
    root.position.set(0,0,0); root.rotation.set(0,0,0); root.scale.setScalar(profile.scale || 1);
    mixer.stopAllAction(); mixer.update(0);
    // Bind-space feet define the ground. Do not fit to the current wingbeat pose.
    this.groundOffset=profile.groundOffset || 0;
    this.size=profile.camera.size; this.zoom=profile.camera.distance;
    this.cameraYaw=.35; this.cameraPitch=.22; this.airFrame=0;
    this.controller=new CreatureController(profile); this.animator=new LocomotionAnimator(mixer,clips,profile);
    this.world=createPlayWorld(scene,this.size,profile.category==='aquatic');
    scene.background=new THREE.Color(0x000001); scene.fog=new THREE.FogExp2(0x000001,.008/this.size);
    scene.environmentIntensity=.3; this.renderer.toneMappingExposure=1;
    camera.near=.03*this.size; camera.far=4000*this.size; camera.updateProjectionMatrix();
    orbit.enabled=false; orbit.autoRotate=false;
    this.input=new PlayInput(this.renderer.domElement,()=>this.exit());
    this.active=true; document.body.classList.add('play-mode');
    this.follow(0,true); document.activeElement?.blur();
  }
  follow(dt,snap=false) {
    const c=this.controller,p=this.profile, camera=this.camera;
    const airborne=['takeoff','flight','glide','land'].includes(c.state);
    this.airFrame=THREE.MathUtils.damp(this.airFrame,airborne?1:0,2.5,dt);
    this.target.copy(c.position); this.target.y+=p.camera.height+this.airFrame*this.size*.85;
    this.offset.set(Math.sin(this.cameraYaw)*Math.cos(this.cameraPitch),Math.sin(this.cameraPitch),Math.cos(this.cameraYaw)*Math.cos(this.cameraPitch));
    this.desired.copy(this.target).addScaledVector(this.offset,this.zoom*(1+.2*this.airFrame+.12*c.speed/(p.motion.run || p.motion.sprint)));
    if (p.category!=='aquatic') this.desired.y=Math.max(this.size*.3,this.desired.y);
    camera.position.lerp(this.desired,snap?1:1-Math.exp(-dt*7));
    camera.lookAt(this.target);
  }
  update(dt, externalInput) {
    if (!this.active) return;
    const i=externalInput || this.input.poll(); if(!this.active)return;
    this.cameraYaw-=(i.lookX || 0)+(i.padLookX || 0)*dt*2.2;
    this.cameraPitch=THREE.MathUtils.clamp(this.cameraPitch+(i.lookY || 0)+(i.padLookY || 0)*dt*1.7,-.5,1.15);
    this.zoom=THREE.MathUtils.clamp(this.zoom*Math.exp((i.zoom || 0)*.001),this.profile.camera.distance*.65,this.size*12);
    const c=this.controller.update(dt,i,this.cameraYaw,this.animator.durations);
    this.root.position.copy(c.position); this.root.position.y+=this.groundOffset;
    this.root.rotation.set(c.pitch,c.yaw+(this.profile.forwardYaw || 0),c.bank,'YXZ');
    this.animator.update(dt,c); this.follow(dt); this.world.update(dt,c.position,this.camera);
  }
  exit() {
    if (!this.active) return; this.active=false;
    const s=this.saved,{root,camera,scene,orbit}=this;
    this.input.dispose(); this.animator.dispose(); this.mixer.stopAllAction(); this.world.dispose();
    root.position.copy(s.rootPosition); root.quaternion.copy(s.rootQuaternion); root.scale.copy(s.rootScale);
    orbit.target.copy(s.target); orbit.enabled=true; orbit.autoRotate=s.autoRotate; orbit.minDistance=s.min; orbit.maxDistance=s.max;
    // Clear OrbitControls' old damping residuals before restoring the camera.
    const damping=orbit.enableDamping; orbit.enableDamping=false;
    camera.position.copy(s.cameraPosition); orbit.update(); orbit.enableDamping=damping;
    camera.position.copy(s.cameraPosition); camera.quaternion.copy(s.cameraQuaternion); camera.near=s.near; camera.far=s.far; camera.updateProjectionMatrix();
    scene.background=s.background; scene.fog=s.fog; scene.environmentIntensity=s.intensity;
    this.renderer.toneMappingExposure=s.exposure; s.visibility.forEach(([o,v])=>o.visible=v);
    document.body.classList.remove('play-mode'); this.onExit?.();
  }
  describe() {
    const c=this.controller;
    return { mode:this.active?'play':'viewer', axes:'Y up; forward -Z at yaw 0; units metres',
      ...(this.active?{state:c.state,position:c.position.toArray(),speed:c.speed,yaw:c.yaw,bank:c.bank,special:c.special?.name || null,animation:this.animator.primary,camera:this.camera.position.toArray()}:{}),
    };
  }
}
