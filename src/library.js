// Pure helpers for the creation library: ordering, search, and plain-language labels.

export function timeOf(item) {
  const time = Date.parse(item.updated ?? '');
  return Number.isNaN(time) ? null : time;
}

// Newest first. Creations without a date keep their shelf order at the end.
export function newestFirst(items) {
  return items
    .map((item, index) => ({ item, index, time: timeOf(item) }))
    .sort((a, b) => {
      if (a.time === null || b.time === null) return (a.time === null) - (b.time === null) || a.index - b.index;
      return b.time - a.time || a.index - b.index;
    })
    .map(({ item }) => item);
}

// Every word typed must appear in the name, ignoring case.
export function matchesSearch(item, query) {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const name = item.name.toLowerCase();
  return words.every(word => name.includes(word));
}

export function formatUpdated(iso) {
  const time = Date.parse(iso ?? '');
  if (Number.isNaN(time)) return 'Date not recorded';
  return new Date(time).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function sourceLabel(item) {
  switch (item.kind) {
    case 'active': return 'Made in Blender for this lab';
    case 'local': return 'Opened from this computer';
    case 'demo': return 'Built-in animation study';
    default: return item.sourceRepository ? `From ${item.sourceRepository}` : 'Shelf model';
  }
}

// The clip to play when a creation opens: one named Idle if there is one (glTF exporters often
// sort clips alphabetically), otherwise the first.
export function defaultClipIndex(clips) {
  const idle = clips.findIndex(clip => /^idle\b/i.test(clip?.name || ''));
  return Math.max(idle, 0);
}
