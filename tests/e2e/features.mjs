// Browser test of: file trees (per mod + result), mod update check, save-version confirmation, warnings, launch part.
// SHOTS=<dir> also writes screenshots there.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-feat-'));
const user = path.join(root, 'user');
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + '.png') }); };
for (const [f, deps, files] of [['Lib', [], ['common/goods/lib_goods.txt', 'common/shared.txt']], ['Economy Overhaul', ['Lib'], ['common/goods/zz_goods.txt', 'common/shared.txt', 'events/eco.txt']], ['Tweaks', [], ['common/tweaks.txt']]]) {
  const id = f.replace(/ /g, '_');
  write(path.join(user, 'mod', id, '.metadata/metadata.json'), JSON.stringify({ name: f, version: '1', relationships: deps.map(d => ({ rel_type: 'dependency', display_name: d })) }));
  for (const rel of files) write(path.join(user, 'mod', id, rel), rel.includes('goods') ? 'steel = { cost = 1 }\n' : 'x = {}\n');
  write(path.join(user, 'mod', `${id}.mod`), `name="${f}"\npath="mod/${id}"\n`);
}
const server = spawn('python3', ['-m', 'modmanager', '--game', 'vic3', '--user-dir', user, '--workshop-dir', path.join(root, 'none'),
  '--game-version', '1.8.1', '--no-browser', '--port', String(port)], { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg') }, stdio: 'inherit' });
const post = async (p, b = {}) => (await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) })).json();
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/vic3/state`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  await post('/api/vic3/playsets', { name: 'Default', mods: ['local:Lib', 'local:Economy_Overhaul', 'local:Tweaks'] });
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 850 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${base}/#vic3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  await page.waitForSelector('#view .row');
  await shot(page, '1-load-order');

  // ---- conflicts show the file each mod defines the key in
  await page.click('[data-tab=conflicts]');
  await page.waitForSelector('text=common/goods: steel');
  assert.match(await page.textContent('#view'), /lib_goods\.txt/);
  assert.match(await page.textContent('#view'), /zz_goods\.txt/);
  await shot(page, '2-conflicts-with-files');

  // ---- result tree: lazily expands, tags the winner, marks doubled files
  await page.click('[data-tab=files]');
  await page.waitForSelector('#ft details');
  await page.locator('#ft summary', { hasText: 'common/' }).first().click();
  await page.waitForSelector('#ft .tf:has-text("shared.txt")');
  assert.match(await page.locator('#ft .tf', { hasText: 'shared.txt' }).textContent(), /Economy Overhaul/);
  assert.match(await page.locator('#ft .tf', { hasText: 'shared.txt' }).textContent(), /2×/);
  await page.fill('#tq', 'eco');
  await page.waitForFunction(() => document.querySelectorAll('#ft details').length === 1);
  await shot(page, '3-result-file-tree');

  // ---- per-mod tree in the drawer
  await page.click('[data-tab=order]');
  await page.locator('#view .nm', { hasText: /^Lib$/ }).click();
  await page.click('[data-filesof]');
  await page.locator('#d-ft summary', { hasText: 'common/' }).first().click();
  await page.waitForSelector('#d-ft .tf:has-text("shared.txt")');
  assert.match(await page.locator('#d-ft .tf', { hasText: 'shared.txt' }).textContent(), /overridden by Economy Overhaul/);
  await shot(page, '4-mod-file-tree');

  // ---- mod updates (Steam answer mocked)
  await page.route('**/api/vic3/mod-updates', route => route.fulfill({ json: [
    { id: 'ws:1', name: 'Some Workshop Mod', remote_id: '1', status: 'update', local: 1000, remote: 1700000000 },
    { id: 'ws:2', name: 'Other', remote_id: '2', status: 'unknown', local: null, remote: null }] }));
  await page.click('[data-tab=library]');
  await page.click('#modupd');
  await page.waitForSelector('text=1 available');
  assert.match(await page.textContent('#view'), /Some Workshop Mod/);
  await shot(page, '5-mod-updates');

  // ---- save-version warning: first launch is refused with a 409, the user confirms, it is retried with the OK flag
  const bodies = [];
  await page.route('**/api/vic3/playsets/*/launch', async route => {
    const b = JSON.parse(route.request().postData() || '{}'); bodies.push(b);
    if (!b.ack_version) return route.fulfill({ status: 409, json: { error: 'Your saves were made on game version 1.7 but a newer version (1.8) is about to start.', code: 'save_version', saved_on: '1.7', game_version: '1.8' } });
    return route.fulfill({ json: { written: 3, file: 'content_load.json', saves: null, via: 'steam' } });
  });
  let asked = '';
  page.on('dialog', d => { asked = d.message(); d.accept(); });
  await page.click('[data-tab=order]');
  await page.click('#launch');
  await page.waitForSelector('#toast.on:has-text("started")');
  assert.match(asked, /1\.7/);
  assert.equal(bodies.length, 2);
  assert.equal(bodies[1].ack_version, true);
  // declining sends nothing more
  bodies.length = 0;
  page.removeAllListeners('dialog'); page.on('dialog', d => d.dismiss());
  await page.click('#launch');
  await page.waitForTimeout(500);
  assert.equal(bodies.length, 1);

  // ---- settings has the save-version switch, on by default, persisted
  await page.click('#appcfg');
  await page.click('[data-st=play]');
  assert.equal(await page.locator('#p-svc').isChecked(), true);
  await shot(page, '6-settings');
  await page.click('#p-cancel');
  assert.deepEqual(errors, [], 'no page errors');
  console.log('features e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
