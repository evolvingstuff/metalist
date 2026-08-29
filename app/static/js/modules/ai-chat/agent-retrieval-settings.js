export const AGENT_RETRIEVAL_PREFERENCE_KEYS = Object.freeze({
    maxNoteCharacters: 'pref.ai.retrieval.max_note_characters',
    maxPageCharacters: 'pref.ai.retrieval.max_page_characters',
    maxNotesPerPage: 'pref.ai.retrieval.max_notes_per_page',
    maxPageApproximateTokens: 'pref.ai.retrieval.max_page_approximate_tokens',
    maxRankedTagsPerPage: 'pref.ai.retrieval.max_ranked_tags_per_page',
    maxWorkingSummaryCharacters: 'pref.ai.retrieval.max_working_summary_characters',
});

export const DEFAULT_AGENT_RETRIEVAL_SETTINGS = Object.freeze({
    maxNoteCharacters: 2000,
    maxPageCharacters: 20000,
    maxNotesPerPage: 50,
    maxPageApproximateTokens: 5000,
    maxRankedTagsPerPage: 50,
    maxWorkingSummaryCharacters: 8000,
});

const AGENT_RETRIEVAL_LIMITS = Object.freeze({
    minimumNoteCharacters: 500,
    maximumNoteCharacters: 10000,
    minimumPageCharacters: 5000,
    maximumPageCharacters: 100000,
    minimumNotesPerPage: 1,
    maximumNotesPerPage: 100,
    minimumPageApproximateTokens: 500,
    maximumPageApproximateTokens: 24000,
    minimumRankedTagsPerPage: 1,
    maximumRankedTagsPerPage: 200,
    minimumWorkingSummaryCharacters: 2000,
    maximumWorkingSummaryCharacters: 32000,
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
    const maxPageApproximateTokens = settings.maxPageApproximateTokens;
    const maxRankedTagsPerPage = settings.maxRankedTagsPerPage;
    const maxWorkingSummaryCharacters = settings.maxWorkingSummaryCharacters;
    return {
        maxNoteCharacters,
        maxPageCharacters,
        maxNotesPerPage,
        maxPageApproximateTokens,
        maxRankedTagsPerPage,
        maxWorkingSummaryCharacters,
    };
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
    const notesPerPageError = integerRangeError(
        settings.maxNotesPerPage,
        'Maximum result trees per page',
        AGENT_RETRIEVAL_LIMITS.minimumNotesPerPage,
        AGENT_RETRIEVAL_LIMITS.maximumNotesPerPage,
    );
    if (notesPerPageError !== '') {
        return notesPerPageError;
    }
    const pageTokenError = integerRangeError(
        settings.maxPageApproximateTokens,
        'Approximate input tokens per evidence page',
        AGENT_RETRIEVAL_LIMITS.minimumPageApproximateTokens,
        AGENT_RETRIEVAL_LIMITS.maximumPageApproximateTokens,
    );
    if (pageTokenError !== '') {
        return pageTokenError;
    }
    const facetPageError = integerRangeError(
        settings.maxRankedTagsPerPage,
        'Maximum ranked tags per facet page',
        AGENT_RETRIEVAL_LIMITS.minimumRankedTagsPerPage,
        AGENT_RETRIEVAL_LIMITS.maximumRankedTagsPerPage,
    );
    if (facetPageError !== '') {
        return facetPageError;
    }
    return integerRangeError(
        settings.maxWorkingSummaryCharacters,
        'Maximum working-summary characters',
        AGENT_RETRIEVAL_LIMITS.minimumWorkingSummaryCharacters,
        AGENT_RETRIEVAL_LIMITS.maximumWorkingSummaryCharacters,
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
        maxPageApproximateTokens: parseStoredInteger(
            getPreference(AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageApproximateTokens),
            DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxPageApproximateTokens,
            'Stored approximate input tokens per evidence page',
        ),
        maxRankedTagsPerPage: parseStoredInteger(
            getPreference(AGENT_RETRIEVAL_PREFERENCE_KEYS.maxRankedTagsPerPage),
            DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxRankedTagsPerPage,
            'Stored maximum ranked tags per facet page',
        ),
        maxWorkingSummaryCharacters: parseStoredInteger(
            getPreference(AGENT_RETRIEVAL_PREFERENCE_KEYS.maxWorkingSummaryCharacters),
            DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxWorkingSummaryCharacters,
            'Stored maximum working-summary characters',
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
