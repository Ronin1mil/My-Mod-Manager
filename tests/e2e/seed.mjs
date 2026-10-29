// The app no longer creates an empty "Default" playset by itself, so scripts that need one make it first.
export async function seed(base, ...games) {
  for (const g of games) {
    const r = await fetch(`${base}/api/${g}/playsets`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Default' }) });
    if (!r.ok) throw new Error(`could not create a playset for ${g}: ${r.status}`);
  }
}
