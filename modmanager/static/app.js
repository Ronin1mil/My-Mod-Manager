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
    const e = new Error(`Could not reach Mod Manager (${err.message}). Is its window still open?`);
    e.network = true; throw e;
  }
  if (!r.ok) { const e = new Error(j.error || 'Request failed'); e.body = j; e.status = r.status; if (j.log_file) logFile = j.log_file; throw e; }
  return j;
};
const api = async (p, b) => { const g = gen, r = await call(`/api/${G}/${p}`, b); if (g !== gen) throw new Stale(); return r; };   // current game
const app = (p, b) => call('/api/' + p, b);        // app-wide
const GNAME = () => (S && S.game ? S.game.name : G);
const M = id => S.mods.find(m => m.id === id);
const cur = () => (S && S.playsets ? S.playsets.find(p => p.id === S.active) : null);
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
  b.innerHTML = `<b>Something went wrong:</b> ${esc(e.message)}<br><span class="mut">Details were saved to <code>${esc(logFile || 'your Documents folder (ModManager-errors.log)')}</code>.</span> <button class="sm" id="bn-x">Hide</button>`;
  $('bn-x').onclick = () => { b.hidden = true; };
}
window.addEventListener('error', ev => { if (ev.error instanceof Stale) return; report(ev.message, ev.error && ev.error.stack, `${ev.filename}:${ev.lineno}`); showFatal(new Error(ev.message)); });
window.addEventListener('unhandledrejection', ev => { const e = ev.reason; if (e instanceof Stale) { ev.preventDefault(); return; } report((e && e.message) || e, e && e.stack, 'promise'); });

async function load(rescanMsg) {
  T = null; P = null;
  S = await api('state');
  if (!S.playsets.length) { await api('playsets', {name: 'Default'}); return load(); }
  if (!cur()) { S.active = S.playsets[0].id; await api(`playsets/${S.active}/activate`, {}); }
  if (rescanMsg) {
    const d = S.diff, bits = [d.added && `${d.added} new`, d.updated && `${d.updated} updated`, d.removed && `${d.removed} removed`].filter(Boolean);
    toast(bits.length ? `Scan: ${bits.join(', ')} (${d.total} mods)` : `Scan: no changes (${d.total} mods)`);
  }
  logoSeen[G] = !!S.has_logo; setLogo(G, GNAME(), S.has_logo);
  document.title = GNAME() + ' Mod Manager';
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
async function patch(fields) {
  const p = cur(); if (!p) return;
  Object.assign(p, await api(`playsets/${p.id}/update`, fields));
  render(); analyse();
  if (tab === 'compare') loadCompare();
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
function badges(m) {
  return (m.change === 'new' ? '<span class="b new">NEW</span>' : m.change === 'updated' ? '<span class="b new">UPDATED</span>' : '') +
    (m.multiplayer_synchronized === false ? '<span class="b warn" title="Not multiplayer synchronized">MP-unsafe</span>' : '') +
    (m.exists ? '' : '<span class="b err">missing</span>') + `<span class="b">${esc(m.source)}</span>`;
}

function render() {
  if (!S || !cur()) return;
  const p = cur(), errs = visIssues().filter(i => i.severity === 'error').length; if (!p) return;
  $('pslist').innerHTML = S.playsets.map(x => `<div class="ps ${x.id === S.active ? 'on' : ''}" data-ps="${esc(x.id)}"><span>${esc(x.name)}</span><span class="mut">${x.mods.length - x.disabled.length}</span></div>`).join('');
  $('title').textContent = p.name;
  $('auto').checked = p.auto_sort;
  $('sortnow').style.display = p.auto_sort ? 'none' : '';
  const nIss = visIssues().length, nCon = A && !A.pending ? A.conflicts.filter(x => x.severity !== 'info' && !x.vanilla).length : 0;
  $('tabs').innerHTML = [['order', 'Load order'], ['library', `Library (${S.mods.length})`], ['problems', `Warnings${nIss ? ` (${nIss})` : ''}`], ['conflicts', `Conflicts${A && A.pending ? ' …' : nCon ? ` (${nCon})` : ''}`], ['files', 'Files'], ['compare', 'Compare'], ['presets', 'Presets']]
    .map(([k, l]) => `<button data-tab="${k}" class="${tab === k ? 'on' : ''}">${l}</button>`).join('');
  const active = p.mods.length - p.disabled.length;
  $('status').innerHTML = `${esc(GNAME())}${S.game_version ? ` ${esc(S.game_version)}` : ''} · ${active} mod${active === 1 ? '' : 's'} active` +
    (errs ? ` · <span class="err">${errs} error${errs === 1 ? '' : 's'}</span>` : A && nIss ? ` · <span class="warn">${nIss} warning${nIss === 1 ? '' : 's'}</span>` : '');
  ({order: viewOrder, library: viewLibrary, problems: viewProblems, conflicts: viewConflicts, compare: viewCompare, presets: viewPresets, files: viewFiles})[tab](p);
  drawer();
}

function viewOrder(p) {
  const bar = `<div class="bar"><span class="mut">Top loads first, bottom wins.</span><span class="grow"></span>
    <button class="sm" data-bulk="enable_all">Enable all</button><button class="sm" data-bulk="disable_all">Disable all</button>
    <button class="sm" data-bulk="prune" title="Remove mods that are no longer installed">Prune</button></div>`;
  $('view').innerHTML = bar + p.mods.map((id, i) => {
    const m = M(id), off = p.disabled.includes(id), w = worst(id);
    return `<div class="row ${off ? 'off' : ''} ${id === sel ? 'sel' : ''}" draggable="true" data-i="${i}">
      <span class="h">⠿</span><span class="n">${i + 1}</span>
      <input type="checkbox" data-tog="${esc(id)}" ${off ? '' : 'checked'}>
      <span class="nm" data-sel="${esc(id)}">${esc(m ? m.name : id + ' (not installed)')}</span>
      ${m ? badges(m) : ''}${w && !off ? `<span class="b ${w}">${w === 'err' ? 'error' : 'warning'}</span>` : ''}
      <button class="sm" data-mv="${i},-1">↑</button><button class="sm" data-mv="${i},1">↓</button><button class="sm" data-rm="${esc(id)}">✕</button></div>`;
  }).join('') || '<div class="empty">This playset is empty.<br>Add mods from the Library tab.</div>';
}

function viewLibrary(p) {
  const f = q.toLowerCase();
  const list = S.mods.filter(m => !f || m.name.toLowerCase().includes(f) || (m.tags || []).some(t => t.toLowerCase().includes(f)));
  const rem = S.removed.length ? `<div class="row static"><span class="warn">Removed since last scan:</span> ${S.removed.map(r => esc(r.name)).join(', ')}</div>` : '';
  $('view').innerHTML = `<div class="bar"><input type="search" id="q" placeholder="Search name or tag…" value="${esc(q)}"><button id="addall">Add all shown</button><button id="modupd" title="Ask Steam which Workshop mods have a newer version">Check mod updates</button></div>${updPanel()}${rem}` +
    (list.map(m => {
      const inn = p.mods.includes(m.id);
      return `<div class="row ${m.id === sel ? 'sel' : ''}"><span class="nm" data-sel="${esc(m.id)}" title="${esc(m.root)}">${esc(m.name)}</span>${badges(m)}
        <button class="sm" data-add="${esc(m.id)}" ${inn || !m.exists ? 'disabled' : ''}>${inn ? '✓ Added' : '+ Add'}</button></div>`;
    }).join('') || `<div class="empty">No mods found.<br>${S.user_dir ? 'Drop a mod archive (.zip, .tar.gz) here to install one, or check the folders in Settings.' : esc(GNAME()) + ' user folder not found. Set it in Settings → Game folders.'}</div>`);
  $('modupd').onclick = guard(async () => { $('modupd').disabled = true; try { U = await api('mod-updates', {}); } finally { $('modupd').disabled = false; } viewLibrary(cur()); });
  const qi = $('q');
  qi.oninput = () => { q = qi.value; const pos = qi.selectionStart; viewLibrary(cur()); const n = $('q'); n.focus(); n.setSelectionRange(pos, pos); };
  $('addall').onclick = guard(async () => {
    const add = list.filter(m => m.exists && !p.mods.includes(m.id)).map(m => m.id);
    if (add.length) await patch({mods: [...p.mods, ...add]});
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
  if (act === 'add') await patch({mods: [...p.mods, t.dataset.id]});
  if (act === 'addall') await patch({mods: [...p.mods, ...C.only_b.filter(id => !p.mods.includes(id))]});
  if (act === 'state') {
    const id = t.dataset.id, on = t.dataset.to === 'enabled';
    await patch({disabled: on ? p.disabled.filter(x => x !== id) : [...p.disabled, id]});
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
async function selfUpdate() {
  if (!confirm('Download the newest version and restart Mod Manager? Your playsets and settings are kept.')) return;
  let st = await app('self-update', {});
  for (let i = 0; i < 600 && ['working', 'restarting'].includes(st.status); i++) {
    toast(st.message || 'Updating…');
    await new Promise(r => setTimeout(r, 1000));
    try { st = await app('self-update'); } catch (e) { if (st.status === 'restarting') break; throw e; }  // old copy exited
  }
  if (st.status === 'error') throw new Error(st.message);
  if (st.status === 'current') return toast(st.message);
  toast('Restarting…');
  for (let i = 0; i < 60; i++) {   // wait for the new copy, then load it
    await new Promise(r => setTimeout(r, 1000));
    try { const r = await fetch('/api/games'); if (r.ok) return location.reload(); } catch (e) { /* not up yet */ }
  }
  throw new Error('Mod Manager did not come back. Start it again from its icon; the update itself was installed.');
}
function banner() {
  const b = $('banner'), u = GI.update; b.className = '';
  if (!u || !u.update_available || GI.settings.dismissed_update === u.latest) { b.hidden = true; b.innerHTML = ''; return; }
  const link = u.url.startsWith(REPO_LINK) ? u.url : REPO_LINK + 'releases';
  b.hidden = false;
  b.innerHTML = `<span class="grow"><b>Version ${esc(u.latest)} is available</b> <span class="mut">(you have ${esc(GI.version)})</span></span>
    ${GI.can_self_update ? '<button class="sm pri" id="bn-now">Update now</button>' : ''}
    <a href="${esc(link)}" target="_blank" rel="noopener noreferrer">View release</a><button class="sm" id="bn-dismiss">Dismiss</button>`;
  if ($('bn-now')) $('bn-now').onclick = guard(selfUpdate);
  $('bn-dismiss').onclick = guard(async () => { GI.settings = await app('settings', {dismissed_update: u.latest}); banner(); });
}
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
  d.innerHTML = `<h2 style="margin-top:0">${first ? 'Set up ' + esc(GNAME()) : 'Settings'}</h2>
    <p class="mut">Mod Manager v${esc(GI.version)}${S.game.verified ? '' : ' · launching is <b>not yet verified</b> on a real ' + esc(GNAME()) + ' install'}</p>
    ${S.imported_from ? `<p class="mut">Playsets were imported from your previous manager (${esc(S.imported_from)}).</p>` : ''}
    <h3 class="sec" style="margin-top:6px;border:0;padding:0">Game folders — ${esc(GNAME())}</h3>
    <div id="p-found" class="mut" style="font-size:13px"></div>
    <div class="paths">
    <label for="p-game">Game folder (paste any path inside your install)</label><input type="text" id="p-game" value="${esc(S.game_root)}"><div class="st" id="p-gst"></div>
    <label for="p-user">User folder (mods, ${esc(S.game.load_file)})</label><input type="text" id="p-user" value="${esc(S.user_dir)}">
    <label for="p-ws">Steam Workshop folder</label><input type="text" id="p-ws" value="${esc(S.workshop_dir)}"></div>
    <label class="chk" style="color:var(--ink);margin-top:12px"><input type="checkbox" id="p-svc" ${S.save_version_check ? 'checked' : ''}> Warn before starting if the saves were made on a different game release (e.g. 1.14 → 1.15)</label>
    <label class="chk" style="color:var(--ink);margin-top:12px"><input type="checkbox" id="p-van" ${S.include_vanilla ? 'checked' : ''}> Compare mods with the base game (flags what each mod overrides)</label>
    <h3 class="sec">Downloading Workshop mods</h3>
    <div class="mut" style="font-size:12px">Optional. "Open in Steam" needs nothing. To download straight from here, give the path to <code>steamcmd</code> and the Steam account name it is already logged in with (log in once in a terminal; this app never sees or stores a password).</div>
    <div class="paths"><label for="p-cmd">steamcmd executable</label><input type="text" id="p-cmd" value="${esc(S.steamcmd)}">
    <label for="p-su">Steam account name</label><input type="text" id="p-su" value="${esc(S.steam_user)}"></div>
    <h3 class="sec">Updates (all games)</h3>
    <label class="chk" style="color:var(--ink)"><input type="checkbox" id="s-auto" ${st.auto_update_check ? 'checked' : ''}> Check for updates when the manager starts</label>
    <div class="mut" style="font-size:12px;margin-top:4px">Off by default. When on, the manager asks api.github.com for the latest release each time it starts. Nothing is downloaded or installed automatically, and nothing else is ever sent.</div>
    <div style="margin-top:10px"><button id="s-check">Check for updates now</button></div>
    <div id="s-result" style="margin-top:10px"></div>
    <div class="dlg-btns"><span></span><span><button id="p-cancel">${first ? 'Skip' : 'Cancel'}</button> <button id="p-save" class="pri">Save</button></span></div>`;
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
      (u.status === 'update' ? `<a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Open the release page</a>` : '');
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
  const psRow = t.closest('[data-ps]');
  if (psRow) { await api(`playsets/${psRow.dataset.ps}/activate`, {}); sel = null; return load(); }
  if (ds.tab) { tab = ds.tab; render(); if (tab === 'compare') await loadCompare(); if (tab === 'files') await loadFiles(); }
  if (ds.f) { flt = ds.f; render(); }
  if (ds.sel) { sel = sel === ds.sel ? null : ds.sel; render(); }
  if (ds.close) { sel = null; render(); }
  if (ds.add) await patch({mods: [...p.mods, ds.add]});
  if (ds.rm) await patch({mods: p.mods.filter(x => x !== ds.rm)});
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
  if (t.dataset.tog) { const id = t.dataset.tog; await patch({disabled: t.checked ? p.disabled.filter(x => x !== id) : [...p.disabled, id]}); }
}));
const view = $('view');
view.addEventListener('dragstart', e => { const r = e.target.closest('[data-i]'); if (r) { drag = +r.dataset.i; r.classList.add('drag'); } });
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
$('imp').onclick = () => $('impf').click();
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
  d.innerHTML = `<h2 style="margin-top:0">Playset settings</h2>
    <label>Name</label><input type="text" id="c-name" maxlength="60" value="${esc(p.name)}">
    <label>Notes</label><textarea id="c-notes" maxlength="2000">${esc(p.notes)}</textarea>
    <label>Extra launch arguments (one per line, e.g. -debug_mode)</label><textarea id="c-args">${esc(p.launch_args.join('\n'))}</textarea>
    <label class="chk" style="color:var(--ink)"><input type="checkbox" id="c-saves" ${p.separate_saves ? 'checked' : ''}> Own save folder for this playset (off = every playset shares the game's normal saves)
    </label><div class="mut" style="font-size:12px">Your existing "save games" folder is never deleted; it is moved aside to a backup the first time.</div>
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
  toast(`Wrote ${r.written} mods to ${r.file} and started ${GNAME()}${r.via === 'steam' ? ' through Steam' : ''}.` +
    (r.saves && r.saves.startsWith('linked_after_backup') ? ' Your old save folder was kept as a backup.' : ''));
});
function applyTheme(g) {
  const root = document.documentElement.style;
  Object.entries(g.theme || {}).forEach(([k, v]) => root.setProperty(k, v));
}
const logoSeen = {};
function setLogo(id, name, has) {   // one place decides logo vs. name, so switching games never flips between them
  const html = has ? `<img src="/api/${id}/logo" alt="${esc(name)}"><span class="sub">Mod Manager</span>`
    : `<span class="wm">${esc(name)}</span><span class="sub">Mod Manager</span>`;
  if ($('logo').dataset.k !== id + has) { $('logo').innerHTML = html; $('logo').dataset.k = id + has; }
}
async function useGame(id, first) {
  gen++; G = id; S = A = C = P = null; sel = null; tab = 'order'; cmpWith = null; lastMissing = []; setupShown = false;
  try { localStorage.setItem('mm-game', id); } catch (e) { /* storage may be blocked */ }
  if (location.hash.slice(1) !== id) history.replaceState(null, '', '#' + id);
  const g = GI.games.find(x => x.id === id);
  applyTheme(g);
  $('game').value = id;
  setLogo(g.id, g.name, logoSeen[g.id]);
  document.title = g.name + ' Mod Manager';
  await load(first);
}
$('game').onchange = guard(() => useGame($('game').value, true));
window.addEventListener('hashchange', () => { const w = location.hash.slice(1); if (GI && w !== G && GI.games.some(g => g.id === w)) useGame(w, true).catch(e => fail(e, 'hash')); });
(async () => {
  GI = await app('games');
  $('ver').textContent = 'v' + GI.version;
  $('game').innerHTML = GI.games.map(g => `<option value="${esc(g.id)}">${esc(g.name)}</option>`).join('');
  let want = location.hash.slice(1);
  try { want = want || localStorage.getItem('mm-game') || ''; } catch (e) { /* ignore */ }
  want = GI.games.some(g => g.id === want) ? want : (GI.games.some(g => g.id === GI.last_game) ? GI.last_game : GI.games[0].id);
  await useGame(want, true);
})().catch(e => fail(e, 'startup'));
