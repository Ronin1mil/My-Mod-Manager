// Browser end-to-end: one server, three games, driven only through the UI (setup dialog, switcher, presets, Play).
// Run:  node tests/e2e/games.mjs   (needs `playwright` + chromium). BROWSER=true keeps steam:// URLs from opening anything.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-games-'));
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
const meta = (name, deps = []) => JSON.stringify({ name, version: '1', relationships: deps.map(d => ({ rel_type: 'dependency', display_name: d })) });

const GAMES = {
  ck3: { name: 'Crusader Kings III', dir: 'Crusader Kings III', app: '1158310', marker: 'game/common', defs: 'common/traits', load: 'dlc_load.json' },
  eu5: { name: 'Europa Universalis V', dir: 'Europa Universalis V', app: '3450310', marker: 'game/in_game', defs: 'in_game/common/goods', load: 'dlc_load.json' },
  vic3: { name: 'Victoria 3', dir: 'Victoria 3', app: '529340', marker: 'game/common', defs: 'common/goods', load: 'content_load.json' },
};
for (const [id, g] of Object.entries(GAMES)) {
  g.lib = path.join(root, id, 'SteamLibrary');
  g.install = path.join(g.lib, 'steamapps/common', g.dir);
  g.user = path.join(root, id, 'user');
  write(path.join(g.install, g.marker, 'x'), '');
  write(path.join(g.install, 'launcher/launcher-settings.json'), JSON.stringify({ rawVersion: 'v1.2.3' }));
  for (const [f, name, deps] of [['Lib', `${id} Core`, []], ['Add', `${id} Addon`, [`${id} Core`]]]) {
    write(path.join(g.user, 'mod', f, '.metadata/metadata.json'), meta(name, deps));
    write(path.join(g.user, 'mod', f, g.defs, `${f}.txt`), 't = { }');
    write(path.join(g.user, 'mod', `${f}.mod`), `name="${name}"\npath="mod/${f}"\n`);
  }
  write(path.join(g.lib, 'steamapps/workshop/content', g.app, '999', '.metadata/metadata.json'), meta(`${id} Workshop`));
}

const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const server = spawn('python3', ['-m', 'modmanager', '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg'), BROWSER: 'true', HOME: path.join(root, 'home') }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 850 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => m.type() === 'error' && errors.push(m.text()));
  page.on('dialog', d => d.accept());
  const acc = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--acc').trim());
  const names = () => page.locator('#view .row .nm').allTextContents();

  await page.goto(`${base}/`);
  await page.waitForSelector('#game option:nth-child(3)', { state: 'attached' });
  assert.deepEqual(await page.locator('#game option').allTextContents(), ['Crusader Kings III', 'Europa Universalis V', 'Victoria 3']);

  const seen = {};
  for (const id of ['ck3', 'eu5', 'vic3']) {
    const g = GAMES[id];
    await page.selectOption('#game', id);
    seen[id] = await acc();
    // each game's first visit opens its setup dialog; paste a path deep inside the install like a user would
    await page.waitForSelector('#dlg[open] #p-game');
    assert.match(await page.textContent('#dlg h2'), new RegExp(`Set up ${g.name}`));
    await page.fill('#p-game', path.join(g.install, g.marker));
    await page.waitForSelector('#p-gst .ok');
    assert.match(await page.textContent('#p-gst'), /version 1\.2\.3/);
    await page.click('[data-st=store]');
    await page.fill('#p-user', g.user);
    await page.click('#p-save');
    await page.waitForFunction(() => !document.getElementById('dlg').open);
    await page.click('[data-tab=library]');
    await page.waitForSelector(`text=${id} Workshop`);  // the Workshop folder was derived from the install's library
    assert.equal((await names()).length, 3);

    // build a playset, check conflicts use this game's script folders, press Play
    for (const mid of ['local:Add', 'local:Lib', 'ws:999']) await page.click(`[data-add="${mid}"]`);
    await page.click('[data-tab=order]');
    await page.waitForFunction(() => document.querySelectorAll('#view .row').length === 3);
    const order = await names();
    assert.ok(order.indexOf(`${id} Core`) < order.indexOf(`${id} Addon`), `dependency first for ${id}: ${order}`);
    await page.click('[data-tab=conflicts]');
    await page.waitForSelector(`text=${g.defs}: t`);
    await page.click('#launch');
    await page.waitForSelector(`text=started ${g.name}`);
    const f = path.join(g.user, g.load);
    for (let i = 0; i < 30 && !fs.existsSync(f); i++) await new Promise(r => setTimeout(r, 100));
    const enabled = JSON.parse(fs.readFileSync(f, 'utf8')).enabled_mods;
    assert.equal(enabled.length, 3, `${id}: ${enabled}`);
    assert.ok(enabled[0].includes('Lib'), `${id} loads the dependency first: ${enabled}`);
  }
  assert.equal(new Set(Object.values(seen)).size, 3, `each game has its own accent colour: ${JSON.stringify(seen)}`);

  // switching back keeps each game's own playset and remembers the choice
  await page.selectOption('#game', 'ck3');
  await page.waitForSelector('#tabs button');
  assert.equal(await acc(), seen.ck3);
  assert.equal((await page.locator('#pslist .ps').count()), 1);
  await page.reload();
  await page.waitForSelector('#tabs button');
  assert.equal(await page.inputValue('#game'), 'ck3', 'last used game is remembered');

  // presets: the RICE draft is labelled unverified; applying it makes a playset and lists what is missing
  await page.click('[data-tab=presets]');
  await page.waitForSelector('text=RICE stack (draft)');
  assert.match(await page.textContent('#view'), /unverified/);
  await page.click('[data-preset="ck3-rice-stack"]');
  await page.waitForSelector('text=Not installed yet (4)');
  await page.click('[data-dl=steam]');
  await page.waitForSelector('#toast.on:has-text("Opened in Steam")');
  assert.match(await page.textContent('#view'), /Set steamcmd in Settings/);   // no steamcmd configured -> no download button
  await page.click('[data-tab=problems]');
  await page.waitForSelector('text=its files were not found');
  // each game lists only its own presets: EU5 shows its collection and none of CK3's
  await page.selectOption('#game', 'eu5');
  await page.click('[data-tab=presets]');
  await page.waitForSelector('text=Roman Empire Collection');
  assert.doesNotMatch(await page.textContent('#view'), /RICE|Cultures Expanded|Seastar|Ultra Historical/);

  assert.deepEqual(errors.filter(e => !/status of 4\d\d/.test(e)), [], 'no console/page errors');
  console.log('games e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
