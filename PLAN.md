# In-Memory Search Cache Implementation Plan

## Overview
Implement an in-memory cache system for note content to enable search functionality while supporting encrypted-at-rest storage. Uses SQLAlchemy events to maintain cache consistency automatically.

## Implementation Steps

### 1. Create Encryption/Decryption System
- Add `ENABLE_ENCRYPTION` config parameter to control encryption on/off
- Implement `encrypt(content: str) -> str` function
  - If `ENABLE_ENCRYPTION=True`: XOR-based encryption for simulation
  - If `ENABLE_ENCRYPTION=False`: passthrough (return content unchanged)
- Implement `decrypt(encrypted_content: str) -> str` function
  - If `ENABLE_ENCRYPTION=True`: XOR-based decryption
  - If `ENABLE_ENCRYPTION=False`: passthrough (return content unchanged)
- Always call encrypt/decrypt functions regardless of config flag

### 2. Create In-Memory Cache System
- Create global in-memory cache: `_search_cache: Dict[str, str] = {}`
- Cache stores `{note_id: decrypted_content}` for fast search access
- Add cache management functions:
  - `populate_cache_from_db()` - scan all notes on startup
  - `get_cached_content(note_id: str) -> str` - retrieve from cache
  - `cache_note(note_id: str, content: str)` - add/update cache entry
  - `remove_cached_note(note_id: str)` - remove from cache

### 3. Server Startup Cache Population
- On application startup, scan through all notes in database
- Decrypt each note's content and populate the cache
- Ensures cache is ready for search operations immediately

### 4. SQLAlchemy Event Handlers for Cache Consistency
Leverage existing event system in `api_transaction.py` to maintain cache:

#### Insert Events
- Hook into `after_insert` event for `DBNote`
- When new note is created, decrypt content and add to cache
- Reuse existing `log_note_after_insert` or create parallel handler

#### Update Events  
- Hook into attribute `set` events for `DBNote.content`
- When content changes, decrypt new value and update cache
- Reuse existing `log_attribute_set` or create parallel handler

#### Delete Events
- Hook into `before_delete` event for `DBNote`
- Remove note from cache when deleted from database
- Reuse existing `log_note_before_delete` or create parallel handler

### 5. Update Database Storage
- Modify note creation/update operations to encrypt content before storing
- Database stores encrypted content, cache stores decrypted content
- Ensure all CRUD operations call encrypt() before DB writes

### 6. Update Search System to Use Cache
- **Current flow**: `/fragment` endpoint → `get_notes_fragment()` → `build_note_tree()` → `db_manager.get_ordered_child_list(db)`
- **New flow**: Replace database calls with cache lookups for note content
- **Search features to maintain**:
  - Case-insensitive substring matching using `strip_html()` on plain text
  - AND logic (all search terms must be present in note or descendants)  
  - Search highlighting with `<span class="search-highlight">` 
  - Redacted rendering for irrelevant notes (opacity 0.4, grayscale 50%)
  - Parent/child relevance marking (ancestors and descendants of matches stay visible)
- **Integration points**:
  - Modify `build_note_tree()` to get content from cache instead of database
  - Cache stores decrypted content for search operations
  - Maintain existing `raw_content` vs `content` distinction for rendering

## Benefits
- **Automatic consistency**: SQLAlchemy events ensure cache stays in sync
- **Minimal code changes**: Existing CRUD operations work unchanged  
- **Performance**: Fast in-memory search without decryption overhead
- **Flexibility**: Encryption can be toggled via config
- **Future-ready**: Easy to swap XOR simulation for real encryption

## Implementation Details
- **Start with encryption enabled**: Implement both encryption and cache together to ensure correct data flow
- **Cache scope**: ALL notes are cached in memory, no size limits or LRU eviction
- **Cache persistence**: Cache is rebuilt from database on every server restart (no persistence)
- **No monitoring**: Cache either works or fails - no metrics or monitoring needed

## Risk Mitigation  
- Event-driven approach reduces places where bugs can be introduced
- Full cache rebuild on restart ensures consistency if corruption occurs
- Starting with encryption forces correct data source validation from day one