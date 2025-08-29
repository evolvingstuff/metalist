# Git Workflow

If I say:

FEATURE: I would like to ... (description goes here)

I would like you to:
1. check if I have uncommitted changes in git and warn me if I do.
2. if everything is checked in, create an appropriately named branch, based on the
feature description
3. interactively implement the future as you would normally do

I can then test it and we can interactively try to fix any issues.

## Testing and Commits

### If Testing Fails
If I test your code and say it failed, you should:
1. Suggest doing a `git reset --hard HEAD` to undo the changes
2. Ask if I want to proceed with the reset before doing it

### If Testing Succeeds
If the code works, you should suggest doing a commit. There are two types:

**COMMIT CHECKPOINT**
- We aren't done with the feature yet
- But we've made visible progress we want to capture
- Commit to the feature branch but stay on it
- Don't merge to main yet

**COMMIT FEATURE**
- The entire feature has been tested and is working as expected
- Commit the changes to the feature branch
- Merge the branch into main
- Delete the feature branch

**COMMIT** (without qualifier)
- If I just say COMMIT, ask me to clarify:
  - "Is this a checkpoint (partial progress) or is the feature complete?"

### Rollback
If I say:

ROLLBACK

I want you to rollback all the changes made on that branch.

# Make errors obvious, immediately

FAIL FAST AND LOUDLY: If anything fails during build processes or at runtime, 
it should fail as fast and as loudly as possible. No error recovery, no graceful 
degradation, no silent failures. The build should stop immediately with clear 
error messages so issues can be identified and fixed quickly. UI should give 
alerts to the user, not just console.error messages.

## CRITICAL: NO SOFT FAILURES - CLAUDE READ THIS

Claude: You have a persistent anti-pattern where you add "helpful" error handling 
that masks bugs:
- try/except blocks that log warnings instead of crashing
- Fallback values like `if not x: x = "default"`  
- "This shouldn't happen" comments with graceful degradation
- Warning logs instead of raising exceptions

THIS PATTERN HAS COST 100+ HOURS OF DEBUGGING TIME. Every soft failure you add:
1. Hides the real bug for hours/days
2. Makes debugging exponentially harder  
3. Directly violates the FAIL FAST AND LOUDLY principle
4. Wastes massive amounts of time

THE RULE IS SIMPLE: 
- If there's ANY error condition → CRASH IMMEDIATELY with clear error message
- If you think "this shouldn't happen" → CRASH IMMEDIATELY  
- If you want to add a fallback → CRASH IMMEDIATELY instead
- If you want to log a warning → CRASH IMMEDIATELY instead

Error handling is a code smell. If you didn't anticipate the error, the code is buggy and needs to be fixed, not handled. The crash tells you exactly what to fix.

## CRITICAL: USE ASSERTIONS LIBERALLY

Assertions should make up about 5% of the code, if not more. Every function should validate its assumptions:
- Assert preconditions at function entry
- Assert postconditions before return
- Assert invariants throughout the code
- Assert that "impossible" states are actually impossible

Python example:
```python
def move_note(note_id: str, parent_id: str):
    assert note_id, "note_id is required"
    assert note_id != parent_id, "Cannot move note to itself"
    note = db.get(Note, note_id)
    assert note, f"Note {note_id} not found"
    # ... do the move ...
    assert note.parent_id == parent_id, "Move failed"
```

JavaScript example:
```javascript
function moveNote(noteId, parentId) {
    if (!noteId) throw new Error("noteId is required");
    if (noteId === parentId) throw new Error("Cannot move note to itself");
    const note = getNote(noteId);
    if (!note) throw new Error(`Note ${noteId} not found`);
    // ... do the move ...
    if (note.parentId !== parentId) throw new Error("Move failed");
}
```

## CRITICAL: NO SOFT FAILURES IN JAVASCRIPT

Claude: The same FAIL FAST AND LOUDLY principle applies to JavaScript:
- NEVER use console.error() or console.warn() → throw new Error() instead
- NEVER use try/catch blocks unless absolutely necessary
- NEVER use optional chaining (?.) or nullish coalescing (??)
- NEVER use OR operator (||) for fallback values
- NEVER use .catch() on promises without re-throwing

If something goes wrong in JavaScript:
- throw new Error('Clear description of what failed')
- Let it crash the browser console
- The stack trace shows exactly what to fix

Example transformations:
- console.error('Failed to load') → throw new Error('Failed to load')
- value || 'default' → if (!value) throw new Error('value is required')
- obj?.property → if (!obj) throw new Error('obj is required'); obj.property
- try { ... } catch(e) { console.error(e) } → just remove the try/catch entirely

## CRITICAL: NO OPTIONAL FIELDS

Claude: ALMOST NEVER use Optional[T] fields in request/response models. Use required fields instead.

Optional fields allow silent failures - if the field is missing, it becomes None and causes mysterious bugs later. Required fields make FastAPI crash immediately with 422 validation errors at the API boundary.

BEFORE using Optional[T], you MUST:
1. Ask for explicit human approval
2. Explain WHY you think Optional is appropriate for this specific case
3. Get confirmation before proceeding

Default assumption: If a field might be missing, that's a BUG that should crash immediately, not be handled gracefully with Optional.

# MANDATORY: Check for Error Handling After Every Code Change

After EVERY file edit that contains Python code, you MUST run:
```
python check_errors.py
```

If this finds any soft error handling, FIX IT IMMEDIATELY before proceeding.
DO NOT continue with other tasks until all error handling is removed.

# Testing Philosophy

NEVER commit untested code. Always wait for user confirmation that changes have been tested and work correctly before committing. If I ask to commit, ask me first: "Have you tested these changes?"