import * as THREE from 'three';

const damp = (a, b, rate, dt) => THREE.MathUtils.damp(a, b, rate, dt);
const angleDelta = (a, b) => Math.atan2(Math.sin(b-a), Math.cos(b-a));

// Pure world controller: +Y up, forward -Z at yaw zero. Animation owns the rig;
// this controller owns the wrapper's world displacement, never the bones.
export class CreatureController {
  constructor(profile) { this.profile = profile; this.position = new THREE.Vector3(); this.velocity = new THREE.Vector3(); this.yaw = 0; this.bank = 0; this.pitch = 0; this.speed = 0; this.state = 'idle'; this.elapsed = 0; this.special = null; }
  transition(state) { if (state !== this.state) { this.state = state; this.elapsed = 0; } }
  update(dt, input, cameraYaw, durations = {}) {
    const p = this.profile, m = p.motion; this.elapsed += dt;
    const aquatic=p.category==='aquatic', slither=p.category==='slither';
    const walkSpeed=m.walk || m.swim || m.slither;
    const runSpeed=m.run || m.sprint;
    if (this.special) { this.special.time += dt; if (this.special.time >= (durations[this.special.name] || 2)) this.special = null; }
    if (input.special && !this.special && this.state === 'idle') {
      const name = Object.keys(p.specials || {})[0]; if (name) this.special = { name, time: 0 };
    }
    if (input.jump && !this.special && !['takeoff','flight','glide','land','jump'].includes(this.state)) {
      if (p.flight) this.transition('takeoff');
      else if (p.jump) { this.transition('jump'); this.velocity.y = m.jump || 4; }
    }
    if (p.flight && ['flight','glide'].includes(this.state) && input.land) this.transition('land');
    const magnitude = Math.min(1, Math.hypot(input.x || 0, input.y || 0));
    const airborne = ['flight','glide','takeoff','land'].includes(this.state);
    let turn = 0;
    if (magnitude > .02) {
      const targetYaw = cameraYaw + Math.atan2(-input.x, input.y);
      turn = angleDelta(this.yaw, targetYaw);
      this.yaw += THREE.MathUtils.clamp(turn, -m.turnRate * dt, m.turnRate * dt);
    }
    const modeSpeed = airborne ? m.fly : input.sprint ? runSpeed : walkSpeed;
    const restrained = this.special || ['takeoff','land'].includes(this.state);
    this.speed = damp(this.speed, restrained ? 0 : modeSpeed * magnitude, m.acceleration, dt);
    this.velocity.x = -Math.sin(this.yaw) * this.speed; this.velocity.z = -Math.cos(this.yaw) * this.speed;
    if (this.state === 'takeoff') {
      const t = Math.min(1, this.elapsed / (durations.takeoff || 2));
      this.position.y = m.takeoffHeight * THREE.MathUtils.smoothstep(t, .25, 1);
      if (t === 1) this.transition('flight');
    } else if (this.state === 'land') {
      // Approach first; only play the touchdown clip once close enough to ground.
      this.position.y = Math.max(0, this.position.y - (m.descend || 2) * dt);
      if (this.position.y > .01) this.elapsed = 0;
      else if (this.elapsed >= (durations.land || 2)) this.transition('idle');
    } else if (airborne) {
      this.transition(input.glide ? 'glide' : 'flight');
      this.velocity.y = damp(this.velocity.y, (input.vertical || 0) * (m.climb || 2), 4, dt);
      this.position.y = Math.max(.2, this.position.y + this.velocity.y * dt);
    } else if (this.state === 'jump') {
      this.velocity.y -= 9.81 * dt; this.position.y += this.velocity.y * dt;
      if (this.position.y <= 0) { this.position.y = 0; this.velocity.y = 0; this.transition('idle'); }
    } else if (aquatic && !this.special) {
      this.velocity.y=damp(this.velocity.y,(input.vertical || 0)*(m.vertical || m.swim),4,dt);
      this.position.y+=this.velocity.y*dt;
      this.transition(Math.abs(this.velocity.y)>.05 ? this.velocity.y>0?'ascend':'descend' : this.speed>.03?'swim':'idle');
    } else if (!this.special) {
      this.velocity.y = 0;
      this.transition(slither ? this.speed>.03?'slither':'idle' : this.speed > m.walk * 1.15 ? 'run' : this.speed > .03 ? 'walk' : 'idle');
    }
    this.position.x += this.velocity.x * dt; this.position.z += this.velocity.z * dt;
    this.bank = damp(this.bank, airborne ? THREE.MathUtils.clamp(turn * -.35, -.45, .45) : 0, 4, dt);
    this.pitch = damp(this.pitch, airborne ? -(input.vertical || 0) * .12 : 0, 4, dt);
    this.turn = turn;
    return this;
  }
}

export class LocomotionAnimator {
  constructor(mixer, clips, profile) {
    this.mixer = mixer; this.profile = profile; this.actions = {}; this.durations = {};
    for (const [semantic, name] of Object.entries({ ...profile.animations, ...profile.specials })) {
      const clip = clips.find(c => c.name === name); if (!clip) continue;
      const a = mixer.clipAction(clip); a.reset().setEffectiveWeight(0).play();
      if (['takeoff','land','jump', ...Object.keys(profile.specials || {})].includes(semantic)) { a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = true; }
      this.actions[semantic] = a; this.durations[semantic] = clip.duration;
    }
    this.weights = {}; this.primary = null; this.cycle = 0; this.entries = Object.entries(this.actions);
  }
  update(dt, c) {
    let primary = c.special?.name || c.state;
    if (['flight','glide'].includes(primary) && Math.abs(c.bank) > .18 && !c.special) primary = c.bank > 0 ? 'bankRight' : 'bankLeft';
    if (primary === 'walk' && Math.abs(c.turn) > .65 && c.speed < this.profile.motion.walk * .8) primary = c.turn > 0 ? 'turnLeft' : 'turnRight';
    if (['swim','slither'].includes(primary) && Math.abs(c.turn)>.65) primary=c.turn>0?'turnLeft':'turnRight';
    if (primary !== this.primary) {
      const a = this.actions[primary]; if (a && !['walk','run','turnLeft','turnRight'].includes(primary)) { a.reset().play(); }
      this.primary = primary;
    }
    const blend = 1 - Math.exp(-dt / (this.profile.blend || .18));
    const runMix = THREE.MathUtils.smoothstep(c.speed, this.profile.motion.walk * .85, this.profile.motion.walk * 1.7);
    const frequency = THREE.MathUtils.lerp(c.speed/(this.profile.motion.walk*this.durations.walk),c.speed/(this.profile.motion.run*this.durations.run),runMix);
    this.cycle = (this.cycle + dt * (Number.isFinite(frequency) ? frequency : 0)) % 1;
    for (const [semantic, a] of this.entries) {
      let target = semantic === primary ? 1 : 0;
      // Weight walk and run around the measured speed. Both stay phase aligned.
      if (['walk','run'].includes(primary) && ['walk','run'].includes(semantic)) {
        const mix = THREE.MathUtils.smoothstep(c.speed, this.profile.motion.walk * .85, this.profile.motion.walk * 1.7);
        target = semantic === 'run' ? mix : 1-mix;
      }
      this.weights[semantic] = THREE.MathUtils.lerp(this.weights[semantic] || 0, target, blend);
      a.setEffectiveWeight(this.weights[semantic]);
      const nominal = this.profile.motion[semantic];
      const gait = ['walk','run','turnLeft','turnRight'].includes(semantic);
      a.setEffectiveTimeScale(gait ? 0 : nominal ? Math.max(.15,c.speed/nominal) : 1);
      if (gait) a.time = this.cycle*this.durations[semantic];
      if (semantic === 'land' && c.position.y > .01) a.time = 0;
    }
    this.mixer.update(dt);
  }
  dispose() { for (const a of Object.values(this.actions)) a.stop(); }
}
