# TODO

* reenable timeout save of note content
* synch between browser windows
* search
* differential updates
  * client must send state, at least search context and settings
  * so we should probably wait until we have the API for search
* menus / dialogs
* expand / collapse
* special item rendering
* on large context changes, blow the undo/redo stack
  * use a @decorator
* Lorem Ipsum stress test
* regex vs parser for content?
  * probably regex for now 
* scrolling / infinite scrolling
  * need differential updates first
* tracking client state?
* indexing
* encryption at rest
  * need to solve indexing first 
* users / login / authentication (Google?)
  * need to solve encryption first
* tags
* "advanced" implications
* @shell functionality
* filesystem integration
* tag suggestions
* search suggestions
  * need tags first
* differential updates (per note?)
* different "view" when rendering
  * need differential updates first? 
* rich text editor?
* different sort orders (e.g. last edited)
* dark theme / colored notes or backgrounds?
* LLM integration
* select multiple notes? group ops?
* allow users to define their own key bindings?
* vim support?
* mobile support?
* allow users to define their own syntax or grammar for tags / implications?

## Architecture / Refactor

- Undo refactor: remove `app/services/store.py` adapter once NoteStore invariants are validated during undo flows (delete/move). Add targeted `note_store.debug_validate_links()` checks and migrate one Cmd at a time.
- NoteStore API: consider adding small atomic helpers for move/delete/restore to avoid call sites manipulating links indirectly via `update_metadata_from_db(rebuild=False)`.
- Utils hygiene:
  - Move `app/utils/text_utils.py` under `app/presentation/` to keep UI helpers together.
  - Remove `app/utils/encryption.py` shim once all callers use `app/security/encryption.py` directly.
- Security layout: consider moving `app/services/tokens.py` under `app/security/` for cohesion.
- Config cleanup: remove `DISABLE_UNDO_SNAPSHOT` from `app/core/config.py` once no call sites read it.
- Enforce boundaries: add a lightweight check (pre-commit or CI) to prevent `services/` importing FastAPI and `usecases/` importing `api/`.
- Docs pass: search and prune any stale references to legacy modules (e.g., removed snapshot/diff undo files).

## Copy/Paste Enhancements

- Eventually don't include tags / comments in copy/paste
