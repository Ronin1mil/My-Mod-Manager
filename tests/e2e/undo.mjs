// Browser test of Undo / Redo (buttons and Ctrl+Z / Ctrl+Y), a note on a mod, and restoring a deleted playset.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';
import { seed } from './seed.mjs';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-undo-'));
const user = path.join(root, 'user');
const port = await freePort();
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
for (const f of ['A', 'B', 'C']) {
  write(path.join(user, 'mod', f, '.metadata/metadata.json'), JSON.stringify({ name: f, version: '1' }));
  write(path.join(user, 'mod', `${f}.mod`), `name="${f}"\npath="mod/${f}"\n`);
}
const server = spawn('python3', ['-m', 'modmanager', '--game', 'vic3', '--user-dir', user, '--workshop-dir', path.join(root, 'none'),
  '--game-version', '1.7.6', '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg') }, stdio: 'inherit' });
const base = `http://127.0.0.1:${port}`;
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/vic3/state`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  await seed(base, 'vic3');
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 800 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  await page.goto(`${base}/#vic3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  const names = () => page.locator('#view .row .nm').allTextContents();
  const rows = n => page.waitForFunction(k => document.querySelectorAll('#view .row').length === k, n);

  assert.equal(await page.isDisabled('#undo'), true, 'nothing to undo in a fresh playset');
  await page.click('[data-tab=library]');
  for (const id of ['A', 'B']) await page.click(`[data-add="local:${id}"]`);
  await page.click('[data-tab=order]');
  await rows(2);
  await page.waitForFunction(() => !document.getElementById('undo').disabled);

  // Undo with the button, Redo with the keyboard
  await page.click('#undo');
  await rows(1);
  assert.deepEqual(await names(), ['A']);
  await page.keyboard.press('Control+y');
  await rows(2);
  await page.keyboard.press('Control+z');
  await rows(1);
  await page.click('#redo');
  await rows(2);
  await page.waitForFunction(() => document.getElementById('redo').disabled);

  // the daily mod update alert names the playset's mods that Steam has a newer version of (the list is given here: no network)
  await page.evaluate(() => { U = [{ id: 'local:A', name: 'A', status: 'update' }, { id: 'local:C', name: 'C', status: 'update' }]; render(); });
  await page.waitForSelector('#view .warnbox');
  assert.match(await page.textContent('#view .warnbox'), /1 mod in this playset has a newer version on Steam.*: A\./);
  await page.click('#view .warnbox [data-closenote]');
  await page.waitForFunction(() => !document.querySelector('#view .warnbox'));

  // a note on a mod: written in the details panel, marked in the list, and one Undo takes it away again
  await page.click('#view .row .nm >> text=B');
  await page.waitForSelector('#d-note');
  await page.fill('#d-note', 'switched off: crashes on start');
  await page.click('#drawer h2');   // the box loses focus: saved
  await page.waitForSelector('#view .mnote');
  assert.match(await page.getAttribute('#view .mnote', 'title'), /crashes on start/);
  let st = await (await fetch(`${base}/api/vic3/state`)).json();
  assert.equal(st.playsets[0].mod_notes['local:B'], 'switched off: crashes on start');
  await page.click('#undo');
  await page.waitForFunction(() => !document.querySelector('#view .mnote'));

  // delete the playset, then bring it back from Import > Recently deleted
  const pid = st.playsets[0].id;
  await fetch(`${base}/api/vic3/playsets/${pid}/delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  await page.reload();
  await page.waitForSelector('#tabs button');
  await page.click('#imp');
  await page.waitForSelector(`[data-restore="${pid}"]`);
  await page.click(`[data-restore="${pid}"]`);
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  await rows(2);
  st = await (await fetch(`${base}/api/vic3/state`)).json();
  assert.deepEqual(st.playsets.map(p => p.id), [pid]);
  assert.deepEqual(st.trash, []);
  assert.deepEqual(errors, []);
  console.log('undo e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
