// Settings -> App & updates -> Erase all data: nothing happens without typing ERASE; with it every playset is gone
// and the page shows the "no playset" screen again.
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
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-erase-'));
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const cfg = path.join(root, 'cfg');
const user = path.join(root, 'user');
fs.mkdirSync(path.join(user, 'mod'), { recursive: true });
const server = spawn('python3', ['-m', 'modmanager', '--game', 'ck3', '--user-dir', user, '--workshop-dir', path.join(root, 'none'), '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_AUTO_IMPORT: '0', MODMANAGER_CONFIG_DIR: cfg, MODMANAGER_LOG_DIR: path.join(root, 'log') }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  await seed(base, 'ck3');
  const file = path.join(cfg, 'ck3', 'playsets.json');
  assert.ok(fs.existsSync(file));
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 860 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let answer = 'nope';
  page.on('dialog', d => (d.type() === 'prompt' ? d.accept(answer) : d.accept()));
  await page.goto(`${base}/#ck3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  const openErase = async () => { await page.click('#appcfg'); await page.click('[data-st=app]'); };
  await openErase();
  // the experimental test-build button is there; with no network (or no release yet) it just says so
  await page.click('#nt-check');
  await page.waitForFunction(() => document.getElementById('nt-status').textContent.length > 0 && document.getElementById('nt-status').textContent !== 'Checking…', null, { timeout: 20000 });
  assert.equal(await page.isDisabled('#nt-go'), true);
  await page.click('#s-erase');
  await page.waitForTimeout(600);
  assert.ok(fs.existsSync(file), 'a wrong answer deletes nothing');
  assert.equal(await page.locator('#pslist .ps').count(), 1);

  answer = 'ERASE';
  await page.click('#s-erase');
  await page.waitForSelector('#psfixed .ps.on', { timeout: 10000 });
  assert.equal(await page.textContent('#title'), 'No mods');
  assert.equal(await page.locator('#pslist .ps').count(), 0);
  assert.deepEqual(Object.keys(JSON.parse(fs.readFileSync(file, 'utf8')).playsets), [], 'no playset is left (the file is rewritten empty when the page picks "No mods")');
  assert.deepEqual(errors, []);
  console.log('erase e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
