"""
Core Architecture:
- MIT licensed components only
- Python-based (pip installable or executable)
- Single user per instance (containerization planned for multi-user future)
- FastAPI backend with Pydantic models
- SQLite3 database / SQLAlchemy ORM
- Mako for server-side templating

Data Model & Storage:
- Everything is a note (no separate concept of subnotes)
- Notes can be hierarchically nested
- Notes can be embedded, copied, or linked (future)
- Each note has:
  - uuid: str
  - content: str
  - parent: Optional[str]
  - prev: Optional[str]    # For efficient sibling ordering
  - next: Optional[str]    # For efficient sibling ordering
- Must handle large numbers of notes efficiently (15,000+)
- Per-note encryption at rest
- Server-side encryption/decryption
- Searchable by content or tags or a combo of both
- Tags and other metadata parsed from note content
- Encrypted search indexes persistent across server restarts

Client-Server Communication:
- TLS for non-localhost connections
- Long-polling for updates
- Server maintains knowledge of client's current view
- Server sends minimal diffs using server-side rendering
- Initial load of 50 relevant notes + infinite scroll

Operations & Sync:
Two categories of operations:
1. Immediate operations (sent instantly):
   - Add note
   - Delete note
   - Move note
   - Change note parent

2. Polled operations (batched, sent every X ms):
   - Search updates / tag suggestions
   - Content edits (push on diff)
   - Cross-device sync

Undo/Redo:
- Server-side implementation
- Three basic operations: ADD_NOTE, UPDATE_NOTE, DELETE_NOTE
- In-memory only (doesn't survive server restart)

UI Architecture:
- Minimal JavaScript
- Server-side rendering with Mako templates
- No client-side build step
- Multiple tabs/devices supported via sync
- Editing done using `contenteditable`

The application should optimize for:
- Server-side processing
- Minimal network traffic
- Clean separation of concerns
- Simple, efficient client implementation
- Single source of truth for all relationships

"""