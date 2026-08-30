export const AGENT_RETRIEVAL_PREFERENCE_KEYS = Object.freeze({
    maxNoteCharacters: 'pref.ai.retrieval.max_note_characters',
    maxPageCharacters: 'pref.ai.retrieval.max_page_characters',
    maxNotesPerPage: 'pref.ai.retrieval.max_notes_per_page',
    maxPageApproximateTokens: 'pref.ai.retrieval.max_page_approximate_tokens',
    maxRankedTagsPerPage: 'pref.ai.retrieval.max_ranked_tags_per_page',
    maxWorkingSummaryCharacters: 'pref.ai.retrieval.max_working_summary_characters',
    idealNarrowedScopeApproximateTokens: (
        'pref.ai.retrieval.ideal_narrowed_scope_approximate_tokens'
    ),
});

export const OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS = Object.freeze({
    maxNoteCharacters: 'pref.ai.openai.retrieval.max_note_characters',
    maxPageCharacters: 'pref.ai.openai.retrieval.max_page_characters',
    maxNotesPerPage: 'pref.ai.openai.retrieval.max_notes_per_page',
    maxPageApproximateTokens: 'pref.ai.openai.retrieval.max_page_approximate_tokens',
    maxRankedTagsPerPage: 'pref.ai.openai.retrieval.max_ranked_tags_per_page',
    maxWorkingSummaryCharacters: (
        'pref.ai.openai.retrieval.max_working_summary_characters'
    ),
    idealNarrowedScopeApproximateTokens: (
        'pref.ai.openai.retrieval.ideal_narrowed_scope_approximate_tokens'
    ),
});

export const DEFAULT_AGENT_RETRIEVAL_SETTINGS = Object.freeze({
    maxNoteCharacters: 2000,
    maxPageCharacters: 20000,
    maxNotesPerPage: 50,
    maxPageApproximateTokens: 5000,
    maxRankedTagsPerPage: 50,
    maxWorkingSummaryCharacters: 8000,
    idealNarrowedScopeApproximateTokens: 10000,
});

export const DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS = Object.freeze({
    ...DEFAULT_AGENT_RETRIEVAL_SETTINGS,
    maxPageApproximateTokens: 250000,
    idealNarrowedScopeApproximateTokens: 500000,
});

const LEGACY_DEFAULT_OPENAI_MAX_PAGE_APPROXIMATE_TOKENS = 24000;
const LEGACY_DEFAULT_OPENAI_IDEAL_NARROWED_SCOPE_APPROXIMATE_TOKENS = 48000;

const AGENT_RETRIEVAL_LIMITS = Object.freeze({
    minimumNoteCharacters: 500,
    maximumNoteCharacters: 10000,
    minimumPageCharacters: 5000,
    maximumPageCharacters: 100000,
    minimumNotesPerPage: 1,
    maximumNotesPerPage: 100,
    minimumPageApproximateTokens: 500,
    maximumOllamaPageApproximateTokens: 24000,
    maximumOpenAiPageApproximateTokens: 500000,
    minimumRankedTagsPerPage: 1,
    maximumRankedTagsPerPage: 200,
    minimumWorkingSummaryCharacters: 2000,
    maximumWorkingSummaryCharacters: 32000,
    minimumIdealNarrowedScopeApproximateTokens: 1000,
    maximumOllamaIdealNarrowedScopeApproximateTokens: 200000,
    maximumOpenAiIdealNarrowedScopeApproximateTokens: 500000,
});


export class AgentRetrievalSettingsValidationError extends Error {}


export function validateAgentRetrievalSettings(settings, provider) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
        throw new TypeError('Agent retrieval settings must be an object');
    }
    const validationMessage = getAgentRetrievalSettingsValidationMessage(
        settings,
        provider,
    );
    if (validationMessage !== '') {
        throw new AgentRetrievalSettingsValidationError(validationMessage);
    }
    const maxNoteCharacters = settings.maxNoteCharacters;
    const maxPageCharacters = settings.maxPageCharacters;
    const maxNotesPerPage = settings.maxNotesPerPage;
    const maxPageApproximateTokens = settings.maxPageApproximateTokens;
    const maxRankedTagsPerPage = settings.maxRankedTagsPerPage;
    const maxWorkingSummaryCharacters = settings.maxWorkingSummaryCharacters;
    const idealNarrowedScopeApproximateTokens = (
        settings.idealNarrowedScopeApproximateTokens
    );
    return {
        maxNoteCharacters,
        maxPageCharacters,
        maxNotesPerPage,
        maxPageApproximateTokens,
        maxRankedTagsPerPage,
        maxWorkingSummaryCharacters,
        idealNarrowedScopeApproximateTokens,
    };
}


export function getAgentRetrievalSettingsValidationMessage(settings, provider) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
        throw new TypeError('Agent retrieval settings must be an object');
    }
    const providerLimits = retrievalLimitsForProvider(provider);
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
        providerLimits.maximumPageApproximateTokens,
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
    const summaryError = integerRangeError(
        settings.maxWorkingSummaryCharacters,
        'Maximum working-summary characters',
        AGENT_RETRIEVAL_LIMITS.minimumWorkingSummaryCharacters,
        AGENT_RETRIEVAL_LIMITS.maximumWorkingSummaryCharacters,
    );
    if (summaryError !== '') {
        return summaryError;
    }
    return integerRangeError(
        settings.idealNarrowedScopeApproximateTokens,
        'Ideal narrowed-scope approximate tokens',
        AGENT_RETRIEVAL_LIMITS.minimumIdealNarrowedScopeApproximateTokens,
        providerLimits.maximumIdealNarrowedScopeApproximateTokens,
    );
}


export function readAgentRetrievalSettings(getPreference, provider) {
    if (typeof getPreference !== 'function') {
        throw new Error('readAgentRetrievalSettings requires getPreference');
    }
    const { preferenceKeys, defaults } = providerRetrievalConfiguration(provider);
    const rawMaxPageApproximateTokens = getPreference(
        preferenceKeys.maxPageApproximateTokens,
    );
    const rawIdealNarrowedScopeApproximateTokens = getPreference(
        preferenceKeys.idealNarrowedScopeApproximateTokens,
    );
    const maxPageApproximateTokens = parseStoredInteger(
        rawMaxPageApproximateTokens,
        defaults.maxPageApproximateTokens,
        'Stored approximate input tokens per evidence page',
    );
    const idealNarrowedScopeApproximateTokens = parseStoredInteger(
        rawIdealNarrowedScopeApproximateTokens,
        defaults.idealNarrowedScopeApproximateTokens,
        'Stored ideal narrowed-scope approximate tokens',
    );
    return validateAgentRetrievalSettings({
        maxNoteCharacters: parseStoredInteger(
            getPreference(preferenceKeys.maxNoteCharacters),
            defaults.maxNoteCharacters,
            'Stored maximum note characters',
        ),
        maxPageCharacters: parseStoredInteger(
            getPreference(preferenceKeys.maxPageCharacters),
            defaults.maxPageCharacters,
            'Stored maximum total characters per result page',
        ),
        maxNotesPerPage: parseStoredInteger(
            getPreference(preferenceKeys.maxNotesPerPage),
            defaults.maxNotesPerPage,
            'Stored maximum result trees per page',
        ),
        maxPageApproximateTokens: migrateLegacyOpenAiPageTokens(
            maxPageApproximateTokens,
            provider,
        ),
        maxRankedTagsPerPage: parseStoredInteger(
            getPreference(preferenceKeys.maxRankedTagsPerPage),
            defaults.maxRankedTagsPerPage,
            'Stored maximum ranked tags per facet page',
        ),
        maxWorkingSummaryCharacters: parseStoredInteger(
            getPreference(preferenceKeys.maxWorkingSummaryCharacters),
            defaults.maxWorkingSummaryCharacters,
            'Stored maximum working-summary characters',
        ),
        idealNarrowedScopeApproximateTokens: migrateLegacyOpenAiNarrowingTokens(
            idealNarrowedScopeApproximateTokens,
            provider,
        ),
    }, provider);
}


function migrateLegacyOpenAiPageTokens(value, provider) {
    if (
        provider === 'openai'
        && value === LEGACY_DEFAULT_OPENAI_MAX_PAGE_APPROXIMATE_TOKENS
    ) {
        return DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS.maxPageApproximateTokens;
    }
    return value;
}


function migrateLegacyOpenAiNarrowingTokens(value, provider) {
    if (
        provider === 'openai'
        && value === LEGACY_DEFAULT_OPENAI_IDEAL_NARROWED_SCOPE_APPROXIMATE_TOKENS
    ) {
        return (
            DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS
                .idealNarrowedScopeApproximateTokens
        );
    }
    return value;
}


function retrievalLimitsForProvider(provider) {
    if (provider === 'ollama') {
        return {
            maximumPageApproximateTokens: (
                AGENT_RETRIEVAL_LIMITS.maximumOllamaPageApproximateTokens
            ),
            maximumIdealNarrowedScopeApproximateTokens: (
                AGENT_RETRIEVAL_LIMITS.maximumOllamaIdealNarrowedScopeApproximateTokens
            ),
        };
    }
    if (provider === 'openai') {
        return {
            maximumPageApproximateTokens: (
                AGENT_RETRIEVAL_LIMITS.maximumOpenAiPageApproximateTokens
            ),
            maximumIdealNarrowedScopeApproximateTokens: (
                AGENT_RETRIEVAL_LIMITS.maximumOpenAiIdealNarrowedScopeApproximateTokens
            ),
        };
    }
    throw new Error(`Unsupported agent retrieval provider: ${provider}`);
}


function providerRetrievalConfiguration(provider) {
    if (provider === 'ollama') {
        return {
            preferenceKeys: AGENT_RETRIEVAL_PREFERENCE_KEYS,
            defaults: DEFAULT_AGENT_RETRIEVAL_SETTINGS,
        };
    }
    if (provider === 'openai') {
        return {
            preferenceKeys: OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS,
            defaults: DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS,
        };
    }
    throw new Error(`Unsupported agent retrieval provider: ${provider}`);
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
