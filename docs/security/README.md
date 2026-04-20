# Security Architecture

## Overview

This document describes the security architecture for MetaList3's password protection and note encryption system. The system uses a two-key architecture to provide strong security while maintaining good performance.

## Current Security Posture (Implemented)

- At-rest data encryption uses AES-256-GCM for note content, note tags, and ontology rules.
- Password-derived key material uses Argon2id with persisted per-vault KDF profile metadata (`vault_version=3`, `kdf_algorithm=ARGON2ID`, memory + parallelism fields).
- `/api2/auth/login` is rate-limited (keyed by client IP, with `x-forwarded-for` first-hop support).
- Runtime hardening runs at startup:
  - core dumps disabled on POSIX
  - optional macOS checks for encrypted swap and no RAM-to-disk hibernation behavior.
- Before any namespace restart/launch work, `main.py` also runs source-level startup sanity gates:
  - Python AST/default/transaction-route rules
  - JS tree-sitter sanity rules for `try/catch`, default params, destructuring defaults, and defaulting operators.
- Password policy is intentionally permissive in current dev mode (see "Password Requirements").

## Two-Key Encryption System

### Key Components

1. **KEK (Key Encryption Key)**
   - Derived from user's password using Argon2id with configurable time-cost (currently 3)
   - Uses a dedicated `kek_salt` (distinct from the auth verifier salt)
   - Never stored on disk - only derived transiently during login/password change operations
   - Used solely to encrypt/decrypt the DEK
   - Not retained after unwrapping the DEK

2. **Auth Verifier**
   - Used only to verify a password attempt during login
   - Computed as `Argon2id(password, auth_salt, auth_iterations)` and stored in the DB
   - Uses a dedicated `auth_salt` (distinct from `kek_salt`)
   - Provides a password guessing target (expected) but is not usable for unwrapping the DEK

3. **DEK (Data Encryption Key)**
   - 256-bit randomly generated AES key
   - Created once when password protection is first enabled
   - Stored in database encrypted by the KEK
   - Used for all note encryption/decryption operations
   - Remains constant even when user changes their password

4. **Vault Metadata**
   - `vault_version` defines the wrapped-key format (current: `3`)
   - `kdf_algorithm` defines password KDF profile (current: `ARGON2ID`)
   - When encryption is enabled, these fields are required and enforced

### Encryption Flow

```
Initial Password Setup:
1. User sets password
2. Password → Argon2id (current config time-cost) → KEK
3. Generate random 256-bit DEK
4. Encrypt DEK with KEK → Encrypted DEK
5. Store Encrypted DEK + Argon2id cost metadata in database
6. Use DEK to encrypt all notes with AES-256-GCM

Login Flow:
1. User enters password
2. Verify password via Auth Verifier (auth_salt + auth_iterations)
3. Derive KEK (kek_salt + kek_iterations)
4. Retrieve Encrypted DEK from database
5. Decrypt DEK using KEK
6. Discard KEK; keep only DEK in memory for session
7. Use DEK for all note operations
8. If the server started with encryption enabled, cache + note-store hydration is deferred.
   - The client calls `/api2/auth/hydrate` after login.
   - A progress UI is shown while the cache + note store are populated.

Password Change Flow:
1. Verify old password using stored Argon2id time-cost
2. Decrypt DEK using old KEK
3. Derive new KEK from new password (current config time-cost)
4. Re-encrypt DEK with new KEK
5. Store newly encrypted DEK + new Argon2id cost metadata in database
6. Notes remain unchanged (still encrypted with same DEK)
```

### Performance Benefits

- **Login**: One expensive Argon2id operation (stored time-cost)
- **Note Operations**: Fast AES-256-GCM encryption/decryption using cached DEK
- **Bulk Operations**: No KDF work per note, just fast AES operations
- **Password Changes**: Only need to re-encrypt the DEK, not all notes
- **Cost Upgrades**: Automatic upgrade to stronger Argon2id costs on password changes

## Cryptographic Details

### Argon2id Configuration
- **Algorithm**: Argon2id
- **Time Cost**: Configurable (currently 3), stored per password hash
- **Memory Cost**: 65,536 KiB
- **Parallelism**: 4
- **Salt**: 32 bytes, randomly generated per password
- **Output**: 256-bit key

### AES-256-GCM Configuration
- **Key Size**: 256 bits (from DEK)
- **Nonce**: 96 bits, randomly generated per encryption
- **Tag**: 128 bits for authentication
- **Mode**: Galois/Counter Mode (GCM) for authenticated encryption

### Database Storage

```sql
app_settings table:
- auth_verifier: Argon2id-based password verifier (not a KEK)
- auth_salt: Salt for auth verifier
- auth_iterations: Argon2id time-cost for auth verifier
- kek_salt: Salt for KEK derivation
- kek_iterations: Argon2id time-cost for KEK derivation
- vault_version: Wrapped-key vault format version (required when encrypted)
- kdf_algorithm: Password KDF profile name (required when encrypted)
- kdf_memory_cost_kib: Argon2id memory-cost parameter persisted per vault
- kdf_parallelism: Argon2id parallelism parameter persisted per vault
- encrypted_dek: DEK encrypted with KEK
- dek_nonce: Nonce used for DEK encryption
- dek_tag: Authentication tag for DEK encryption
- encryption_enabled: Boolean flag
- encryption_algorithm: "AES-256-GCM"

notes table:
- content: Encrypted note content (Base64)
- encryption_nonce: Per-note nonce for AES-GCM
- encryption_tag: Per-note authentication tag
- tags: Encrypted note tags (Base64)
- tags_encryption_nonce: Tags nonce for AES-GCM
- tags_encryption_tag: Tags authentication tag

ontology_rules table:
- rule_text: Encrypted rule text (Base64) when password protection is enabled
- rule_encryption_nonce: Per-rule nonce for AES-GCM
- rule_encryption_tag: Per-rule authentication tag

Important: if any note rows have `encryption_nonce/encryption_tag` (content)
or `tags_encryption_nonce/tags_encryption_tag` (tags) set, that field is
encrypted and unrecoverable without the DEK. The same applies to ontology rule
rows with `rule_encryption_nonce/rule_encryption_tag`. If the
`app_settings.encrypted_dek` fields are cleared while encrypted rows remain,
the server should refuse to start rather than display placeholders. When
password protection is enabled, new rule writes must be encrypted (no plaintext
writes).
```

## Security Properties

### Strengths
- **Strong Key Derivation**: Memory-hard Argon2id protects against brute force
- **Future-Proof**: Stored KDF cost allows seamless security upgrades
- **Authenticated Encryption**: AES-GCM prevents tampering and ensures integrity
- **Memory-Only KEK**: KEK never touches disk
- **Unique Nonces**: Each encryption uses a fresh random nonce
- **Defense in Depth**: Multiple layers (auth + encryption)

### Threat Model

**Protected Against:**
- Database theft (encrypted notes, strong Argon2id)
- Brute force attacks (configurable KDF costs)
- Tampering (GCM authentication)
- Rainbow tables (random salts)
- Replay attacks (unique nonces)
- Security obsolescence (upgradeable KDF costs)

**Not Protected Against:**
- Memory dumps while server is running (keys in RAM)
- Malicious server administrator (has access to memory)
- Weak passwords (use password strength requirements)
- Client-side attacks (assumes secure client)

## Implementation Notes

### Session Management
- Each authenticated session maintains the DEK in memory (not the password or KEK)
- DEK is tied to authentication tokens
- DEK cleared on logout or token expiry
- Server restart requires re-authentication

### Mutation Transaction Enforcement
- Mutating FastAPI routes are expected to use `@transactional_route`.
- Startup sanity rejects mutation endpoints that omit the decorator or place it in the wrong order.
- Request-scoped writer sessions are reused across the wrapped route path so the commit happens once at the end of the request, not in intermediate steps.

### Runtime Memory Safeguards
- Core dumps are disabled at process startup (`RLIMIT_CORE=0`) on POSIX systems.
- On macOS, startup hardening checks can enforce:
  - no hibernation-to-disk behavior (`hibernatemode=0`, `standby=0`, `autopoweroff=0`)
  - swap reported as encrypted by the OS (`sysctl vm.swapusage` includes `(encrypted)`).
- These checks fail startup when enabled and not satisfied.
- Environment toggles:
  - `SECURITY_HARDENING_ENABLED`
  - `SECURITY_REQUIRE_MACOS_NO_HIBERNATION`
  - `SECURITY_REQUIRE_ENCRYPTED_SWAP`
- Default behavior:
  - core dump disabling enabled by default
  - macOS hibernation/swap enforcement disabled by default (enable explicitly for strict mode).

## Remote Access / HTTPS

- Plain `python main.py` from a source checkout now restarts already-running namespaces from the current checkout, launches stopped namespaces with their saved/default profiles, prints their URLs, and exits.
- `python main.py --namespace work` starts a separate process against `~/MetaList/namespaces/work/work.metalist.db`.
- After a namespace has been launched once with explicit ports, `python main.py work` reuses that namespace's remembered HTTP / HTTPS / MCP sidecar ports from `~/MetaList/namespaces.db`.
- With no explicit namespace on a single-namespace launch, the default namespace DB is `~/MetaList/namespaces/default/default.metalist.db`.
- Deleting a namespace removes both its saved launch profile from `~/MetaList/namespaces.db` and its namespace directory on disk, including the namespace SQLite databases and backups under `~/MetaList/namespaces/<namespace>/`.
- HTTPS is opt-in via existing PEM files at `certs/metalist-cert.pem` and `certs/metalist-key.pem`, or explicit `METALIST_TLS_CERT` and `METALIST_TLS_KEY`.
- When those PEMs exist, MetaList also starts `0.0.0.0:8443` and redirects non-loopback HTTP hostnames to HTTPS.
- For direct HTTPS from an explicit single-namespace `python main.py ...` run, set both:
  - `METALIST_TLS_CERT=/path/to/fullchain.pem`
  - `METALIST_TLS_KEY=/path/to/privkey.pem`
- For a quick LAN cert, use `./scripts/generate-lan-cert.sh` and then open `https://<lan-ip>:8443` from the other machine.
- For HTTPS terminated by a reverse proxy, keep MetaList on loopback and trust forwarded headers only from the proxy IPs:
  - `METALIST_HOST=127.0.0.1`
  - `METALIST_FORWARDED_ALLOW_IPS=127.0.0.1,::1` (default)
- Login rate limiting already prefers the first `x-forwarded-for` hop, so when you deploy behind a trusted proxy you still get client-IP-based throttling.
- Namespace selection is independent of listener ports. Use `--namespace` / `METALIST_NAMESPACE` for DB selection and `--port` / `METALIST_PORT` for listener selection.
- Listener precedence is explicit CLI flags > env vars > saved namespace profile in `~/MetaList/namespaces.db` > built-in defaults.
- The MCP sidecar redirect now supports a public override via `MCP_AGENT_PUBLIC_ORIGIN=https://host:port`. If you are not exposing the sidecar remotely, disable it with `MCP_AGENT_WEB_ENABLED=0`.
- When `main.py` auto-starts the MCP sidecar, its default MCP URL now follows the resolved MetaList HTTP port for that process.
- If multiple MetaList processes auto-start sidecars on the same machine, use `--mcp-port` or `MCP_AGENT_WEB_PORT` to avoid sidecar port collisions.

### Multi-Client Support
- Token issuance clears any previous tokens (single active session enforced)
- Token verification is bound to an `X-Metalist-Tab-Id` owner (tab-scoped sessions)
- DEK is stored in memory alongside the active token; no DEK is persisted to disk

### Login Rate Limiting
- Enforced on `POST /api2/auth/login` before password verification.
- Default configuration:
  - `LOGIN_RATE_LIMIT_MAX_ATTEMPTS=5`
  - `LOGIN_RATE_LIMIT_WINDOW_SECONDS=300`
  - `LOGIN_RATE_LIMIT_BLOCK_SECONDS=300`
- Keying strategy:
  - first `x-forwarded-for` hop when present
  - fallback to direct client IP
  - fallback to user-agent prefix when IP is unavailable.

### Password Requirements
- Current enforced rule: password length must be `> 3` characters.
- This is intentionally permissive for development convenience.
- For production hardening, enforce stricter server-side requirements:
  - minimum length (e.g., 12+)
  - complexity rules
  - common/breached-password rejection.

## Data Import Strategy

For fresh imports using `convert-from-legacy.py`:

1. This is a destructive fresh-import path (existing DB is deleted first).
2. Import plaintext legacy data into a new SQLite database.
3. Optionally set a password at import time.
4. Password enablement writes the same vault metadata (`vault_version`, `kdf_algorithm`)
   and KDF parameters used by the runtime auth service.
5. Input selection:
   - pass `--input /path/to/export.json` for non-interactive runs
   - omit `--input` to use the Tk file picker.
6. Namespace targeting:
   - pass `--namespace work` to import into `~/MetaList/namespaces/work/work.metalist.db`
   - omit `--namespace` to import into `~/MetaList/namespaces/default/default.metalist.db`.
7. Launch profile prompting:
   - if `--namespace`, `--port`, `--https-port`, or `--mcp-port` are omitted, the importer prompts for them
   - the chosen ports are saved in `~/MetaList/namespaces.db` so later `python main.py work` can reuse them.

## API Endpoints

When password protection is enabled, requests must include:
- `Authorization: Bearer <token>`
- `X-Metalist-Tab-Id: <uuid>` (required by auth/token verification)

Auth:
- `POST /api2/auth/login` - Authenticate and establish session
- `POST /api2/auth/logout` - Revoke token and clear in-memory keys
- `POST /api2/auth/session` - Claim passwordless session (only when no password is set)
- `GET /api2/auth/status` - Poll auth/encryption status
- `POST /api2/auth/namespaces/delete-current` - Delete the active non-default namespace after typed confirmation and, when enabled, password re-entry. The tab moves to a dedicated namespace-removal status page while a detached worker shuts down the current namespace and deletes its directory and saved launch profile.
- `POST /api2/auth/settings/password/create` - Enable password protection
- `PUT /api2/auth/settings/password/change` - Change password (re-encrypts DEK)
- `DELETE /api2/auth/settings/password/remove` - Disable encryption
- `GET /api2/auth/sessions` - List active session(s)

Backup:
- `GET /api2/backup/settings` - Read backup destination settings
- `PUT /api2/backup/settings` - Update the configured backup folder, selected namespaces, and per-namespace retention count
- `GET /api2/backup/list` - List available configured-folder backup snapshots
- `POST /api2/backup/run` - Create one versioned workspace archive snapshot and write it to the enabled destination(s)
- `POST /api2/backup/restore` - Restore the selected folder archive snapshot and trigger the usual post-restore runtime reset/restart flow
  - Backup scope follows the active DB path, so namespaced runs use `~/MetaList/namespaces/<namespace>/backups/` and write one versioned archive per snapshot, for example `cla-<timestamp>.metalist-backup.tar.gz`. Legacy `.bak` snapshots remain restorable.
  - Backup settings are stored per namespace; when namespace encryption is enabled, that settings payload is encrypted at rest too.
  - Manual backup runs now target one selected folder and can include multiple namespaces in the same run.
- `POST /api2/backup/folder/pick` - Open the native folder picker and return the selected absolute backup path

Notes:
- `POST /api2/notes/view`
- `POST /api2/notes/new`
- `POST /api2/notes/new-sibling/{note_id}`
- `POST /api2/notes/new-child/{note_id}`
- `PUT /api2/notes/{note_id}`
- `PUT /api2/notes/{note_id}/save`
- `POST /api2/notes/{note_id}/move`
- `POST /api2/notes/{note_id}/collapse`
- `POST /api2/notes/{note_id}/expand`
- `DELETE /api2/notes/{note_id}`
- `POST /api2/notes/{note_id}/copy`
- `POST /api2/notes/paste-sibling/{target_note_id}`
- `POST /api2/notes/paste-child/{target_note_id}`
- `POST /api2/notes/edit-mode`
- `POST /api2/notes/undo`
- `POST /api2/notes/redo`

Memory:
- `POST /api2/memory`

## Monitoring and Logging

### Should Log:
- Authentication attempts (success/failure)
- Login rate-limit blocks (key + retry delay, no secrets)
- Password change events
- Session creation/destruction
- Encryption system enable/disable

### Should NOT Log:
- Passwords or keys
- Decrypted note content
- Token values
- Salt or nonce values

## Future Enhancements

- **Advanced UI Controls**: Add UI option to customize Argon2id time-cost during password changes
  - Toggle for "Advanced Settings" in password change modal
  - Input field for custom time-cost with validation (1 - 10 range)
  - Real-time estimate of login delay impact
  - Default to current config value but allow override
- **Key Rotation**: Periodically generate new DEK and re-encrypt notes
- **Hardware Security Module (HSM)**: Store DEK in HSM for additional protection
- **Client-Side Encryption**: End-to-end encryption with client-side keys
- **Multi-Factor Authentication**: Additional authentication layer
