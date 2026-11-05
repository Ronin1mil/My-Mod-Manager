// Random New World (beta) in the browser, Europa Universalis V: the tab, finding the generator, the worlds with their settings,
// making a world through a stand-in generator, turning one world on (the others and the hub off) and removing it.
import { createRequire } from 'node:module';
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';
import { seed } from './seed.mjs';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-rnw-'));
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
const code = execFileSync('python3', ['-c', 'from tests.test_rnw import CODE; print(CODE)'], { encoding: 'utf8' }).trim();
const stub = path.resolve('tests/rnwstub.py');
const rnworld = path.join(root, 'island.rnworld');   // a map file like the one Random New World exports
execFileSync('python3', ['-c', 'import sys; from tests.test_rnw import make_rnworld, make_code; make_rnworld(sys.argv[1], code=make_code(5, 11))', rnworld]);

const game = path.join(root, 'game'), user = path.join(root, 'user'), ws = path.join(root, 'ws');
write(path.join(game, 'game/in_game/x.txt'), 'x');
const meta = (name, extra = {}) => JSON.stringify({ name, version: '1', relationships: [], ...extra });
write(path.join(user, 'mod/Refined/.metadata/metadata.json'), meta('Refined Colonization'));
write(path.join(ws, '3829217331/.metadata/metadata.json'), meta('Random New World'));
const w1 = path.join(user, 'mod/rnw_exp_world_aaaaa22222');
write(path.join(w1, '.metadata/metadata.json'), meta('RNW: Continents AAAA', { short_description: `World ${code}` }));
write(path.join(w1, '.metadata/rnw-library/world.json'), JSON.stringify({ schema: 1, id: 'aaaaa22222', code, preset: 'continents', seed: 42, generator: '1.1.0', game_build: '26300913', created: 1700000000, seconds: 91, name: '', record: { settings: { new_world: { land_permille: 350 } } } }));
// the stand-in generator: rnw.cmd runs tests/rnwstub.py
const gen = path.join(root, 'rnwhere');
write(path.join(gen, 'rnw.cmd'), `#!/bin/sh\nexec python3 "${stub}" "$@"\n`);
fs.chmodSync(path.join(gen, 'rnw.cmd'), 0o755);
write(path.join(root, 'worlds.json'), '[]');

const port = await freePort(), base = `http://127.0.0.1:${port}`;
const server = spawn('python3', ['-m', 'modmanager', '--game', 'eu5', '--game-dir', game, '--user-dir', user, '--workshop-dir', ws, '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_FETCH_LOGOS: '0', MODMANAGER_AUTO_IMPORT: '0', MODMANAGER_CONFIG_DIR: path.join(root, 'cfg'), MODMANAGER_LOG_DIR: path.join(root, 'log'), BROWSER: 'true',
    RNW_STUB_MODS: path.join(user, 'mod'), RNW_STUB_WORLDS: path.join(root, 'worlds.json'), RNW_STUB_CODE: code }, stdio: 'inherit' });
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/games`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  await seed(base, 'eu5');
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.type() === 'prompt' ? d.accept(gen) : d.accept());
  await page.goto(`${base}/#eu5`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  const tabs = await page.locator('#tabs button').allTextContents();
  assert.equal(tabs[tabs.length - 1], 'Random New World (beta)');
  assert.equal(tabs[tabs.length - 2], 'Crash help (beta)');   // right next to Crash help

  // the playset gets the hub, Refined Colonization and the world
  const st = await (await fetch(`${base}/api/eu5/state`)).json();
  const pid = st.active, ids = st.mods.map(m => m.id);
  await fetch(`${base}/api/eu5/playsets/${pid}/update`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mods: ids }) });
  await page.reload();
  await page.waitForSelector('#tabs button');

  const rnwCalls = [];
  page.on('request', r => { if (r.url().includes('/rnw/') && !r.url().endsWith('/rnw/job')) rnwCalls.push(r.url()); });
  await page.click('[data-tab=rnw]');
  await page.waitForSelector('.rnw');
  // 1. the tab opens on a menu that already lists the maps (rnw/files reads the mod folder and the app's records; no program is started)
  assert.match(await page.textContent('.rnw'), /What do you want to do\?/);
  await page.waitForFunction(() => /Your maps \(1\)/.test(document.querySelector('.rnw').textContent));
  assert.match(await page.textContent('.rnw'), /RNW: Continents AAAA/);
  assert.deepEqual(rnwCalls.map(u => u.split('/rnw/')[1]), ['files']);
  rnwCalls.length = 0;
  // the settings of a map open when clicked, stay open when the list is redrawn, and close with the Hide settings button
  const info = page.locator('.rnw-w [data-rnw=info]').first();
  await info.click();
  assert.equal(await page.locator('.rnw-infobody').first().isVisible(), true);
  assert.match(await page.textContent('.rnw-infobody'), /World code/);
  await page.waitForTimeout(2500);
  await page.evaluate(() => render());                      // a redraw of the page keeps it open
  assert.equal(await page.locator('.rnw-infobody').count(), 1);
  await page.click('.rnw-infobody [data-rnw=info]');
  assert.equal(await page.locator('.rnw-infobody').count(), 0);

  // 2. Import my maps: says what it does, reads the mod folder only, lists the installed world with its settings
  await page.click('[data-rnw=goimport]');
  await page.waitForFunction(() => /Your maps \(1\)/.test(document.querySelector('.rnw').textContent));
  assert.match(await page.textContent('.rnw-log'), /Reading your mod folder.*found 1 map/);
  assert.deepEqual(rnwCalls.map(u => u.split('/rnw/')[1]), ['files']);   // no program was started
  assert.match(await page.textContent('.rnw-w'), /RNW: Continents AAAA/);
  assert.match(await page.textContent('.rnw-w'), /Continents · seed 42 · generator 1\.1\.0 · game build 26300913/);
  await page.locator('.rnw-w [data-rnw=info]').first().click();
  assert.match(await page.textContent('.rnw-infobody'), /World: land\s*35 %/);              // a setting read from the world's code
  assert.match(await page.textContent('.rnw-w [data-rnw=info]'), /read from the world's own files, the world's code/);
  assert.match(await page.textContent('.rnw-infobody'), /settings\.new_world\.land_permille\s*350/);   // and the generator's own record

  // 3. import a map folder from somewhere else, and a world code
  const other = path.join(root, 'elsewhere/rnw_exp_world_ccccc33333');
  write(path.join(other, '.metadata/metadata.json'), meta('RNW: Brought from elsewhere'));
  write(path.join(other, 'in_game/x.txt'), 'x');
  await page.fill('[data-rnwf=path]', other);
  await page.click('[data-rnw=importdir]');
  await page.waitForFunction(() => /Your maps \(2\)/.test(document.querySelector('.rnw').textContent), null, { timeout: 15000 });
  assert.equal(fs.existsSync(path.join(user, 'mod/rnw_exp_world_ccccc33333/in_game/x.txt')), true);
  assert.equal(fs.existsSync(other), true);   // copied, not moved
  await page.fill('[data-rnwf=code]', code);
  await page.click('[data-rnw=importcode]');
  await page.waitForFunction(() => /Remembered the code/.test(document.querySelector('.rnw-log').textContent));
  // a .rnworld file: remembered at once with its name, tag and settings; nothing is copied or built
  await page.fill('[data-rnwf=path]', rnworld);
  await page.click('[data-rnw=importdir]');
  await page.waitForFunction(() => /Your maps \(3\)/.test(document.querySelector('.rnw').textContent));
  assert.match(await page.textContent('.rnw-log'), /Remembered island\.rnworld/);
  assert.match(await page.textContent('.rnw'), /My island/);
  // Show map: the picture in the file is a table of location numbers; the page paints a real map from it and lists what it contains
  await page.click('[data-rnw=openmap]');
  await page.waitForSelector('#rnwmapcv canvas');
  const px = (x, y) => page.evaluate(([x, y]) => [...document.querySelector('#rnwmapcv canvas').getContext('2d').getImageData(x, y, 1, 1).data], [x, y]);
  assert.deepEqual(await px(1, 0), [200, 30, 30, 255]);     // land of the country Aland: its colour
  assert.deepEqual(await px(0, 0), [20, 40, 70, 255]);      // open sea
  assert.deepEqual(await px(3, 0), [150, 150, 140, 255]);   // land nobody owns
  assert.match(await page.textContent('.rnw-map'), /2 land locations, 1 of them settled/);
  assert.match(await page.textContent('.rnw-map'), /1 states and 0 tribes/);
  assert.match(await page.textContent('.rnw-map'), /Aland\s*ALA/);
  await page.locator('#rnwmapcv canvas').scrollIntoViewIfNeeded();
  const box = await page.locator('#rnwmapcv canvas').boundingBox();
  await page.mouse.move(box.x + box.width * 1.5 / 6, box.y + box.height * 0.5 / 4);
  assert.match(await page.textContent('#rnwmaptip'), /Aland town.*Aland \(ALA, state\).*population 1,000/);
  await page.click('[data-rnw=layer][data-l=topography]');
  assert.deepEqual(await px(1, 0), [150, 190, 110, 255]);   // flatland
  assert.match(await page.textContent('.rnw-map'), /flatland/);
  assert.equal(await page.locator('.rnw-w [data-rnw=closemap]').count(), 1);     // while it is open the list offers Hide map
  await page.click('.rnw-maphead [data-rnw=closemap]');                         // the Close button at the top closes it
  assert.equal(await page.locator('.rnw-map').count(), 0);
  await page.click('[data-rnw=openmap]');                                       // open again: the one at the bottom, the list's Hide map, and Esc also close it
  await page.waitForSelector('.rnw-map #rnwmapcv canvas');
  await page.click('.rnw-map > p [data-rnw=closemap]');
  assert.equal(await page.locator('.rnw-map').count(), 0);
  await page.click('[data-rnw=openmap]');
  await page.waitForSelector('.rnw-map #rnwmapcv canvas');
  await page.click('.rnw-w [data-rnw=closemap]');
  assert.equal(await page.locator('.rnw-map').count(), 0);
  await page.click('[data-rnw=openmap]');
  await page.waitForSelector('.rnw-map #rnwmapcv canvas');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.rnw-map').count(), 0);

  // 4. back to the menu, then Make a new map: the app does not search, it asks for the folder and reports what it finds there
  await page.click('[data-rnw=menu]');
  await page.waitForFunction(() => /Your maps \(\d+\)/.test(document.querySelector('.rnw').textContent));
  assert.match(await page.textContent('.rnw'), /What do you want to do\?/);
  assert.match(await page.textContent('.rnw'), /My island/);                // the menu lists every map, imported files too
  assert.ok(await page.locator('.rnw [data-rnw=openmap]').count() >= 1);   // and offers Show map from there
  await page.click('[data-rnw=gomake]');
  await page.waitForFunction(() => /none yet/.test(document.querySelector('.rnw-log').textContent));
  assert.match(await page.textContent('.rnw'), /Where is Random New World\?/);
  assert.match(await page.textContent('.rnw'), /The app does not search your whole disk/);
  assert.equal(await page.locator('[data-rnw=new]').isDisabled(), true);                    // cannot make maps until a folder was checked
  // Browse… opens the system's folder window on the server; here the answer is faked (a real window cannot open in a test)
  await page.route('**/api/eu5/rnw/pick', r => r.fulfill({ json: { path: gen, cancelled: false, error: '' } }));
  await page.click('[data-rnw=browse][data-what=generator]');
  await page.waitForFunction(() => /Ready: maps can be made from here/.test(document.querySelector('.rnw-log').textContent));
  assert.match(await page.textContent('.rnw-log'), /you chose/);
  assert.equal(await page.locator('[data-rnw=browse][data-what=generator]').isVisible(), true);   // the folder box and Browse… stay on screen once a folder is chosen
  await page.fill('[data-rnwf=gpath]', path.join(root, 'nowhere'));
  await page.click('[data-rnw=check]');
  await page.waitForFunction(() => /is not a folder/.test(document.querySelector('.rnw-log').textContent));
  assert.match(await page.textContent('.rnw'), /Where is Random New World\?/);              // a failed check keeps asking
  await page.fill('[data-rnwf=gpath]', gen);
  await page.click('[data-rnw=check]');
  await page.waitForFunction(() => /Using/.test(document.querySelector('.rnw').textContent));
  assert.match(await page.textContent('.rnw'), /Using/);
  assert.match(await page.textContent('.rnw'), /Command line: rnw\.cmd/);

  // make a world
  await page.selectOption('[data-rnwf=preset]', 'small_continents');
  await page.fill('[data-rnwf=seed]', '42');
  await page.click('[data-rnw=new]');
  await page.waitForFunction(() => /Your maps \(4\)/.test(document.querySelector('.rnw').textContent), null, { timeout: 30000 });
  assert.match(await page.textContent('#rnwjob'), /done/);
  assert.equal(fs.existsSync(path.join(user, 'mod/rnw_exp_world_abcde23456')), true);
  const made = JSON.parse(fs.readFileSync(path.join(root, 'cfg/eu5/rnw-worlds.json'), 'utf8')).worlds[code];
  assert.equal(made.state, 'done');
  assert.equal(made.preset, 'continents');   // the stand-in prints the code of its own fixture

  // use the new world: it is on, the other world and the hub are off, it loads after Refined Colonization
  const target = page.locator('.rnw-w [data-f=rnw_exp_world_abcde23456]').first();
  await target.click();
  await page.waitForFunction(() => /On in this playset/.test(document.querySelector('.rnw').textContent));
  const ps = (await (await fetch(`${base}/api/eu5/state`)).json()).playsets[0];
  const on = ps.mods.filter(m => !ps.disabled.includes(m));
  assert.equal(on[on.length - 1], 'local:rnw_exp_world_abcde23456');
  assert.ok(on.includes('local:Refined'));
  assert.ok(ps.disabled.includes('ws:3829217331') && ps.disabled.includes('local:rnw_exp_world_aaaaa22222'));
  await page.screenshot({ path: path.join(process.env.SHOT_DIR || root, 'rnw.png') });

  // remove it again
  await page.locator('[data-rnw=remove][data-id=abcde23456]').click();
  await page.waitForFunction(() => /Your maps \(3\)/.test(document.querySelector('.rnw').textContent), null, { timeout: 15000 });
  assert.equal(fs.existsSync(path.join(user, 'mod/rnw_exp_world_abcde23456')), false);
  assert.deepEqual(errors, []);
  console.log('rnw ok');
} finally {
  if (browser) await browser.close();
  server.kill();
}
