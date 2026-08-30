import { isValidTagToken } from '../tag-token.js';


export const CLOUD_PRIVACY_POLICY_PREFERENCE_KEY = 'pref.ai.cloud_privacy_policy';
const MAX_ENTRIES_PER_LIST = 200;
const MAX_TAG_LENGTH = 256;
const MAX_PHRASE_LENGTH = 500;


export function emptyCloudPrivacyPolicy() {
    return {
        whitelistTags: [],
        whitelistPhrases: [],
        blacklistTags: [],
        blacklistPhrases: [],
    };
}


function validateEntries(entries, { fieldLabel, isTag }) {
    if (!Array.isArray(entries)) {
        throw new Error(`${fieldLabel} must be an array`);
    }
    if (entries.length > MAX_ENTRIES_PER_LIST) {
        throw new Error(`${fieldLabel} accepts at most ${MAX_ENTRIES_PER_LIST} entries.`);
    }
    const seen = new Set();
    return entries.map((rawEntry) => {
        if (typeof rawEntry !== 'string') {
            throw new Error(`${fieldLabel} entries must be text`);
        }
        const entry = rawEntry.trim();
        if (entry === '' || entry !== rawEntry) {
            throw new Error(`${fieldLabel} entries must be trimmed and non-empty`);
        }
        const maximumLength = isTag ? MAX_TAG_LENGTH : MAX_PHRASE_LENGTH;
        if (entry.length > maximumLength) {
            throw new Error(`${fieldLabel} entries may not exceed ${maximumLength} characters.`);
        }
        if (isTag && !isValidTagToken(entry)) {
            throw new Error(`${fieldLabel} contains an invalid MetaList tag: ${entry}`);
        }
        const normalized = entry.toLowerCase();
        if (seen.has(normalized)) {
            throw new Error(`${fieldLabel} contains a duplicate entry: ${entry}`);
        }
        seen.add(normalized);
        return entry;
    });
}


export function validateCloudPrivacyPolicy(policy) {
    if (!policy || typeof policy !== 'object' || Array.isArray(policy)) {
        throw new Error('Cloud privacy policy must be an object');
    }
    const expectedKeys = [
        'blacklistPhrases',
        'blacklistTags',
        'whitelistPhrases',
        'whitelistTags',
    ];
    if (
        Object.keys(policy).length !== expectedKeys.length
        || expectedKeys.some((key) => !Object.prototype.hasOwnProperty.call(policy, key))
    ) {
        throw new Error('Cloud privacy policy has missing or unknown fields');
    }
    return {
        whitelistTags: validateEntries(policy.whitelistTags, {
            fieldLabel: 'Whitelisted tags',
            isTag: true,
        }),
        whitelistPhrases: validateEntries(policy.whitelistPhrases, {
            fieldLabel: 'Whitelisted phrases',
            isTag: false,
        }),
        blacklistTags: validateEntries(policy.blacklistTags, {
            fieldLabel: 'Blacklisted tags',
            isTag: true,
        }),
        blacklistPhrases: validateEntries(policy.blacklistPhrases, {
            fieldLabel: 'Blacklisted phrases',
            isTag: false,
        }),
    };
}


export function readCloudPrivacyPolicy(readPreference) {
    if (typeof readPreference !== 'function') {
        throw new Error('readCloudPrivacyPolicy requires preference reader');
    }
    const rawValue = readPreference(CLOUD_PRIVACY_POLICY_PREFERENCE_KEY);
    if (rawValue === null) {
        return emptyCloudPrivacyPolicy();
    }
    if (typeof rawValue !== 'string') {
        throw new Error('Stored cloud privacy policy must be a string');
    }
    const parsed = JSON.parse(rawValue);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Stored cloud privacy policy must decode to an object');
    }
    const policy = {
        whitelistTags: parsed.whitelist_tags,
        whitelistPhrases: parsed.whitelist_phrases,
        blacklistTags: parsed.blacklist_tags,
        blacklistPhrases: parsed.blacklist_phrases,
    };
    const validated = validateCloudPrivacyPolicy(policy);
    if (serializeCloudPrivacyPolicy(validated) !== rawValue) {
        throw new Error('Stored cloud privacy policy must use canonical JSON');
    }
    return validated;
}


export function serializeCloudPrivacyPolicy(policy) {
    const validated = validateCloudPrivacyPolicy(policy);
    return JSON.stringify({
        blacklist_phrases: validated.blacklistPhrases,
        blacklist_tags: validated.blacklistTags,
        whitelist_phrases: validated.whitelistPhrases,
        whitelist_tags: validated.whitelistTags,
    });
}


function parseLines(value, fieldLabel, isTag) {
    if (typeof value !== 'string') {
        throw new Error(`${fieldLabel} must be text`);
    }
    const entries = value
        .split(/\r?\n/u)
        .map((entry) => entry.trim())
        .filter((entry) => entry !== '');
    return validateEntries(entries, { fieldLabel, isTag });
}


function linesFromText(value) {
    if (typeof value !== 'string') {
        return null;
    }
    return value
        .split(/\r?\n/u)
        .map((entry) => entry.trim())
        .filter((entry) => entry !== '');
}


function validateTextFieldForUser(value, fieldLabel, isTag) {
    const entries = linesFromText(value);
    if (entries === null) {
        return `${fieldLabel} must be text.`;
    }
    if (entries.length > MAX_ENTRIES_PER_LIST) {
        return `${fieldLabel} accepts at most ${MAX_ENTRIES_PER_LIST} entries.`;
    }
    const seen = new Set();
    const maximumLength = isTag ? MAX_TAG_LENGTH : MAX_PHRASE_LENGTH;
    for (const entry of entries) {
        if (entry.length > maximumLength) {
            return `${fieldLabel} entries may not exceed ${maximumLength} characters.`;
        }
        if (isTag && !isValidTagToken(entry)) {
            return `${fieldLabel} contains an invalid MetaList tag: ${entry}`;
        }
        const normalized = entry.toLowerCase();
        if (seen.has(normalized)) {
            return `${fieldLabel} contains a duplicate entry: ${entry}`;
        }
        seen.add(normalized);
    }
    return '';
}


export function getCloudPrivacyTextFieldsValidationMessage(fields) {
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)) {
        return 'Cloud privacy settings are missing.';
    }
    for (const [value, fieldLabel, isTag] of [
        [fields.whitelistTagsText, 'Whitelisted tags', true],
        [fields.whitelistPhrasesText, 'Whitelisted phrases', false],
        [fields.blacklistTagsText, 'Blacklisted tags', true],
        [fields.blacklistPhrasesText, 'Blacklisted phrases', false],
    ]) {
        const message = validateTextFieldForUser(value, fieldLabel, isTag);
        if (message !== '') {
            return message;
        }
    }
    return '';
}


export function parseCloudPrivacyTextFields(fields) {
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)) {
        throw new Error('Cloud privacy text fields must be an object');
    }
    return validateCloudPrivacyPolicy({
        whitelistTags: parseLines(fields.whitelistTagsText, 'Whitelisted tags', true),
        whitelistPhrases: parseLines(
            fields.whitelistPhrasesText,
            'Whitelisted phrases',
            false,
        ),
        blacklistTags: parseLines(fields.blacklistTagsText, 'Blacklisted tags', true),
        blacklistPhrases: parseLines(
            fields.blacklistPhrasesText,
            'Blacklisted phrases',
            false,
        ),
    });
}


export function cloudPrivacyPolicyToTextFields(policy) {
    const validated = validateCloudPrivacyPolicy(policy);
    return {
        whitelistTagsText: validated.whitelistTags.join('\n'),
        whitelistPhrasesText: validated.whitelistPhrases.join('\n'),
        blacklistTagsText: validated.blacklistTags.join('\n'),
        blacklistPhrasesText: validated.blacklistPhrases.join('\n'),
    };
}
