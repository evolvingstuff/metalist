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
For a published install, users should run `pip install metalist`. For a non-editable local install from this checkout, use `pip install .` instead of the editable command below.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

npm install
```

### Run
The installed entrypoint starts Uvicorn with the FastAPI app:
```bash
metalist
```
For source-checkout compatibility, `python main.py` still works.

By default, this binds HTTP on `0.0.0.0:8000`, matching the old MetaList LAN-friendly behavior.
On first startup, MetaList also auto-generates a self-signed TLS pair at `~/MetaList/certs/metalist-cert.pem` and `~/MetaList/certs/metalist-key.pem`, then enables HTTPS on `0.0.0.0:8443`. If you already have real PEM files, point `METALIST_TLS_CERT` and `METALIST_TLS_KEY` at them instead. Set `METALIST_AUTO_GENERATE_TLS=0` only if you explicitly want HTTP-only startup.

Database selection:
- No explicit namespace: `~/MetaList/namespaces/default/default.metalist.db`
- `--namespace work` or `METALIST_NAMESPACE=work`: `~/MetaList/namespaces/work/work.metalist.db`
- The related files DB is derived automatically, so `namespaces/work/work.metalist.db` uses `namespaces/work/work.metalist.files.db`
- Remembered launch ports are stored per namespace in `~/MetaList/namespaces.db`
- Launch precedence is: explicit CLI flags > env vars > saved namespace profile > built-in defaults
- Backups stay beside the namespace data under `~/MetaList/namespaces/work/backups/` and use self-identifying filenames like `<timestamp>.work.metalist.db.bak`

Useful env flags:
- `CRASH_SERVER_ON_FAIL=1` (default): fail-fast on validation errors
- `API_PREFIX=/api2`: override API prefix (client assumes `/api2` by default)
- `METALIST_NAMESPACE=work`: select `~/MetaList/namespaces/work/work.metalist.db`
- `METALIST_HOST=0.0.0.0` (default): bind the main app to a different interface such as `127.0.0.1`
- `METALIST_PORT=8000` (default): bind the main app to a different port
- `METALIST_HTTPS_PORT=8443`: override the HTTPS port when TLS is enabled
- `MCP_AGENT_WEB_PORT=8765` (default): bind the MCP sidecar web UI to a different port
- `METALIST_TLS_CERT=/path/to/fullchain.pem` + `METALIST_TLS_KEY=/path/to/privkey.pem`: override TLS paths
- `METALIST_AUTO_GENERATE_TLS=0`: disable automatic creation of the default self-signed TLS pair
- default TLS paths: `~/MetaList/certs/metalist-cert.pem` and `~/MetaList/certs/metalist-key.pem`
- `METALIST_FORWARDED_ALLOW_IPS=127.0.0.1,::1` (default): trust proxy headers only from those reverse-proxy IPs
- `MCP_AGENT_PUBLIC_ORIGIN=https://notes.example.com:8765`: public origin for the MCP sidecar redirect when it is exposed behind HTTPS or a separate hostname/port

### Remote Access / HTTPS
Plain LAN or VPN HTTP works with a normal PyCharm run:
```bash
metalist
```
On a fresh machine, that first launch also creates the default TLS cert pair automatically. Then open either `http://<laptop-ip>:8000` or `https://<laptop-ip>:8443` from the other machine.

Namespaced launch example:
```bash
metalist --namespace work --port 8001 --mcp-port 8766
```
This starts a separate process backed by `~/MetaList/namespaces/work/work.metalist.db` on `http://127.0.0.1:8001`.
Its related backup snapshots live under `~/MetaList/namespaces/work/backups/` with filenames like `<timestamp>.work.metalist.db.bak`.

After you launch a namespace once with explicit ports, MetaList remembers them in `~/MetaList/namespaces.db`, so later you can use the shorthand:
```bash
metalist work
```
and MetaList will reuse the saved HTTP / HTTPS / MCP sidecar ports for `work`. The same applies to the default namespace: `metalist` will reuse the saved default-namespace profile.

Equivalent explicit launch, if you want it:
```bash
METALIST_HOST=0.0.0.0 \
METALIST_PORT=8000 \
METALIST_HTTPS_PORT=8443 \
metalist
```
From the other machine, open `https://<laptop-ip>:8443`.

If you already have a real certificate and key, use the same dual-listener flow:
```bash
METALIST_HOST=0.0.0.0 \
METALIST_PORT=8000 \
METALIST_HTTPS_PORT=8443 \
METALIST_TLS_CERT=/path/to/fullchain.pem \
METALIST_TLS_KEY=/path/to/privkey.pem \
metalist
```

If you want to rotate or regenerate the default self-signed pair manually, the helper script is still available:
```bash
generate-lan-cert.sh
```

When HTTPS is enabled:
- remote HTTP requests to `http://<laptop-ip>:8000` are redirected to HTTPS
- localhost HTTP requests still stay on plain `http://127.0.0.1:8000` so the laptop can keep using the non-TLS port

If TLS is terminated by a reverse proxy on the same machine instead, keep MetaList on loopback and let the proxy forward to it:
```bash
METALIST_HOST=127.0.0.1 \
METALIST_PORT=8000 \
METALIST_FORWARDED_ALLOW_IPS=127.0.0.1,::1 \
metalist
```

If you do not need the MCP sidecar remotely, disable it:
```bash
MCP_AGENT_WEB_ENABLED=0 metalist
```

### MCP (Phase 1 Read-Only)
MCP is available automatically when you run:
```bash
metalist
```

`metalist` also auto-starts the agent web app sidecar and prints:
- `Agent web app: http://127.0.0.1:8765`
- The sidecar default MCP URL follows the resolved MetaList HTTP port for the current process.
- Use `--mcp-port` when you want multiple MetaList instances to auto-start sidecars without colliding on `8765`.
- On startup, local Ollama (`127.0.0.1`) is reset by default so a fresh runner is used.
- Sidecar Ollama auto-start uses `OLLAMA_CONTEXT_LENGTH=16384` by default.

Manual web mode (optional):
```bash
metalist-mcp web --port 8765
```
Then open `http://127.0.0.1:8765`.

Run direct MCP CLI calls:
```bash
metalist-mcp cli tools/list
metalist-mcp cli tools/call health_check '{}'
```

Compatibility shortcut (still works):
```bash
python mcp_client.py tools/list
```

Disable auto sidecar if needed:
```bash
MCP_AGENT_WEB_ENABLED=0 metalist
```

Control Ollama startup behavior:
```bash
# disable Ollama reset-on-start (default is enabled)
MCP_AGENT_RESET_OLLAMA_ON_START=0 metalist

# override auto-start context length (default 16384)
MCP_AGENT_OLLAMA_CONTEXT_LENGTH=32768 metalist
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
convert-from-legacy.py --input /path/to/legacy-export.json
```

Target a namespaced database during import:
```bash
convert-from-legacy.py --namespace work --input /path/to/legacy-export.json
```

If `--namespace`, `--port`, `--https-port`, or `--mcp-port` are omitted, the import script prompts for them and saves the resulting launch profile to `~/MetaList/namespaces.db`. That means a one-time import into `work` can immediately seed later shorthand launches like `metalist work`.

### Publishing
For the real user-facing install flow:
```bash
pip install metalist
metalist
```

This repo now packages itself under the PyPI distribution name `metalist`. The remaining release step is publishing version `0.3.0` to the existing PyPI project.

Recommended release path:
1. In the existing PyPI project `metalist`, configure GitHub Trusted Publishing for `evolvingstuff/metalist3` and the workflow file `.github/workflows/publish-pypi.yml`.
2. Push a tag such as `v0.3.0`.
3. After the GitHub Actions workflow completes, users can install with `pip install metalist`.

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
