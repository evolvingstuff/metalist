# Security Architecture

## Overview

This document describes the security architecture for MetaList3's password protection and note encryption system. The system uses a two-key architecture to provide strong security while maintaining good performance.

## Two-Key Encryption System

### Key Components

1. **Master Key**
   - Derived from user's password using PBKDF2-SHA256 with 250,000 iterations
   - Never stored on disk - only exists in server memory during active sessions
   - Used solely to encrypt/decrypt the DEK
   - Cleared from memory on logout or session expiry

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
2. Password → PBKDF2 (250k iterations) → Master Key
3. Generate random 256-bit DEK
4. Encrypt DEK with Master Key → Encrypted DEK
5. Store Encrypted DEK in database
6. Use DEK to encrypt all notes with AES-256-GCM

Login Flow:
1. User enters password
2. Password → PBKDF2 (250k iterations) → Master Key
3. Retrieve Encrypted DEK from database
4. Decrypt DEK using Master Key
5. Keep both keys in memory for session
6. Use DEK for all note operations

Password Change Flow:
1. Verify old password and derive old Master Key
2. Decrypt DEK using old Master Key
3. Derive new Master Key from new password (250k iterations)
4. Re-encrypt DEK with new Master Key
5. Store newly encrypted DEK in database
6. Notes remain unchanged (still encrypted with same DEK)
```

### Performance Benefits

- **Login**: One expensive PBKDF2 operation (250k iterations)
- **Note Operations**: Fast AES-256-GCM encryption/decryption using cached DEK
- **Bulk Operations**: No PBKDF2 iterations per note, just fast AES operations
- **Password Changes**: Only need to re-encrypt the DEK, not all notes

## Cryptographic Details

### PBKDF2 Configuration
- **Algorithm**: PBKDF2-HMAC-SHA256
- **Iterations**: 250,000 for Master Key derivation
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
- password_hash: PBKDF2 hash for authentication (250k iterations)
- password_salt: Salt for password hashing
- encrypted_dek: DEK encrypted with Master Key
- dek_nonce: Nonce used for DEK encryption
- dek_tag: Authentication tag for DEK encryption
- encryption_enabled: Boolean flag
- encryption_algorithm: "AES-256-GCM"

notes table:
- content: Encrypted note content (Base64)
- nonce: Per-note nonce for AES-GCM
- tag: Per-note authentication tag
```

## Security Properties

### Strengths
- **Strong Key Derivation**: 250,000 PBKDF2 iterations protects against brute force
- **Authenticated Encryption**: AES-GCM prevents tampering and ensures integrity
- **Memory-Only Master Key**: Master Key never touches disk
- **Unique Nonces**: Each encryption uses a fresh random nonce
- **Defense in Depth**: Multiple layers (auth + encryption)

### Threat Model

**Protected Against:**
- Database theft (encrypted notes, strong PBKDF2)
- Brute force attacks (250k iterations)
- Tampering (GCM authentication)
- Rainbow tables (random salts)
- Replay attacks (unique nonces)

**Not Protected Against:**
- Memory dumps while server is running (keys in RAM)
- Malicious server administrator (has access to memory)
- Weak passwords (use password strength requirements)
- Client-side attacks (assumes secure client)

## Implementation Notes

### Session Management
- Each authenticated session maintains its own Master Key and DEK in memory
- Keys are tied to authentication tokens
- Keys cleared on logout or token expiry
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

- `POST /api/auth/login` - Authenticate and establish session
- `POST /api/auth/logout` - Clear session and keys from memory
- `POST /api/auth/settings/password/create` - Enable password protection
- `PUT /api/auth/settings/password/change` - Change password (re-encrypts DEK)
- `DELETE /api/auth/settings/password/remove` - Disable encryption
- `GET /api/notes/*` - All note operations use cached DEK

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

- **Key Rotation**: Periodically generate new DEK and re-encrypt notes
- **Hardware Security Module (HSM)**: Store DEK in HSM for additional protection
- **Client-Side Encryption**: End-to-end encryption with client-side keys
- **Multi-Factor Authentication**: Additional authentication layer
- **Argon2**: Consider upgrading from PBKDF2 to Argon2id for better resistance against GPU attacks