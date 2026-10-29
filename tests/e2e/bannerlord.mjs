// Bannerlord in the browser: modules from a fake install are listed, a new playset starts with the official modules,
// auto-sort puts a dependency first, there is no Conflicts tab, and Play starts the game with the module list.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-bannerlord-'));
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
const mod = (id, name, deps = [], official = false, version = 'v1.0.0') =>
  `<?xml version="1.0" encoding="utf-8"?><Module><Id value="${id}"/><Name value="${name}"/><Version value="${version}"/>${official ? '<Official value="true"/>' : ''}` +
  (deps.length ? `<DependedModules>${deps.map(d => `<DependedModule Id="${d}"/>`).join('')}</DependedModules>` : '') + '</Module>';
const game = path.join(root, 'game');
for (const [id, deps] of [['Native', []], ['SandBoxCore', ['Native']], ['CustomBattle', ['Native', 'SandBoxCore']], ['Sandbox', ['Native', 'SandBoxCore']], ['StoryMode', ['Native', 'SandBoxCore', 'Sandbox']]])
  write(path.join(game, 'Modules', id, 'SubModule.xml'), mod(id, id, deps, true, 'v1.2.9.12345'));
write(path.join(game, 'Modules/Bannerlord.Harmony/SubModule.xml'), mod('Bannerlord.Harmony', 'Harmony', ['Native']));
write(path.join(game, 'Modules/BigOverhaul/SubModule.xml'), mod('BigOverhaul', 'Big Overhaul', ['Native', 'SandBoxCore', 'Bannerlord.Harmony']));
const exe = path.join(game, 'bin/Win64_Shipping_Client/Bannerlord.exe');
write(exe, `#!/bin/sh\nprintf '%s\\n' "$@" > "${root}/args.txt"\n`);
fs.chmodSync(exe, 0o755);
const port = await freePort(), base = `http://127.0.0.1:${port}`;
const server = spawn('python3', ['-m', 'modmanager', '--game', 'bannerlord', '--game-dir', game, '--user-dir', path.join(root, 'docs'),
  '--workshop-dir', path.join(root, 'ws'), '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_AUTO_IMPORT: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg'), MODMANAGER_LOG_DIR: path.join(root, 'log'), BROWSER: 'true' }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 860 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  await page.goto(`${base}/#bannerlord`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  assert.match(await page.textContent('#status'), /Mount & Blade II: Bannerlord 1\.2\.9 · 5 mods active/);   // the official modules are in from the start
  assert.deepEqual(await page.locator('#tabs button').allTextContents().then(t => t.map(x => x.replace(/ \(\d+\)/, ''))), ['Load order', 'Library', 'Warnings', 'Files', 'Compare', 'Presets']);
  assert.deepEqual(await page.locator('#view .nm').allTextContents(), ['Native', 'SandBoxCore', 'CustomBattle', 'Sandbox', 'StoryMode']);

  // add the overhaul BEFORE its dependency: auto-sort fixes the order
  await page.click('[data-tab=library]');
  await page.click('[data-add="local:BigOverhaul"]');
  await page.click('[data-add="local:Bannerlord.Harmony"]');
  await page.click('[data-tab=order]');
  await page.waitForFunction(() => document.querySelectorAll('#view .nm').length === 7);
  const names = await page.locator('#view .nm').allTextContents();
  assert.ok(names.indexOf('Harmony') < names.indexOf('Big Overhaul'), `dependency first: ${names}`);
  assert.deepEqual(names.slice(0, 5), ['Native', 'SandBoxCore', 'CustomBattle', 'Sandbox', 'StoryMode']);

  // the settings do not offer what this game does not have
  await page.click('#appcfg'); await page.click('[data-st=play]');
  assert.equal(await page.locator('#p-svc').isVisible(), false);
  assert.equal(await page.locator('#p-van').isVisible(), false);
  await page.click('#p-cancel');

  // Play: the game gets the module list on its command line
  await page.click('#launch');
  await page.waitForSelector('#toast.on:has-text("Started Mount & Blade II: Bannerlord with 7 modules")');
  for (let i = 0; i < 100 && !fs.existsSync(path.join(root, 'args.txt')); i++) await new Promise(r => setTimeout(r, 50));
  const args = fs.readFileSync(path.join(root, 'args.txt'), 'utf8').trim().split('\n');
  assert.deepEqual(args, ['/singleplayer', '_MODULES_*Native*SandBoxCore*CustomBattle*Sandbox*StoryMode*Bannerlord.Harmony*BigOverhaul*_MODULES_']);
  assert.deepEqual(errors, [], 'no page errors');
  console.log('bannerlord e2e ok');
} finally { await browser?.close(); server.kill(); fs.rmSync(root, { recursive: true, force: true }); }
