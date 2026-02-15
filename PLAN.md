# PLAN: Minimal Menu Functions for Dogfooding

## Goal
Ship the remaining minimal menu/command-palette functions so daily dogfooding is possible:
1. Save a timestamped SQLite backup
2. Restore from a selected backup
3. Logout
4. Generate a random password

## Scope
- Add backend backup/restore endpoints and service logic.
- Add command-palette endpoints + tags for the 4 actions.
- Add a minimal restore UX and random-password generator modal UI.
- Reuse existing auth/logout and modal patterns.

## Proposed Implementation

### 1) Backup + Restore Backend
- Add a dedicated service (e.g. `app/services/backup_service.py`) that:
  - Resolves the active DB path from `SafeSession`.
  - Creates backups in a sibling `backups/` directory with timestamped filenames.
  - Uses SQLite’s backup API (not raw file copy) for WAL-safe snapshots.
  - Lists available backup files (newest first).
  - Restores from a chosen backup file with strict filename/path validation.
- Add API routes (likely under `/api2/auth`) for:
  - `POST .../backup/create`
  - `GET .../backup/list`
  - `POST .../backup/restore`
- After restore:
  - Clear/rebuild in-memory state as needed (`view_cache`, locks, auth cache state, tab state).
  - Revoke tokens and clear encryption key so client must re-auth/reload cleanly.

### 2) Command Palette: New Menu Actions
- Extend `app/static/js/modules/command-palette/endpoint-registry.js` with:
  - `action.create_backup`
  - `action.restore_backup`
  - `action.logout`
  - `action.generate_random_password`
- Wire required handlers in `command-palette-controller.js`.
- Add tag mappings in `app/static/config/command_palette_tags.json` (required to satisfy existing endpoint/tag validation).

### 3) Restore Backup UX (Minimal)
- Add a small modal for restore flow:
  - Fetch backup list.
  - Let user pick one backup.
  - Require explicit confirmation before restore.
  - On success, force clean reload/login.

### 4) Random Password Generator UX
- Add a modal utility aligned with your provided UI:
  - Length input
  - Editable character set textarea
  - Generated password result textarea
  - Regenerate button
- Use secure randomness (`crypto.getRandomValues`) on client.
- Add minimal input validation (length > 0, non-empty character set).

### 5) Docs + Validation
- Update docs for new menu entries and behavior:
  - `docs/ui/command-palette.md`
  - `docs/ui/controls.md` (if shortcuts/actions are user-facing there)
- Run targeted checks:
  - Python tests for backup/restore route/service behavior.
  - JS unit tests for random password generation helpers / registry wiring.
  - `./sanitycheck/run` (if present).

## Success Criteria
- Menu exposes all four requested actions and they execute end-to-end.
- Backup creates timestamped SQLite snapshots without breaking the running app.
- Restore replaces app data from a chosen backup and safely resets session state.
- Logout action works from menu/command palette.
- Random password utility is usable for password creation/change workflow.
- Relevant docs are updated.

## Notes / Risks
- There is no dedicated existing doc for backup/restore behavior; this will be newly documented in UI docs (and optionally security docs if you want operational guidance there).
- Restore is high-impact; confirmation + forced re-auth are required to avoid stale in-memory/auth state.
