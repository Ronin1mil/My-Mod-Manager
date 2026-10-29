// Browser end-to-end test: real server, fake game folder, stub game executable.
// GAME=ck3|vic3 (default vic3) picks the game; the other games have their own layout and are covered by games.mjs.
// Run:  node tests/e2e/ui.mjs   (needs `playwright` + chromium; CI installs them)
import { createRequire } from 'node:module';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');

const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const GAME = process.env.GAME || 'vic3';
const NAME = { ck3: 'Crusader Kings III', vic3: 'Victoria 3' }[GAME];
const LOADFILE = { ck3: 'dlc_load.json', vic3: 'content_load.json' }[GAME];
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-e2e-'));
const user = path.join(root, 'user');
const cfg = path.join(root, 'cfg');
const port = await freePort();
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
const meta = (name, deps = []) => JSON.stringify({ name, version: '1.0', supported_game_version: '1.7.*',
  relationships: deps.map(d => ({ rel_type: 'dependency', display_name: d })) });
for (const [folder, name, deps] of [['Lib', 'Core Library', []], ['A', 'Alpha', ['Core Library']], ['B', 'Beta', []]]) {
  write(path.join(user, 'mod', folder, '.metadata/metadata.json'), meta(name, deps));
  write(path.join(user, 'mod', `${folder}.mod`), `name="${name}"\npath="mod/${folder}"\n`);
}
write(path.join(user, 'mod/A/common/goods/x.txt'), 'g = { }');
write(path.join(user, 'mod/B/common/goods/x.txt'), 'g = { }');
const exe = path.join(root, 'game/stub.sh');
write(exe, `#!/bin/sh\nprintf '%s\\n' "$@" > "$(dirname "$0")/args.txt"\ncp "${user}/${LOADFILE}" "$(dirname "$0")/load.json"\n`);
fs.chmodSync(exe, 0o755);
const zip = path.join(root, 'new-mod.zip');
spawnSync('python3', ['-c', `import zipfile,sys;z=zipfile.ZipFile(sys.argv[1],'w');z.writestr('Gamma/.metadata/metadata.json',${JSON.stringify(meta('Gamma'))});z.writestr('Gamma/common/y.txt','y = {}')`, zip]);

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
fs.mkdirSync(path.join(cfg, GAME), { recursive: true });
fs.writeFileSync(path.join(cfg, GAME, 'logo.png'), png);
const server = spawn('python3', ['-m', 'modmanager', '--game', GAME, '--user-dir', user, '--workshop-dir', path.join(root, 'none'),
  '--game-exe', exe, '--game-version', '1.7.6', '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_CONFIG_DIR: cfg }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${port}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => m.type() === 'error' && !m.text().includes('status of 400') && errors.push(m.text())); // the 400 is the rejected hostile argument
  page.on('dialog', d => d.accept());
  await page.goto(`http://127.0.0.1:${port}/#${GAME}`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {}); // first-run setup: skip like a user would
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  await page.waitForSelector('#logo img');
  assert.equal((await fetch(`http://127.0.0.1:${port}/api/${GAME}/logo`)).headers.get('content-type'), 'image/png');

  // Library: add Alpha only -> dependency problem with one-click fix
  await page.click('[data-tab=library]');
  await page.click('[data-add="local:A"]');
  await page.click('[data-tab=problems]');
  await page.waitForSelector('text=Alpha needs Core Library');
  await page.click('[data-fix=enable]');
  await page.click('[data-tab=order]');
  const names = await page.locator('#view .nm').allTextContents();
  assert.deepEqual(names, ['Core Library', 'Alpha'], 'dependency loads first after the fix');

  // Details drawer explains the position
  await page.click('[data-sel="local:A"]');
  await page.waitForSelector('text=Loads after Core Library');

  // Conflicts appear once Beta is added
  await page.click('[data-tab=library]');
  await page.click('[data-add="local:B"]');
  await page.click('[data-tab=conflicts]');
  await page.waitForSelector('text=common/goods/x.txt');

  // Install a zip through the file input
  await page.setInputFiles('#installf', zip);
  await page.waitForSelector('text=Installed: Gamma');
  await page.click('[data-tab=library]');
  await page.waitForSelector('text=Gamma');
  await page.waitForSelector('.b.new:has-text("NEW")');

  // Settings: a hostile launch argument is rejected, a normal one accepted
  await page.click('#cfg');
  await page.fill('#c-args', '-x; rm -rf /');
  await page.click('#c-save');
  await page.waitForSelector('#toast.bad');
  await page.fill('#c-args', '-debug_mode');
  await page.click('#c-save');
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  // Play: stub game receives exactly the profile's args and mod list
  await page.click('#launch');
  await page.waitForSelector(`text=started ${NAME}`);
  for (let i = 0; i < 50 && !fs.existsSync(path.join(root, 'game/load.json')); i++) await new Promise(r => setTimeout(r, 100));
  assert.equal(fs.readFileSync(path.join(root, 'game/args.txt'), 'utf8'), '-debug_mode\n');
  const cl = JSON.parse(fs.readFileSync(path.join(root, 'game/load.json'), 'utf8'));
  assert.deepEqual(cl.enabled_mods, ['mod/Lib.mod', 'mod/A.mod', 'mod/B.mod']);

  // Security headers and host check
  const r = await fetch(`http://127.0.0.1:${port}/`);
  assert.match(r.headers.get('content-security-policy'), /script-src 'self'/);
  const status = await new Promise((res, rej) => http.get({ host: '127.0.0.1', port, path: `/api/${GAME}/state`,
    headers: { Host: 'evil.example' } }, r => { r.resume(); res(r.statusCode); }).on('error', rej));
  assert.equal(status, 403, 'DNS-rebinding style Host header is refused');
  assert.equal((await fetch(`http://127.0.0.1:${port}/../../etc/passwd`)).status, 404);

  if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT, fullPage: true });
  assert.deepEqual(errors, [], 'no console/page errors');
  console.log('e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
