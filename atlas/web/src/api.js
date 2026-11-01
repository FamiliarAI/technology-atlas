const get = async (path) => {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
};

export const loadAtlas = async () => {
  const [catalog, progress] = await Promise.all([get('/api/catalog'), get('/api/progress')]);
  const fields = catalog.fields.map((f) => ({ ...f, items: [] }));
  const byField = Object.fromEntries(fields.map((f) => [f.id, f]));
  const items = catalog.innovations.map((i) => {
    const p = progress[i.id] || { status: [], count: 0 };
    const met = p.status.filter((s) => s === 'met').length;
    const moving = p.status.filter((s) => s === 'in_progress').length;
    return { ...i, status: p.status, progressCount: p.count, score: met * 2 + moving, color: byField[i.field].color };
  });
  // Within a lane, the furthest-advanced innovations come first; ties keep ID order.
  for (const i of items) byField[i.field].items.push(i);
  for (const f of fields) f.items.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  const related = {};
  for (const c of catalog.connections) {
    (related[c.source] ||= new Set()).add(c.target);
    (related[c.target] ||= new Set()).add(c.source);
  }
  return { fields, items: Object.fromEntries(items.map((i) => [i.id, i])), connections: catalog.connections, related, asOf: catalog.as_of };
};

export const loadInnovation = (id) => get('/api/innovations/' + encodeURIComponent(id));
