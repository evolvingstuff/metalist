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
By default, this binds HTTP on `0.0.0.0:8000`, matching the old MetaList LAN-friendly behavior.
HTTPS on `0.0.0.0:8443` only turns on if TLS files already exist at `certs/metalist-cert.pem` and `certs/metalist-key.pem`, or if you point `METALIST_TLS_CERT` and `METALIST_TLS_KEY` at existing PEM files.

Useful env flags:
- `CRASH_SERVER_ON_FAIL=1` (default): fail-fast on validation errors
- `API_PREFIX=/api2`: override API prefix (client assumes `/api2` by default)
- `METALIST_HOST=0.0.0.0` (default): bind the main app to a different interface such as `127.0.0.1`
- `METALIST_PORT=8000` (default): bind the main app to a different port
- `METALIST_HTTPS_PORT=8443`: override the HTTPS port when TLS is enabled
- `METALIST_TLS_CERT=/path/to/fullchain.pem` + `METALIST_TLS_KEY=/path/to/privkey.pem`: override TLS paths
- default TLS paths: `certs/metalist-cert.pem` and `certs/metalist-key.pem`
- `METALIST_FORWARDED_ALLOW_IPS=127.0.0.1,::1` (default): trust proxy headers only from those reverse-proxy IPs
- `MCP_AGENT_PUBLIC_ORIGIN=https://notes.example.com:8765`: public origin for the MCP sidecar redirect when it is exposed behind HTTPS or a separate hostname/port

### Remote Access / HTTPS
Plain LAN or VPN HTTP works with a normal PyCharm run:
```bash
python main.py
```
Then open `http://<laptop-ip>:8000` from the other machine.

For LAN-friendly HTTPS, manually generate or supply PEM files first:
```bash
./scripts/generate-lan-cert.sh
```
Then a plain PyCharm run or `python main.py` will also start `https://<laptop-ip>:8443`.

Equivalent explicit launch, if you want it:
```bash
METALIST_HOST=0.0.0.0 \
METALIST_PORT=8000 \
METALIST_HTTPS_PORT=8443 \
python main.py
```
From the other machine, open `https://<laptop-ip>:8443`.

If you already have a real certificate and key, use the same dual-listener flow:
```bash
METALIST_HOST=0.0.0.0 \
METALIST_PORT=8000 \
METALIST_HTTPS_PORT=8443 \
METALIST_TLS_CERT=/path/to/fullchain.pem \
METALIST_TLS_KEY=/path/to/privkey.pem \
python main.py
```

When HTTPS is enabled:
- remote HTTP requests to `http://<laptop-ip>:8000` are redirected to HTTPS
- localhost HTTP requests still stay on plain `http://127.0.0.1:8000` so the laptop can keep using the non-TLS port

If TLS is terminated by a reverse proxy on the same machine instead, keep MetaList on loopback and let the proxy forward to it:
```bash
METALIST_HOST=127.0.0.1 \
METALIST_PORT=8000 \
METALIST_FORWARDED_ALLOW_IPS=127.0.0.1,::1 \
python main.py
```

If you do not need the MCP sidecar remotely, disable it:
```bash
MCP_AGENT_WEB_ENABLED=0 python main.py
```

### MCP (Phase 1 Read-Only)
MCP is available automatically when you run:
```bash
python main.py
```

`main.py` also auto-starts the agent web app sidecar and prints:
- `Agent web app: http://127.0.0.1:8765`
- On startup, local Ollama (`127.0.0.1`) is reset by default so a fresh runner is used.
- Sidecar Ollama auto-start uses `OLLAMA_CONTEXT_LENGTH=16384` by default.

Manual web mode (optional):
```bash
python mcp_client.py web --port 8765
```
Then open `http://127.0.0.1:8765`.

Run direct MCP CLI calls:
```bash
python mcp_client.py cli tools/list
python mcp_client.py cli tools/call health_check '{}'
```

Compatibility shortcut (still works):
```bash
python mcp_client.py tools/list
```

Disable auto sidecar if needed:
```bash
MCP_AGENT_WEB_ENABLED=0 python main.py
```

Control Ollama startup behavior:
```bash
# disable Ollama reset-on-start (default is enabled)
MCP_AGENT_RESET_OLLAMA_ON_START=0 python main.py

# override auto-start context length (default 16384)
MCP_AGENT_OLLAMA_CONTEXT_LENGTH=32768 python main.py
```

Optional: direct stdio transport (advanced/manual):
```bash
python -m app.mcp
```

Tool catalog and schemas:
- `docs/mcp_tools.md`

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
