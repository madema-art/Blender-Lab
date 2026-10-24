export function analog(value, deadZone = .16) {
  const magnitude = Math.max(0, (Math.abs(value || 0) - deadZone) / (1 - deadZone));
  return Math.sign(value || 0) * magnitude * magnitude;
}
export function readPad(pad, out) {
  out.x = analog(pad?.axes[0]); out.y = -analog(pad?.axes[1]);
  out.lookX = analog(pad?.axes[2]); out.lookY = analog(pad?.axes[3]);
  const b = i => pad?.buttons[i]?.value || 0;
  out.sprint = b(7); out.vertical = b(7) - b(6);
  out.jump = b(0) > .5; out.land = b(1) > .5;
  out.special = b(2) > .5; out.glide = b(3) > .5; out.exit = b(9) > .5;
  return out;
}
export class PlayInput {
  constructor(canvas, exit) {
    this.canvas = canvas; this.exit = exit; this.keys = new Set(); this.previous = {};
    this.pad = {}; this.frame = {}; this.dx = 0; this.dy = 0; this.zoom = 0;
    this.controller = new AbortController(); const options = { signal: this.controller.signal };
    window.addEventListener('keydown', e => {
      if (e.code === 'Escape') { e.preventDefault(); this.exit(); return; }
      if (['Space','KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','KeyR','KeyG','KeyL','ShiftLeft','ShiftRight'].includes(e.code)) { e.preventDefault(); this.keys.add(e.code); }
    }, options);
    window.addEventListener('keyup', e => this.keys.delete(e.code), options);
    window.addEventListener('blur', () => this.clear(), options);
    document.addEventListener('visibilitychange', () => { if (document.hidden) this.clear(); }, options);
    canvas.addEventListener('pointerdown', e => { this.dragging = true; canvas.setPointerCapture?.(e.pointerId); }, options);
    canvas.addEventListener('pointerup', () => { this.dragging = false; }, options);
    canvas.addEventListener('pointermove', e => {
      if (this.dragging || document.pointerLockElement === canvas) { this.dx += e.movementX; this.dy += e.movementY; }
    }, options);
    canvas.addEventListener('dblclick', () => { canvas.requestPointerLock?.()?.catch?.(() => {}); }, options);
    canvas.addEventListener('wheel', e => { e.preventDefault(); this.zoom += e.deltaY; }, { ...options, passive: false });
    canvas.addEventListener('contextmenu', e => e.preventDefault(), options);
  }
  clear() { this.keys.clear(); this.dragging = false; this.dx = this.dy = this.zoom = 0; this.previous = {}; }
  poll() {
    const pads = navigator.getGamepads?.() || [];
    const pad = Array.from(pads).find(p => p?.connected && p.mapping === 'standard');
    readPad(pad, this.pad); const p = this.pad, k = this.keys, f = this.frame;
    f.x = (Number(k.has('KeyD')) - Number(k.has('KeyA'))) || p.x;
    f.y = (Number(k.has('KeyW')) - Number(k.has('KeyS'))) || p.y;
    const length = Math.hypot(f.x, f.y); if (length > 1) { f.x /= length; f.y /= length; }
    f.sprint = k.has('ShiftLeft') || k.has('ShiftRight') || p.sprint > .3;
    f.vertical = (Number(k.has('KeyE')) - Number(k.has('KeyQ'))) || p.vertical;
    f.glide = k.has('KeyG') || p.glide;
    for (const [name, key] of [['jump','Space'],['land','KeyL'],['special','KeyR']]) {
      const down = k.has(key) || p[name]; f[name] = down && !this.previous[name]; this.previous[name] = down;
    }
    if (p.exit && !this.previous.exit) this.exit(); this.previous.exit = p.exit;
    f.lookX = this.dx * .004; f.lookY = this.dy * .004; f.padLookX = p.lookX; f.padLookY = p.lookY;
    f.zoom = this.zoom; this.dx = this.dy = this.zoom = 0;
    return f;
  }
  dispose() { this.controller.abort(); this.clear(); if (document.pointerLockElement === this.canvas) document.exitPointerLock(); }
}
