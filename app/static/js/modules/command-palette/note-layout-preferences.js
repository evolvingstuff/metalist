export const NOTE_LAYOUT_PREFERENCE_KEYS = Object.freeze({
    topLevelNoteSize: 'pref.note_layout.top_level_note_size',
    childIndentation: 'pref.note_layout.child_indentation',
    verticalSpacing: 'pref.note_layout.vertical_spacing',
    noteCorners: 'pref.note_layout.note_corners',
    tagStyle: 'pref.note_layout.tag_style',
});

export const NOTE_LAYOUT_OPTIONS = Object.freeze({
    topLevelNoteSize: Object.freeze([
        Object.freeze({ value: 'same', label: 'Same as children' }),
        Object.freeze({ value: 'larger', label: 'Larger' }),
        Object.freeze({ value: 'largest', label: 'Even larger' }),
    ]),
    childIndentation: Object.freeze([
        Object.freeze({ value: 'compact', label: 'Compact' }),
        Object.freeze({ value: 'standard', label: 'Standard' }),
        Object.freeze({ value: 'wide', label: 'Wide' }),
    ]),
    verticalSpacing: Object.freeze([
        Object.freeze({ value: 'compact', label: 'Compact' }),
        Object.freeze({ value: 'comfortable', label: 'Comfortable' }),
        Object.freeze({ value: 'spacious', label: 'Spacious' }),
    ]),
    noteCorners: Object.freeze([
        Object.freeze({ value: 'subtle', label: 'Subtle' }),
        Object.freeze({ value: 'rounded', label: 'Rounded' }),
        Object.freeze({ value: 'round', label: 'Round' }),
    ]),
    tagStyle: Object.freeze([
        Object.freeze({ value: 'pills', label: 'Pills' }),
        Object.freeze({ value: 'text', label: 'Plain text' }),
    ]),
});

export const DEFAULT_NOTE_LAYOUT_SETTINGS = Object.freeze({
    topLevelNoteSize: 'larger',
    childIndentation: 'standard',
    verticalSpacing: 'comfortable',
    noteCorners: 'round',
    tagStyle: 'pills',
});


function validatePreset(key, value) {
    if (typeof value !== 'string') {
        throw new Error(`Note layout ${key} must be a string`);
    }
    const allowedValues = NOTE_LAYOUT_OPTIONS[key].map((option) => option.value);
    if (!allowedValues.includes(value)) {
        throw new Error(`Invalid note layout ${key}: ${value}`);
    }
}


export function validateNoteLayoutSettings(settings) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
        throw new Error('Note layout settings must be an object');
    }
    validatePreset('topLevelNoteSize', settings.topLevelNoteSize);
    validatePreset('childIndentation', settings.childIndentation);
    validatePreset('verticalSpacing', settings.verticalSpacing);
    validatePreset('noteCorners', settings.noteCorners);
    validatePreset('tagStyle', settings.tagStyle);
    return {
        topLevelNoteSize: settings.topLevelNoteSize,
        childIndentation: settings.childIndentation,
        verticalSpacing: settings.verticalSpacing,
        noteCorners: settings.noteCorners,
        tagStyle: settings.tagStyle,
    };
}


export function applyNoteLayoutSettings(bodyElement, settings) {
    if (!bodyElement || typeof bodyElement.setAttribute !== 'function') {
        throw new Error('applyNoteLayoutSettings requires a body element');
    }
    const validated = validateNoteLayoutSettings(settings);
    bodyElement.setAttribute('data-top-level-note-size', validated.topLevelNoteSize);
    bodyElement.setAttribute('data-child-indentation', validated.childIndentation);
    bodyElement.setAttribute('data-note-vertical-spacing', validated.verticalSpacing);
    bodyElement.setAttribute('data-note-corners', validated.noteCorners);
    bodyElement.setAttribute('data-tag-style', validated.tagStyle);
}
