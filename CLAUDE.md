# Notes for working on this repository

## Names (always)
- Official releases are **Version X.Y.Z**. Nothing else: no "test", no "preview".
- In-between versions (from the `nightly` branch) are **nightly builds**, named only by their build id (short commit id).
- Never write "test build" in the app, docs, changelog, commit messages or release notes. Do not invent other names.
- The GitHub tag `test-build` is the one exception: installed copies look it up, so it stays. The app never shows it.
- Details: docs/19-nightly-builds-and-releases.md, docs/06-decisions.md.

## Flow
- Work on `nightly`; every push runs CI and, if it passes, replaces the rolling nightly build.
- `main` only gets releases: bump `__version__`, add a CHANGELOG section, fast-forward `main` to the tested commit, then run CI with `publish` and `python_only`. Do not push to `main` or publish without being told.
- Releases carry only `Mod-Manager-python.pyzw`.
- The user's name and email never go into the repository or releases; the Windows user name in logs is redacted to `<user>`.
