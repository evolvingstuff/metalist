# Note App Controls

## Keyboard Shortcuts

### When Editing a Note
| Shortcut | Action |
|----------|--------|
| `Esc` | Exit edit mode for current note |
| `Tab` | Toggle focus between note content and tag bar (restores cursor position) |
| `⌘ + Enter` | Add new sibling note below current note |
| `⇧ + ⌘ + Enter` | Add new child note under current note |
| `⌘ + ←` | Outdent note (one level left) |
| `⌘ + →` | Indent note (one level right) |
| `⌘ + ↑` | Move current note up (one visible sibling) |
| `⇧ + ⌘ + ↑` | Move the selected root note to the top of the current root view (including filtered/search views), or move a child note to the top of its siblings |
| `⌘ + ↓` | Move current note down (one visible sibling) |
| `⌘ + P` | Save + exit edit mode, then open password modal |
| `⌘ + C` | Copy selection (default), or copy whole note when no selection |
| `⌘ + R` | Copy as embedded reference for the most recently copied note UUID |
| `⌘ + S` | Split note at selection/caret into sibling notes; selected segment becomes its own note |
| `⌘ + U` | Unformat current note content (strip rich formatting but keep links and images) |
| `⌘ + X` | Cut selection (default), or cut whole note when no selection |
| `⌘ + V` | Paste note as sibling (when note clipboard active; scrolls new note into view). If the selected note has no visible content and no children, paste replaces it. |
| `⇧ + ⌘ + V` | Paste note as child (when note clipboard active; scrolls new note into view) |

- If note clipboard conditions are **not** met and edit mode is active, `⌘ + V` uses browser clipboard paste and runs external HTML sanitization before insertion.
- When note paste replaces an empty target, the target keeps its search-context tags and merges in copied root tags with case-insensitive dedupe.
- If the clipboard value came from `Generate random password…`, pasting into an empty note also adds `@password` automatically when that tag is not already present.
- See `docs/ui/paste-sanitization.md` for the full policy.
- `⌘ + R` inserts the reference token on its own line; if the caret is mid-line, the line is split around the inserted token.
- `⌘ + R` avoids adding a synthetic extra blank line when caret is already on an empty line.
- See `docs/ui/references.md` for full reference behavior.
- `⌘ + S` splits the current editing note at the caret or selection; a caret at the front creates a blank note above, and a caret at the end creates a blank note below.
- `⌘ + S` no-ops when the entire note is selected or when split would produce no content segment.
- `⌘ + S` trims selection-edge empty nodes/whitespace so generated split notes do not get a synthetic leading blank line.
- `⌘ + S` records the full split as one undo/redo step.
- `⌘ + U` rewrites the note's stored content HTML into plain HTML, removing inline/block formatting wrappers while preserving links and images.
- `⌘ + U` does not remove meta-tags like `@bold`, `@todo`, or any other tag-bar formatting tags.
- `⇧ + ⌘ + ↑` is server-authoritative: for filtered/search views it inserts the root note at the top of the visible root view without corrupting the underlying root-order links.
- In any non-normal sort order, root-note reordering is disabled for drag/drop, `⌘ + ↑`, `⌘ + ↓`, and `⇧ + ⌘ + ↑`. Child-note reordering still works.
- While the single-note tag bar is focused, note-level edit shortcuts still target the current note: create sibling/child, delete, move up/down, move to top, indent/outdent, split, unformat, note copy/cut/paste, and password modal.

### General Shortcuts
| Shortcut | Action |
|----------|--------|
| `Enter` | Add new note at top (when not editing) |
| `Space` | Toggle collapse/expand hovered note |
| `⌘ + /` | Open command palette |
| `Tab` | Focus the search input and select its full query (view mode only) |
| `?` | Open keyboard shortcuts help (idle mode) |
| `M` | Open memory/search contexts (idle mode) |
| `⌘ + ;` | Open tag relationships editor |
| `⌘ + Z` | Undo |
| `⌘ + Y` | Redo |

- When a non-normal sort mode is active, a floating pill above the sticky top bar shows the active mode and includes an `×` to return to normal sorting without reopening the command palette.
- The memory/search contexts overlay is pinned to the lower-left on all screen sizes. The backlinks panel follows that placement so the two overlays stay grouped.

### Search Input Behavior
- Pressing `Enter` while focused in the search input creates a new **root** note.
- Pressing `Esc` while focused in the search input blurs the field and dismisses search suggestions, without clearing the current query or search results.
- If the search query contains required tag terms (unquoted tokens like `asdf`), the new root note is created with those tags in its tag bar.
- When creating a child (`⇧ + ⌘ + Enter`) or sibling (`⌘ + Enter`) note under a note that already provides the required **non-meta** tags via inheritance, the new note is **not** redundantly tagged.
- Sort modes do not change canonical insertion behavior. New roots are still inserted into the manual root order first, then rendered in the active sort order.

### Search Suggestions
- Suggestions are **tag-only** (no text suggestions).
- For a blank search or the first tag prefix in a query, up to the top 3 suggestion slots are reserved for matching tags with the strongest recent interaction scores in the current namespace.
- Case-equivalent tags are collapsed in the suggestion list, and the most-used spelling is shown.
- A successful non-empty search execution counts toward that recent-tag weighting when it has matching results.
- Adding a new non-meta tag to a note also counts for that tag after the note is saved.
- Later server-backed interactions in an active searched result set also count, including toggling todo/done, creating, moving, collapsing/expanding, saving, deleting, or entering edit mode on notes.
- Scrolling can also qualify once it triggers the persisted tab-state server write while that search is active.
- Recency weighting uses event-based exponential decay, so scores shift only when new qualifying search interactions are credited.
- Recent-tag promotion ranks tags directly by summing those decayed interaction scores across the qualifying searches that include each tag, with most-recent interaction time breaking ties.
- While typing a partial tag token, suggestions are segment-aware for connector-separated tags: a prefix can match the start of the full tag or the start of any connector-separated segment (`-`, `_`, `.`, `/`).
- Example: `wor` can suggest `workspaces` and `databricks-workspaces`; `orksp` suggests neither.
- When the active prefix starts with `@`, matching meta-tag suggestions are ordered by notebook usage frequency (note count), with alphabetical tiebreaks for equal counts.
- After completing a tag and adding a space, suggestions are ordered by tag co-occurrence with all existing tag tokens in the query (strict overlap count > Jaccard within overlap).
- Suggestions appear only when the search input is focused.
- Moving the pointer onto a note below the suggestion popup hides open search suggestions while keeping focus in the search input.
- Arrow keys move selection; `Enter` accepts the selected suggestion without adding a trailing space.
- Suggestion matching is broader than actual filtering: search results still match exact effective tag terms only.

### Tag Suggestions
- Suggestions appear only when the tag bar is focused.
- Prefix behavior mirrors search suggestions (segment-aware while typing, co-occurrence after a space).
- Top suggestions interleave the strongest content matches with the strongest direct co-occurrence hits from the current explicit non-meta tags before the broader hierarchy/context fallbacks.
- For blank-prefix suggestions, content-hit candidates whose matched segments are already covered by an explicit or inherited tag are suppressed as redundant.
- Literal segment hits can surface connector-separated tags, but low-signal glue segments like `and`, `no`, `of`, `the`, `to`, or `up` do not count on their own. They still contribute to exact full-phrase literal matches, so `No Kings` can strongly promote `no-kings` even though bare `no` would not.
- Connector-heavy tags need near-complete literal coverage before they surface from content alone: if a tag has `k` raw connector-separated chunks, content must cover at least `k-1` of those chunks, capped by the number of meaningful non-noise chunks in the tag. So `X-Y-Z` can surface for `X Y`, `Y Z`, or `Y X`, but not for `X`, `Y`, `Z`, or an unrelated two-chunk overlap like `W Z`.
- For partial connector matches, the most literal candidate is ordered first: fewer unmatched connector segments beat more padded tags, and prefix-aligned partials beat suffix-aligned ones when coverage otherwise ties.
- Lowercase one-letter connector segments still count as noise. Uppercase one-letter segments can still match as meaningful literals for entity-like tags, but prose-like `A` and `I` are treated as noise.
- For otherwise tied literal content hits, more structured/longer specific tags beat shorter plain words before frequency breaks the tie.
- Full multi-segment phrase hits rank above single-segment hits, so note content like `databricks workspaces` prefers `databricks-workspaces` over `databricks` or `workspaces`.
- Surrounding prose punctuation is ignored for content matching, so content like `(github?)` still promotes `github`.
- When the active prefix starts with `@`, matching meta-tag suggestions are ordered by notebook usage frequency (note count), with alphabetical tiebreaks for equal counts.
- Case-equivalent tags are collapsed in the suggestion list, and the most-used spelling is shown.
- Ontology-equivalent tags are collapsed the same way: only the most-used eligible synonym is shown, unless the current prefix only matches a less-common synonym variant.
- Tags already present via explicit tags, inheritance, or ontology inference are suppressed unless they match the prefix (then they appear at the bottom).
- Suggestions may render above the tag bar if space below is tight, but the list still keeps the same best-on-top ordering and initial scroll position.
- Arrow keys move selection; `Enter` accepts the selected suggestion without adding a trailing space.

### Mouse Controls
| Action | Result |
|--------|--------|
| Click `+` button | Add new note at top |
| Click menu (`≡`) button | Open command palette |
| Click `↑` button | Scroll to the top |
| Click note arrow | Toggle collapse/expand note |
| Click note or blank space inside its outer card | Edit/select that note. Parent-note whitespace still counts as the parent until you click into a child note/card. |
| Click redacted note | Reveal the full redacted set in that note's subtree for the current tab; the revealed notes stay dimmed to show they are still excluded by the active search |
| Click `+/-` on a rendered reference block | Toggle reference mode (`[[UUID]]` <-> `![[UUID]]`) for that specific token occurrence |
| Click link-mode reference text | Set search input to the referenced UUID and run search |
| Drag note body (while not editing) | Reorder among visible siblings based on vertical drop position, or indent/outdent on horizontal drags. Short drags act like clicks. |
| Drag-select text in note | Available only in edit mode; releasing mouse outside note keeps edit mode + selection |
| Right-click note | Open the note context menu (`Add Sibling Note`, `Add Child Note`, `Delete Note`, `Move Note to Top`) |
| Right-click image in note | Adds image actions to the note context menu: `Copy Image`, `Save Image`, `Zoom Image`, `Open Image in New Tab` |
| Right-click tag in search input or tag bar | Open tag context menu (Edit Tag Relationships) |

> Tip: You can right-click directly on a tag without selecting the full text first (selection still works).
> In non-normal sort modes, drag/drop cannot reorder root notes, but it can still reorder children within a root.
> Saved-file image actions are available in view mode on rendered image previews; edit mode only contains the raw UUID token for those files.

### Command Palette Utility Entries
- Create backup now (opens Backup Settings, where you choose one backup folder, select the namespaces to include, set retention, and then run the backup; typing `backups` in the palette also matches it, and the completion modal shows archive size)
- Restore from backup…
- Logout
- Generate random password…
- Keyboard shortcuts help…

> Note: On Windows/Linux, use `Ctrl` instead of `⌘` (Command) 

## Tag Bar Syntax
- See `docs/ui/tag-bar.md` for the full grammar (tokens, wrappers, and `/* ... */` comments).
- Leaving the tag bar (Tab toggle or click-away) sanitizes the value by removing incomplete/broken items.
