# XOR Encryption Implementation Plan

## Overview
Add XOR encryption to simulate future encryption at rest while maintaining a plaintext cache in memory for fast operations. Use clear naming conventions throughout.

## Naming Convention
- `content_enc` = encrypted content (stored in database)
- `content_dec` = decrypted/plaintext content (in memory/cache)
- `raw_content_dec` = raw decrypted content (for search operations)

## Core Architecture

### 1. ContentCache Service
**File**: `app/services/content_cache.py`
- Singleton service managing encryption/decryption and plaintext cache
- `cache: Dict[str, str]` mapping note_id → content_dec
- Simple XOR function (symmetric encryption/decryption)
- Methods:
  - `create(note_id: str, content_dec: str) -> str` - encrypt for DB, cache plaintext, FAIL HARD if note_id already exists
  - `retrieve(note_id: str) -> str` - get from cache, FAIL HARD if cache miss
  - `update(note_id: str, content_dec: str) -> str` - encrypt for DB, update cache, FAIL HARD if note_id not in cache
  - `delete(note_id: str)` - remove from cache, FAIL HARD if note_id not in cache
  - `init_cache(db)` - populate cache from DB on startup
  - `encrypt(content_dec: str) -> str` - internal XOR function (for now)
  - `decrypt(content_enc: str) -> str` - internal XOR function (for now)

### 2. Database Schema Changes
**File**: `app/models/database.py`
- Change `content` field to `content_enc` in DBNote class
- Update event listener tracking in `api_transaction.py`

### 3. CRUD Layer Updates
**File**: `app/models/note_crud.py`
- Import ContentCache service
- `create_note_top()`: Use `cache.encrypt(note_id, "")` for new notes
- `update_note()`: Change signature to `content_dec: str`, use `cache.encrypt()`
- `delete_note()`: Call `cache.remove()` for deleted notes and descendants

### 4. Rendering Layer Updates
**File**: `app/render/note_renderer.py`
- Import ContentCache service
- `build_note_tree()`: Get `content_dec = cache.decrypt(note.id, note.content_enc)`
- Update render functions to take `content_dec` parameter
- Change `raw_content` to `raw_content_dec` in note_dict
- Pass decrypted content to all render modes

### 5. Copy Operations
**File**: `app/models/utils.py`
- Import ContentCache service
- `_copy_note_recursive()`: Decrypt source content, encrypt for new note ID
- Ensure cache is updated for copied notes

### 6. Undo/Redo (Simple Approach)
**Files**: `app/undo_redo.py`, `app/models/api_transaction.py`
- Keep existing logic - store encrypted content_enc in command states
- Update field references from `content` to `content_enc`
- In `_create_note_in_db()` and `_update_note_in_db()`: Update cache when restoring
- In `_delete_note_from_db()`: Remove from cache

### 7. Startup Initialization
**File**: `app/main.py`
- Add startup event handler
- Call `cache.init_cache(db)` to populate cache from database
- Add debug logging showing encrypted → decrypted content

### 8. Config Flag
**File**: `app/core/config.py`
- Add `USE_XOR_ENCRYPTION = True` flag
- XOR function respects this flag

## Implementation Order
1. Add config flag
2. Create ContentCache service
3. Update database schema (content → content_enc)
4. Update CRUD operations
5. Update rendering layer
6. Update undo/redo field references and cache updates
7. Update copy operations
8. Add startup initialization
9. Test all operations

## Key Principles
1. **Minimal Changes**: Only touch files that directly handle content
2. **Clear Boundaries**: Database always has content_enc, memory operations use content_dec
3. **Cache Consistency**: Always update cache when content changes
4. **Simple Undo/Redo**: Store encrypted states, update cache on restore
5. **Backwards Compatibility**: Frontend still gets `content` field (which is rendered decrypted content)

## Testing Checklist
- [ ] Note creation works
- [ ] Note updates work
- [ ] Note deletion works and cleans cache
- [ ] Copy/paste operations work
- [ ] Search operations work with decrypted content
- [ ] Undo/redo works correctly
- [ ] Startup shows encrypted → decrypted debug logs
- [ ] Frontend rendering works normally

## Files to Modify
- `app/core/config.py` - Add flag
- `app/services/content_cache.py` - New service
- `app/models/database.py` - Schema change
- `app/models/note_crud.py` - CRUD operations
- `app/models/utils.py` - Copy operations
- `app/render/note_renderer.py` - Rendering
- `app/undo_redo.py` - Field name updates
- `app/models/api_transaction.py` - Event listener updates
- `app/main.py` - Startup initialization

## Risk Mitigation
- Test each component incrementally
- Keep existing DB logic unchanged (just field names)
- Maintain existing API contracts
- Use simple, symmetric XOR for testing
- Clear variable naming prevents confusion