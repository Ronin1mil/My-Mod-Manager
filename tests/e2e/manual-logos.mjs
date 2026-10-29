// MANUAL (needs internet, not run in CI): with no logos on the PC, each game's header gets Steam's public art
// and the settings window looks right. SHOTS=<dir> writes screenshots.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';
const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-logos-'));
const port = await freePort(), base = `http://127.0.0.1:${port}`;
const shot = async (page, n) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, n + '.png') }); };
const server = spawn('python3', ['-m', 'modmanager', '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_CONFIG_DIR: path.join(root, 'cfg'), MODMANAGER_LOG_DIR: path.join(root, 'log'), HOME: root, USERPROFILE: root, APPDATA: root }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 860 } });
  page.on('dialog', d => d.accept());
  for (const g of ['ck3', 'eu5', 'vic3']) {
    await page.goto(`${base}/#${g}`); await page.reload();
    await page.waitForSelector('#dlg[open]', { timeout: 4000 }).then(() => page.click('#p-cancel')).catch(() => {});
    await page.waitForSelector('#logo img.ok', { timeout: 30000 });
    assert.doesNotMatch(await page.textContent('#logo'), /Crusader|Europa|Victoria/);
    await shot(page, `logo-${g}`);
  }
  await page.click('#appcfg');
  await shot(page, 'settings-1-game');
  for (const t of ['store', 'play', 'dl', 'app']) { await page.click(`[data-st=${t}]`); await shot(page, `settings-${t}`); }
  console.log('logos ok');
} finally { await browser?.close(); server.kill(); fs.rmSync(root, { recursive: true, force: true }); }
