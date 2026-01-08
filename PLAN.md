# Sticky Tag Bar Feature

## V1 Scope

This version focuses on the UI behavior only. The tag bar should be fully functional from a look-and-feel perspective—visible, positioned correctly, typeable—but **input will not be persisted**. The goal is to nail down the interaction and visual design before wiring up the backend.

### Clarifications / Decisions (V1)

- **Single edit target:** only one note can be in edit mode at a time (so only one tag bar exists at a time).
- **No prefill:** the input does not need to show existing tags yet.
- **Reset is OK:** typed tags can reset on rerender / refresh / reopen; persistence is explicitly out of scope.
- **Styling is secondary:** minimal styling is fine as long as the positioning + visibility behavior is correct (rounded corners suggested but not required).

## Overview

When a note is in edit mode, a tag bar should appear at the bottom of that note. The tag bar must remain accessible regardless of scroll position while maintaining a clear association with the note being edited.

## What the Tag Bar Is

The tag bar is a styled container (e.g., a div with rounded corners, background color, padding) that contains a text input field for viewing and editing the tags associated with a note.

### Display
- Shows the current tags for the note being edited
- Tags are space-separated (e.g., `arXiv machine-learning transformers`)

### Input Behavior
- User types directly into the field to add or modify tags
- Typing a tag that doesn't exist creates a new tag
- Typing a tag that already exists applies it to the note
- Context-sensitive autocomplete suggests likely tags as the user types (important given the system may have thousands of tags)

### Tag Inheritance Context
- Notes are hierarchical; child notes inherit tags from their parents
- The tag bar shows/edits only the tags directly applied to this note, not inherited ones
- Child notes can add more specific tags to enable more nuanced search results

## Core Behavior

### Positioning

The tag bar is part of the normal document flow—it lives at the bottom of the note being edited and pushes down any sibling notes below it and/or expands the boundaries of the containing note. It is **not** floating or absolutely positioned by default.

It uses sticky positioning with a 15px offset from the viewport bottom:

```css
position: sticky;
bottom: 15px;
```

This means:
- When the note's bottom edge is well within the viewport, the tag bar sits naturally at the end of the note content, as part of the flow
- When scrolling would push the tag bar below the 15px threshold from the viewport bottom, it "sticks" and remains 15px above the viewport bottom (this is the only time it floats)
- The 15px gap allows a sliver of content below the tag bar to remain visible, signaling to the user that more content exists below (this mirrors the existing pattern at the top of the UI where content peeks above the search bar)

### Visibility Rules

The tag bar is visible **if and only if** any part of the note being edited is visible on screen.

- If the user scrolls such that the entire note is above the viewport: tag bar disappears
- If the user scrolls such that the entire note is below the viewport: tag bar disappears
- If any portion of the note (even 1px) is visible: tag bar is visible

### Transitions

All visibility changes are **instant**. No animations, no fades. This follows the Sublime Text philosophy of immediate, predictable UI response.

## Context

### Why This Design?

Previous implementation placed the tag bar at the bottom of the parent note, even when editing a child note. This caused two problems:

1. If the parent note is large, the tag bar is far from the content being edited
2. If the child note is long, the tag bar could be below the fold and inaccessible

The sticky behavior solves both: the tag bar stays associated with the specific note being edited, and never becomes inaccessible due to scroll position.

## Implementation Notes

### Detecting Note Visibility

You will need to track whether the note being edited has any part visible in the viewport. This can be done via:

- Intersection Observer API (preferred, performant)
- Scroll event listener with bounding rect calculations (fallback)

The visibility check must account for both directions—the note could scroll out of view by going off the top or the bottom of the viewport.

Suggested approach (V1):

- Attach an `IntersectionObserver` to the *edited note container* element.
- Show the tag bar when `isIntersecting` is true; hide it when false.
- Ensure the observer is disconnected / updated when edit mode changes (since there is only one edited note at a time).

### Sticky Positioning Context

Ensure the sticky positioning context is correct. The tag bar should be a child of the note container so that `position: sticky` works relative to that note's scroll context. If the note container isn't the scroll container, you may need to adjust the DOM structure or use JavaScript to achieve the sticky effect.

### Edge Cases to Handle

1. **Editing a deeply nested note**: The tag bar appears at the bottom of that specific note, not any ancestor
2. **Very short notes**: Tag bar simply sits at the bottom; no stickiness needed since it never approaches the viewport edge
3. **Rapid scrolling across the visibility boundary**: Visibility toggles instantly, no debouncing
4. **Switching edit mode**: When the edited note changes, the old tag bar/observer is removed and the new one is attached
5. **Viewport resize**: Visibility should remain correct when the window size changes

## Acceptance Criteria

- [ ] Tag bar appears at bottom of note when entering edit mode
- [ ] Tag bar is a styled container (e.g., rounded corners) containing a text input that accepts keyboard input
- [ ] Only one tag bar is visible at a time (since only one note can be edited at once)
- [ ] Tag bar uses `position: sticky; bottom: 15px`
- [ ] Tag bar disappears instantly when edited note is fully scrolled out of view (either direction)
- [ ] Tag bar reappears instantly when any part of edited note becomes visible
- [ ] No animations or transitions on show/hide
- [ ] 15px viewport gap maintained when sticky, allowing content peek below

### Out of Scope for V1

- Persisting tag changes to storage
- Autocomplete suggestions
- Tag validation or creation logic
