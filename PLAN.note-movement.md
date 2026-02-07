# PLAN: Note Movement System

## Overview

Implement a four-directional note movement system. Each direction performs one atomic operation on the selected note. The selected note's subtree (all descendants) always moves with it. No other notes are reparented, moved, or otherwise affected — only the selected note and its subtree change position.

---

## Operations

### Move Up

Move the selected note one position earlier among its siblings.

**Precondition:** The note is not the first child of its parent.

**Behavior:** Swap the note (and its subtree) with the immediately preceding sibling. The preceding sibling's subtree is unaffected — only ordering changes.

**No-op:** If the note is already the first sibling, do nothing.

### Move Down

Move the selected note one position later among its siblings.

**Precondition:** The note is not the last child of its parent.

**Behavior:** Swap the note (and its subtree) with the immediately following sibling. The following sibling's subtree is unaffected — only ordering changes.

**No-op:** If the note is already the last sibling, do nothing.

### Indent (Move Right)

Make the selected note a child of the sibling immediately above it.

**Precondition:** There is a sibling directly above the selected note.

**Behavior:** Remove the note (and its subtree) from its current sibling list. Append it as the last child of the sibling that was immediately above it.

**Example:**
```
A
    B
    C    ← indent C
    D
```
Result:
```
A
    B
        C
    D
```

**No-op:** If the note is the first child of its parent (no sibling above), do nothing.

### Outdent (Move Left)

Make the selected note a sibling of its current parent, placed directly after the parent.

**Precondition:** The note has a parent that is not the root level.

**Behavior:** Remove the note (and its subtree) from its current sibling list. Insert it as the next sibling after its former parent. No other notes move — remaining siblings of the note stay where they are under the original parent.

**Example:**
```
A
    B
    C    ← outdent C
    D
```
Result:
```
A
    B
    D
C
```

Note: D does **not** become a child of C. D does **not** get outdented. Only C (and any children C may have) moves.

**No-op:** If the note is already at root level, do nothing.

---

## Invariants

1. **Only the selected note and its subtree move.** No other notes are reparented, reordered, or relocated as a side effect.
2. **One operation = one move.** Each invocation of any direction performs exactly one atomic change.
3. **No-ops are silent.** If a move is impossible (e.g., outdenting a root note, moving up when already first), nothing happens. No error is thrown.
4. **Subtree integrity is preserved.** The internal structure of the selected note's subtree is never modified by a move operation. Children, grandchildren, etc. maintain their relative positions within the subtree.

---

## Input Methods

### Keyboard Shortcuts

Each direction maps to a keyboard shortcut. A single keypress = one move. Holding or repeating the key performs multiple sequential moves.

Exact key bindings TBD, but the interface must support all four directions.

### Cardinal Drag Gesture (Mouse)

A drag gesture on a note is interpreted as a directional command, not a free-placement drag-and-drop.

**Detection:**
1. Record mouse position on `mouseDown`.
2. Record mouse position on `mouseUp`.
3. Compute the Euclidean distance between the two points.
4. If the distance is below a threshold (suggested range: 15–30px, tune by feel), treat it as a click, not a drag. Do nothing.
5. If the distance meets or exceeds the threshold, compute the angle (theta) between the start and end points.
6. Snap theta to the nearest cardinal direction (up, down, left, right) — i.e., whichever of 0°, 90°, 180°, 270° has the smallest angular distance.
7. Execute the corresponding move operation exactly once.

**Key properties:**
- The note does **not** visually follow the cursor during the gesture. This is a swipe/flick gesture, not a drag-and-drop.
- After the gesture is recognized and the move executes, the note animates to its new position.
- One gesture = one move, regardless of drag distance. Distance determines whether the gesture is recognized, not how far the note moves.
- The angle snapping means a slightly diagonal drag is always resolved to one of the four cardinal directions. There is no diagonal or ambiguous state.

---

## Undo / Redo

Each move operation is a single undo step. Pressing undo after a move reverses exactly one position change. This applies uniformly to all four directions and both input methods (keyboard and drag gesture).

---

## Relationship to Cut / Paste

The four directional moves handle local rearrangements (moving a note 1–4 positions). For large-distance relocations (e.g., moving a note 20 siblings up, or to a completely different part of the tree), cut and paste is the appropriate mechanism. Cut always includes the full subtree.

These two systems are complementary. No additional "move to" dialog or intermediate mechanism is needed.
