# Command Palette

Open with `⌘ + /` or the menu (`≡`) button in the upper right.

## Undo/Redo Boundary
Opening the command palette creates an explicit undo/redo boundary.
After you open it, subsequent undo/redo should not traverse operations that occurred before.

## Semantics
- Query is an unordered bag of words.
- AND-only matching against manually-authored tags.
- While you are mid-token (no trailing space), it behaves as a prefix filter.

## Results
- Booleans toggle with `Enter`.
- Selects cycle with `Enter` (and adjust with `←`/`→`).
- Actions run with `Enter`.

## Sort Order
- `Sort order` is a per-tab, server-owned view setting. Duplicating a tab inherits its current sort mode.
- Modes are `Normal`, `Datetime created`, and `Datetime last updated`.
- In the datetime modes, root notes are ordered by the newest matching timestamp anywhere in that root subtree, not just on the root note itself.
- The server returns the ordered root window plus `sortMode`/`rootSortBuckets`; the client inserts day-separator rows between visible roots.
- When a datetime mode is active, the UI shows a floating dismissible pill above the sticky top bar so the view override is visually obvious and can be cleared in one click.
- Changing sort mode is treated as a global view-context switch: the tab scroll state resets and undo/redo history is blanked for that tab context.

## Config
- Tag mappings live in `app/static/config/command_palette_tags.json`.
- Endpoint definitions (behavior/labels) live in code.
- Palette preferences (`pref.*`) and command usage history are persisted per namespace in the main SQLite DB via `/api2/auth/client-state*`, not in browser `localStorage`.
- Session idle timeout is a namespace-scoped server setting stored in `app_settings` and managed via `/api2/auth/settings/session-timeout`.
- On first launch after this change, the browser imports any legacy command-palette `localStorage` values into the namespace DB and then clears those legacy keys.

## Utility Actions
- `Create backup now`: opens Backup Settings, where the user chooses one backup folder, picks which namespaces to include, sets the retention count, and then runs the backup.
  - Each backup snapshot is one versioned `.tar.gz` archive containing the notes DB plus sibling file/search-history DBs when present.
  - The completion modal shows one result row per namespace.
- `Restore from backup…`: opens a restore picker for configured-folder snapshots, applies the selected archive, then shows a success confirmation with `OK` before reload.
  - Restore reuses the same archive pipeline for both sources and recreates sibling file/search-history DBs from the archive contents.
- `Export as HTML`: downloads a self-contained HTML file for the current view with inline CSS, the active light/dark theme, all exported notes fully expanded, no command/search chrome, no collapse arrows, and `@password` note values redacted to matching-length `X` characters while keeping the blur styling.
- `Logout`: revokes the current session and returns to login.
- `Generate random password…`: opens a password generator modal with editable length/character set controls, explicit `Copy`, `Regenerate`, and `Close` actions, and a clipboard handoff that auto-adds `@password` when that copied value is pasted into an empty note.
- `Session idle timeout…`: opens a modal for changing the namespace-scoped inactivity window before reauthentication is required again, or disabling idle timeout entirely.
- `Keyboard shortcuts help…`: opens the keyboard shortcuts modal from the command palette.
- `Switch or create namespace…`: opens a namespace modal that can select an existing namespace or define a new one, prefill remembered ports from `~/MetaList/namespaces.db`, suggest the next free ports for new namespaces, reject port conflicts, restart an already-running target namespace from the current code, or fork a new `python main.py --namespace ...` process and then open it.
- `Delete current namespace…`: opens a destructive confirmation modal for the active non-default namespace. The confirm button is red, the user must type `permanently delete`, and when password protection is enabled they must also re-enter the current password. After submission, the tab moves to a dedicated namespace-removal status page that polls for completion and then offers links to the remaining namespaces.
- `Attach file…`: opens the native file picker, uploads the selected file, and inserts an embedded file reference token into the current note. If no note is active, it creates a new note first.
- `Trim unused files`: deletes file rows whose UUIDs are no longer referenced anywhere in note content. This is the only automatic cleanup path for orphaned attachments.
- `Prioritize tag to front (current view)…`: opens a modal with single-tag input and suggestions limited to tags present on root notes in the active view. Applying it stably moves matching root notes to the front of the full active view while preserving relative order inside the matching and non-matching groups. This mutates stored root order through the current view subset, not just the currently rendered DOM.
- `Prioritize tag to back (current view)…`: same as above, but stably moves matching root notes to the back of the full active view.

## Collapse/Expand All
"(current view)" means the full active search context (not just rendered DOM).
The implementation uses `POST /api2/notes/set-collapsed-in-context`.

These are treated as **global** actions:
- The client bumps the undo-context epoch.
- The server clears undo/redo history for the active undo context.
