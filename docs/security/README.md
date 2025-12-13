# Security Architecture

## Overview

This document describes the security architecture for MetaList3's password protection and note encryption system. The system uses a two-key architecture to provide strong security while maintaining good performance.

## Two-Key Encryption System

### Key Components

1. **Master Key**
   - Derived from user's password using PBKDF2-SHA256 with configurable iterations (currently 1,000,000)
   - Iteration count is stored with each password hash to allow future upgrades
   - Never stored on disk - only derived transiently during login/password change operations
   - Used solely to encrypt/decrypt the DEK
   - Not retained after unwrapping the DEK

2. **DEK (Data Encryption Key)**
   - 256-bit randomly generated AES key
   - Created once when password protection is first enabled
   - Stored in database encrypted by the Master Key
   - Used for all note encryption/decryption operations
   - Remains constant even when user changes their password

### Encryption Flow

```
Initial Password Setup:
1. User sets password
2. Password → PBKDF2 (current config iterations) → Master Key
3. Generate random 256-bit DEK
4. Encrypt DEK with Master Key → Encrypted DEK
5. Store Encrypted DEK + iteration count in database
6. Use DEK to encrypt all notes with AES-256-GCM

Login Flow:
1. User enters password
2. Retrieve stored iteration count from database
3. Password → PBKDF2 (stored iterations) → Master Key
4. Retrieve Encrypted DEK from database
5. Decrypt DEK using Master Key
6. Discard Master Key; keep only DEK in memory for session
7. Use DEK for all note operations

Password Change Flow:
1. Verify old password using stored iteration count
2. Decrypt DEK using old Master Key
3. Derive new Master Key from new password (current config iterations)
4. Re-encrypt DEK with new Master Key
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
- password_hash: PBKDF2 hash for authentication
- password_salt: Salt for password hashing
- password_iterations: PBKDF2 iteration count used for this hash
- encrypted_dek: DEK encrypted with Master Key
- dek_nonce: Nonce used for DEK encryption
- dek_tag: Authentication tag for DEK encryption
- encryption_enabled: Boolean flag
- encryption_algorithm: "AES-256-GCM"

notes table:
- content: Encrypted note content (Base64)
- nonce: Per-note nonce for AES-GCM
- tag: Per-note authentication tag

Important: if any note rows have nonce/tag set, they are encrypted and the
plaintext is unrecoverable without the DEK. If the `app_settings.encrypted_dek`
fields are cleared while encrypted notes remain, the server should refuse to
start rather than display placeholders.
```

## Security Properties

### Strengths
- **Strong Key Derivation**: Configurable PBKDF2 iterations (currently 1M) protects against brute force
- **Future-Proof**: Iteration count stored with hash allows seamless security upgrades
- **Authenticated Encryption**: AES-GCM prevents tampering and ensures integrity
- **Memory-Only Master Key**: Master Key never touches disk
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
- Each authenticated session maintains the DEK in memory (not the password or Master Key)
- DEK is tied to authentication tokens
- DEK cleared on logout or token expiry
- Server restart requires re-authentication

### Multi-Client Support
- Each client session has independent keys in memory
- Token-based authentication identifies sessions
- No key sharing between clients

### Password Requirements
- Minimum length should be enforced (recommend 12+ characters)
- Consider implementing password strength meter
- Could add checks against common password lists

## Migration Strategy

When implementing this architecture from a different system:

1. **During Password Set/Change**:
   - Generate new DEK
   - Encrypt DEK with Master Key
   - Store encrypted DEK
   - Re-encrypt all notes with DEK

2. **Backward Compatibility**:
   - Check for presence of encrypted_dek field
   - If missing, system is using old architecture
   - Trigger migration on next password operation

## API Endpoints

All endpoints except login require authentication token when password protection is enabled:

- `POST /api2/auth/login` - Authenticate and establish session
- `POST /api2/auth/logout` - Clear session and keys from memory
- `POST /api2/auth/settings/password/create` - Enable password protection
- `PUT /api2/auth/settings/password/change` - Change password (re-encrypts DEK)
- `DELETE /api2/auth/settings/password/remove` - Disable encryption
- `GET /api2/notes/*` - All note operations use cached DEK

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
