// Browser test of Import > From a list (pasted text) and Playset settings > Export as text.
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
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-textimport-'));
const user = path.join(root, 'user');
const port = await freePort();
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
for (const f of ['Alpha', 'Beta']) {
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
  await page.goto(`${base}/#vic3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  await page.click('#imp');
  await page.waitForSelector('#lt-text');
  await page.fill('#lt-name', 'From a forum');
  await page.fill('#lt-text', '# my list\n1. beta\n[off] Alpha\n- Gone Mod\n');
  await page.click('#lt-go');
  await page.waitForFunction(() => document.getElementById('toast').textContent.includes('Gone Mod'));
  await page.waitForFunction(() => document.querySelectorAll('#view .row').length === 2);
  const st = await (await fetch(`${base}/api/vic3/state`)).json();
  const ps = st.playsets.find(p => p.name === 'From a forum');
  assert.deepEqual([ps.mods, ps.disabled], [['local:Beta', 'local:Alpha'], ['local:Alpha']]);

  const x = await (await fetch(`${base}/api/vic3/playsets/${ps.id}/share-text`)).json();
  assert.match(x.text, /^# Playset: From a forum\n# Game: vic3\n/);
  assert.match(x.text, /\nBeta\n\[off\] Alpha\n$/);
  assert.deepEqual(errors, []);
  console.log('text import e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
