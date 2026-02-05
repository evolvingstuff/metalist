# PLAN

## Goal
- Build `convert-from-legacy.py` to import legacy JSON into the current SQLite schema at `~/MetaList/metalist2.db` (via `app.config.DATABASE_URL`).
- Default to a native file picker; support `--input /path/to/file.json` as a fallback.
- Conversion is destructive: delete the existing DB file and rebuild from scratch.

## Assumptions / Invariants
- `encryption.encrypted` is always `false` (assert).
- Each `data` item has a `subitems` array.
- The first `subitem` is the only `indent=0` entry (assert).
- `subitems` order defines sibling order; no `prev/next` in old data.
- Indent defines hierarchy; indent never jumps by more than 1 (assert).
- `creation` + `last_edit` (epoch ms) exist on each top-level item (assert).
- All new notes get new UUIDs; `tags` are copied as-is.
- Subitems tagged `@implies` become ontology rules and are not imported as notes.

## Plan
1. Implement `convert-from-legacy.py` with CLI + picker:
   - `argparse` with optional `--input`.
   - If `--input` missing, open a `tkinter` file dialog; if GUI fails, raise with instructions to pass `--input`.
   - Load JSON + validate invariants, including `encryption.encrypted == false`.
2. Rebuild the database:
   - Resolve SQLite path from `DATABASE_URL`; require sqlite URL.
   - Delete the existing DB file (if present), create parent dir.
   - Open `SafeSession` to initialize schema; insert default settings.
3. Convert and insert notes/rules:
   - For each top-level item, create the root note from the first subitem.
   - If a subitem has `@implies`, parse `A => B` / `A = B` rules into ontology entries and skip note creation.
   - Build nested notes using an indent stack; insert notes with `insert_note`.
   - Track sibling order per parent; apply `prev/next` links with `update_links`.
   - Use `creation`/`last_edit` timestamps for all notes in that item.
4. Documentation:
   - Add usage + destructive warning to `README.md` or `docs/README.md`.
5. Manual verification:
   - Run `python convert.py` on a sample JSON.
   - Confirm `~/MetaList/metalist2.db` is created and the app renders notes.
