"""
Core Architecture:
- Python-based (pip installable or executable)
- Single user per instance (containerization planned for multi-user future)
- FastAPI backend with Pydantic models
- SQLite3 database
- MIT licensed components only
- Mako for server-side templating

Data Model & Storage:
- Notes stored as "items" in an ordered linked list structure
- Per-item encryption at rest
- Server-side encryption/decryption
- Searchable by tags and text content
- Encrypted search indexes persistent across server restarts
- Must handle large numbers of items efficiently

Client-Server Communication:
- TLS for non-localhost connections
- Long-polling for updates
- Server maintains knowledge of each client's current view
- Server sends minimal diffs using server-side rendering
- Initial load of 50 relevant items + infinite scroll

Operations & Sync:
Two categories of operations:
1. Immediate operations (sent instantly):
   - Add item/subitem
   - Paste item/subitem
   - Delete item/subitem
   - Move item/subitem

2. Polled operations (batched, sent every X ms):
   - Search updates
   - Content edits

Undo/Redo:
- Server-side implementation
- Three basic operations: ADD_ITEM, UPDATE_ITEM, DELETE_ITEM
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