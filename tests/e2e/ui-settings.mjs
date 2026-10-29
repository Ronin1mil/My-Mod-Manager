// Settings -> UI: pick a colour scheme and a text size per game; they apply at once and are remembered.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-uiset-'));
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const user = path.join(root, 'user');
fs.mkdirSync(path.join(user, 'mod'), { recursive: true });
const server = spawn('python3', ['-m', 'modmanager', '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_AUTO_IMPORT: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg'), MODMANAGER_LOG_DIR: path.join(root, 'log'), HOME: root, USERPROFILE: root, APPDATA: root }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 860 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  const css = (v) => page.evaluate(n => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), v);
  await page.goto(`${base}/#ck3`);
  await page.waitForSelector('#psfixed .ps.on');
  const first = await page.evaluate(() => document.querySelector('#psfixed').getBoundingClientRect().top < document.querySelector('#pslist').getBoundingClientRect().top + 1);
  assert.ok(first, 'the No mods playset is at the top of the list');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  const ck3Acc = await css('--acc');

  await page.click('#appcfg');
  await page.click('[data-st=ui]');
  await page.click('[data-scheme=forest]');
  await page.waitForFunction(() => getComputedStyle(document.documentElement).getPropertyValue('--acc').trim() === '#8fd08a');
  await page.selectOption('#ui-text', 'xlarge');
  await page.waitForFunction(() => getComputedStyle(document.documentElement).getPropertyValue('--zoom').trim() === '1.3');
  await page.click('#p-cancel');
  // the big text must not make the page scroll: the layout is still exactly one screen
  const sizes = await page.evaluate(() => ({ sh: document.documentElement.scrollHeight, ih: window.innerHeight, sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  assert.ok(sizes.sh <= sizes.ih + 2 && sizes.sw <= sizes.iw + 2, JSON.stringify(sizes));

  // remembered after a reload, and only for this game
  await page.reload();
  await page.waitForSelector('#psfixed .ps.on');
  assert.equal(await css('--acc'), '#8fd08a');
  await page.selectOption('#game', 'vic3');
  await page.waitForFunction(() => document.title.startsWith('Victoria 3'));
  await page.waitForFunction(() => getComputedStyle(document.documentElement).getPropertyValue('--zoom').trim() === '1');
  assert.notEqual(await css('--acc'), '#8fd08a', 'another game keeps its own look');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});  // its first-run setup
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  await page.selectOption('#game', 'ck3');
  await page.waitForFunction(() => document.title.startsWith('Crusader'));
  assert.equal(await css('--acc'), '#8fd08a');

  // back to the game's own look
  await page.click('#appcfg'); await page.click('[data-st=ui]');
  await page.click('[data-scheme=default]');
  await page.waitForFunction(a => getComputedStyle(document.documentElement).getPropertyValue('--acc').trim() === a, ck3Acc);
  assert.deepEqual(errors, []);
  console.log('ui settings e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
