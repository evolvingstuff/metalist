export const NOTE_LAYOUT_PREFERENCE_KEYS = Object.freeze({
    topLevelNoteSize: 'pref.note_layout.top_level_note_size',
    childIndentation: 'pref.note_layout.child_indentation',
    verticalSpacing: 'pref.note_layout.vertical_spacing',
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
});

export const DEFAULT_NOTE_LAYOUT_SETTINGS = Object.freeze({
    topLevelNoteSize: 'larger',
    childIndentation: 'standard',
    verticalSpacing: 'comfortable',
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
    return {
        topLevelNoteSize: settings.topLevelNoteSize,
        childIndentation: settings.childIndentation,
        verticalSpacing: settings.verticalSpacing,
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
}
