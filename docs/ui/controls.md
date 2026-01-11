# Note App Controls

## Keyboard Shortcuts

### When Editing a Note
| Shortcut | Action |
|----------|--------|
| `Esc` | Exit edit mode for current note |
| `Tab` | Toggle focus between note content and tag bar (restores cursor position) |
| `⌘ + Enter` | Add new sibling note below current note |
| `⇧ + ⌘ + Enter` | Add new child note under current note |
| `⌘ + P` | Save + exit edit mode, then open password modal |
| `⌘ + C` | Copy selection (default), or copy whole note when no selection |
| `⌘ + X` | Cut selection (default), or cut whole note when no selection |
| `⌘ + V` | Paste note as sibling (when note clipboard active) |
| `⇧ + ⌘ + V` | Paste note as child (when note clipboard active) |

### General Shortcuts
| Shortcut | Action |
|----------|--------|
| `Enter` | Add new note at top (when not editing) |
| `Space` | Toggle collapse/expand hovered note |
| `⌘ + Z` | Undo |
| `⌘ + Y` | Redo |

### Mouse Controls
| Action | Result |
|--------|--------|
| Click `+` button | Add new note at top |
| Click `↑` button | Scroll to the top |
| Click note arrow | Toggle collapse/expand note |
| Click note | Edit note |
| Drag-select text in note | Releasing mouse outside note keeps edit mode + selection |

> Note: On Windows/Linux, use `Ctrl` instead of `⌘` (Command) 

## Tag Bar Syntax
- Tags are space-separated tokens stored on each note.
- Tokens may be wrapped with matching `[]`, `{}`, or `()` (repeat 1–3 times), e.g. `[tag]`, `((tag))`, `{{{tag}}}`.
- Invalid/mismatched closing wrappers are stripped as you type (e.g. `[tag)` → `[tag`).
- Unclosed wrappers and unclosed `/*` comments show a validation warning; incomplete tokens are omitted from the saved tag string.
