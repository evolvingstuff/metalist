export const AGENT_RETRIEVAL_PREFERENCE_KEYS = Object.freeze({
    maxNoteCharacters: 'pref.ai.retrieval.max_note_characters',
    maxPageCharacters: 'pref.ai.retrieval.max_page_characters',
    maxNotesPerPage: 'pref.ai.retrieval.max_notes_per_page',
});

export const DEFAULT_AGENT_RETRIEVAL_SETTINGS = Object.freeze({
    maxNoteCharacters: 2000,
    maxPageCharacters: 20000,
    maxNotesPerPage: 50,
});

const AGENT_RETRIEVAL_LIMITS = Object.freeze({
    minimumNoteCharacters: 500,
    maximumNoteCharacters: 10000,
    minimumPageCharacters: 5000,
    maximumPageCharacters: 100000,
    minimumNotesPerPage: 1,
    maximumNotesPerPage: 100,
});


export class AgentRetrievalSettingsValidationError extends Error {}


export function validateAgentRetrievalSettings(settings) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
        throw new TypeError('Agent retrieval settings must be an object');
    }
    const validationMessage = getAgentRetrievalSettingsValidationMessage(settings);
    if (validationMessage !== '') {
        throw new AgentRetrievalSettingsValidationError(validationMessage);
    }
    const maxNoteCharacters = settings.maxNoteCharacters;
    const maxPageCharacters = settings.maxPageCharacters;
    const maxNotesPerPage = settings.maxNotesPerPage;
    return { maxNoteCharacters, maxPageCharacters, maxNotesPerPage };
}


export function getAgentRetrievalSettingsValidationMessage(settings) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
        throw new TypeError('Agent retrieval settings must be an object');
    }
    const noteCharacterError = integerRangeError(
        settings.maxNoteCharacters,
        'Maximum note characters',
        AGENT_RETRIEVAL_LIMITS.minimumNoteCharacters,
        AGENT_RETRIEVAL_LIMITS.maximumNoteCharacters,
    );
    if (noteCharacterError !== '') {
        return noteCharacterError;
    }
    const pageCharacterError = integerRangeError(
        settings.maxPageCharacters,
        'Maximum total characters per result page',
        AGENT_RETRIEVAL_LIMITS.minimumPageCharacters,
        AGENT_RETRIEVAL_LIMITS.maximumPageCharacters,
    );
    if (pageCharacterError !== '') {
        return pageCharacterError;
    }
    return integerRangeError(
        settings.maxNotesPerPage,
        'Maximum result trees per page',
        AGENT_RETRIEVAL_LIMITS.minimumNotesPerPage,
        AGENT_RETRIEVAL_LIMITS.maximumNotesPerPage,
    );
}


export function readAgentRetrievalSettings(getPreference) {
    if (typeof getPreference !== 'function') {
        throw new Error('readAgentRetrievalSettings requires getPreference');
    }
    return validateAgentRetrievalSettings({
        maxNoteCharacters: parseStoredInteger(
            getPreference(AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNoteCharacters),
            DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxNoteCharacters,
            'Stored maximum note characters',
        ),
        maxPageCharacters: parseStoredInteger(
            getPreference(AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageCharacters),
            DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxPageCharacters,
            'Stored maximum total characters per result page',
        ),
        maxNotesPerPage: parseStoredInteger(
            getPreference(AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNotesPerPage),
            DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxNotesPerPage,
            'Stored maximum result trees per page',
        ),
    });
}


function parseStoredInteger(rawValue, defaultValue, label) {
    if (rawValue === null) {
        return defaultValue;
    }
    if (typeof rawValue !== 'string' || !/^[1-9][0-9]*$/.test(rawValue)) {
        throw new Error(`${label} is invalid`);
    }
    const parsed = Number(rawValue);
    if (!Number.isSafeInteger(parsed) || String(parsed) !== rawValue) {
        throw new Error(`${label} is invalid`);
    }
    return parsed;
}


function integerRangeError(value, label, minimum, maximum) {
    if (!Number.isInteger(value) || value < minimum || value > maximum) {
        return `${label} must be an integer from ${minimum} to ${maximum}`;
    }
    return '';
}
