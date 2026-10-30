'use strict';
let G = null, GI = null, S = null, A = null, C = null, P = null, cmpWith = null, drag = null, tab = 'order', sel = null, flt = 'all', q = '', lastMissing = [];
const REPO_LINK = 'https://github.com/Ronin1mil/My-Mod-Manager/';
const $ = i => document.getElementById(i);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
let gen = 0, logFile = '', reported = 0;
class Stale extends Error {}   // an answer for a game/playset the user has already left; dropped silently
const report = (message, stack, where) => {
  if (reported++ > 20) return;
  try { fetch('/api/client-error', {method: 'POST', headers: {'Content-Type': 'application/json'}, keepalive: true,
    body: JSON.stringify({message: String(message), stack: String(stack || ''), where: where || '', game: G || ''})})
    .then(r => r.json()).then(j => { if (j.log_file) logFile = j.log_file; }).catch(() => {}); } catch (e) { /* nothing more to do */ }
};
const call = async (url, b) => {
  let r, j;
  try {
    r = await fetch(url, b === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)});
    j = await r.json();
  } catch (err) {  // server gone, or an answer that is not JSON
    const e = new Error(`Could not reach Ronin Mod Manager (${err.message}). Is its window still open?`);
    e.network = true; throw e;
  }
  if (!r.ok) { const e = new Error(j.error || 'Request failed'); e.body = j; e.status = r.status; if (j.log_file) logFile = j.log_file; throw e; }
  return j;
};
const api = async (p, b) => {
  if (S && S.no_mods && /^playsets\/nomods\/(update|autosort|enable|enable_all|disable_all|prune|delete|save-preset)$/.test(p)) {   // the built-in playset is read-only
    toast('The "No mods" playset cannot be changed. Press + New to make a playset of your own.', true); throw new Stale();
  }
  const g = gen, r = await call(`/api/${G}/${p}`, b); if (g !== gen) throw new Stale(); return r; };   // current game
const app = (p, b) => call('/api/' + p, b);        // app-wide
const GNAME = () => (S && S.game ? S.game.name : G);
const M = id => S.mods.find(m => m.id === id);
const cur = () => (S && S.playsets ? S.playsets.find(p => p.id === S.active) || (S.no_mods && S.no_mods.id === S.active ? S.no_mods : null) : null);
const nameOf = id => { const m = M(id); return id === '__vanilla__' ? 'Base game' : m ? m.name : id; };
const KINDS = {file: 'File', definition: 'Definition', patch: 'Patch', replace: 'Replace path', localization: 'Localization', vanilla: 'Base game'};
let toastT, U = null, T = null, tq = '';
function updPanel() {
  if (!U) return '';
  const up = U.filter(x => x.status === 'update'), unk = U.filter(x => x.status === 'unknown').length;
  return `<div class="pre"><h3>Mod updates <span class="b ${up.length ? 'warn' : 'ok'}">${up.length ? up.length + ' available' : 'all up to date'}</span></h3>` +
    (up.map(x => `<div class="row static"><span class="nm" style="cursor:default">${esc(x.name)}</span><span class="b">updated ${esc(new Date(x.remote * 1000).toLocaleDateString())}</span>
      <button class="sm" data-dl1="${esc(x.remote_id)}">Open in Steam</button></div>`).join('')) +
    (unk ? `<p class="mut">${unk} mod(s) could not be compared (no Steam record yet, or the item is hidden).</p>` : '') +
    '<p class="mut">Steam normally downloads updates itself; open the page only if it has not.</p></div>';
}
// ---- file trees ----
function mountTree(box, entries) {
  const root = {d: {}, f: []};
  for (const e of entries) { let n = root; const parts = e.path.split('/'); for (const part of parts.slice(0, -1)) n = n.d[part] ||= {d: {}, f: []}; n.f.push([parts[parts.length - 1], e.tag || '']); }
  const count = n => n.f.length + Object.values(n.d).reduce((a, c) => a + count(c), 0);
  const nodes = new Map();
  const kids = (n, key) => Object.keys(n.d).sort().map(k => { nodes.set(key + k, n.d[k]); return `<details data-k="${esc(key + k)}"><summary>${esc(k)}/ <span class="mut">${count(n.d[k])}</span></summary></details>`; }).join('') +
    n.f.sort((a, b) => a[0].localeCompare(b[0])).map(([nm, tag]) => `<div class="tf">${esc(nm)} ${tag}</div>`).join('');
  box.className = 'tree'; box.innerHTML = kids(root, '');
  box.addEventListener('toggle', e => { const d = e.target; if (d.open && !d.dataset.done) { d.dataset.done = 1; d.insertAdjacentHTML('beforeend', kids(nodes.get(d.dataset.k), d.dataset.k + '/')); } }, true);
}
async function loadFiles() { T = await api(`tree/${S.active}`); if (tab === 'files') render(); }
function viewFiles() {
  if (!T) { $('view').innerHTML = '<div class="empty">Loading…</div>'; loadFiles(); return; }
  const f = tq.toLowerCase(), list = T.files.filter(([p]) => !f || p.toLowerCase().includes(f)).slice(0, 4000);
  $('view').innerHTML = `<div class="bar"><input type="search" id="tq" placeholder="Filter files…" value="${esc(tq)}"></div>
    <p class="mut">What the game sees: every file of the enabled mods in load order, tagged with the mod that wins. ${T.total} files${list.length < T.total ? ` · showing ${list.length}` : ''}${T.truncated ? ' · list cut off' : ''}. <span class="b">2×</span> = more than one mod has this file.</p><div id="ft"></div>`;
  mountTree($('ft'), list.map(([p, w, c]) => ({path: p, tag: `<span class="mut">${esc(nameOf(T.mods[w]))}</span>${c > 1 ? ` <span class="b warn">${c}×</span>` : ''}`})));
  const qi = $('tq'); qi.oninput = () => { tq = qi.value; const pos = qi.selectionStart; viewFiles(); const n = $('tq'); n.focus(); n.setSelectionRange(pos, pos); };
}
function toast(msg, bad) {
  const t = $('toast'); t.textContent = msg; t.className = 'on' + (bad ? ' bad' : '');
  clearTimeout(toastT); toastT = setTimeout(() => t.className = '', 4500);
}
const guard = fn => async (...a) => { try { await fn(...a); } catch (e) { if (!(e instanceof Stale)) fail(e, fn.name); } };
// Show the real error where the user can see it, and keep a copy in the log file (see the Documents folder).
function fail(e, where) {
  if (e instanceof Stale) return;
  toast(e.message, true);
  if (e.status >= 500 || !e.status) report(e.message, e.stack, where);
  if (e.status >= 500 || e.network) showFatal(e);
}
function showFatal(e) {
  const b = $('banner'); if (!b) return;
  b.hidden = false; b.className = 'bad';
  b.innerHTML = `<b>Something went wrong:</b> ${esc(e.message)}<br><span class="mut">Details were saved to <code>${esc(logFile || 'your Documents folder (Ronin Mod Manager/RoninModManager-errors.log)')}</code>.</span> <button class="sm" id="bn-x">Hide</button>`;
  $('bn-x').onclick = () => { b.hidden = true; };
}
window.addEventListener('error', ev => { if (ev.error instanceof Stale) return; report(ev.message, ev.error && ev.error.stack, `${ev.filename}:${ev.lineno}`); showFatal(new Error(ev.message)); });
window.addEventListener('unhandledrejection', ev => { const e = ev.reason; if (e instanceof Stale) { ev.preventDefault(); return; } report((e && e.message) || e, e && e.stack, 'promise'); });

async function load(rescanMsg) {
  T = null; P = null;
  S = await api('state');
  if (!cur()) { S.active = S.playsets.length ? S.playsets[0].id : S.no_mods.id; await api(`playsets/${S.active}/activate`, {}); }
  if (rescanMsg) {
    const d = S.diff, bits = [d.added && `${d.added} new`, d.updated && `${d.updated} updated`, d.removed && `${d.removed} removed`].filter(Boolean);
    toast(bits.length ? `Scan: ${bits.join(', ')} (${d.total} mods)` : `Scan: no changes (${d.total} mods)`);
  }
  setLogo(G); showImportButton(); applyUI();
  document.title = GNAME() + ' · Ronin Mod Manager';
  render(); analyse(); banner(); pollUpdate();
  if (S.setup_needed && !setupShown) { setupShown = true; openPaths(true); }
}
let polls = 0, setupShown = false;
function pollDownload(id) {
  setTimeout(guard(async () => {
    const job = (await api('downloads')).find(j => j.id === id), el = $('dlstat');
    if (!job) return;
    const items = Object.entries(job.items), done = items.filter(([, i]) => i.state === 'done').length;
    if (el) el.innerHTML = `steamcmd: ${done}/${items.length} downloaded` + items.filter(([, i]) => i.state === 'failed').map(([k, i]) => `<div class="err">#${esc(k)}: ${esc(i.message)}</div>`).join('') +
      (job.state === 'done' ? `<div class="ok">Done. Files are in <code>${esc(job.dir)}</code>${S.workshop_dir === job.dir ? '' : ' — add that folder as your Workshop folder in Settings so they are found.'}</div>` : '');
    if (job.state === 'queued' || job.state === 'running') pollDownload(id);
    else if (done) { await load(true); }
  }), 1500);
}
function pollUpdate() {
  if (!GI.update_pending || polls >= 15) return;
  polls++;
  setTimeout(guard(async () => { const st = await app('games'); GI.update = st.update; GI.update_pending = st.update_pending; GI.settings = st.settings; banner(); pollUpdate(); }), 1000);
}
async function analyse() {
  const id = S.active, r = await api('analyse/' + id + '?fast=1');   // load-order problems: quick
  if (!S || id !== S.active) return;
  const keep = A && A.pid === id ? A : null;
  A = {...r, pid: id, conflicts: keep ? keep.conflicts : [], counts: keep ? keep.counts : {}, pending: true};
  render();
  const c = await api('conflicts/' + id);                          // file/definition conflicts: slow, loaded behind
  if (!S || id !== S.active || !A) return;
  Object.assign(A, c, {pending: false}); render();
}
let patchQ = Promise.resolve();
// Changes to the playset run one after another, each building on the answer to the previous one: a quick second click
// must add to the first click's result, not overwrite it. `fields` may be a function of the current playset.
function patch(fields) {
  const run = async () => {
    const p = cur(); if (!p) return;
    Object.assign(p, await api(`playsets/${p.id}/update`, typeof fields === 'function' ? fields(p) : fields));
    render(); analyse();
    if (tab === 'compare') loadCompare();
  };
  patchQ = patchQ.then(run, run);
  return patchQ;
}
const WARN_CODES = {missing_module: 'Mod files missing', version_mismatch: 'Game version mismatch', metadata_error: 'Damaged mod metadata',
  missing_dependency: 'Missing dependency', disabled_dependency: 'Disabled dependency', incompatible: 'Incompatible mods',
  duplicate: 'Duplicate mod names', cycle: 'Dependency cycle', wrong_order: 'Wrong load order'};
const wkey = () => 'mm-warn-' + G;
const hiddenCodes = () => { try { return JSON.parse(localStorage.getItem(wkey()) || '[]'); } catch { return []; } };
const visIssues = () => { const h = hiddenCodes(); return A ? A.issues.filter(i => !h.includes(i.code)) : []; };
const issuesOf = id => (A ? A.issues.filter(i => i.module === id) : []);
function worst(id) {
  const is = issuesOf(id);
  return is.some(i => i.severity === 'error') ? 'err' : is.length ? 'warn' : '';
}
function badges(m, before = '') {   // `before` (a warning or error) sits just left of the Workshop/Local tag so that tag always ends the row
  return (m.change === 'new' ? '<span class="b new">NEW</span>' : m.change === 'updated' ? '<span class="b new">UPDATED</span>' : '') +
    (m.multiplayer_synchronized === false ? '<span class="b warn" title="Not multiplayer synchronized">MP-unsafe</span>' : '') +
    (m.exists ? '' : '<span class="b err">missing</span>') + before + `<span class="b">${esc(m.source)}</span>`;
}

// A redraw between mouse-down and mouse-up replaces the element under the pointer and the click is lost (the late
// analysis result and the window-focus rescan both redraw). So a redraw asked for while a button is held waits for the
// release; the click that follows the release draws by itself, and a redraw still waiting runs just after it.
let pressed = false, redrawLater = false;
const release = () => {
  pressed = false;
  if (redrawLater) setTimeout(() => { if (redrawLater && !pressed) render(); }, 30);
};
document.addEventListener('pointerdown', () => { pressed = true; setTimeout(release, 4000); }, true);   // the timer: never wait forever
['pointerup', 'pointercancel', 'dragend'].forEach(t => document.addEventListener(t, release, true));
function render() {
  if (pressed) { redrawLater = true; return; }
  redrawLater = false;
  if (!S || !cur()) return;
  const p = cur(), errs = visIssues().filter(i => i.severity === 'error').length; if (!p) return;
  $('pslist').innerHTML = S.playsets.slice().sort((a, b) => !!b.favorite - !!a.favorite).map(x => `<div class="ps ${x.id === S.active ? 'on' : ''}" data-ps="${esc(x.id)}"><button class="star ${x.favorite ? 'on' : ''}" data-favps="${esc(x.id)}" title="${x.favorite ? 'Remove from favourites' : 'Favourite: keep this playset at the top'}" aria-label="Favourite">${x.favorite ? '★' : '☆'}</button><span class="grow">${esc(x.name)}</span><span class="mut">${x.mods.length - x.disabled.length}</span></div>`).join('');
  $('psfixed').innerHTML = `<div class="ps fixed ${S.no_mods.id === S.active ? 'on' : ''}" data-ps="${esc(S.no_mods.id)}" title="Starts the game with no mods: use it to check whether a problem comes from a mod or from the game"><span>No mods</span><span class="mut">${S.no_mods.mods.length || ''}</span></div>`;
  document.body.classList.toggle('nomods', !!p.virtual);
  $('title').textContent = p.name;
  $('auto').checked = p.auto_sort;
  $('sortnow').style.display = p.auto_sort ? 'none' : '';
  const nIss = visIssues().length, nCon = A && !A.pending ? A.conflicts.filter(x => x.severity !== 'info' && !x.vanilla).length : 0;
  $('tabs').innerHTML = [['order', 'Load order'], ['library', `Library (${S.mods.length})`], ['problems', `Warnings${nIss ? ` (${nIss})` : ''}`], ['conflicts', `Conflicts${A && A.pending ? ' …' : nCon ? ` (${nCon})` : ''}`], ['files', 'Files'], ['compare', 'Compare'], ['presets', 'Presets']].filter(([k]) => k !== 'conflicts' || S.game.has_conflicts)
    .map(([k, l]) => `<button data-tab="${k}" class="${tab === k ? 'on' : ''}">${l}</button>`).join('');
  const active = p.mods.length - p.disabled.length;
  $('status').innerHTML = `${esc(GNAME())}${S.game_version ? ` ${esc(S.game_version)}` : ''} · ${active} mod${active === 1 ? '' : 's'} active` +
    (errs ? ` · <span class="err">${errs} error${errs === 1 ? '' : 's'}</span>` : A && nIss ? ` · <span class="warn">${nIss} warning${nIss === 1 ? '' : 's'}</span>` : '');
  ({order: viewOrder, library: viewLibrary, problems: viewProblems, conflicts: viewConflicts, compare: viewCompare, presets: viewPresets, files: viewFiles})[tab](p);
  drawer();
}

function viewOrder(p) {
  if (p.virtual) {
    $('view').innerHTML = `<div class="empty">${esc(p.notes)}<br><span class="mut">Press ▶ Play to start ${esc(GNAME())} without mods.${p.mods.length ? ' (The game\'s own required modules are still loaded.)' : ''}</span></div>`;
    return;
  }
  const bar = `<div class="bar"><span class="mut">Top loads first, bottom wins.</span><span class="grow"></span>
    <button class="sm" data-bulk="enable_all">Enable all</button><button class="sm" data-bulk="disable_all">Disable all</button>
    <button class="sm" data-bulk="prune" title="Remove mods that are no longer installed">Prune</button></div>`;
  $('view').innerHTML = bar + p.mods.map((id, i) => {
    const m = M(id), off = p.disabled.includes(id), w = worst(id);
    return `<div class="row ${off ? 'off' : ''} ${id === sel ? 'sel' : ''}" data-i="${i}">
      <span class="h" draggable="true">⠿</span><span class="n">${i + 1}</span>
      <label class="tick"><input type="checkbox" data-tog="${esc(id)}" ${off ? '' : 'checked'}></label>
      <span class="nm" data-sel="${esc(id)}">${esc(m ? m.name : id + ' (not installed)')}</span>
      ${m ? badges(m, w && !off ? `<span class="b ${w}">${w === 'err' ? 'error' : 'warning'}</span>` : '') : (w && !off ? `<span class="b ${w}">${w === 'err' ? 'error' : 'warning'}</span>` : '')}
      <button class="sm" data-mv="${i},-1">↑</button><button class="sm" data-mv="${i},1">↓</button><button class="sm" data-rm="${esc(id)}">✕</button></div>`;
  }).join('') || '<div class="empty">This playset is empty.<br>Add mods from the Library tab.</div>';
}

// Library sorting: by name, by where the mod comes from (Workshop / Local), by its tags, or source then tag.
// The tags come from each mod's own descriptor or metadata, read at every scan and kept in the library file.
const SORTS = {name: 'Name', source: 'Workshop, then Local', 'source-tag': 'Workshop / Local, then tag', tag: 'Tag', used: 'Most playsets first', fav: 'Favourites first'};
let libUse = {}, favOnly = false;
let libSort = 'source-tag', libTag = '';
try { libSort = localStorage.getItem('libSort') || libSort; } catch (e) { /* storage blocked: the default is fine */ }
if (!SORTS[libSort]) libSort = 'source-tag';
const SRC_ORDER = {workshop: 0, local: 1};
const SRC_NAME = {workshop: 'Workshop', local: 'Local'};
const byName = (a, b) => a.name.localeCompare(b.name, undefined, {sensitivity: 'base'});
const firstTag = m => ((m.tags || []).slice().sort((a, b) => a.localeCompare(b, undefined, {sensitivity: 'base'}))[0]) || '';
function libGroups(list) {
  // -> [{h: header text, sub: [...]|null, mods}] in display order
  const srcKey = m => (m.source in SRC_ORDER ? m.source : 'local');
  const cmpTag = (a, b) => (firstTag(a) === '' ? 1 : 0) - (firstTag(b) === '' ? 1 : 0) || firstTag(a).localeCompare(firstTag(b), undefined, {sensitivity: 'base'}) || byName(a, b);
  const grp = (items, key, label, order) => {
    const m = new Map();
    items.forEach(x => { const k = key(x); if (!m.has(k)) m.set(k, []); m.get(k).push(x); });
    return [...m.entries()].sort(order).map(([k, v]) => ({key: k, h: label(k), mods: v}));
  };
  if (libSort === 'name') return [{h: '', mods: list.slice().sort(byName)}];
  if (libSort === 'used') return [{h: '', mods: list.slice().sort((a, b) => (libUse[b.id] || 0) - (libUse[a.id] || 0) || byName(a, b))}];
  if (libSort === 'fav') { const fav = new Set(S.fav_mods || []), f = list.filter(m => fav.has(m.id)).sort(byName), o = list.filter(m => !fav.has(m.id)).sort(byName); return [f.length && {h: '★ Favourites', mods: f}, o.length && {h: f.length ? 'Everything else' : '', mods: o}].filter(Boolean); }
  if (libSort === 'tag') return grp(list.slice().sort(cmpTag), firstTag, k => k || 'No tags', (a, b) => (a[0] === '') - (b[0] === '') || a[0].localeCompare(b[0], undefined, {sensitivity: 'base'}));
  const bySrc = grp(list, srcKey, k => SRC_NAME[k], (a, b) => SRC_ORDER[a[0]] - SRC_ORDER[b[0]]);
  if (libSort === 'source') return bySrc.map(g => ({...g, mods: g.mods.sort(byName)}));
  return bySrc.map(g => ({...g, sub: grp(g.mods.sort(cmpTag), firstTag, k => k || 'No tags', (a, b) => (a[0] === '') - (b[0] === '') || a[0].localeCompare(b[0], undefined, {sensitivity: 'base'}))}));
}
function libRow(m, p) {
  const inn = p.mods.includes(m.id), tags = (m.tags || []).slice(0, 4);
  const fav = (S.fav_mods || []).includes(m.id), n = libUse[m.id] || 0;
  return `<div class="row ${m.id === sel ? 'sel' : ''}"><button class="star ${fav ? 'on' : ''}" data-favmod="${esc(m.id)}" title="${fav ? 'Remove from favourites' : 'Add to favourites'}" aria-label="Favourite">${fav ? '★' : '☆'}</button><span class="nm" data-sel="${esc(m.id)}" title="${esc(m.root)}">${esc(m.name)}</span><span class="mut" title="How many of your playsets contain this mod">${n} playset${n === 1 ? '' : 's'}</span>${tags.map(t => `<span class="tg">${esc(t)}</span>`).join('')}${badges(m)}
        <button class="sm" data-add="${esc(m.id)}" ${inn || !m.exists ? 'disabled' : ''}>${inn ? '✓ Added' : '+ Add'}</button></div>`;
}
function viewLibrary(p) {
  if (libTag && !(libTag in (S.tag_counts || {}))) libTag = '';   // a tag of another game
  const f = q.toLowerCase();
  libUse = {}; S.playsets.forEach(ps => ps.mods.forEach(id => { libUse[id] = (libUse[id] || 0) + 1; }));
  const fv = new Set(S.fav_mods || []);
  const list = S.mods.filter(m => (!f || m.name.toLowerCase().includes(f) || (m.tags || []).some(t => t.toLowerCase().includes(f))) && (!libTag || (m.tags || []).includes(libTag)) && (!favOnly || fv.has(m.id)));
  const rem = S.removed.length ? `<div class="row static"><span class="warn">Removed since last scan:</span> ${S.removed.map(r => esc(r.name)).join(', ')}</div>` : '';
  const tagOpts = Object.entries(S.tag_counts || {}).map(([t, n]) => `<option value="${esc(t)}" ${t === libTag ? 'selected' : ''}>${esc(t)} (${n})</option>`).join('');
  const rows = libGroups(list).map(g => (g.h ? `<div class="grp">${esc(g.h)} <span class="mut">${g.sub ? g.sub.reduce((n, s) => n + s.mods.length, 0) : g.mods.length}</span></div>` : '') +
    (g.sub ? g.sub.map(s => `<div class="grp sub">${esc(s.h)} <span class="mut">${s.mods.length}</span></div>` + s.mods.map(m => libRow(m, p)).join('')).join('') : g.mods.map(m => libRow(m, p)).join(''))).join('');
  $('view').innerHTML = `<div class="bar"><input type="search" id="q" placeholder="Search name or tag…" value="${esc(q)}">
    <select id="lib-sort" title="Sort the library" aria-label="Sort">${Object.entries(SORTS).map(([k, n]) => `<option value="${k}" ${k === libSort ? 'selected' : ''}>Sort: ${n}</option>`).join('')}</select>
    <select id="lib-tag" title="Show only mods with this tag" aria-label="Tag"><option value="">All tags</option>${tagOpts}</select>
    <button id="favonly" class="${favOnly ? 'on' : ''}" title="Show only your favourite mods">★ Favourites only</button><button id="addall">Add all shown</button><button id="modupd" title="Ask Steam which Workshop mods have a newer version">Check mod updates</button></div>${updPanel()}${rem}` +
    (rows || `<div class="empty">No mods found.<br>${S.user_dir ? 'Drop a mod archive (.zip, .tar.gz) here to install one, or check the folders in Settings.' : esc(GNAME()) + ' user folder not found. Set it in Settings → Game folders.'}</div>`);
  $('lib-sort').onchange = () => { libSort = $('lib-sort').value; try { localStorage.setItem('libSort', libSort); } catch (e) { /* only a convenience */ } viewLibrary(cur()); };
  $('favonly').onclick = () => { favOnly = !favOnly; viewLibrary(cur()); };
  $('lib-tag').onchange = () => { libTag = $('lib-tag').value; viewLibrary(cur()); };
  $('modupd').onclick = guard(async () => { $('modupd').disabled = true; try { U = await api('mod-updates', {}); } finally { $('modupd').disabled = false; } viewLibrary(cur()); });
  const qi = $('q');
  qi.oninput = () => { q = qi.value; const pos = qi.selectionStart; viewLibrary(cur()); const n = $('q'); n.focus(); n.setSelectionRange(pos, pos); };
  $('addall').onclick = guard(async () => {
    const add = list.filter(m => m.exists && !p.mods.includes(m.id)).map(m => m.id);
    if (add.length) await patch(q => ({mods: [...q.mods, ...add.filter(id => !q.mods.includes(id))]}));
  });
}

function fixBtn(i) {
  if (!i.fix) return '';
  return i.fix.kind === 'enable' ? `<button class="sm" data-fix="enable" data-id="${esc(i.fix.id)}">Enable ${esc(nameOf(i.fix.id))}</button>`
    : `<button class="sm" data-fix="autosort">Auto-sort</button>`;
}
function viewProblems() {
  if (!A) return;
  const vis = visIssues(), hid = A.issues.length - vis.length;
  const head = `<div class="cmp-bar"><span class="mut">Everything wrong with the load order of <b>${esc(cur().name)}</b>${hid ? ` · ${hid} hidden by your warning settings` : ''}</span>
    <span class="grow"></span><button class="sm" id="warn-cfg" title="Choose which warnings are shown" aria-label="Warning settings">⚙</button></div>`;
  $('view').innerHTML = head + (vis.map(i => `<div class="row static"><span class="${i.severity === 'error' ? 'err' : 'warn'}">${i.severity === 'error' ? '✖' : '▲'}</span>
    <span class="nm" style="white-space:normal;cursor:default">${esc(i.message)}</span>${fixBtn(i)}</div>`).join('') || '<div class="empty ok">No problems found. Ready to play.</div>');
}
function viewConflicts() {
  if (!A) return;
  if (A.pending) { $('view').innerHTML = '<div class="empty">Reading mod files to look for conflicts…<br><span class="mut">This can take a little while the first time with many mods.</span></div>'; return; }
  const ct = A.counts || {};
  const chips = [['all', 'All'], ...Object.keys(KINDS).filter(k => ct[k]).map(k => [k, `${KINDS[k]} (${ct[k]})`])]
    .map(([k, l]) => `<button data-f="${k}" class="${flt === k ? 'on' : ''}">${l}</button>`).join('');
  const rows = A.conflicts.filter(x => flt === 'all' || (flt === 'vanilla' ? x.vanilla : flt === x.kind && !x.vanilla)).map(x => `<div class="row static"><span class="${x.severity}">${x.vanilla ? 'Base game' : KINDS[x.kind]}</span>
    <span class="nm" style="white-space:normal;cursor:default"><code>${esc(x.path)}</code> — ${x.mods.map(i => (i === x.winner ? `<b class="ok">${esc(nameOf(i))}</b>` : esc(nameOf(i))) + (x.files && x.files[i] ? ` <span class="mut">(${x.files[i].map(f => esc(f.split('/').pop())).join(', ')})</span>` : '')).join(' → ')}</span></div>`).join('');
  $('view').innerHTML = `<div class="chips">${chips}</div>` + (rows || `<div class="empty ok">No conflicts.${S.include_vanilla ? '' : '<br><span class="mut">Comparison with the base game is off (Settings → Game folders).</span>'}</div>`) + (A.truncated ? '<div class="mut">List truncated.</div>' : '');
}

async function loadCompare() {
  const others = S.playsets.filter(x => x.id !== S.active);
  if (!others.some(x => x.id === cmpWith)) cmpWith = others.length ? others[0].id : null;
  C = cmpWith ? await api(`compare/${S.active}/${cmpWith}`) : null;
  if (tab === 'compare') render();
}
function viewCompare(p) {
  const others = S.playsets.filter(x => x.id !== S.active), o = S.playsets.find(x => x.id === cmpWith);
  if (!others.length) { $('view').innerHTML = '<div class="empty">Create or import a second playset to compare it with this one.</div>'; return; }
  const bar = `<div class="cmp-bar"><span class="mut">Compare <b>${esc(p.name)}</b> with</span><select id="cmpsel">${others.map(x => `<option value="${esc(x.id)}" ${x.id === cmpWith ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></div>`;
  if (!C || !o) { $('view').innerHTML = bar + '<div class="empty">Loading…</div>'; wireCmp(); return; }
  const sm = k => `${C.summary[k].errors} errors, ${C.summary[k].warnings} warnings, ${C.summary[k].conflicts} conflicts`;
  const here = esc(p.name), there = esc(o.name);
  const row = (id, extra, btn) => `<div class="row static"><span class="nm" style="cursor:default">${esc(nameOf(id))}</span>${extra || ''}${btn || ''}</div>`;
  const head = (t, n, btn) => n ? `<div class="cmp-h"><span>${t} <span class="mut">(${n})</span></span>${btn || ''}</div>` : '';
  let h = bar;
  if (C.identical) h += '<div class="row static ok">These playsets are identical.</div>';
  h += `<div class="cmp-bar"><button class="sm" data-cmp="merge" title="Make a new playset with every mod of both (this one's order first); neither playset is changed">Merge both into a new playset</button></div>`;
  h += `<div class="cmp-sum"><span>${here}: ${sm('a')}</span><span>${there}: ${sm('b')}</span></div>`;
  h += head(`Only in ${here}`, C.only_a.length) + C.only_a.map(id => row(id)).join('');
  h += head(`Only in ${there}`, C.only_b.length, '<button class="sm" data-cmp="addall">Add all to ' + here + '</button>') +
    C.only_b.map(id => row(id, '', `<button class="sm" data-cmp="add" data-id="${esc(id)}">+ Add</button>`)).join('');
  h += head('Enabled in one, disabled in the other', C.state.length) +
    C.state.map(s => row(s.id, `<span class="b">${here}: ${s.a}</span><span class="b">${there}: ${s.b}</span>`,
      `<button class="sm" data-cmp="state" data-id="${esc(s.id)}" data-to="${s.b}">Match ${there}</button>`)).join('');
  h += head('Loaded in a different order', C.moved.length, '<button class="sm" data-cmp="order">Match ' + there + '\'s order</button>') +
    C.moved.map(m => row(m.id, `<span class="b">#${m.a} in ${here}</span><span class="b">#${m.b} in ${there}</span>`)).join('');
  h += head('Settings that differ', C.settings.length) + C.settings.map(s => {
    const f = v => esc(Array.isArray(v) ? (v.join(' ') || '—') : typeof v === 'boolean' ? (v ? 'on' : 'off') : (v || '—'));
    return `<div class="row static"><span class="nm" style="cursor:default">${esc(s.field.replace('_', ' '))}</span><span class="b">${here}: ${f(s.a)}</span><span class="b">${there}: ${f(s.b)}</span></div>`;
  }).join('');
  $('view').innerHTML = h;
  wireCmp();
}
function wireCmp() {
  const sel = $('cmpsel');
  if (sel) sel.onchange = guard(async () => { cmpWith = sel.value; C = null; render(); await loadCompare(); });
}
document.addEventListener('click', guard(async e => {
  const t = e.target, act = t.dataset && t.dataset.cmp, p = cur(); if (!p) return;
  if (!act) return;
  if (act === 'merge') {
    const o = S.playsets.find(x => x.id === cmpWith); if (!o) return;
    const n = prompt('Name for the merged playset', `${p.name} + ${o.name}`); if (!n) return;
    const r = await api(`playsets/${p.id}/merge`, {with: o.id, name: n});
    await api(`playsets/${r.id}/activate`, {}); tab = 'order'; return load();
  }
  if (act === 'add') await patch(q => ({mods: q.mods.includes(t.dataset.id) ? q.mods : [...q.mods, t.dataset.id]}));
  if (act === 'addall') await patch(q => ({mods: [...q.mods, ...C.only_b.filter(id => !q.mods.includes(id))]}));
  if (act === 'state') {
    const id = t.dataset.id, on = t.dataset.to === 'enabled';
    await patch(q => ({disabled: on ? q.disabled.filter(x => x !== id) : [...q.disabled, id]}));
  }
  if (act === 'order') {
    const common = new Set([...C.same, ...C.moved.map(m => m.id)]);
    const slots = p.mods.map((m, i) => common.has(m) && !p.disabled.includes(m) ? i : -1).filter(i => i >= 0);
    const next = [...p.mods];
    C.common_order_b.forEach((id, k) => { next[slots[k]] = id; });
    await patch({mods: next});
  }
}));

// Replace this app with the newest release (downloaded app only), then reload once the new copy answers.
async function selfUpdate(say, ask = true, channel = 'stable') {
  say = say || toast;
  if (ask && !confirm(channel === 'nightly' ? 'Install the newest TEST build and restart Ronin Mod Manager? It may contain bugs. Your playsets and settings are kept.' : 'Download the newest version and restart Ronin Mod Manager? Your playsets and settings are kept.')) return;
  let st = await app('self-update', {channel});
  for (let i = 0; i < 600 && ['working', 'restarting'].includes(st.status); i++) {
    say(st.message || 'Updating…');
    await new Promise(r => setTimeout(r, 1000));
    try { st = await app('self-update'); } catch (e) { if (st.status === 'restarting') break; throw e; }  // old copy exited
  }
  if (st.status === 'error') throw new Error(st.message);
  if (st.status === 'current') return say(st.message);
  say('Restarting…');
  for (let i = 0; i < 60; i++) {   // wait for the new copy, then load it (an app window is replaced by the new copy's own)
    await new Promise(r => setTimeout(r, 1000));
    try { const r = await fetch('/api/games'); if (r.ok) return location.reload(); } catch (e) { /* not up yet */ }
  }
  throw new Error('Ronin Mod Manager did not come back. Start it again from its icon; the update itself was installed.');
}
function banner() {
  const b = $('banner'), u = GI.update; b.className = '';
  if (!u || !u.update_available || GI.settings.dismissed_update === u.latest) { b.hidden = true; b.innerHTML = ''; return; }
  const link = u.url.startsWith(REPO_LINK) ? u.url : REPO_LINK + 'releases';
  b.hidden = false;
  b.innerHTML = `<span class="grow"><b>Version ${esc(u.latest)} is available</b> <span class="mut">(you have ${esc(GI.version)})</span></span>
    ${GI.can_self_update ? '<button class="sm pri" id="bn-now">Update now</button>' : ''}
    <a href="${esc(link)}" target="_blank" rel="noopener noreferrer">View release</a><button class="sm" id="bn-dismiss">Dismiss</button>`;
  if ($('bn-now')) $('bn-now').onclick = guard(() => selfUpdate());
  $('bn-dismiss').onclick = guard(async () => { GI.settings = await app('settings', {dismissed_update: u.latest}); banner(); });
}
$('dlg').addEventListener('close', () => { $('dlg').className = ''; });
$('appcfg').onclick = () => openPaths(false);
let inspectT;
async function inspect() {
  const v = $('p-game').value.trim(), el = $('p-gst');
  if (!v) { el.textContent = ''; return; }
  const r = await api('inspect?path=' + encodeURIComponent(v)), i = r.install;
  el.innerHTML = i ? `<span class="ok">✔ ${esc(GNAME())} found${i.version ? ' · version ' + esc(i.version) : ''} · ${esc(i.path)}</span>`
    : `<span class="err">✖ No ${esc(GNAME())} install here (expected a ${esc(S.game.install_marker || 'game')} folder)</span>`;
  if (i && !$('p-ws').value) $('p-ws').value = i.workshop_dir || '';
}
async function openPaths(first) {
  const d = $('dlg'), st = GI.settings;
  d.className = 'wide';
  d.innerHTML = `<div class="st-head"><h2>${first ? 'Set up ' + esc(GNAME()) : 'Settings'}</h2>
      <span class="mut">Ronin Mod Manager v${esc(GI.version)}${S.game.verified ? '' : ' · launching is <b>not yet verified</b> on a real ' + esc(GNAME()) + ' install'}</span>
    </div>
    <div class="st-body">
    <nav class="st-tabs" id="st-tabs"><button data-st="game" class="on"><i>🎮</i>Game</button><button data-st="store"><i>📁</i>Storage</button><button data-st="play"><i>▶</i>Playing</button><button data-st="ui"><i>🎨</i>UI</button><button data-st="dl"><i>⬇</i>Downloads</button><button data-st="app"><i>⟳</i>App &amp; updates</button></nav>
    <div class="st-panes">
    <section data-pane="game">
      <div class="card">
        <h3>${esc(GNAME())} install</h3>
        <p class="desc">Where the game is installed. Paste any path inside the install folder and the manager finds the right one.</p>
        <div id="p-found" class="mut"></div>
        <label class="fld" for="p-game">Game folder</label><input type="text" id="p-game" value="${esc(S.game_root)}"><div class="st" id="p-gst"></div>
      </div>
      <div class="card">
        <h3>Check this game <span class="b warn">beta</span></h3>
        <p class="desc">Shows step by step what the app found for ${esc(GNAME())} (install, folders, mods, launcher) and what it was looking for where something is missing.</p>
        <div class="acts"><button id="dg-run">Check now</button><button id="dg-copy" hidden>Copy report</button></div>
        <div id="dg-out"></div>
      </div>
      ${S.game.custom ? `<div class="card">
        <h3>Added game <span class="b warn">beta</span></h3>
        <p class="desc">You added this game yourself, so nothing about it is checked against a real install. If something does not work, use "Check this game" above and fix the field it points to.</p>
        <div class="acts"><button id="cg-edit">Edit this game…</button><button id="cg-remove" class="danger">Remove from the list…</button></div>
      </div>` : ''}
    </section>
    <section data-pane="ui" hidden>
      <div class="card">
        <h3>Colour scheme</h3>
        <p class="desc">How ${esc(GNAME())} looks in this app. "Game look" is the game's own colours. Changes apply straight away.</p>
        <div class="schemes">${[['default', 'Game look', null], ...Object.entries(SCHEMES).map(([k, x]) => [k, x.name, x.v])].map(([k, n, v]) => {
          const c = v || (G && GI.games.find(g => g.id === G).theme) || {};
          return `<button class="scheme ${S.ui_scheme === k ? 'on' : ''}" data-scheme="${k}"><b>${esc(n)}</b><span class="chips">${['--bg', '--panel', '--acc', '--p2'].map(x => `<i style="background:${esc(c[x] || '#444')}"></i>`).join('')}</span></button>`;
        }).join('')}</div>
      </div>
      <div class="card">
        <h3>Text size</h3>
        <p class="desc">Makes everything in the app bigger or smaller.</p>
        <select id="ui-text">${Object.entries(TEXT_SIZES).map(([k, [n]]) => `<option value="${k}" ${S.ui_text === k ? 'selected' : ''}>${n}</option>`).join('')}</select>
      </div>
      <div class="card"><div class="acts"><button id="ui-all">Use these for all games</button><span class="mut" id="ui-msg"></span></div></div>
    </section>
    <section data-pane="store" hidden>
      <div class="card">
        <h3>Mods &amp; saves</h3>
        <p class="desc">${S.game.kind === 'modules' ? 'The game\'s folder in Documents, where it keeps saves and the launcher\'s settings. Mods themselves are read from the install\'s Modules folder and the Steam Workshop folder.' : `The game's own folder in Documents. Your mods, saves and <code>${esc(S.game.load_file)}</code> live here.`}</p>
        <label class="fld" for="p-user">User folder</label><input type="text" id="p-user" value="${esc(S.user_dir)}">
      </div>
      <div class="card">
        <h3>Steam Workshop</h3>
        <p class="desc">Where Steam keeps the Workshop mods you subscribed to.</p>
        <label class="fld" for="p-ws">Workshop folder</label><input type="text" id="p-ws" value="${esc(S.workshop_dir)}">
      </div>
    </section>
    <section data-pane="play" hidden>
      <div class="card">
        <h3>Before you play</h3>
        <p class="desc">Checks the manager runs for you.</p>
        <label class="srow" style="${S.game.has_saves ? '' : 'display:none'}"><span class="rt"><b>Warn about save versions</b><span class="hint">Warn if the saves were made on a different game release, for example 1.14 saves with 1.15 installed</span></span><input type="checkbox" class="sw" id="p-svc" ${S.save_version_check ? 'checked' : ''}></label>
        <label class="srow" style="${S.game.has_conflicts ? '' : 'display:none'}"><span class="rt"><b>Compare mods with the base game</b><span class="hint">Shows what each mod overrides from the original game files</span></span><input type="checkbox" class="sw" id="p-van" ${S.include_vanilla ? 'checked' : ''}></label>
      </div>
      <div class="card">
        <h3>Playsets</h3>
        <p class="desc">How playsets get into the manager. The Import menu (sidebar) does the same by hand.</p>
        <label class="srow"><span class="rt"><b>Import launcher playsets automatically</b><span class="hint">When the game opens, bring in playsets from the game's own launcher that were never imported before</span></span><input type="checkbox" class="sw" id="s-imp-auto" ${st.auto_import_launcher ? 'checked' : ''}></label>
        <label class="srow"><span class="rt"><b>Show the Import button</b><span class="hint">The Import button above the playset list</span></span><input type="checkbox" class="sw" id="s-imp-show" ${st.show_import_button ? 'checked' : ''}></label>
      </div>
    </section>
    <section data-pane="dl" hidden>
      <div class="card">
        <h3>Downloading Workshop mods</h3>
        <p class="desc">Optional. <b>Open in Steam</b> needs nothing. To download straight from here, give the path to <code>steamcmd</code> and the Steam account name it is already logged in with. No password is ever asked for, stored or sent by this app.</p>
        <label class="fld" for="p-cmd">steamcmd executable</label><input type="text" id="p-cmd" value="${esc(S.steamcmd)}">
        <label class="fld" for="p-su">Steam account name</label><input type="text" id="p-su" value="${esc(S.steam_user)}">
      </div>
    </section>
    <section data-pane="app" hidden>
      <div class="card">
        <h3>Updates</h3>
        <p class="desc">${GI.can_self_update ? 'This is the downloaded app. When a newer version exists, update from the banner at the top. Your playsets and settings are kept.' : 'This copy runs from source files, so it cannot replace itself. Update it with Git or download the ZIP again. The downloadable app from the Releases page updates itself.'}</p>
        <label class="srow"><span class="rt"><b>Check for updates on start</b><span class="hint">Off by default. Asks api.github.com for the latest release; nothing is installed until you press Update</span></span><input type="checkbox" class="sw" id="s-auto" ${st.auto_update_check ? 'checked' : ''}></label>
        <div class="acts"><button id="s-check">Check for updates now</button></div>
        <div id="s-result"></div>
      </div>
      <div class="card">
        <h3>Game logos</h3>
        <label class="srow"><span class="rt"><b>Download missing logos</b><span class="hint">Fetches a missing game logo once from Steam's public art server, only when none is found on this PC</span></span><input type="checkbox" class="sw" id="s-logos" ${st.fetch_logos ? 'checked' : ''}></label>
      </div>
      <div class="card">
        <h3>Test builds (nightly) <span class="b warn">experimental</span></h3>
        <p class="desc">Builds made automatically from the version being worked on, before it becomes a release. They may contain bugs; your playsets and settings are kept. A release only contains what was tried here first. You have: <b>v${esc(GI.version)}${GI.build ? ' · test build ' + esc(GI.build) : ' (a normal release)'}</b>. To go back to the newest release, press "Check for updates now" above.</p>
        <p class="mut" id="nt-status"></p>
        <div class="acts"><button id="nt-check">Check for a test build</button><button id="nt-go" class="danger" disabled>Install the test build</button></div>
      </div>
      <div class="card">
        <h3>Erase all data <span class="b warn">experimental</span></h3>
        <p class="desc">Deletes everything this app saved: every playset, the library, backups, logos, your own presets and the settings, for all games. Use it for a completely fresh start. The games' own files, your mods, saves and the error log are not touched.</p>
        <div class="acts"><button id="s-erase">Erase all data…</button></div>
      </div>
      <div class="card">
        <h3>Problems</h3>
        <p class="desc">Errors are saved to <code>${esc(GI.log_file || 'Documents/Ronin Mod Manager/RoninModManager-errors.log')}</code>. Send that file when reporting a bug.</p>
      </div>
    </section>
    </div>
    </div>
    <div class="st-foot"><span class="mut">Changes on this window are applied when you press Save.</span><span><button id="p-cancel">${first ? 'Skip' : 'Cancel'}</button> <button id="p-save" class="pri">Save</button></span></div>`;
  $('st-tabs').onclick = e => {
    const t = e.target.closest && e.target.closest('[data-st]'), k = t && t.dataset.st; if (!k) return;
    d.querySelectorAll('[data-st]').forEach(b => b.classList.toggle('on', b.dataset.st === k));
    d.querySelectorAll('[data-pane]').forEach(x => { x.hidden = x.dataset.pane !== k; });
  };
  $('dg-run').onclick = guard(async () => {
    $('dg-out').innerHTML = '<p class="mut">Checking…</p>';
    const r = await api('diagnose');
    $('dg-out').innerHTML = r.checks.map(c => `<div class="dg ${c.ok ? 'ok' : 'warn'}"><b>${c.ok ? '✓' : '✗'} ${esc(c.label)}</b><div class="mut">${esc(c.detail)}</div></div>`).join('');
    const text = `${r.game} (Ronin Mod Manager v${GI.version})\n` + r.checks.map(c => `${c.ok ? '[ok]' : '[!!]'} ${c.label}: ${c.detail}`).join('\n');
    $('dg-copy').hidden = false;
    $('dg-copy').onclick = () => { try { navigator.clipboard.writeText(text).then(() => toast('Report copied.')); } catch (e) { toast('Could not copy. Select the text instead.', true); } };
  });
  if ($('cg-edit')) {
    $('cg-edit').onclick = () => { d.close(); openGameDialog(G); };
    $('cg-remove').onclick = guard(async () => {
      if (!confirm(`Remove ${GNAME()} from the list?\n\nThe game's own files are never touched. Your playsets for it stay saved here unless you choose to erase them next.`)) return;
      const erase = confirm('Also erase the playsets and settings this app saved for this game?\n\nOK = erase them, Cancel = keep them.');
      const r = await app('custom-games/remove', {id: G, erase_data: erase});
      d.close(); await adoptGames(r); await useGame(GI.games[0].id, true);
    });
  }
  $('s-imp-auto').onchange = guard(async () => { GI.settings = await app('settings', {auto_import_launcher: $('s-imp-auto').checked}); });
  $('s-imp-show').onchange = guard(async () => { GI.settings = await app('settings', {show_import_button: $('s-imp-show').checked}); showImportButton(); });
  const saveUI = async (b, all) => {
    for (const g of all ? GI.games.map(x => x.id) : [G]) { const r = await call(`/api/${g}/ui`, b); if (g === G) S = r; }
    applyUI(); render();
  };
  d.querySelectorAll('[data-scheme]').forEach(b => { b.onclick = guard(async () => {
    await saveUI({ui_scheme: b.dataset.scheme});
    d.querySelectorAll('[data-scheme]').forEach(x => x.classList.toggle('on', x === b));
  }); });
  $('ui-text').onchange = guard(() => saveUI({ui_text: $('ui-text').value}));
  $('ui-all').onclick = guard(async () => { await saveUI({ui_scheme: S.ui_scheme, ui_text: S.ui_text}, true); $('ui-msg').textContent = 'Done.'; });
  $('nt-check').onclick = guard(async () => {
    $('nt-status').textContent = 'Checking…'; $('nt-go').disabled = true;
    const r = await app('nightly');
    $('nt-status').textContent = r.message + (r.published ? ` (built ${r.published})` : '') + (r.update_available && !GI.can_self_update ? ' This copy runs from source files, so it cannot replace itself.' : '');
    $('nt-go').disabled = !(r.update_available && GI.can_self_update);
  });
  $('nt-go').onclick = guard(async () => {
    $('nt-go').disabled = true;
    try { await selfUpdate(m => { $('nt-status').textContent = m; }, true, 'nightly'); } finally { $('nt-go').disabled = false; }
  });
  $('s-erase').onclick = guard(async () => {
    const t = prompt('This deletes ALL playsets and settings saved by this app, for every game. Your games and mods are not touched.\n\nType ERASE to continue.');
    if (t === null) return;
    const r = await app('erase-all', {confirm: t.trim()});
    if (r.failed.length) { alert('Some data could not be deleted:\n' + r.failed.join('\n')); }
    location.reload();
  });
  $('s-logos').onchange = guard(async () => { GI.settings = await app('settings', {fetch_logos: $('s-logos').checked}); });
  d.showModal();
  $('p-cancel').onclick = guard(async () => { if (first) { S = await api('skip-setup', {}); } d.close(); });
  $('p-game').oninput = () => { clearTimeout(inspectT); inspectT = setTimeout(guard(inspect), 250); };
  $('p-save').onclick = guard(async () => {
    S = await api('paths', {game_dir: $('p-game').value.trim(), user_dir: $('p-user').value.trim(), workshop_dir: $('p-ws').value.trim(),
      include_vanilla: $('p-van').checked, save_version_check: $('p-svc').checked, steamcmd: $('p-cmd').value.trim(), steam_user: $('p-su').value.trim()});
    d.close(); await load(true);
  });
  $('s-auto').onchange = guard(async () => { GI.settings = await app('settings', {auto_update_check: $('s-auto').checked}); toast($('s-auto').checked ? 'Will check for updates on start.' : 'Automatic update checks are off.'); });
  $('s-check').onclick = guard(async () => {
    $('s-result').innerHTML = '<span class="mut">Checking…</span>';
    const u = await app('update-check', {force: true});
    GI.update = u; banner();
    const link = u.url.startsWith(REPO_LINK) ? u.url : REPO_LINK + 'releases';
    $('s-result').innerHTML = `<div class="${u.status === 'update' ? 'ok' : u.status === 'current' ? 'ok' : 'warn'}"><b>${esc(u.message)}</b></div>` +
      (u.latest ? `<div class="mut">Running ${esc(u.current)} · latest ${esc(u.latest)}${u.published ? ' · ' + esc(u.published) : ''}</div>` : '') +
      (u.notes ? `<div class="notes">${esc(u.notes)}</div>` : '') +
      (u.status === 'update' ? `<div class="acts">${GI.can_self_update ? '<button class="pri" id="s-now">Download and restart</button> ' : ''}<a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Release page</a></div><div id="s-prog" class="mut"></div>` : '');
    if ($('s-now')) $('s-now').onclick = guard(async () => {
      $('s-now').disabled = true; $('s-check').disabled = true;
      try { await selfUpdate(m => { $('s-prog').textContent = m; }, false); }
      catch (e) { $('s-now').disabled = false; $('s-check').disabled = false; throw e; }
    });
  });
  inspect();
  const {installs} = await api('detect');
  $('p-found').innerHTML = installs.length ? '<b>Found on this PC:</b>' + installs.map(i => `<div><label class="chk" style="margin:4px 0;color:var(--ink)"><input type="radio" name="inst" value="${esc(i.path)}" ${i.path === S.game_root ? 'checked' : ''}> ${esc(i.path)}${i.version ? ' <span class="mut">v' + esc(i.version) + '</span>' : ''}</label></div>`).join('')
    : `<span class="warn">Could not find ${esc(GNAME())} automatically — paste the folder below.</span>`;
  $('p-found').onchange = e => { if (e.target.name === 'inst') { $('p-game').value = e.target.value; $('p-ws').value = ''; guard(inspect)(); } };
}

// ---- presets ----
async function loadPresets() { P = await api('presets'); if (tab === 'presets') render(); }
function viewPresets() {
  if (!P) { $('view').innerHTML = '<div class="empty">Loading…</div>'; loadPresets(); return; }
  const miss = lastMissing.length ? `<div class="pre"><h3>Not installed yet (${lastMissing.length})</h3>
    <p>${lastMissing.map(m => `${esc(m.name)} <span class="mut">#${esc(m.workshop_id)}</span>`).join('<br>')}</p>
    <div class="acts"><button data-dl="steam">Open in Steam…</button>${S.steamcmd && S.steam_user ? '<button data-dl="steamcmd" class="pri">Download with steamcmd</button>' : '<span class="mut">Set steamcmd in Settings to download from here.</span>'}
    <button data-dl="rescan">Rescan</button></div><div id="dlstat" class="mut"></div></div>` : '';
  const imp = `<div class="pre"><h3>Import a Workshop collection</h3><p class="mut">Paste a Steam Workshop collection link. Only the list of mods is fetched from Steam (nothing is downloaded) and saved as a preset.</p>
    <div class="acts"><input id="col-url" placeholder="https://steamcommunity.com/sharedfiles/filedetails/?id=…" style="flex:1;min-width:0"><button id="col-go" class="pri">Import</button></div></div>`;
  $('view').innerHTML = imp + miss + (P.map(x => `<div class="pre"><h3>${esc(x.name)} ${x.status === 'verified' ? '<span class="b ok">verified</span>' : '<span class="b warn">unverified</span>'} <span class="b">${x.installed}/${x.total} installed</span></h3>
    <p>${esc(x.description)}</p><p>${x.mods.map(m => esc(m.name)).join(' · ')}</p>
    <div class="acts"><button class="pri" data-preset="${esc(x.id)}">Create playset</button></div></div>`).join('')
    || `<div class="empty">No presets for ${esc(GNAME())}.<br>Save one from a playset's settings, or drop a JSON file in the presets folder.</div>`);
}
function drawer() {
  const d = $('drawer'), m = sel && M(sel);
  d.className = m ? 'open' : '';
  if (!m) { d.innerHTML = ''; return; }
  const p = cur(); if (!p) return;
  const idx = p.mods.indexOf(m.id), note = A && A.notes[m.id];
  const deps = m.dependencies.map(x => {
    const dm = S.mods.find(o => o.name === x || String(o.remote_id) === x || 'ugc_' + o.remote_id === x);
    const st = !dm ? '<span class="b err">not installed</span>' : p.mods.includes(dm.id) && !p.disabled.includes(dm.id) ? '<span class="b ok">enabled</span>' : '<span class="b warn">not enabled</span>';
    return `<p>${esc(x)} ${st}</p>`;
  }).join('') || '<p class="mut">None</p>';
  d.innerHTML = `<button class="sm" data-close="1" style="float:right">✕</button><h2>${esc(m.name)}</h2>
    <p class="mut">${esc(m.version ? 'v' + m.version : '')} ${badges(m)}</p>
    ${m.description ? `<p>${esc(m.description)}</p>` : ''}
    ${m.supported_version ? `<h3>Made for game version</h3><p>${esc(m.supported_version)}</p>` : ''}
    ${m.tags.length ? `<h3>Tags</h3><p>${m.tags.map(t => `<span class="b">${esc(t)}</span>`).join(' ')}</p>` : ''}
    <h3>Dependencies</h3>${deps}
    ${idx >= 0 && note ? `<h3>Why is it here?</h3><p>${esc(note.reason)}</p>` : ''}
    ${issuesOf(m.id).length ? `<h3>Issues</h3>${issuesOf(m.id).map(i => `<p class="${i.severity === 'error' ? 'err' : 'warn'}">${esc(i.message)} ${fixBtn(i)}</p>`).join('')}` : ''}
    <h3>Location</h3><p class="mut"><code>${esc(m.root || '—')}</code></p>
    <h3>Files</h3><div id="d-files"><button class="sm" data-filesof="${esc(m.id)}">Show file tree</button></div>
    ${m.source === 'local' && m.exists ? `<p><button class="danger sm" data-uninstall="${esc(m.id)}">Uninstall (kept in backups)</button></p>` : ''}`;
}

// ---- actions ----
document.addEventListener('click', guard(async e => {
  const t = e.target, p = cur(), ds = t.dataset; if (!p) return;
  const starPs = t.closest('[data-favps]'), starMod = t.closest('[data-favmod]');
  if (starPs) { const id = starPs.dataset.favps, ps = S.playsets.find(x => x.id === id); await api(`playsets/${id}/update`, {favorite: !(ps && ps.favorite)}); return load(); }
  if (starMod) { const id = starMod.dataset.favmod, on = !(S.fav_mods || []).includes(id); S.fav_mods = (await api('fav-mod', {id, on})).fav_mods; return render(); }
  const psRow = t.closest('[data-ps]');
  if (psRow) { await api(`playsets/${psRow.dataset.ps}/activate`, {}); sel = null; return load(); }
  if (ds.tab) { tab = ds.tab; render(); if (tab === 'compare') { C = null; render(); await loadCompare(); } if (tab === 'files') await loadFiles(); }
  if (ds.f) { flt = ds.f; render(); }
  if (ds.sel) { sel = sel === ds.sel ? null : ds.sel; render(); }
  if (ds.close) { sel = null; render(); }
  if (ds.add) await patch(q => ({mods: q.mods.includes(ds.add) ? q.mods : [...q.mods, ds.add]}));
  if (ds.rm) await patch(q => ({mods: q.mods.filter(x => x !== ds.rm)}));
  if (ds.mv) {
    const [i, d] = ds.mv.split(',').map(Number), j = i + d;
    if (j >= 0 && j < p.mods.length) { const m = [...p.mods]; [m[i], m[j]] = [m[j], m[i]]; await patch({mods: m}); }
  }
  if (ds.bulk) { Object.assign(p, await api(`playsets/${p.id}/${ds.bulk}`, {})); render(); analyse(); }
  if (e.target.id === 'col-go') {
    const url = $('col-url').value.trim(); if (!url) return;
    try { const r = await api('presets/import-collection', {url}); P = null; toast(`Imported "${r.name}" (${r.mods.length} mods). Create a playset from it below.`); loadPresets(); }
    catch (err) { toast(err.message || String(err)); }
  }
  if (ds.preset) {
    const r = await api(`presets/${ds.preset}/apply`, {});
    lastMissing = r.missing; await api(`playsets/${r.id}/activate`, {}); await load();
    tab = 'presets'; render();
    toast(r.missing.length ? `Playset created. ${r.missing.length} mod(s) still need downloading.` : 'Playset created. Everything is installed.');
  }
  if (ds.dl1) await api('downloads', {ids: [ds.dl1], method: 'steam'});
  if (ds.filesof) {
    const r = await api(`tree/${S.active}/${encodeURIComponent(ds.filesof)}`);
    $('d-files').innerHTML = '<div class="mut">' + r.total + ' files' + (r.truncated ? ' (first ' + r.files.length + ')' : '') + '</div><div id="d-ft"></div>';
    mountTree($('d-ft'), r.files.map(f => ({path: f.path, tag: f.overridden_by ? `<span class="b warn">overridden by ${esc(nameOf(f.overridden_by))}</span>` : f.overrides.length ? `<span class="b ok">wins over ${f.overrides.length}</span>` : ''})));
  }
  if (ds.dl === 'rescan') { await api('rescan', {}); await load(true); lastMissing = lastMissing.filter(m => !S.mods.some(x => String(x.remote_id) === m.workshop_id)); render(); }
  if (ds.dl === 'steam' || ds.dl === 'steamcmd') {
    const r = await api('downloads', {ids: lastMissing.map(m => m.workshop_id), method: ds.dl});
    if (ds.dl === 'steam') toast('Opened in Steam. Press Subscribe on each, then Rescan once Steam has finished.');
    else pollDownload(r.job.id);
  }
  if (ds.fix === 'enable') { Object.assign(p, await api(`playsets/${p.id}/enable`, {id: ds.id})); render(); analyse(); }
  if (ds.fix === 'autosort') { Object.assign(p, await api(`playsets/${p.id}/autosort`, {})); render(); analyse(); }
  if (ds.uninstall && confirm(`Uninstall "${nameOf(ds.uninstall)}"? Its files are moved to the backups folder, not deleted.`)) {
    const r = await api(`mods/${encodeURIComponent(ds.uninstall)}/uninstall`, {});
    sel = null; await load(); toast('Moved to ' + r.backup);
  }
}));
document.addEventListener('change', guard(async e => {
  const t = e.target, p = cur(); if (!p) return;
  if (t.dataset.tog) { const id = t.dataset.tog; await patch(q => ({disabled: t.checked ? q.disabled.filter(x => x !== id) : [...q.disabled, id]})); }
}));
const view = $('view');
view.addEventListener('dragstart', e => { const r = e.target.closest('[data-i]'); if (r) { drag = +r.dataset.i; r.classList.add('drag'); if (e.dataTransfer) e.dataTransfer.setDragImage(r, 10, 10); } });
view.addEventListener('dragover', e => { if (drag !== null) e.preventDefault(); });
view.addEventListener('drop', guard(async e => {
  const r = e.target.closest('[data-i]'), p = cur(); if (!p) return;
  if (r && drag !== null) { e.preventDefault(); const m = [...p.mods], [x] = m.splice(drag, 1); m.splice(+r.dataset.i, 0, x); drag = null; await patch({mods: m}); }
}));
view.addEventListener('dragend', () => { drag = null; render(); });

$('auto').onchange = guard(() => patch({auto_sort: $('auto').checked}));
$('sortnow').onclick = guard(async () => { Object.assign(cur(), await api(`playsets/${S.active}/autosort`, {})); render(); analyse(); });
$('rescan').onclick = guard(() => api('rescan', {}).then(() => load(true)));
$('new').onclick = guard(async () => {
  const n = prompt('Playset name'); if (!n) return;
  const r = await api('playsets', {name: n}); await api(`playsets/${r.id}/activate`, {}); load();
});
$('imp').onclick = guard(() => openImport());
function showImportButton() { $('imp').hidden = GI.settings.show_import_button === false; }
// The Import menu: playsets from the game's own launcher, a file, and the two preferences.
async function openImport() {
  const d = $('dlg'); d.className = 'menu';
  d.innerHTML = '<h2>Import playsets</h2><p class="mut">Loading…</p>';
  d.showModal();
  const g = gen; let L;
  try { L = await api('launcher'); } catch (e) { d.close(); throw e; }
  if (g !== gen) return d.close();
  const st = GI.settings, fresh = L.playsets.filter(p => !p.imported);
  const rows = L.playsets.map(p => `<label class="srow"><span class="rt"><b>${esc(p.name)}</b><span class="hint">${p.mods} mod${p.mods === 1 ? '' : 's'}${p.active ? ' · active in the launcher' : ''} · ${p.imported ? 'already here' : 'not imported yet'}</span></span>
      <input type="checkbox" class="sw" data-lp="${esc(p.id)}" ${p.imported ? '' : 'checked'}></label>`).join('');
  d.innerHTML = `<h2>Import playsets</h2>
    <div class="card"><h3>From the ${esc(GNAME())} launcher</h3>
      ${L.error ? `<p class="warn">${esc(L.error)}</p>` : !L.found ? `<p class="desc">${esc(L.message)}</p>` : L.playsets.length ? `<p class="desc">Playsets already in the game's own launcher. Switch off the ones you do not want. The launcher itself is only read, never changed.</p>${rows}` : '<p class="desc">The launcher has no playsets yet.</p>'}
      <div class="acts"><button class="pri" id="lp-go" ${L.playsets.length ? '' : 'disabled'}>Import ${fresh.length ? fresh.length + ' new' : 'selected'}</button><span id="lp-msg" class="mut"></span></div></div>
    <div class="card"><h3>From a file</h3><p class="desc">A playset file someone shared with you (Playset settings → Export).</p>
      <div class="acts"><button id="lp-file">Choose a file…</button></div></div>
    <div class="card"><h3>Preferences</h3>
      <label class="srow"><span class="rt"><b>Import launcher playsets automatically</b><span class="hint">When the game opens, bring in launcher playsets that were never imported before. One you deleted here does not come back by itself.</span></span><input type="checkbox" class="sw" id="im-auto" ${st.auto_import_launcher ? 'checked' : ''}></label>
      <label class="srow"><span class="rt"><b>Show this Import button</b><span class="hint">Hide it if you do not need it. You can bring it back under Settings → Playing.</span></span><input type="checkbox" class="sw" id="im-show" ${st.show_import_button ? 'checked' : ''}></label></div>
    <div class="dlg-btns"><span></span><button id="lp-close">Close</button></div>`;
  $('lp-close').onclick = () => d.close();
  $('lp-file').onclick = () => { d.close(); $('impf').click(); };
  $('im-auto').onchange = guard(async () => { GI.settings = await app('settings', {auto_import_launcher: $('im-auto').checked}); });
  $('im-show').onchange = guard(async () => { GI.settings = await app('settings', {show_import_button: $('im-show').checked}); showImportButton(); });
  $('lp-go').onclick = guard(async () => {
    const ids = [...d.querySelectorAll('[data-lp]')].filter(c => c.checked).map(c => c.dataset.lp);
    if (!ids.length) { $('lp-msg').textContent = 'Nothing is switched on.'; return; }
    $('lp-go').disabled = true;
    try {
      const r = await api('launcher/import', {ids});
      await load();
      d.close();
      const n = r.imported.length, miss = r.imported.reduce((a, i) => a + i.missing, 0);
      toast(n ? `Imported ${n} playset${n === 1 ? '' : 's'}${miss ? ` (${miss} mod${miss === 1 ? '' : 's'} not installed yet)` : ''}${r.lost.length ? `; ${r.lost.length} could not be matched` : ''}.` : 'Everything selected is already here.');
    } finally { $('lp-go').disabled = false; }
  });
}
$('impf').onchange = guard(async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  if (f.size > 1024 * 1024) throw new Error('That file is too large to be a playset.');
  const r = await api('import', JSON.parse(await f.text()));
  await api(`playsets/${r.id}/activate`, {}); await load();
  toast(r.missing.length ? `Imported. Not installed (skipped): ${r.missing.join(', ')}` : 'Imported.');
});
$('installbtn').onclick = () => $('installf').click();
$('installf').onchange = e => { const f = e.target.files[0]; e.target.value = ''; if (f) install(f); };
const install = guard(async f => {
  toast(`Installing ${f.name}…`);
  const r = await fetch(`/api/${G}/install`, {method: 'POST', headers: {'X-Filename': f.name}, body: f});
  const j = await r.json(); if (!r.ok) throw new Error(j.error);
  await load();
  toast('Installed: ' + j.installed.map(i => i.name + (i.upgraded ? ' (upgraded, old version backed up)' : '')).join(', '));
});
window.addEventListener('dragover', e => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { e.preventDefault(); $('drop').className = 'on'; } });
window.addEventListener('dragleave', e => { if (!e.relatedTarget) $('drop').className = ''; });
window.addEventListener('drop', e => {
  $('drop').className = '';
  const f = e.dataTransfer && e.dataTransfer.files[0];
  if (f) { e.preventDefault(); install(f); }
});
window.addEventListener('focus', () => { if (S) api('rescan', {}).then(s => { S = s; render(); analyse(); }).catch(() => {}); });
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); $('new').click(); }
});

$('cfg').onclick = () => {
  const p = cur(), d = $('dlg'); if (!p) return;
  d.className = 'mid';
  d.innerHTML = `<h2 style="margin-top:0">Playset settings</h2>
    <label>Name</label><input type="text" id="c-name" maxlength="60" value="${esc(p.name)}">
    <label>Notes</label><textarea id="c-notes" maxlength="2000">${esc(p.notes)}</textarea>
    <label>Extra launch arguments (one per line, e.g. -debug_mode)</label><textarea id="c-args">${esc(p.launch_args.join('\n'))}</textarea>
    <label class="chk" style="color:var(--ink);${S.game.has_saves ? '' : 'display:none'}"><input type="checkbox" id="c-saves" ${p.separate_saves ? 'checked' : ''}> Own save folder for this playset (off = every playset shares the game's normal saves)
    </label><div class="mut" style="font-size:12px;${S.game.has_saves ? '' : 'display:none'}">Your existing "save games" folder is never deleted; it is moved aside to a backup the first time.</div>
    <div class="dlg-btns"><span><button id="c-dup">Duplicate</button> <button id="c-exp">Export</button> <button id="c-pre" title="Keep this Workshop mod list as a reusable preset">Save as preset</button> <button id="c-del" class="danger">Delete</button></span>
    <span><button id="c-cancel">Cancel</button> <button id="c-save" class="pri">Save</button></span></div>`;
  d.showModal();
  $('c-cancel').onclick = () => d.close();
  $('c-save').onclick = guard(async () => {
    await patch({name: $('c-name').value, notes: $('c-notes').value, separate_saves: $('c-saves').checked,
      launch_args: $('c-args').value.split('\n').map(s => s.trim()).filter(Boolean)});
    d.close();
  });
  $('c-dup').onclick = guard(async () => {
    const n = prompt('Name for the copy', p.name + ' copy'); if (!n) return;
    const r = await api(`playsets/${p.id}/duplicate`, {name: n}); await api(`playsets/${r.id}/activate`, {}); d.close(); load();
  });
  $('c-exp').onclick = guard(async () => {
    const x = await api(`playsets/${p.id}/share`), a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(x, null, 2)], {type: 'application/json'}));
    a.download = x.name.replace(/[^\w.-]+/g, '_') + `.${G}playset.json`; a.click();
  });
  $('c-pre').onclick = guard(async () => {
    const n = prompt('Preset name', p.name); if (!n) return;
    const id = n.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'preset';
    await api(`playsets/${p.id}/save-preset`, {id, name: n}); P = null; toast('Saved. Find it in the Presets tab.');
  });
  $('c-del').onclick = guard(async () => {
    if (!confirm(`Delete playset "${p.name}"? Mods are not touched.`)) return;
    await api(`playsets/${p.id}/delete`, {}); d.close(); load();
  });
};

document.addEventListener('click', e => { if (e.target.id === 'warn-cfg') openWarnCfg(); });
function openWarnCfg() {
  const d = $('dlg'), h = hiddenCodes();
  d.className = 'mid';
  d.innerHTML = `<h2 style="margin-top:0">Warning settings</h2><p class="mut">Untick a kind of warning to hide it for ${esc(GNAME())}. Hidden warnings are still real; they just stop counting and showing. Saved in this browser.</p>
    ${Object.entries(WARN_CODES).map(([c, l]) => `<label style="display:flex;gap:8px;align-items:center;color:var(--ink);font-size:14px"><input type="checkbox" data-wc="${c}" ${h.includes(c) ? '' : 'checked'}> ${esc(l)}</label>`).join('')}
    <div class="dlg-btns"><button id="w-all">Show all</button><span><button id="w-close" class="pri">Done</button></span></div>`;
  d.querySelectorAll('[data-wc]').forEach(c => c.onchange = () => {
    const hid = [...d.querySelectorAll('[data-wc]')].filter(x => !x.checked).map(x => x.dataset.wc);
    try { localStorage.setItem(wkey(), JSON.stringify(hid)); } catch {}
    render();
  });
  $('w-all').onclick = () => { d.querySelectorAll('[data-wc]').forEach(c => c.checked = true); try { localStorage.removeItem(wkey()); } catch {} render(); };
  $('w-close').onclick = () => d.close();
  d.showModal();
}

$('launchpart').onclick = guard(async () => {
  const p = cur(); if (!p) return;
  const ids = p.mods.filter(id => !p.disabled.includes(id) && M(id));
  if (!ids.length) return toast('This playset has no enabled mods.');
  const d = $('dlg');
  d.className = 'mid';
  d.innerHTML = `<h2 style="margin-top:0">Launch part of this playset</h2><p class="mut">Choose which mods to start ${esc(GNAME())} with. The playset itself is not changed.</p>
    <div class="acts"><button class="sm" id="lp-all">All</button><button class="sm" id="lp-none">None</button>
    <button class="sm" id="lp-deps" title="Also tick everything the ticked mods need">+ Their dependencies</button></div>
    <div style="max-height:46vh;overflow:auto;margin-top:8px">${ids.map(id => `<label style="display:flex;gap:8px;align-items:center;color:var(--ink);font-size:14px;margin:4px 0"><input type="checkbox" data-lp="${esc(id)}" checked> ${esc(nameOf(id))}</label>`).join('')}</div>
    <div id="lp-warn" class="warn" style="margin-top:8px"></div>
    <div class="dlg-btns"><button id="lp-cancel">Cancel</button><button id="lp-go" class="pri">▶ Launch selected</button></div>`;
  const boxes = () => [...d.querySelectorAll('[data-lp]')];
  const chosen = () => boxes().filter(b => b.checked).map(b => b.dataset.lp);
  const check = () => {
    const have = new Set(chosen()), miss = [];
    have.forEach(id => (M(id).dependencies || []).forEach(dep => {
      const dm = S.mods.find(o => o.name === dep || String(o.remote_id) === dep || 'ugc_' + o.remote_id === dep);
      if (dm && !have.has(dm.id) && !miss.includes(dm.name)) miss.push(dm.name);
    }));
    $('lp-warn').textContent = miss.length ? `Needed but not ticked: ${miss.join(', ')}` : '';
  };
  d.onchange = check;
  $('lp-all').onclick = () => { boxes().forEach(b => b.checked = true); check(); };
  $('lp-none').onclick = () => { boxes().forEach(b => b.checked = false); check(); };
  $('lp-deps').onclick = () => {
    for (let n = 0; n < 20; n++) { const before = chosen().length;
      chosen().forEach(id => (M(id).dependencies || []).forEach(dep => { const dm = S.mods.find(o => o.name === dep || String(o.remote_id) === dep || 'ugc_' + o.remote_id === dep); const b = dm && boxes().find(x => x.dataset.lp === dm.id); if (b) b.checked = true; }));
      if (chosen().length === before) break; }
    check();
  };
  $('lp-cancel').onclick = () => d.close();
  $('lp-go').onclick = guard(async () => {
    const only = chosen(); if (!only.length) return toast('Tick at least one mod.');
    d.close();
    const r = await launchCall(p, {only}); if (!r) return;
    toast(`Started ${GNAME()} with ${r.written} of ${ids.length} mods.` + (r.problems ? ` ${r.problems} problem(s) in that selection.` : ''));
  });
  check(); d.showModal();
});

async function launchCall(p, body) {
  try { return await api(`playsets/${p.id}/launch`, body); }
  catch (e) {
    if (e.body && e.body.code === 'save_version') {
      if (!confirm(e.message + '\n\nLaunch anyway?')) return null;
      return api(`playsets/${p.id}/launch`, {...body, ack_version: true});
    }
    throw e;
  }
}
$('launch').onclick = guard(async () => {
  const p = cur(), errs = visIssues().filter(i => i.severity === 'error').length; if (!p) return;
  if (errs && !confirm(`This playset has ${errs} error${errs === 1 ? '' : 's'} (see Warnings). Launch anyway?`)) return;
  const r = await launchCall(p, {}); if (!r) return;
  toast((r.file === 'command line' ? `Started ${GNAME()} with ${r.written} module${r.written === 1 ? '' : 's'}.` : `Wrote ${r.written} mods to ${r.file} and started ${GNAME()}${r.via === 'steam' ? ' through Steam' : ''}.`) +
    (r.saves && r.saves.startsWith('linked_after_backup') ? ' Your old save folder was kept as a backup.' : ''));
});
function applyTheme(g) {
  const root = document.documentElement.style;
  Object.entries(g.theme || {}).forEach(([k, v]) => root.setProperty(k, v));
  root.colorScheme = 'dark';
}
// The player's own colours and text size (Settings -> UI), kept per game. "default" is the game's own look.
const SCHEMES = {
  midnight: {name: 'Midnight', dark: true, v: {'--bg': '#0b0f1a', '--side': '#0f1524', '--panel': '#151d30', '--line': '#26324d', '--ink': '#e6ecf8', '--mut': '#93a0bb', '--acc': '#6cb0ff', '--accink': '#06121f', '--p1': '#2b4d86', '--p2': '#3a66ad', '--p3': '#244070'}},
  parchment: {name: 'Parchment (light)', dark: false, v: {'--bg': '#f3ead6', '--side': '#e9dcc0', '--panel': '#fbf5e6', '--line': '#cdbd98', '--ink': '#2a2116', '--mut': '#6b5c45', '--acc': '#8a5a1c', '--accink': '#fffaf0', '--p1': '#b07a2a', '--p2': '#9a6620', '--p3': '#7a4f14'}},
  forest: {name: 'Forest', dark: true, v: {'--bg': '#0c130e', '--side': '#101a13', '--panel': '#16231a', '--line': '#2a3d2f', '--ink': '#e3efe0', '--mut': '#8fa591', '--acc': '#8fd08a', '--accink': '#0a1a0c', '--p1': '#2f6b3a', '--p2': '#3f8a4c', '--p3': '#25532e'}},
  slate: {name: 'Slate', dark: true, v: {'--bg': '#14161a', '--side': '#101215', '--panel': '#1c1f25', '--line': '#2f343d', '--ink': '#e8eaee', '--mut': '#9199a6', '--acc': '#c9ced8', '--accink': '#14161a', '--p1': '#454c5a', '--p2': '#5a6374', '--p3': '#3a404c'}},
  rose: {name: 'Rose', dark: true, v: {'--bg': '#150d12', '--side': '#1b1018', '--panel': '#241520', '--line': '#43263a', '--ink': '#f6e6ee', '--mut': '#b496a6', '--acc': '#f08cb4', '--accink': '#2a0c1a', '--p1': '#8a2f5c', '--p2': '#ad3f75', '--p3': '#6a2247'}},
  contrast: {name: 'High contrast', dark: true, v: {'--bg': '#000000', '--side': '#000000', '--panel': '#0d0d0d', '--line': '#8a8a8a', '--ink': '#ffffff', '--mut': '#d0d0d0', '--acc': '#ffd400', '--accink': '#000000', '--p1': '#1f3fd0', '--p2': '#2f55f0', '--p3': '#1a34a8'}},
};
const TEXT_SIZES = {small: ['Small', .9], normal: ['Normal', 1], large: ['Large', 1.15], xlarge: ['Extra large', 1.3]};
function applyUI() {
  const root = document.documentElement.style, sc = S && SCHEMES[S.ui_scheme];
  if (sc) { Object.entries(sc.v).forEach(([k, v]) => root.setProperty(k, v)); root.colorScheme = sc.dark ? 'dark' : 'light'; }
  else if (G && GI) applyTheme(GI.games.find(g => g.id === G) || {});
  root.setProperty('--zoom', String((TEXT_SIZES[S && S.ui_text] || TEXT_SIZES.normal)[1]));
}
// The header always shows the game's logo, never its name as text. While the logo is still being fetched
// (or if it cannot be had) a neutral crest in the game's colours stands in, so nothing flips or jumps.
const CREST = '<svg class="crest" viewBox="0 0 64 64" aria-hidden="true"><path d="M32 4 56 12v20c0 14-10 24-24 28C18 56 8 46 8 32V12z" fill="none" stroke="currentColor" stroke-width="3"/><path d="M32 16v32M20 26h24" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>';
let logoTry = 0;
function setLogo(id) {
  const box = $('logo');
  if (box.dataset.k === id) return;
  box.dataset.k = id; logoTry = 0;
  box.innerHTML = `<div class="logo-box">${CREST}<img alt="" src="/api/${id}/logo"></div><span class="sub">Ronin Mod Manager</span>`;
  const img = box.querySelector('img');
  img.onload = () => {   // a dark logo (e.g. black lettering) would vanish on the dark theme: lighten it
    try {
      const c = document.createElement('canvas'); c.width = c.height = 48;
      const x = c.getContext('2d', {willReadFrequently: true}); x.drawImage(img, 0, 0, 48, 48);
      const d = x.getImageData(0, 0, 48, 48).data; let sum = 0, n = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 128) { sum += (d[i] + d[i + 1] + d[i + 2]) / 3; n++; }
      if (n > 20 && sum / n < 70) img.style.filter = 'invert(1) brightness(.92) drop-shadow(0 2px 6px rgba(0,0,0,.6))';
    } catch (e) { /* cross-origin or blocked canvas: leave as is */ }
    img.classList.add('ok');
  };
  img.onerror = () => { if (logoTry++ < 8 && box.dataset.k === id) setTimeout(() => { if (box.dataset.k === id) img.src = `/api/${id}/logo?r=${logoTry}`; }, 1500); };
}
async function useGame(id, first) {
  gen++; G = id; S = A = C = P = null; sel = null; tab = 'order'; cmpWith = null; lastMissing = []; setupShown = false;
  try { localStorage.setItem('mm-game', id); } catch (e) { /* storage may be blocked */ }
  if (location.hash.slice(1) !== id) history.replaceState(null, '', '#' + id);
  const g = GI.games.find(x => x.id === id);
  applyTheme(g);
  $('game').value = id;
  setLogo(g.id);
  document.title = g.name + ' · Ronin Mod Manager';
  await load(first);
}
// ---- games the user adds (beta) ----
const ADD_GAME = '__add';
function fillGames() {
  $('game').innerHTML = GI.games.map(g => `<option value="${esc(g.id)}">${esc(g.name)}${g.custom ? ' (beta)' : ''}</option>`).join('') +
    `<option value="${ADD_GAME}">＋ Add a game (beta)…</option>`;
  if (G) $('game').value = G;
}
async function adoptGames(r) {   // the answer carries the whole game list
  GI.games = r.games; GI.custom_games = r.custom_games; GI.game_templates = r.game_templates;
  fillGames();
}
const GAME_FORM = [   // [key, label, hint, only for kind]
  ['name', 'Game name', 'Shown in the game list.'],
  ['app_id', 'Steam app id', 'The number in the game\'s Steam store address (store.steampowered.com/app/<number>). Used to start the game and to find its Workshop folder. Leave empty if it is not on Steam.'],
  ['user_dir_name', 'Folder in Documents', 'The game\'s own folder, where it keeps saves and mods, for example "Stellaris".'],
  ['user_parent', 'Inside which folder', 'The folder that holds it. Paradox games use "Paradox Interactive"; leave empty if it is straight in Documents.'],
  ['install_dir_name', 'Install folder name', 'The folder under steamapps/common, for example "Stellaris".'],
  ['install_marker', 'Folder that proves it is the game', 'A folder inside the install, for example "common" or "game/common". Used to recognise the install when you point to it.'],
  ['content_dir', 'Base content folder', 'Where the game\'s own files live inside the install: "game" for most Paradox games, empty if they are straight in the install folder.'],
  ['load_file', 'Mod list file', 'The file in the Documents folder the game reads its mods from, usually dlc_load.json.', 'paradox'],
  ['load_style', 'How mods are listed', '"descriptor" = mod/ugc_<id>.mod files; "path" = folder paths in the list.', 'paradox'],
  ['def_dirs', 'Folders to check for conflicts', 'Script folders inside a mod where two mods can clash, comma separated.', 'paradox'],
  ['vanilla_only', 'Base game folders to compare', 'Optional. Only these folders of the base game are compared with mods (comma separated). Empty = all.', 'paradox'],
  ['seed_mods', 'Modules every playset starts with', 'Comma separated module ids.', 'modules'],
  ['exe_rel', 'Game executable', 'Inside the install folder, for example bin/Win64_Shipping_Client/Game.exe.', 'modules'],
  ['launch_prefix', 'Arguments before the module list', 'For example /singleplayer.', 'modules'],
];
function openGameDialog(editId) {
  const d = $('dlg'), def = editId ? GI.custom_games[editId] : null, T = GI.game_templates;
  d.className = 'wide gform';
  d.innerHTML = `<div class="st-head"><h2>${def ? 'Edit ' + esc(def.name) : 'Add a game'} <span class="b warn">beta</span></h2>
      <span class="mut">For games that work like Paradox\'s or like Bannerlord. Nothing here is checked against a real install.</span></div>
    <div class="st-form">
      <div class="card">
        ${def ? '' : `<div><label class="fld" for="gf-tpl">Start from<span class="hint">Fills in the fields below. Check them against your game.</span></label>
          <select id="gf-tpl">${T.map((t, i) => `<option value="${i}">${esc(t.label)}</option>`).join('')}</select></div>`}
        <div><label class="fld" for="gf-kind">Type of game<span class="hint">"paradox": mods are listed in a file in the game\'s Documents folder. "modules": Bannerlord style, mods are module folders and the game is started with the list.</span></label>
        <select id="gf-kind"><option value="paradox">Paradox style (mod list file)</option><option value="modules">Bannerlord style (modules)</option></select></div>
        ${GAME_FORM.map(([k, l, h, only]) => `<div data-only="${only || ''}"><label class="fld" for="gf-${k}">${esc(l)}<span class="hint">${esc(h)}</span></label><input type="text" id="gf-${k}"></div>`).join('')}
        <div><label class="fld" for="gf-accent">Colour<span class="hint">The accent colour of the app for this game.</span></label>
        <input type="color" id="gf-accent" value="#8fa8d0"></div>
        <p class="warn" id="gf-msg"></p>
      </div></div>
    <div class="st-foot"><span class="mut">The game\'s folders are chosen afterwards under Settings &gt; Game and Storage. The game\'s own files are never changed by this form.</span><span><button id="gf-cancel">Cancel</button> <button id="gf-save" class="pri">${def ? 'Save' : 'Add game'}</button></span></div>`;
  const fill = v => {
    $('gf-kind').value = v.kind || 'paradox';
    GAME_FORM.forEach(([k]) => { $('gf-' + k).value = v[k] == null ? '' : v[k]; });
    $('gf-accent').value = v.accent || '#8fa8d0';
    show();
  };
  const show = () => d.querySelectorAll('[data-only]').forEach(x => { x.hidden = !!x.dataset.only && x.dataset.only !== $('gf-kind').value; });
  $('gf-kind').onchange = show;
  if (def) fill(def); else { fill(T[0]); $('gf-tpl').onchange = () => fill(T[+$('gf-tpl').value]); }
  $('gf-cancel').onclick = () => d.close();
  $('gf-save').onclick = guard(async () => {
    const game = {kind: $('gf-kind').value, accent: $('gf-accent').value};
    GAME_FORM.forEach(([k, , , only]) => { if (!only || only === game.kind) game[k] = $('gf-' + k).value; });
    $('gf-msg').textContent = '';
    let r;
    try { r = await app('custom-games', {game, ...(def ? {id: editId} : {})}); } catch (e) { $('gf-msg').textContent = e.message; return; }
    d.close(); await adoptGames(r);
    if (def) { await useGame(editId, true); } else { await useGame(r.id, true); toast('Added. Set its folders under Settings, then use "Check this game".'); }
  });
  d.showModal();
}
$('game').onchange = guard(async () => {
  if ($('game').value === ADD_GAME) { $('game').value = G; return openGameDialog(); }
  await useGame($('game').value, true);
});
window.addEventListener('hashchange', () => { const w = location.hash.slice(1); if (GI && w !== G && GI.games.some(g => g.id === w)) useGame(w, true).catch(e => fail(e, 'hash')); });
(async () => {
  GI = await app('games');
  $('ver').textContent = 'v' + GI.version + (GI.build ? ' · test ' + GI.build : '');
  fillGames();
  let want = location.hash.slice(1);
  try { want = want || localStorage.getItem('mm-game') || ''; } catch (e) { /* ignore */ }
  want = GI.games.some(g => g.id === want) ? want : (GI.games.some(g => g.id === GI.last_game) ? GI.last_game : GI.games[0].id);
  await useGame(want, true);
})().catch(e => fail(e, 'startup'));
