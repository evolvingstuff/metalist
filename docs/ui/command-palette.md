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
- `Restore from backup…`: opens a restore picker, applies the selected backup, then shows a success confirmation with `OK` before reload.
- `Logout`: revokes the current session and returns to login.
- `Generate random password…`: opens a utility modal for password generation.
- `Keyboard shortcuts help…`: opens the keyboard shortcuts modal from the command palette.

## Collapse/Expand All
"(current view)" means the full active search context (not just rendered DOM).
The implementation uses `POST /api2/notes/set-collapsed-in-context`.

These are treated as **global** actions:
- The client bumps the undo-context epoch.
- The server clears undo/redo history for the active undo context.
