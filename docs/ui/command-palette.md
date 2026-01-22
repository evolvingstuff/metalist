# Command Palette

Open with `⌘ + /`.

## Semantics
- Query is an unordered bag of words.
- AND-only matching against manually-authored tags.
- While you are mid-token (no trailing space), it behaves as a prefix filter.

## Results
- Booleans toggle with `Enter`.
- Selects cycle with `Enter` (and adjust with `←`/`→`).
- Actions run with `Enter`.

## Config
- Tag mappings live in `app/static/config/command_palette_tags.json`.
- Endpoint definitions (behavior/labels) live in code.

## Collapse/Expand All
"(current view)" means the full active search context (not just rendered DOM).
The implementation uses `POST /api2/notes/set-collapsed-in-context`.

