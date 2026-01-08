# Sticky Tag Bar Feature - V2: Persistence

## Overview

V2 adds persistence to the tag bar. Tags entered in the tag bar will be saved when exiting edit mode and restored when re-entering edit mode.

## Prerequisites

- V1 complete (tag bar UI, positioning, visibility all working)

## Schema Change

Add a `tags` column to the `notes` table:

```sql
ALTER TABLE notes ADD COLUMN tags TEXT NOT NULL DEFAULT '';
```

Tags are stored as a space-separated string (matching the input format).

## Encryption

If encryption is enabled, tags must be encrypted at rest following the same process used for the `content` column. Mirror the existing approach exactly—do not implement a separate path for tags.

## Behavior

### On Enter Edit Mode

1. Read the note's `tags` value from the in-memory note object
2. Populate the tag bar input with this value

### On Exit Edit Mode

1. Read the current value from the tag bar input
2. Update the in-memory note object
3. Persist to database (same process as `content`)
4. Update `updated_at` timestamp

### Edge Cases

- **Empty tags**: Valid state; store as empty string
- **Whitespace normalization**: Consider trimming leading/trailing whitespace and collapsing multiple spaces to single spaces before saving (optional, decide based on preference)
- **Exit without changes**: Still safe to save; no optimization needed for V2

## Acceptance Criteria

- [ ] `tags` column added to `notes` table with `DEFAULT ''`
- [ ] Tags are encrypted at rest using the same mechanism as `content`
- [ ] Entering edit mode populates the tag bar with the note's saved tags
- [ ] Exiting edit mode persists the tag bar contents to the database
- [ ] Round-trip works: enter edit → type tags → exit → re-enter → tags are there

## Out of Scope for V2

- Tag autocomplete / suggestions
- Tag validation
- Displaying tags outside of edit mode
- Tag search / filtering integration
- Inherited tag display