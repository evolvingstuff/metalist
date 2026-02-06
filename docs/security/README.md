# Security Architecture

## Overview

This document describes the security architecture for MetaList3's password protection and note encryption system. The system uses a two-key architecture to provide strong security while maintaining good performance.

## Two-Key Encryption System

### Key Components

1. **KEK (Key Encryption Key)**
   - Derived from user's password using PBKDF2-SHA256 with configurable iterations (currently 1,000,000)
   - Uses a dedicated `kek_salt` (distinct from the auth verifier salt)
   - Never stored on disk - only derived transiently during login/password change operations
   - Used solely to encrypt/decrypt the DEK
   - Not retained after unwrapping the DEK

2. **Auth Verifier**
   - Used only to verify a password attempt during login
   - Computed as `PBKDF2(password, auth_salt, auth_iterations)` and stored in the DB
   - Uses a dedicated `auth_salt` (distinct from `kek_salt`)
   - Provides a password guessing target (expected) but is not usable for unwrapping the DEK

3. **DEK (Data Encryption Key)**
   - 256-bit randomly generated AES key
   - Created once when password protection is first enabled
   - Stored in database encrypted by the KEK
   - Used for all note encryption/decryption operations
   - Remains constant even when user changes their password

### Encryption Flow

```
Initial Password Setup:
1. User sets password
2. Password → PBKDF2 (current config iterations) → KEK
3. Generate random 256-bit DEK
4. Encrypt DEK with KEK → Encrypted DEK
5. Store Encrypted DEK + iteration count in database
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
1. Verify old password using stored iteration count
2. Decrypt DEK using old KEK
3. Derive new KEK from new password (current config iterations)
4. Re-encrypt DEK with new KEK
5. Store newly encrypted DEK + new iteration count in database
6. Notes remain unchanged (still encrypted with same DEK)
```

### Performance Benefits

- **Login**: One expensive PBKDF2 operation (stored iteration count)
- **Note Operations**: Fast AES-256-GCM encryption/decryption using cached DEK
- **Bulk Operations**: No PBKDF2 iterations per note, just fast AES operations
- **Password Changes**: Only need to re-encrypt the DEK, not all notes
- **Iteration Upgrades**: Automatic upgrade to stronger iterations on password changes

## Cryptographic Details

### PBKDF2 Configuration
- **Algorithm**: PBKDF2-HMAC-SHA256
- **Iterations**: Configurable (currently 1,000,000), stored per password hash
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
- auth_verifier: PBKDF2-based password verifier (not a KEK)
- auth_salt: Salt for auth verifier
- auth_iterations: PBKDF2 iteration count for auth verifier
- kek_salt: Salt for KEK derivation
- kek_iterations: PBKDF2 iteration count for KEK derivation
- encrypted_dek: DEK encrypted with KEK
- dek_nonce: Nonce used for DEK encryption
- dek_tag: Authentication tag for DEK encryption
- encryption_enabled: Boolean flag
- encryption_algorithm: "AES-256-GCM"

Legacy fields (migrated/cleared on successful login):
- password_hash, password_salt, password_iterations

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
- **Strong Key Derivation**: Configurable PBKDF2 iterations (currently 1M) protects against brute force
- **Future-Proof**: Iteration count stored with hash allows seamless security upgrades
- **Authenticated Encryption**: AES-GCM prevents tampering and ensures integrity
- **Memory-Only KEK**: KEK never touches disk
- **Unique Nonces**: Each encryption uses a fresh random nonce
- **Defense in Depth**: Multiple layers (auth + encryption)

### Threat Model

**Protected Against:**
- Database theft (encrypted notes, strong PBKDF2)
- Brute force attacks (configurable high iteration count)
- Tampering (GCM authentication)
- Rainbow tables (random salts)
- Replay attacks (unique nonces)
- Security obsolescence (upgradeable iterations)

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

### Multi-Client Support
- Token issuance clears any previous tokens (single active session enforced)
- Token verification is bound to an `X-Metalist-Tab-Id` owner (tab-scoped sessions)
- DEK is stored in memory alongside the active token; no DEK is persisted to disk

### Password Requirements
- Minimum length should be enforced (recommend 12+ characters)
- Consider implementing password strength meter
- Could add checks against common password lists

## Migration Strategy

When implementing this architecture from a different system:

1. **During Password Set/Change**:
   - Generate new DEK
   - Encrypt DEK with KEK
   - Store encrypted DEK
   - Re-encrypt all notes with DEK

2. **Backward Compatibility**:
   - Check for presence of encrypted_dek field
   - If missing, system is using old architecture
   - Trigger migration on next password operation

## API Endpoints

When password protection is enabled, requests must include:
- `Authorization: Bearer <token>`
- `X-Metalist-Tab-Id: <uuid>` (required by auth/token verification)

Auth:
- `POST /api2/auth/login` - Authenticate and establish session
- `POST /api2/auth/logout` - Revoke token and clear in-memory keys
- `POST /api2/auth/session` - Claim passwordless session (only when no password is set)
- `GET /api2/auth/status` - Poll auth/encryption status
- `POST /api2/auth/settings/password/create` - Enable password protection
- `PUT /api2/auth/settings/password/change` - Change password (re-encrypts DEK)
- `DELETE /api2/auth/settings/password/remove` - Disable encryption
- `GET /api2/auth/sessions` - List active session(s)

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
- Password change events
- Session creation/destruction
- Encryption system enable/disable

### Should NOT Log:
- Passwords or keys
- Decrypted note content
- Token values
- Salt or nonce values

## Future Enhancements

- **Advanced UI Controls**: Add UI option to customize PBKDF2 iterations during password changes
  - Toggle for "Advanced Settings" in password change modal
  - Input field for custom iteration count with validation (100k - 10M range)
  - Real-time estimate of login delay impact
  - Default to current config value but allow override
- **Key Rotation**: Periodically generate new DEK and re-encrypt notes
- **Hardware Security Module (HSM)**: Store DEK in HSM for additional protection
- **Client-Side Encryption**: End-to-end encryption with client-side keys
- **Multi-Factor Authentication**: Additional authentication layer
- **Argon2**: Consider upgrading from PBKDF2 to Argon2id for better resistance against GPU attacks
