// Browser test of the Compare tab, the Settings dialog (auto-update setting, off by default) and the update banner.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-cmp-'));
const user = path.join(root, 'user');
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
for (const [f, deps] of [['Lib', []], ['A', ['Lib']], ['B', []], ['C', []]]) {
  write(path.join(user, 'mod', f, '.metadata/metadata.json'), JSON.stringify({ name: f, version: '1',
    relationships: deps.map(d => ({ rel_type: 'dependency', display_name: d })) }));
  write(path.join(user, 'mod', `${f}.mod`), `name="${f}"\npath="mod/${f}"\n`);
}
const server = spawn('python3', ['-m', 'modmanager', '--game', 'vic3', '--user-dir', user, '--workshop-dir', path.join(root, 'none'),
  '--no-browser', '--port', String(port)], { env: { ...process.env, MODMANAGER_CONFIG_DIR: path.join(root, 'cfg') }, stdio: 'inherit' });
const post = async (p, b = {}) => { const r = await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }); return r.json(); };
const get = async p => (await fetch(base + p)).json();
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/vic3/state`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const first = await post('/api/vic3/playsets', { name: 'Default', mods: ['local:Lib', 'local:A', 'local:B'] });
  const second = await post('/api/vic3/playsets', { name: 'Second', mods: ['local:C', 'local:Lib', 'local:A'] });
  await post(`/api/vic3/playsets/${first.id}/activate`);
  await post(`/api/vic3/playsets/${first.id}/update`, { auto_sort: false });
  await post(`/api/vic3/playsets/${second.id}/update`, { auto_sort: false });

  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 850 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  let injected = null;
  await page.route('**/api/games', async route => {
    const r = await route.fetch(); const j = await r.json();
    if (injected) j.update = injected;
    await route.fulfill({ json: j });
  });
  await page.goto(`${base}/#vic3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {}); // first-run setup: skip like a user would
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  await page.waitForSelector('#view .row');
  const rows = () => page.locator('#view .row .nm').allTextContents();
  const refresh = async () => { await page.click('#rescan'); await page.waitForTimeout(400); };  // pick up edits made outside the page
  const order = async pid => (await get('/api/vic3/state')).playsets.find(p => p.id === pid).mods.map(m => m.split(':')[1]);

  // ---- Compare: add what is only in the other playset
  await page.click('[data-tab=compare]');
  await page.waitForSelector('#cmpsel');
  await page.waitForSelector('text=Only in Default');
  assert.match(await page.textContent('#view'), /Only in Second/);
  assert.deepEqual(await page.locator('#view .cmp-h', { hasText: 'Only in Default' }).locator('xpath=following-sibling::div[1]').locator('.nm').allTextContents(), ['B']);
  await page.click('[data-cmp=add][data-id="local:C"]');
  await page.waitForFunction(() => !document.querySelector('[data-cmp=add]'));
  assert.ok((await order(first.id)).includes('C'));

  // ---- Compare: enabled/disabled differs -> "Match"
  await post(`/api/vic3/playsets/${second.id}/update`, { disabled: ['local:A'] });
  await refresh(); await page.click('[data-tab=order]'); await page.click('[data-tab=compare]');
  await page.waitForSelector('text=Enabled in one, disabled in the other');
  await page.click('[data-cmp=state][data-id="local:A"]');
  await page.waitForFunction(() => !document.querySelector('[data-cmp=state]'));
  assert.deepEqual((await get('/api/vic3/state')).playsets.find(p => p.id === first.id).disabled, ['local:A']);

  // ---- Compare: minimal "moved" set and "Match order"
  await post(`/api/vic3/playsets/${first.id}/update`, { disabled: [], mods: ['local:Lib', 'local:A', 'local:B', 'local:C'] });
  await post(`/api/vic3/playsets/${second.id}/update`, { disabled: [], mods: ['local:C', 'local:Lib', 'local:A', 'local:B'] });
  await refresh(); await page.click('[data-tab=order]'); await page.click('[data-tab=compare]');
  await page.waitForSelector('text=Loaded in a different order');
  const moved = await page.locator('#view .cmp-h', { hasText: 'different order' }).locator('xpath=following-sibling::div[position()<=4]').locator('.nm').allTextContents();
  assert.ok(moved.includes('C') && moved.length <= 2, `only the displaced mod(s) are listed, got ${moved}`);
  await page.click('[data-cmp=order]');
  await page.waitForSelector('text=These playsets are identical');
  assert.deepEqual(await order(first.id), ['C', 'Lib', 'A', 'B']);

  // ---- Compare: settings differences and the single-playset empty state
  await post(`/api/vic3/playsets/${second.id}/update`, { notes: 'hello', launch_args: ['-debug_mode'] });
  await refresh(); await page.click('[data-tab=order]'); await page.click('[data-tab=compare]');
  await page.waitForSelector('text=Settings that differ');
  assert.match(await page.textContent('#view'), /launch args/);
  await post(`/api/vic3/playsets/${second.id}/delete`);
  await page.reload(); await page.click('[data-tab=compare]');
  await page.waitForSelector('text=Create or import a second playset');

  // ---- Settings: auto-update check is OFF by default, toggling persists
  assert.equal((await get('/api/games')).settings.auto_update_check, false);
  await page.click('#appcfg');
  assert.equal(await page.locator('#s-auto').isChecked(), false);
  assert.match(await page.textContent('#dlg'), /Off by default/);
  await page.check('#s-auto');
  await page.waitForSelector('#toast.on');
  assert.equal((await get('/api/games')).settings.auto_update_check, true);
  await page.uncheck('#s-auto');
  await page.waitForFunction(async () => (await (await fetch('/api/games')).json()).settings.auto_update_check === false);

  // ---- "Check now" renders the result; hostile release content is inert
  await page.route('**/api/update-check', route => route.fulfill({ json: {
    current: '0.1.0', latest: '9.9.9', update_available: true, status: 'update', message: 'Version 9.9.9 is available.',
    url: 'https://evil.example/phish', notes: '<img src=x onerror="window.__pwned=1"> notes', published: '2026-11-01', assets: [] } }));
  await page.click('#s-check');
  await page.waitForSelector('text=Version 9.9.9 is available.');
  assert.equal(await page.locator('#s-result img').count(), 0, 'release notes are text, not HTML');
  assert.equal(await page.evaluate(() => window.__pwned), undefined);
  const href = await page.locator('#s-result a').getAttribute('href');
  assert.ok(href.startsWith('https://github.com/Ronin1mil/My-Mod-Manager/'), `off-repo link replaced, got ${href}`);
  assert.equal(await page.locator('#s-result a').getAttribute('rel'), 'noopener noreferrer');
  await page.click('#p-cancel');

  // ---- Banner on start-up when an update is known; Dismiss persists per version
  injected = { current: '0.1.0', latest: '9.9.9', update_available: true, status: 'update', message: 'x',
    url: 'https://github.com/Ronin1mil/My-Mod-Manager/releases/tag/v9.9.9', notes: '', published: '', assets: [] };
  await page.reload();
  await page.waitForSelector('#banner:not([hidden])');
  assert.match(await page.textContent('#banner'), /Version 9\.9\.9 is available/);
  await page.click('#bn-dismiss');
  await page.waitForSelector('#banner[hidden]', { state: 'attached' });
  await page.reload();
  await page.waitForSelector('#view .row, #view .empty');
  assert.equal(await page.locator('#banner').isHidden(), true, 'dismissed version stays dismissed');
  injected = { ...injected, latest: '9.9.10', url: injected.url.replace('9.9.9', '9.9.10') };
  await page.reload();
  await page.waitForSelector('#banner:not([hidden])');  // a newer version shows again

  assert.deepEqual(errors, [], 'no page errors');
  console.log('compare/settings e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
