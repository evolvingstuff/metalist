# MetaList

A minimalist single-user note-taking app focused on server-side rendering (SSR), fast in-memory tree operations, and efficient sync/diff updates.

## Features
- Rich text editing (ContentEditable) with image support
- Drag-and-drop note reordering
- Real-time content saving
- Keyboard shortcuts (press `?` in the app)
- Linked-list ordering model for efficient reorders
- Optional password protection + encryption at rest (AES-GCM)
- Multi-tab search contexts with server-persisted scroll/search state (survives browser restarts)

## Technology Stack

### Backend
- FastAPI
- SQLite (via stdlib `sqlite3`) with a guard-aware wrapper (`SafeSession`)
- Mako templates for SSR

### Frontend
- Vanilla JavaScript (no framework)
- HTML5 Drag and Drop API
- ContentEditable for rich text editing
- CSS custom properties for theming

### Testing
- Cypress end-to-end UI suite (primary automated coverage)

## Architecture (High Level)
- Server renders the base page via Mako templates.
- The browser client drives interaction via `/api2` JSON endpoints.
- Notes are loaded/decrypted into an in-memory store at startup; a post-startup DB read guard prevents accidental runtime SELECTs.

## Development

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

npm install
```

### Run
The default entrypoint starts Uvicorn with the FastAPI app:
```bash
python main.py
```
Then visit `http://127.0.0.1:8000`.

Useful env flags:
- `CRASH_SERVER_ON_FAIL=1` (default): fail-fast on validation errors
- `API_PREFIX=/api2`: override API prefix (client assumes `/api2` by default)

### Legacy Import
`convert-from-legacy.py` replaces the SQLite database referenced by `app.config.DATABASE_URL` and imports notes from a legacy JSON export.

This is destructive. It deletes the existing DB file before rebuilding it.

Example usage:
```bash
python convert-from-legacy.py --input /path/to/legacy-export.json
```

If `--input` is omitted, a file picker opens (when `tkinter` is available).
Notes tagged with `@implies` are converted into ontology rules and are not imported as notes.

### Run Tests (Cypress)

**Headless (recommended)**: starts the server in `TEST_MODE=1` and runs Cypress:
```bash
bash run_cypress_tests.sh
```

Notes:
- `TEST_MODE=1` uses `test.db` and deletes it on startup.
- The script will kill anything already listening on port `8000`.

**Interactive**:
1. Start the server in test mode:
   ```bash
   source .venv/bin/activate
   TEST_MODE=1 uvicorn app.main:app --port 8000
   ```
2. In another terminal:
   ```bash
   cd tests/ui
   npx cypress open
   ```

### Diagrams
Render Mermaid diagrams to PNGs:
```bash
npm run render-diagrams
```
