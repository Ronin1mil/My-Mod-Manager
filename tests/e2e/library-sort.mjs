// Library: sort by name, by Workshop/Local, by tag, or Workshop/Local then tag; filter by one tag.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-libsort-'));
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const user = path.join(root, 'user'), ws = path.join(root, 'ws');
const meta = (dir, name, tags) => { fs.mkdirSync(path.join(dir, '.metadata'), { recursive: true }); fs.writeFileSync(path.join(dir, '.metadata/metadata.json'), JSON.stringify({ name, version: '1', tags, relationships: [] })); };
meta(path.join(user, 'mod', 'zeta'), 'Zeta Local', ['Map']);
meta(path.join(user, 'mod', 'alpha'), 'Alpha Local', ['Gameplay']);
meta(path.join(user, 'mod', 'plain'), 'Plain Local', []);
meta(path.join(ws, '111'), 'Mid Workshop', ['Gameplay', 'Balance']);
meta(path.join(ws, '222'), 'Bare Workshop', []);
meta(path.join(ws, '333'), 'Art Workshop', ['Graphics']);
const server = spawn('python3', ['-m', 'modmanager', '--game', 'vic3', '--user-dir', user, '--workshop-dir', ws, '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_AUTO_IMPORT: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg'), MODMANAGER_LOG_DIR: path.join(root, 'log') }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 860 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${base}/#vic3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  await page.click('[data-tab=library]');
  const names = () => page.locator('#view .row .nm').allTextContents();
  const heads = () => page.locator('#view .grp').evaluateAll(els => els.map(e => e.firstChild.textContent.trim()));

  // default: Workshop first, then Local, each grouped by tag (no tag last), names within a tag
  assert.deepEqual(await heads(), ['Workshop', 'Balance', 'Graphics', 'No tags', 'Local', 'Gameplay', 'Map', 'No tags']);
  assert.deepEqual(await names(), ['Mid Workshop', 'Art Workshop', 'Bare Workshop', 'Alpha Local', 'Zeta Local', 'Plain Local']);

  await page.selectOption('#lib-sort', 'name');
  assert.deepEqual(await names(), ['Alpha Local', 'Art Workshop', 'Bare Workshop', 'Mid Workshop', 'Plain Local', 'Zeta Local']);
  await page.selectOption('#lib-sort', 'source');
  assert.deepEqual(await heads(), ['Workshop', 'Local']);
  assert.deepEqual(await names(), ['Art Workshop', 'Bare Workshop', 'Mid Workshop', 'Alpha Local', 'Plain Local', 'Zeta Local']);
  await page.selectOption('#lib-sort', 'tag');
  assert.deepEqual(await heads(), ['Balance', 'Gameplay', 'Graphics', 'Map', 'No tags']);

  // the tag filter lists every tag with a count and shows only those mods
  assert.match(await page.locator('#lib-tag').textContent(), /Gameplay \(2\)/);
  await page.selectOption('#lib-tag', 'Gameplay');
  assert.deepEqual((await names()).sort(), ['Alpha Local', 'Mid Workshop']);
  await page.selectOption('#lib-tag', '');

  // the choice is remembered after a reload
  await page.selectOption('#lib-sort', 'source');
  await page.reload(); await page.waitForSelector('#tabs button'); await page.click('[data-tab=library]');
  assert.equal(await page.inputValue('#lib-sort'), 'source');
  assert.deepEqual(errors, []);
  console.log('library sort e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
