// Switching games quickly while the first game is still loading must not show the wrong game's logo/name,
// throw "cannot read properties of null (reading 'playsets')", or flip between the logo and the name.
// Also checks that a page error ends up in the error log file.
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
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-switch-'));
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const logs = path.join(root, 'docs');
// CK3 has a logo (the user's own file in its config folder), VIC3 has none
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
fs.mkdirSync(path.join(root, 'cfg/ck3'), { recursive: true });
fs.writeFileSync(path.join(root, 'cfg/ck3/logo.png'), png);
const server = spawn('python3', ['-m', 'modmanager', '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg'), MODMANAGER_LOG_DIR: logs, HOME: root, USERPROFILE: root, APPDATA: root, XDG_DATA_HOME: root }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  await seed(base, 'ck3', 'eu5', 'vic3', 'bannerlord');
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  // make CK3 slow so the user can switch away while it is still loading
  await page.route('**/api/ck3/state', async route => { await new Promise(r => setTimeout(r, 1500)); await route.continue(); });
  await page.route('**/api/ck3/analyse/**', async route => { await new Promise(r => setTimeout(r, 800)); await route.continue(); });
  await page.route('**/api/vic3/state', async route => { await new Promise(r => setTimeout(r, 1500)); await route.continue(); });
  await page.goto(`${base}/#ck3`);
  await page.waitForSelector('#game option', {state: 'attached'});
  await page.selectOption('#game', 'vic3');              // switch while CK3 is still loading
  await page.waitForTimeout(300);
  await page.click('#logo');                              // clicking anywhere while the page is still loading used to throw
  await page.keyboard.press('Escape');
  assert.doesNotMatch(await page.textContent('#toast'), /Cannot read|null/, 'clicking during a load must not show a script error');
  await page.waitForSelector('#dlg[open]', { timeout: 8000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForSelector('#title');
  await page.waitForTimeout(3500);                        // let the abandoned CK3 answers arrive
  assert.doesNotMatch(await page.textContent('#logo'), /Victoria|Crusader|Europa/, 'the header never shows a game name as text');
  assert.match(await page.getAttribute('#logo img', 'src'), /\/api\/vic3\/logo/, 'VIC3 header uses VIC3 art, not CK3');
  assert.equal(await page.evaluate(() => document.title), 'Victoria 3 · Ronin Mod Manager');
  assert.equal(await page.inputValue('#game'), 'vic3');
  assert.deepEqual(errors, [], `no page errors, got ${errors}`);

  // CK3 now (fast), logo shows and stays
  await page.unroute('**/api/ck3/state'); await page.unroute('**/api/ck3/analyse/**');
  await page.selectOption('#game', 'ck3');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForSelector('#logo img.ok');
  const seen = new Set();
  for (let i = 0; i < 10; i++) { seen.add(await page.locator('#logo img.ok').count() + ':' + (await page.textContent('#logo')).replace(/\s/g, '').length); await page.waitForTimeout(150); }
  assert.equal(seen.size, 1, `logo stays put: ${[...seen]}`);
  assert.match(await page.getAttribute('#logo img', 'src'), /\/api\/ck3\/logo/);
  assert.deepEqual(errors, []);

  // a script error is written to the log file with its stack
  await page.evaluate(() => setTimeout(() => { throw new Error('test-boom'); }, 0));
  const logfile = path.join(logs, 'Ronin Mod Manager', 'RoninModManager-errors.log');
  for (let i = 0; i < 40 && !(fs.existsSync(logfile) && /test-boom/.test(fs.readFileSync(logfile, 'utf8'))); i++) await new Promise(r => setTimeout(r, 100));
  const txt = fs.readFileSync(logfile, 'utf8');
  assert.match(txt, /\[page\] .*test-boom/);
  assert.match(txt, /ck3/);
  await page.waitForSelector('#banner.bad');
  assert.match(await page.textContent('#banner'), /RoninModManager-errors\.log/);
  console.log('switch e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
