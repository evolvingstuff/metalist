# External HTML Paste Sanitization

## Scope
- Applies only to **system clipboard** paste while editing note content.
- Internal MetaList note clipboard paste (`class="note-content"` payload) still uses server note copy/paste actions.

## Entry Points
- Paste handler: `app/static/js/modules/mode-manager/events/keyboard-events.js`
  - `handlePasteEvent(...)`
- Sanitizer service: `app/static/js/modules/mode-manager/services/html-paste-sanitizer-service.js`
  - `sanitizeAndInsertExternalPaste(event)`
  - `sanitizeExternalClipboardHtml(rawHtml)`

## Pipeline
1. Read `text/html` from clipboard.
2. Parse with `DOMParser`.
3. Walk DOM and sanitize nodes/attributes/styles/URLs.
4. Insert sanitized HTML into current selection.
5. If no usable HTML remains, fallback to `text/plain`.

## Security Policy

### Blocked tags
- `script`, `style`, `iframe`, `object`, `embed`, `applet`, `meta`, `base`, `link`, `svg`, `math`, `form`, `input`, `button`, `textarea`, `select`, `option`, `template`, `noscript`

### Attribute rules
- Remove all `on*` event handlers.
- Remove `id`, `class`, and all `data-*`.
- Remove `srcset`.
- Sanitize URL-bearing attributes (`href`, `src`, `xlink:href`, `action`, `formaction`, `poster`, `background`, `cite`, `longdesc`).

### URL rules
- Dangerous prefixes are rejected, including encoded forms (`javascript:`, `vbscript:`, `file:`, `filesystem:`, `data:text/html`, `data:application/*`).
- Allowed `href` schemes: `http`, `https`, `mailto`, `tel`.
- Allowed `src` schemes: `http`, `https`, `blob`, and safe `data:image/*;base64,...`.
- Relative URLs and anchors are preserved.

### Data image size cap (browser-side)
- Config key: `app/static/js/modules/config.js`
  - `CONFIG.PASTE.MAX_DATA_IMAGE_BYTES`
- Current default: `1_048_576` bytes (1 MiB estimated decoded payload).
- Oversized `data:image` URLs are removed.

## Formatting Preservation Policy

### Kept (allowlist)
- Text styles: `white-space`, `font-weight`, `font-style`, `text-decoration`, `text-decoration-line`, `vertical-align`
- Block indentation styles (block tags only): `margin-left`, `padding-left`, `text-indent`
- Image box styles (`img` only): `width`, `height`, `max-width`, `max-height`

### Rejected
- Any style containing dangerous payloads (`url(...)`, `expression(...)`, `@import`, encoded entity escapes, angle-bracket/backtick payload chars, etc.).
- Hidden content wrappers:
  - `hidden` attribute
  - `aria-hidden="true"`
  - inline style with `display:none` or `visibility:hidden`

## Avatar Clamp Heuristic
- Goal: keep thread avatars from dominating pasted comment content.
- Behavior:
  - Detect likely avatars from a weighted signal model:
    - avatar/profile/snoo-like hints in `class`/`alt`/`src`/`id`/`aria-label`
    - repeated image source frequency
    - small square-ish declared dimensions
    - nearby author/time metadata in DOM-order context
  - Clamp matched avatars to `48px x 48px`.
- Implementation detail:
  - Avatar detection runs **before** attribute stripping, then clamp is applied after attribute sanitization.

## Tests
- Unit tests: `tests/unit/html_paste_sanitizer_service.test.mjs`
- Validation command:
  - `node --test tests/unit/html_paste_sanitizer_service.test.mjs`
