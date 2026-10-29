// The Import menu: the game's own launcher playsets are listed and imported, pressing again adds nothing, the
// automatic import brings them in when the game opens, and the Import button can be hidden and brought back.
import { createRequire } from 'node:module';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-launcher-'));
const user = path.join(root, 'user'), cfg = path.join(root, 'cfg'), ws = path.join(root, 'ws');
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
for (const [id, name] of [['111', 'Alpha'], ['222', 'Beta']]) write(path.join(ws, id, '.metadata/metadata.json'), JSON.stringify({ name, version: '1' }));
const dbfile = path.join(user, 'launcher-v2.sqlite');
fs.mkdirSync(user, { recursive: true });
const r = spawnSync('python3', ['-c', `
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("CREATE TABLE playsets (id TEXT PRIMARY KEY, name TEXT, isActive INTEGER, isRemoved INTEGER)")
c.execute("CREATE TABLE playsets_mods (playsetId TEXT, modId TEXT, enabled INTEGER, position INTEGER)")
c.execute("CREATE TABLE mods (id TEXT PRIMARY KEY, displayName TEXT, steamId TEXT, pdxId TEXT, gameRegistryId TEXT, dirPath TEXT, source TEXT)")
c.executemany("INSERT INTO playsets VALUES (?,?,?,0)", [("p1", "Launcher Main", 1), ("p2", "Launcher Extra", 0)])
c.executemany("INSERT INTO mods VALUES (?,?,?,'', ?, '', 'steam')", [("m1", "Alpha", "111", "mod/ugc_111.mod"), ("m2", "Beta", "222", "mod/ugc_222.mod")])
c.executemany("INSERT INTO playsets_mods VALUES (?,?,?,?)", [("p1", "m1", 1, 0), ("p1", "m2", 1, 1), ("p2", "m2", 1, 0)])
c.commit()
`, dbfile]);
assert.equal(r.status, 0, String(r.stderr));
const start = async (autoImport) => {
  const port = await freePort();
  const server = spawn('python3', ['-m', 'modmanager', '--game', 'ck3', '--user-dir', user, '--workshop-dir', ws, '--no-browser', '--port', String(port)],
    { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_AUTO_IMPORT: autoImport ? '1' : '0', MODMANAGER_CONFIG_DIR: cfg, MODMANAGER_LOG_DIR: path.join(root, 'log') }, stdio: 'inherit' });
  for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${port}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  return { server, base: `http://127.0.0.1:${port}` };
};
let browser, srv;
try {
  srv = await start(false);
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 860 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  await page.goto(`${srv.base}/#ck3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  // the menu lists the launcher's playsets; nothing is imported yet
  await page.click('#imp');
  await page.waitForSelector('#dlg.menu [data-lp]');
  assert.equal(await page.locator('#dlg [data-lp]').count(), 2);
  assert.match(await page.textContent('#dlg'), /Launcher Main[\s\S]*2 mods[\s\S]*active in the launcher/);
  await page.click('#lp-go');
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  await page.waitForSelector('#pslist >> text=Launcher Main');
  await page.waitForSelector('#pslist >> text=Launcher Extra');
  await page.click('#pslist >> text=Launcher Main');
  await page.click('[data-tab=order]');
  assert.deepEqual(await page.locator('#view .nm').allTextContents(), ['Alpha', 'Beta']);

  // pressing again: both are marked as already here and nothing new is added
  await page.click('#imp');
  await page.waitForSelector('#dlg [data-lp]');
  assert.equal(await page.locator('#dlg [data-lp]:checked').count(), 0);
  assert.match(await page.textContent('#dlg'), /already here/);
  await page.click('#lp-close');

  // the Import button can be hidden from the menu and brought back from Settings
  await page.click('#imp');
  await page.waitForSelector('#im-show');
  await page.uncheck('#im-show');
  await page.waitForFunction(() => document.getElementById('imp').hidden);
  await page.click('#lp-close');
  await page.click('#appcfg'); await page.click('[data-st=play]');
  assert.equal(await page.locator('#s-imp-show').isChecked(), false);
  await page.check('#s-imp-show');
  await page.waitForFunction(() => !document.getElementById('imp').hidden);
  await page.click('#p-cancel');
  assert.deepEqual(errors, [], 'no page errors');
  await browser.close(); browser = null;
  srv.server.kill();

  // a fresh app that is allowed to import automatically brings the playsets in by itself
  fs.rmSync(cfg, { recursive: true, force: true });
  srv = await start(true);
  browser = await chromium.launch();
  const p2 = await browser.newPage({ viewport: { width: 1300, height: 860 } });
  p2.on('dialog', d => d.accept());
  await fetch(`${srv.base}/api/ck3/skip-setup`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });  // first start: the setup dialog is done
  const state = await (await fetch(`${srv.base}/api/ck3/state`)).json();
  assert.deepEqual(state.playsets.map(p => p.name).sort(), ['Launcher Extra', 'Launcher Main']);
  console.log('launcher e2e ok');
} finally { await browser?.close(); srv?.server.kill(); fs.rmSync(root, { recursive: true, force: true }); }
