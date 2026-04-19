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

## Config
- Tag mappings live in `app/static/config/command_palette_tags.json`.
- Endpoint definitions (behavior/labels) live in code.

## Utility Actions
- `Create backup now`: creates a timestamped SQLite backup in the app backup directory. If total backups are 25 or more, the app opens a retention modal asking how many backups to keep (defaults to 3, with an explicit "Keep all backups" option), then shows a completion modal with `OK`.
  - When file attachments exist, the backup includes the sibling `*.files.db` database as a paired sidecar backup.
- `Restore from backup…`: opens a restore picker, applies the selected backup, then shows a success confirmation with `OK` before reload.
  - Restore also restores the paired file-attachment database, or resets it to empty when the selected backup predates file attachments.
- `Export as HTML`: downloads a self-contained HTML file for the current view with inline CSS, the active light/dark theme, all exported notes fully expanded, no command/search chrome, no collapse arrows, and `@password` note values redacted to matching-length `X` characters while keeping the blur styling.
- `Logout`: revokes the current session and returns to login.
- `Generate random password…`: opens a password generator modal with editable length/character set controls, explicit `Copy`, `Regenerate`, and `Close` actions, and a clipboard handoff that auto-adds `@password` when that copied value is pasted into an empty note.
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
