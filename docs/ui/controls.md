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
| `⌘ + P` | Save + exit edit mode, then open password modal |
| `⌘ + C` | Copy selection (default), or copy whole note when no selection |
| `⌘ + R` | Insert `![[UUID]]` for the most recently copied note UUID |
| `⌘ + X` | Cut selection (default), or cut whole note when no selection |
| `⌘ + V` | Paste note as sibling (when note clipboard active; scrolls new note into view). If the selected note is empty with no tags, paste replaces it. |
| `⇧ + ⌘ + V` | Paste note as child (when note clipboard active; scrolls new note into view) |

- If note clipboard conditions are **not** met and edit mode is active, `⌘ + V` uses browser clipboard paste and runs external HTML sanitization before insertion.
- See `docs/ui/paste-sanitization.md` for the full policy.
- `⌘ + R` inserts the reference token on its own line; if the caret is mid-line, the line is split around the inserted token.
- See `docs/ui/references.md` for full reference behavior.

### General Shortcuts
| Shortcut | Action |
|----------|--------|
| `Enter` | Add new note at top (when not editing) |
| `Space` | Toggle collapse/expand hovered note |
| `⌘ + /` | Open command palette |
| `⌘ + Z` | Undo |
| `⌘ + Y` | Redo |
| `⌘ + ↑` | Move note up (one visible sibling) |
| `⌘ + ↓` | Move note down (one visible sibling) |

### Search Input Behavior
- Pressing `Enter` while focused in the search input creates a new **root** note.
- If the search query contains required tag terms (unquoted tokens like `asdf`), the new root note is created with those tags in its tag bar.
- When creating a child (`⇧ + ⌘ + Enter`) or sibling (`⌘ + Enter`) note under a note that already provides the required **non-meta** tags via inheritance, the new note is **not** redundantly tagged.

### Search Suggestions
- Suggestions are **tag-only** (no text suggestions).
- While typing a partial tag token (e.g. `jour`), suggestions are prefix completions.
- After completing a tag and adding a space, suggestions are ordered by tag co-occurrence with all existing tag tokens in the query (strict overlap count > Jaccard within overlap).
- Suggestions appear only when the search input is focused.
- Arrow keys move selection; `Enter` accepts the selected suggestion without adding a trailing space.

### Tag Suggestions
- Suggestions appear only when the tag bar is focused.
- Prefix behavior mirrors search suggestions (prefix completions while typing, co-occurrence after a space).
- Content matches (tag phrases found in the note body) are listed first.
- Tags already present via explicit tags, inheritance, or ontology inference are suppressed unless they match the prefix (then they appear at the bottom).
- Suggestions may render above the tag bar if space below is tight; the ordering reverses so the closest suggestion sits nearest the input.
- Arrow keys move selection; `Enter` accepts the selected suggestion without adding a trailing space.

### Mouse Controls
| Action | Result |
|--------|--------|
| Click `+` button | Add new note at top |
| Click menu (`≡`) button | Open command palette |
| Click `↑` button | Scroll to the top |
| Click note arrow | Toggle collapse/expand note |
| Click note | Edit note |
| Drag note body (while not editing) | Move note one step in the dragged cardinal direction (up/down/indent/outdent). Short drags act like clicks. |
| Drag-select text in note | Releasing mouse outside note keeps edit mode + selection |
| Right-click tag in search input or tag bar | Open tag context menu (Edit Tag Relationships) |

> Tip: You can right-click directly on a tag without selecting the full text first (selection still works).

### Command Palette Utility Entries
- Create backup now (if 25 or more backups exist, opens a retention modal asking how many backups to keep, defaulting to 3; finishes with a completion `OK` modal)
- Restore from backup…
- Logout
- Generate random password…

> Note: On Windows/Linux, use `Ctrl` instead of `⌘` (Command) 

## Tag Bar Syntax
- See `docs/ui/tag-bar.md` for the full grammar (tokens, wrappers, and `/* ... */` comments).
- Leaving the tag bar (Tab toggle or click-away) sanitizes the value by removing incomplete/broken items.
