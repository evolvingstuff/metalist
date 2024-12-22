"""
Core Architecture:
- Python-based (pip installable or executable)
- Single user per instance (containerization planned for multi-user future)
- FastAPI backend with Pydantic models
- SQLite3 database
- MIT licensed components only
- Mako for server-side templating

Data Model & Storage:
- Notes stored in an ordered linked list structure
- Per-note encryption at rest
- Server-side encryption/decryption
- Searchable by tags and text content
- Encrypted search indexes persistent across server restarts
- Must handle large numbers of notes efficiently

Client-Server Communication:
- TLS for non-localhost connections
- Long-polling for updates
- Server maintains knowledge of client's current view
- Server sends minimal diffs using server-side rendering
- Initial load of 50 relevant notes + infinite scroll

Operations & Sync:
Two categories of operations:
1. Immediate operations (sent instantly):
   - Add note/subnote
   - Paste note/subnote
   - Delete note/subnote
   - Move note/subnote

2. Polled operations (batched, sent every X ms):
   - Search updates
   - Content edits

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

Please help me implement this system, starting with setting up a FastAPI app to serve a basic webpage, using Mako as a template lib.

"""