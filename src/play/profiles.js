// Explicit semantic contracts, never guesses based on an asset's display name.
export const CATEGORY_REQUIREMENTS = {
  quadruped: ['idle', 'walk', 'run', 'turnLeft', 'turnRight'],
  biped: ['idle', 'walk', 'run', 'turnLeft', 'turnRight'],
  aquatic: ['idle', 'swim', 'turnLeft', 'turnRight', 'ascend', 'descend'],
  slither: ['idle', 'slither', 'turnLeft', 'turnRight'],
};
export function requiredSemantics(profile) {
  return [...new Set([...(CATEGORY_REQUIREMENTS[profile.category] || []),
    ...(profile.flight ? ['takeoff', 'flight', 'glide', 'bankLeft', 'bankRight', 'land'] : []),
    ...(profile.jump ? ['jump'] : []), ...Object.keys(profile.specials || {})])];
}
export function readiness(profile, clips, model) {
  const errors = [];
  if (!profile) return ['No creature capability profile. This creation is available in the inspection viewer.'];
  if (profile.version !== 1 || !CATEGORY_REQUIREMENTS[profile.category]) errors.push('Unsupported capability profile version or anatomy.');
  const map = new Map(clips.map(c => [c.name, c]));
  for (const semantic of requiredSemantics(profile)) {
    const name = profile.animations?.[semantic] || profile.specials?.[semantic];
    const clip = map.get(name);
    if (!clip || clip.duration <= 0 || !clip.tracks.some(t => t.times.length > 1)) errors.push(`Missing keyed ${semantic} animation (${name || 'unmapped'}).`);
    else if (model && clip.tracks.some(t => !model.getObjectByName(t.name.slice(0, t.name.lastIndexOf('.'))))) errors.push(`Animation ${name} targets an incompatible rig.`);
  }
  const gait = profile.category === 'aquatic' ? 'swim' : profile.category === 'slither' ? 'slither' : 'walk';
  for (const key of [gait, gait === 'walk' ? 'run' : 'sprint', 'acceleration', 'turnRate']) if (!(profile.motion?.[key] > 0)) errors.push(`Invalid motion setting: ${key}.`);
  if (profile.flight && !(profile.motion.fly > 0)) errors.push('Missing flight speed.');
  for (const key of ['size','distance']) if (!Number.isFinite(profile.camera?.[key]) || profile.camera[key]<=0) errors.push(`Invalid camera ${key}.`);
  if (!Number.isFinite(profile.camera?.height)) errors.push('Missing camera target height.');
  if (profile.scale!==undefined && (!Number.isFinite(profile.scale)||profile.scale<=0)) errors.push('Invalid model scale.');
  return errors;
}
