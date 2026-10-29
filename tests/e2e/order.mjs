// Browser test of the load-order list: drag and drop, arrow buttons, enable/disable, auto-sort on/off,
// "Sort now", the details drawer explanation, and persistence across a page reload.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import assert from 'node:assert/strict';

const { chromium } = createRequire(import.meta.url)('playwright');
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modmanager-order-'));
const user = path.join(root, 'user');
const port = await freePort();
const write = (p, t) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, t); };
// Lib <- A <- B ; C and D are free
for (const [f, name, deps] of [['Lib', 'Lib', []], ['A', 'A', ['Lib']], ['B', 'B', ['A']], ['C', 'C', []], ['D', 'D', []]]) {
  write(path.join(user, 'mod', f, '.metadata/metadata.json'), JSON.stringify({ name, version: '1',
    relationships: deps.map(d => ({ rel_type: 'dependency', display_name: d })) }));
  write(path.join(user, 'mod', `${f}.mod`), `name="${name}"\npath="mod/${f}"\n`);
}
const server = spawn('python3', ['-m', 'modmanager', '--game', 'vic3', '--user-dir', user, '--workshop-dir', path.join(root, 'none'),
  '--game-version', '1.7.6', '--no-browser', '--port', String(port)],
  { env: { ...process.env, MODMANAGER_CONFIG_DIR: path.join(root, 'cfg') }, stdio: 'inherit' });
const base = `http://127.0.0.1:${port}`;
let browser;
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`${base}/api/vic3/state`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 800 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  await page.goto(`${base}/#vic3`);
  await page.waitForSelector('#tabs button');
  await page.waitForSelector('#dlg[open]', { timeout: 3000 }).then(() => page.click('#p-cancel')).catch(() => {}); // first-run setup: skip like a user would
  await page.waitForFunction(() => !document.getElementById('dlg').open);

  const row = name => page.locator('#view .row').filter({ has: page.locator('.nm', { hasText: new RegExp(`^${name}$`) }) });
  const names = async () => page.locator('#view .row .nm').allTextContents();
  const apiOrder = async () => {
    const s = await (await fetch(`${base}/api/vic3/state`)).json();
    return s.playsets[0].mods.map(m => m.split(':')[1]);
  };
  const waitOrder = async expected => {
    for (let i = 0; i < 40; i++) { if (JSON.stringify(await names()) === JSON.stringify(expected)) return; await page.waitForTimeout(100); }
    assert.deepEqual(await names(), expected);
  };

  // --- auto-sort ON: adding in a bad order always yields a valid order
  await page.click('[data-tab=library]');
  for (const id of ['B', 'D', 'A', 'C', 'Lib']) await page.click(`[data-add="local:${id}"]`);
  await page.click('[data-tab=order]');
  await page.waitForFunction(() => document.querySelectorAll('#view .row').length === 5);
  let n = await names();
  assert.ok(n.indexOf('Lib') < n.indexOf('A') && n.indexOf('A') < n.indexOf('B'), `valid order, got ${n}`);
  assert.deepEqual([...n].sort(), ['A', 'B', 'C', 'D', 'Lib']);
  assert.match(await page.textContent('#status'), /5 mods active/);
  assert.equal(await page.locator('#tabs button', { hasText: 'Warnings' }).textContent(), 'Warnings');

  // --- auto-sort ON: dragging a mod ABOVE its dependency is undone (the list stays valid)
  const before = await names();
  await row('B').dragTo(page.locator('#view .row').first());
  await page.waitForTimeout(500);
  n = await names();
  assert.ok(n.indexOf('Lib') < n.indexOf('A') && n.indexOf('A') < n.indexOf('B'), `auto-sort keeps it valid, got ${n}`);

  // --- auto-sort OFF: the manual order is kept and violations are flagged
  await page.uncheck('#auto');
  await page.waitForSelector('#sortnow', { state: 'visible' });
  await row('B').dragTo(page.locator('#view .row').first());
  await page.waitForTimeout(500);
  n = await names();
  assert.equal(n[0], 'B', `manual drag is honoured, got ${n}`);
  assert.deepEqual((await apiOrder())[0], 'B', 'server stored the manual order');
  assert.match(await page.textContent('#tabs'), /Warnings \(\d+\)/);
  assert.match(await page.textContent('#status'), /error/);
  await page.click('[data-tab=problems]');
  await page.waitForSelector('text=B must load after A');
  assert.ok(await page.locator('[data-fix=autosort]').count() >= 1);
  // warning settings: hiding "Wrong load order" removes it and the badge; showing all brings it back
  await page.click('#warn-cfg');
  await page.uncheck('[data-wc=wrong_order]');
  await page.click('#w-close');
  await page.waitForSelector('text=hidden by your warning settings');
  assert.equal(await page.locator('text=B must load after A').count(), 0);
  await page.click('#warn-cfg'); await page.click('#w-all'); await page.click('#w-close');
  await page.waitForSelector('text=B must load after A');

  // arrow buttons move by one
  await page.click('[data-tab=order]');
  const t0 = await names();
  await page.locator('#view .row').nth(1).locator('[data-mv$=",-1"]').click();
  await waitOrder([t0[1], t0[0], ...t0.slice(2)]);
  await page.locator('#view .row').nth(0).locator('[data-mv$=",1"]').click();
  await waitOrder(t0);
  // top row cannot move up, bottom cannot move down
  await page.locator('#view .row').first().locator('[data-mv$=",-1"]').click();
  await waitOrder(t0);

  // --- one-click "Sort now" fixes everything
  await page.click('#sortnow');
  await page.waitForTimeout(400);
  n = await names();
  assert.ok(n.indexOf('Lib') < n.indexOf('A') && n.indexOf('A') < n.indexOf('B'));
  await page.click('[data-tab=problems]');
  await page.waitForSelector('text=No problems found', {timeout: 3000}).catch(async e => { console.log('VIEW:', await page.textContent('#view')); throw e; });

  // --- disabling a dependency raises the one-click enable fix, which also restores a valid order
  await page.click('[data-tab=order]');
  await row('Lib').locator('[data-tog]').uncheck();
  await page.click('[data-tab=problems]');
  await page.waitForSelector('text=A needs Lib');
  await page.click('[data-fix=enable]');
  await page.click('[data-tab=order]');
  assert.equal(await page.locator('#view .row.off').count(), 0);
  assert.match(await page.textContent('#status'), /5 mods active/);

  // --- removing a mod (✕) and re-adding it from the library
  await row('D').locator('[data-rm]').click();
  await page.waitForTimeout(300);
  assert.ok(!(await names()).includes('D'));
  await page.click('[data-tab=library]');
  await page.click('[data-add="local:D"]');
  await page.click('[data-tab=order]');
  assert.ok((await names()).includes('D'));

  // --- details drawer explains position; toggling the row selection closes it
  await page.click('[data-tab=order]');
  await page.locator('#view .nm', { hasText: /^B$/ }).click();
  await page.waitForSelector('#drawer.open');
  assert.match(await page.textContent('#drawer'), /Loads after A \(dependency\)/);
  await page.locator('#view .nm', { hasText: /^B$/ }).click();
  await page.waitForSelector('#drawer:not(.open)');

  // --- launch part: dialog lists enabled mods, dependency helper ticks what is needed
  page.removeAllListeners('dialog'); page.on('dialog', d => d.accept());
  await page.click('#launchpart');
  await page.waitForSelector('#dlg[open] [data-lp]');
  await page.click('#lp-none');
  await page.check('[data-lp="local:B"]');
  await page.waitForSelector('text=Needed but not ticked');
  await page.click('#lp-deps');
  assert.equal(await page.locator('[data-lp]:checked').count(), 3);  // B + A + Lib
  await page.click('#lp-cancel');

  // --- order and disabled state survive a reload
  await row('C').locator('[data-tog]').uncheck();
  await page.waitForTimeout(300);
  const saved = await names();
  await page.reload();
  await page.waitForSelector('#view .row');
  assert.deepEqual(await names(), saved);
  assert.equal(await page.locator('#view .row.off').count(), 1);
  assert.equal(await page.locator('#auto').isChecked(), false, 'auto-sort setting persisted');

  // --- two playsets keep independent orders
  page.removeAllListeners('dialog');
  page.on('dialog', d => d.accept('Second'));
  await page.click('#new');
  await page.waitForSelector('#title:has-text("Second")');
  assert.equal(await page.locator('#view .row').count(), 0);
  await page.click('.ps >> text=Default');
  await page.waitForSelector('#title:has-text("Default")');
  assert.deepEqual(await names(), saved);

  assert.deepEqual(errors, [], 'no page errors');
  console.log('order e2e ok');
} finally {
  await browser?.close();
  server.kill();
  fs.rmSync(root, { recursive: true, force: true });
}
