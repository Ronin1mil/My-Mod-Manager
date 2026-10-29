// Walkthrough + test: get the "RICE + Cultures Expanded" stack on CK3, from the Presets tab to Play.
// The Steam client is the only simulated part: "subscribe + download" is imitated by creating the Workshop folders
// (with the real titles) and Steam's appworkshop record. SHOTS=<dir> writes numbered screenshots.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-ce-'));
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + '.png') }); };

// a stand-in CK3 install + user folder
const steam = path.join(root, 'Steam/steamapps');
const game = path.join(steam, 'common/Crusader Kings III');
const ws = path.join(steam, 'workshop/content/1158310');
const user = path.join(root, 'user');
write(path.join(game, 'game/common/traits/00_traits.txt'), 'brave = { }\n');
write(path.join(game, 'launcher/launcher-settings.json'), JSON.stringify({ rawVersion: '1.15.1' }));
const exe = path.join(game, 'start.sh');
write(exe, `#!/usr/bin/env python3\nimport json,os,sys\nd=os.path.dirname(os.path.abspath(__file__))\njson.dump({"args":sys.argv[1:],"load":json.load(open(os.path.join(os.environ["STUB_USER"],"dlc_load.json")))},open(os.path.join(d,"record.json"),"w"))\n`);
fs.chmodSync(exe, 0o755);
fs.mkdirSync(user, { recursive: true });

const MODS = [  // real Workshop ids and titles (checked against Steam's API); dependencies as their pages state
  ['2273832430', 'Regional Immersion and Cultural Enrichment (RICE)', [], ['common/culture/cultures/rice_cultures.txt', 'common/traits/00_traits.txt']],
  ['2507209632', 'Ethnicities & Portraits Expanded', [], ['gfx/portraits/epe_ethnicities.txt', 'common/culture/cultures/epe_cultures.txt']],
  ['2829397295', 'Cultures Expanded', ['Ethnicities & Portraits Expanded'], ['common/culture/cultures/ce_cultures.txt', 'localization/english/ce_l_english.yml']],
];
const fakeSteamDownload = () => {
  for (const [id, name, deps, files] of MODS) {
    write(path.join(ws, id, '.metadata/metadata.json'), JSON.stringify({ name, version: '1', relationships: deps.map(d => ({ rel_type: 'dependency', display_name: d })) }));
    for (const f of files) write(path.join(ws, id, f), f.endsWith('.yml') ? 'l_english:\n ce_key:0 "x"\n' : `x_${id} = { }\n`);
  }
  write(path.join(steam, 'workshop/appworkshop_1158310.acf'), '"AppWorkshop"\n{\n\t"appid"\t"1158310"\n\t"WorkshopItemsInstalled"\n\t{\n' +
    MODS.map(m => `\t\t"${m[0]}"\n\t\t{\n\t\t\t"timeupdated"\t"1000"\n\t\t}\n`).join('') + '\t}\n}\n');
};

const server = spawn('python3', ['-m', 'modmanager', '--game', 'ck3', '--game-dir', game, '--user-dir', user, '--workshop-dir', ws,
  '--game-exe', exe, '--no-browser', '--port', String(port)],
  { env: { ...process.env, BROWSER: 'true', STUB_USER: user, MODMANAGER_CONFIG_DIR: path.join(root, 'cfg') }, stdio: 'inherit' });
const get = async p => (await fetch(base + p)).json();
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/ck3/state`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  await page.goto(`${base}/#ck3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 2500 }).then(() => page.click('#p-cancel')).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  // STEP 1: the empty app
  await page.waitForSelector('#view');
  await shot(page, '01-empty-app');

  // STEP 2: Presets tab
  await page.click('[data-tab=presets]');
  await page.waitForSelector('[data-preset="ck3-culture-expanded"]');
  await shot(page, '02-presets-tab');

  // STEP 3: Create playset from "RICE + Cultures Expanded"
  await page.click('[data-preset="ck3-culture-expanded"]');
  await page.waitForSelector('text=Not installed yet (3)');
  await shot(page, '03-playset-created-mods-missing');

  // STEP 4: Warnings tab says exactly what is missing
  await page.click('[data-tab=problems]');
  await page.waitForSelector('text=Cultures Expanded');
  assert.ok((await page.locator('#view .row.static').count()) >= 3);
  await shot(page, '04-warnings-not-installed');

  // STEP 5: "Open in Steam…" (Steam client then shows each page; user presses Subscribe)
  await page.click('[data-tab=presets]');
  await page.click('[data-dl=steam]');
  await page.waitForSelector('#toast.on:has-text("Opened in Steam")');
  await shot(page, '05-open-in-steam');

  // STEP 6: Steam downloads (simulated), then Rescan
  fakeSteamDownload();
  await page.click('[data-dl=rescan]');
  await page.waitForSelector('text=3/3 installed');
  await shot(page, '06-after-rescan-installed');

  // STEP 7: load order is valid (dependency first), no warnings
  await page.click('[data-tab=order]');
  const names = await page.locator('#view .row .nm').allTextContents();
  assert.ok(names.indexOf('Ethnicities & Portraits Expanded') < names.indexOf('Cultures Expanded'), `EPE before CE, got ${names}`);
  await shot(page, '07-load-order');
  await page.click('[data-tab=problems]');
  await page.waitForSelector('text=No problems found');
  await shot(page, '08-no-warnings');

  // STEP 8: conflicts + file tree
  await page.click('[data-tab=conflicts]');
  await shot(page, '09-conflicts');
  await page.click('[data-tab=files]');
  await page.waitForSelector('#ft details');
  await shot(page, '10-file-tree');

  // STEP 9: update check against the REAL Steam API (local record says 1000 = ancient, so all three are "newer")
  await page.click('[data-tab=library]');
  await page.click('#modupd');
  await page.waitForSelector('text=3 available', { timeout: 20000 });
  await shot(page, '11-mod-update-check-real-steam');

  // STEP 10: Play. The game is a stub that records what it was given.
  await page.click('[data-tab=order]');
  await page.click('#launch');
  await page.waitForSelector('#toast.on:has-text("Wrote 3 mods")', {timeout: 8000}).catch(async e => { console.log('TOAST:', await page.textContent('#toast')); throw e; });
  await shot(page, '12-launched');
  const rec = path.join(game, 'record.json');
  for (let i = 0; i < 100 && !fs.existsSync(rec); i++) await new Promise(r => setTimeout(r, 50));
  const got = JSON.parse(fs.readFileSync(rec, 'utf8'));
  assert.equal(got.load.enabled_mods.length, 3);
  assert.ok(got.load.enabled_mods.every(m => /^mod\/ugc_\d+\.mod$/.test(m)), JSON.stringify(got.load));
  for (const [id] of MODS) assert.ok(fs.existsSync(path.join(user, 'mod', `ugc_${id}.mod`)), `stub descriptor for ${id}`);
  const order = got.load.enabled_mods.map(m => m.match(/\d+/)[0]);
  assert.ok(order.indexOf('2507209632') < order.indexOf('2829397295'), 'EPE launched before Cultures Expanded');

  // STEP 11: second launch with the save-version guard: pretend the saves are from 1.14
  fs.mkdirSync(path.join(user, 'save games'), { recursive: true });
  fs.writeFileSync(path.join(user, 'save games', 'old.ck3'), 'meta { version="1.14.2" }');
  let asked = '';
  page.removeAllListeners('dialog'); page.on('dialog', d => { asked = d.message(); d.dismiss(); });
  await page.click('#launch');
  await page.waitForTimeout(600);
  assert.match(asked, /1\.14/);
  assert.match(asked, /1\.15/);
  assert.deepEqual(errors, [], 'no page errors');
  console.log('culture-expanded walkthrough ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
