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
- Modes are exposed as distinct actions: `Sort order: Normal`, `Sort order: Datetime created`, `Sort order: Datetime last updated`, and `Sort order: Alphabetical`.
- In the datetime modes, root notes are ordered by the newest matching timestamp anywhere in that root subtree, not just on the root note itself.
- In alphabetical mode, root notes are ordered by root-note content without rewriting the stored manual order.
- The server returns the ordered root window plus `sortMode`/`rootSortBuckets`; the client inserts day-separator rows between visible roots.
- When a non-normal sort mode is active, the UI shows a floating dismissible pill above the sticky top bar so the view override is visually obvious and can be cleared in one click.
- Changing sort mode is treated as a global view-context switch: the tab scroll state resets and undo/redo history is blanked for that tab context.

## Config
- Tag mappings live in `app/static/config/command_palette_tags.json`.
- Endpoint definitions (behavior/labels) live in code.
- Palette preferences (`pref.*`) and command usage history are persisted per namespace in the main SQLite DB via `/api2/auth/client-state*`, not in browser `localStorage`.
- `Animated transitions` is on by default and controls UI motion such as tag-bar edit transitions and note expand/collapse transitions.
- Session idle timeout is a namespace-scoped server setting stored in `app_settings` and managed via `/api2/auth/settings/session-timeout`.
- On first launch after this change, the browser imports any legacy command-palette `localStorage` values into the namespace DB and then clears those legacy keys.

## Utility Actions
- `Create backup now`: opens Backup Settings, where the user chooses one backup folder, picks which namespaces to include, sets the retention count, and then runs the backup. Typing `backups` in the palette also matches this action, and the completion modal shows the created archive size per namespace.
  - Each backup snapshot is one versioned `.tar.gz` archive containing the notes DB plus sibling files DB when present.
  - The completion modal shows one result row per namespace.
- `Restore from backup…`: opens a restore picker for configured-folder snapshots, applies the selected archive, then shows a success confirmation with `OK` before reload.
  - Restore reuses the same archive pipeline for both sources and recreates the sibling files DB from the archive contents. Legacy search-history sidecars are ignored.
- `Export as HTML`: downloads a self-contained HTML file for the current view with inline CSS, the active light/dark theme, all exported notes fully expanded, no command/search chrome, no collapse arrows, and `@password` note values redacted to matching-length `X` characters while keeping the blur styling.
- `Logout`: revokes the current session and returns to login.
- `Generate random password…`: opens a password generator modal with editable length/character set controls, explicit `Copy`, `Regenerate`, and `Close` actions, and a clipboard handoff that auto-adds `@password` when that copied value is pasted into an empty note.
- `Session idle timeout…`: opens a modal for changing the namespace-scoped inactivity window before reauthentication is required again, or disabling idle timeout entirely.
- `Reminders…`: opens the privacy-first in-app reminder registry and builder. Reminders are namespace-local, encrypted with the namespace when password protection is enabled, and never use browser/system push notifications. See `docs/ui/reminders.md`.
- `Keyboard shortcuts help…`: opens the keyboard shortcuts modal from the command palette.
- `Switch namespace…`: opens a simple namespace picker and launches/restarts the selected non-current namespace with its saved/default profile.
- `Create namespace…`: opens a namespace creation modal with defaulted HTTP / HTTPS / MCP ports, saves the profile, launches the namespace, and opens it.
- `Manage namespace ports…`: opens a table of saved launch profiles from each namespace's main DB; saving this table only updates future launch profiles and does not switch tabs, launch namespaces, or restart the current process. Current-namespace port edits apply on the next MetaList launch.
- `Delete namespace…`: asks which namespace to delete, then opens a destructive confirmation view for that target. The confirm button is red, the user must type the namespace name, and when that namespace is password-protected they must also re-enter its password. Deleting the active namespace moves the tab to a dedicated namespace-removal status page; deleting an inactive namespace stays in the current tab and reports completion in the modal.
- `Attach file…`: opens the native file picker, uploads the selected file, and inserts an embedded file reference token into the current note. If no note is active, it creates a new note first.
- `Trim unused files`: deletes file rows whose UUIDs are no longer referenced anywhere in note content. This is the only automatic cleanup path for orphaned attachments.
- `Prioritize tag to front (global)…`: opens a warning modal with single-tag input and suggestions from all root notes. Applying it stably moves all matching root notes to the front of the global root order while preserving relative order inside the matching and non-matching groups. Cmd+Z cannot undo this action; the undo/redo queue is cleared.
- `Prioritize tag to back (global)…`: same as above, but stably moves all matching root notes to the back of the global root order.
- `Alphabetize root notes A-Z (current view)…`: after confirmation, permanently rearranges only root-level notes in the active search context by root-note content. Hidden roots and child notes are not reordered. Cmd+Z cannot undo this action; the undo/redo queue is cleared like a view-context switch.
- `Alphabetize root notes Z-A (current view)…`: same as A-Z, but descending by root-note content.
- `Repair: reset updated time to created time (current view)…`: after confirmation, resets every note inside each matching root subtree in the active search context so `updated_at = created_at`. Notes outside the current view are not changed. Cmd+Z cannot undo this action; the undo/redo queue is cleared.

## Collapse/Expand All
"(current view)" means the full active search context (not just rendered DOM).
The implementation uses `POST /api2/notes/set-collapsed-in-context`.

These are treated as **global** actions:
- The client bumps the undo-context epoch.
- The server clears undo/redo history for the active undo context.
