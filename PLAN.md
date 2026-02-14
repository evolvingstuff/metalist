# PLAN

## Goal
Add smart HTML sanitization for external clipboard paste into note editing, preserving useful formatting while removing unsafe/noisy markup.

## Non-Goals
- No changes to note-to-note clipboard (internal copy/paste) behavior.
- No automatic rewrite of existing stored notes.

## Context
- External paste currently uses browser default behavior in `handlePasteEvent`.
- Note content is persisted as HTML and rendered via `innerHTML`, so paste-time sanitization is the primary safety boundary.

## Assumptions / Constraints
- Sanitization is client-side and runs only for external HTML paste.
- Internal logic remains fail-fast; malformed external HTML is normalized to safe output.
- Legacy regex rules are the baseline for value validation.

## Inferred Sanitizer Policy (from legacy rules)
1. Allowed tags
- Inline: `a`, `strong`, `em`, `u`, `code`, `span`, `br`.
- Block: `p`, `div`, `blockquote`, `pre`, `ul`, `ol`, `li`, `h1`-`h6`.
- Excluded by default: tables, images, iframes, forms, media embeds.

2. Disallowed tags
- Remove unsafe tags (`script`, `style`, `iframe`, `object`, `embed`, `form`, `input`, etc.).
- For unknown non-unsafe tags, unwrap and keep text/children where safe.

3. Allowed attributes
- `a`: `href`, `title`.
- Other allowed tags: `title`, `style` (validated subset only).
- Always drop: `class`, `id`, `data-*`, `aria-*`, and all `on*` handlers.

4. URL validation
- Allowed protocols: `http:`, `https:`, `mailto:`, `tel:`.
- Drop `href` values with any other scheme (`javascript:`, `data:`, `vbscript:`, etc.).

5. Style validation (strict subset)
- Property-name validation uses alpha/hyphen rules.
- Allowed properties:
  - `color`, `background-color` with values matching hex/rgb/rgba/hsl/hsla regexes.
  - `font-size`, `line-height`, `margin`, `margin-top`, `margin-right`, `margin-bottom`, `margin-left`, `padding`, `padding-top`, `padding-right`, `padding-bottom`, `padding-left` with length/percent regex.
  - `font-weight`, `font-style`, `text-decoration`, `text-align` with alpha token values.
- Disallow any style declaration failing validation.

6. Text/entity normalization
- Decode entities safely and normalize whitespace around block boundaries.
- Keep user-visible text; do not silently drop text content.

## Legacy Regex Inventory (port/reference)
- `/^[a-z1-6]$/`
- `/^[a-z\-]$/`
- `/^[\"'`=<>]$/`
- `/^\s$/`
- `/^.*&#.*$/`
- `/^.*\\[0-9A-Fa-f].*$/`
- `/(\%[0-9a-fA-F]{2})/g`
- `/(\&[\#\d\w]+;)/g`
- `/^#([0-9A-Fa-f]{3}){1,2}$/`
- `/^rgb\(\s*\d+%?\s*,\s*\d+%?\s*,\s*\d+%?\s*\)$/`
- `/^rgba\(\s*\d+%?\s*,\s*\d+%?\s*,\s*\d+%?\s*,\s*(\d+\.)?\d+\s*\)$/`
- `/^hsl\(\s*\d+\s*,\s*\d+%\s*,\s*\d+%\s*\)$/`
- `/^hsla\(\s*\d+\s*,\s*\d+%\s*,\s*\d+%\s*,\s*(\d+\.)?\d+\s*\)$/`
- `/^(-?\d+(px|cm|pt|em|ex|pc|mm|in)?|\d+%)$/`
- `/^[a-zA-Z]+$/`
- `/^[a-zA-Z0-9]+$/`
- `/[\-\[\]\/\{\}\(\)\*\+\?\.\\\^\$\|]/g`
- `new RegExp('^[' + escaped_chars + ']+$')`

## Implementation Plan
1. Add a dedicated sanitizer module under `app/static/js/modules/mode-manager/services/`.
2. Implement parser + sanitize pipeline:
- Parse clipboard HTML into DOM.
- Rebuild sanitized fragment with allowlisted tags/attrs/styles.
- Drop unsafe nodes/attrs and normalize output HTML.
3. Integrate into paste flow in `handlePasteEvent`:
- For external HTML in edit mode: `preventDefault()`, sanitize, insert sanitized fragment at current caret.
- Preserve existing internal note clipboard behavior.
- Preserve plain-text-only paste behavior.
4. Synchronize editor state after sanitized insertion:
- Ensure `ModeContext.currentContent` and dirty state update immediately.
- Preserve selection snapshot behavior used by existing editor commands.
5. Add tests:
- Unit tests for sanitizer allow/deny cases and style/url validators.
- Regression tests for dangerous payloads (`javascript:` links, event handlers, unsafe tags).
6. Update docs:
- Add external paste sanitization behavior to relevant UI docs.

## Validation
- Run targeted JS unit tests for sanitizer.
- Manual verification with paste sources: web articles, docs editors, chat apps, plain text.
- Run `./sanitycheck/run` if feature code changes are complete in this branch.

## Remaining Decisions (only if you want changes from inferred defaults)
- Include tables/images now or keep excluded.
- Keep or drop `style` entirely after initial test pass.
