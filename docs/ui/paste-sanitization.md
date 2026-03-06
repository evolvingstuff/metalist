# External HTML Paste Sanitization

## Scope
- Applies to **system clipboard paste** and **drag/drop file images**.
  - Dropping into the actively edited note embeds the image there.
  - Dropping an image anywhere else creates a new top note, then embeds the image there.
- Internal MetaList note clipboard paste (`class="note-content"` payload) still uses server note copy/paste actions.

## Entry Points
- Clipboard/drop handler: `app/static/js/modules/mode-manager/events/keyboard-events.js`
  - `handleDragOverEvent(...)`
  - `handleDropEvent(...)`
  - `handlePasteEvent(...)`
- Sanitizer service: `app/static/js/modules/mode-manager/services/html-paste-sanitizer-service.js`
  - `sanitizeAndInsertExternalPaste(event)`
  - `sanitizeExternalClipboardHtml(rawHtml)`

## Pipeline
1. If clipboard contains image/file items (`image/*`) while editing, pick the largest image candidate and process it client-side.
2. If a drag/drop payload contains image files, process each dropped image client-side after resolving the target note (current editor or a new top note).
3. Downscale/re-encode to keep embedded payload in the configured KB range.
4. Build inline `<img src="data:image/...">` HTML (embedded content, not file links).
5. Otherwise read `text/html` from clipboard.
6. Parse with `DOMParser`.
7. Walk DOM and sanitize nodes/attributes/styles/URLs.
8. Insert sanitized HTML into current selection.
9. If no usable HTML remains, fallback to `text/plain`.

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
- Current default: `10_485_760` bytes (10 MiB estimated decoded payload).
- Oversized `data:image` URLs are removed.

### Embedded image footprint controls
- Config keys:
  - `CONFIG.PASTE.EMBED_TARGET_IMAGE_BYTES` (target compressed size, default `350_000`)
  - `CONFIG.PASTE.EMBED_MAX_DIMENSION_PX` (initial resize cap, default `1_600`)
  - `CONFIG.PASTE.MAX_CLIPBOARD_IMAGE_BYTES` (input guardrail, default `31_457_280`)
- Behavior:
  - encode attempts use lossy formats and quality steps
  - dimensions are reduced iteratively when needed
  - if target is not reached but output is still under hard max, best effort output is used
  - if output exceeds hard max, paste is rejected with an error.

### Embedded image behavior
- Clipboard image/file paste is embedded into note content as `data:image/...` (no `file://` links).
- Embedded images remain stored with note content, so they are portable across machines with the DB.
- If clipboard only contains file-reference metadata (for example Finder file-icon copy) rather than image bytes, paste is blocked with an error instead of inserting icon-preview HTML.

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

## General Image Clamp
- All pasted images are normalized to:
  - remove incoming `width`/`height` attributes
  - enforce `max-width: 100%`, `width:auto`, `height:auto`.
- Goal: prevent giant pasted icon/preview markup from dominating the editor.

## Tests
- Unit tests: `tests/unit/html_paste_sanitizer_service.test.mjs`
- Validation command:
  - `node --test tests/unit/html_paste_sanitizer_service.test.mjs`
