// "Add a game (beta)": the entry under the game list opens a form, an added game works like a built-in one (its mods are
// found, "Check this game" explains what is missing), it can be edited and removed, and a bad field is refused.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-addgame-'));
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const cfg = path.join(root, 'cfg');
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
const server = spawn('python3', ['-m', 'modmanager', '--game', 'ck3', '--user-dir', path.join(root, 'ck3user'), '--workshop-dir', path.join(root, 'none'), '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_AUTO_IMPORT: '0', MODMANAGER_CONFIG_DIR: cfg, MODMANAGER_LOG_DIR: path.join(root, 'log') }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let confirms = [];
  page.on('dialog', d => { confirms.push(d.message()); d.accept(); });
  await page.goto(`${base}/#ck3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  // the entry sits under the games
  const opts = await page.locator('#game option').allTextContents();
  assert.match(opts[opts.length - 1], /Add a game \(beta\)/);

  // add Stellaris from its template; the user folder is made to exist first so its mod is found
  const user = path.join(root, 'Documents', 'Paradox Interactive', 'Stellaris');
  write(path.join(user, 'mod', 'Cool', '.metadata', 'metadata.json'), JSON.stringify({ name: 'Cool Mod', version: '1' }));
  write(path.join(user, 'mod', 'Cool.mod'), 'name="Cool Mod"\npath="mod/Cool"\n');
  await page.selectOption('#game', '__add');
  await page.waitForSelector('#gf-name');
  assert.equal(await page.locator('#game').inputValue(), 'ck3', 'the list keeps showing the game you are on');
  await page.selectOption('#gf-tpl', { label: 'Stellaris (unverified)' });
  assert.equal(await page.inputValue('#gf-name'), 'Stellaris');
  assert.equal(await page.inputValue('#gf-content_dir'), '');
  assert.equal(await page.isVisible('#gf-exe_rel'), false, 'module-only fields are hidden for a Paradox game');
  // a field that would climb out of its folder is refused with a readable message and nothing is added
  await page.fill('#gf-install_marker', '../../etc');
  await page.click('#gf-save');
  await page.waitForFunction(() => document.getElementById('gf-msg').textContent.length > 0);
  assert.match(await page.textContent('#gf-msg'), /plain folder name/);
  assert.equal((await (await fetch(`${base}/api/games`)).json()).games.length, 4);
  await page.fill('#gf-install_marker', 'common');
  await page.fill('#gf-user_dir_name', 'Stellaris');
  await page.click('#gf-save');
  await page.waitForFunction(() => /Stellaris/.test(document.querySelector('#game').selectedOptions[0].textContent));
  await page.waitForFunction(() => S && S.game && S.game.custom);   // loaded: Settings reads this state
  assert.match(await page.locator('#game').evaluate(s => s.selectedOptions[0].textContent), /Stellaris \(beta\)/);
  const gid = await page.locator('#game').inputValue();
  assert.match(gid, /^cg-stellaris/);
  // its own first-run setup shows; point its user folder at the fake Documents folder
  await page.waitForSelector('#dlg[open]');
  await page.click('[data-st=store]');
  await page.fill('#p-user', user);
  await page.click('#p-save');
  await page.waitForFunction(() => !document.getElementById('dlg').open);
  await page.click('[data-tab=library]');
  await page.waitForSelector('text=Cool Mod');

  // Check this game: the install is missing and it says what it looked for
  await page.click('#appcfg');
  await page.click('#dg-run');
  await page.waitForSelector('#dg-out .dg');
  const report = await page.textContent('#dg-out');
  assert.match(report, /Game install/);
  assert.match(report, /contains 'common'/);
  assert.match(report, /1 local/);
  assert.ok(await page.isVisible('#dg-copy'));
  assert.ok(await page.isVisible('#cg-edit'));

  // edit: change the name
  await page.click('#cg-edit');
  await page.waitForSelector('#gf-name');
  await page.fill('#gf-name', 'Stellaris Two');
  await page.click('#gf-save');
  await page.waitForFunction(() => /Stellaris Two/.test(document.querySelector('#game').selectedOptions[0].textContent));
  await page.waitForFunction(() => S && S.game && S.game.name === 'Stellaris Two');   // the game finished loading (Settings needs its state)

  // remove: back to the built-in games
  await page.click('#appcfg');
  await page.click('#cg-remove');
  await page.waitForFunction(() => document.querySelectorAll('#game option').length === 5);
  assert.equal((await (await fetch(`${base}/api/games`)).json()).games.length, 4);
  assert.ok(confirms.some(m => /never touched/.test(m)));
  assert.ok(fs.existsSync(path.join(user, 'mod', 'Cool.mod')), 'the game\'s own files are never touched');
  assert.deepEqual(errors, []);
  console.log('add-game e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
