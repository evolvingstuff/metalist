# PLAN: References (Files + Notes)

**Goal**
Add embedded note references only (no files yet). References must flow through the existing `/api2/notes/view` snapshot+diff system so changes show up in the UI without a full refresh. UI exposure can be minimal (rendered output only) for now.

**Non-Goals**
No file references or blob storage work yet.
No graph view or global link explorer in this iteration unless explicitly requested.

**Decisions (Confirmed)**
References are parsed from note content (no dedicated references table).
Note references are created by copying a note (Cmd-C with no text selection) to put its UUID on the clipboard, then inserting a ref with Cmd-R.
Cmd-X does not create a reference.
Backlinks are deferred for now.
Everything is encrypted at rest.
Reference syntax (current draft):
- `[[UUID]]` link
- `[[UUID|display text]]` link with custom text
- `![[UUID]]` embed
- `![[UUID|caption]]` embed with caption
Cmd-R is a no-op when the clipboard does not contain a note UUID.
Embeds should render the referenced note plus its children (subtree) with a distinct background.
No jump-to-note behavior yet.

**Open Questions**
Should we support both link and embed formats now, or only embeds?
Should embeds respect the referenced note’s collapsed state or always render fully expanded?
When a UUID is searched, should the app focus the note (select/scroll) or just include it in results?

**Plan**
1. Requirements pass.
Confirm reference syntax, Cmd-R behavior, file reference creation UX, backlink toggle behavior, and file metadata encryption approach.

2. Data model design.
References live in note content (Option B) and are parsed into an in-memory index.
Document the syntax rules in `docs/` if needed.

3. Backend persistence and services.
Implement a reference parser + indexer service that can rebuild on startup and update incrementally on note create/update/delete.
Add strict validation (no Optional fields in request models).

4. Snapshot + diff integration.
Include rendered embeds (and any reference metadata if needed) in `app/services/snapshot.py` payloads.
Extend `_compute_hash` to include a stable serialization of rendered embed content so view diffs update correctly.
Update `app/services/view_diff.py` tests that assume payload shape.

5. API surface.
Update `app/static/js/modules/api-client.js` to consume reference-rendered content in `/notes/view` (no new endpoints unless needed).

6. Frontend UI + interactions.
Extend note rendering to display embedded notes parsed from content, with distinct styling.
Add Cmd-R handler to insert note references from clipboard.
Defer backlinks UI; keep minimal rendering only.

7. Tests.
Add unit tests for reference parsing/indexing + snapshot hashing.
Add focused lower-level tests for any non-trivial interaction logic.
Run `./sanitycheck/run` if present.

**Success Criteria**
Embedded note references are parsed from content, cached, and round-trip via `/notes/view` diffs without full refresh.
UI renders embedded notes with a distinct style and includes their children.

**Risks**
Snapshot hash churn if references are not serialized deterministically.
Recursive embedding needs guardrails to avoid infinite loops.
