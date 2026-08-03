import {
    sanitizeStyleAttributeValue,
    sanitizeUrlAttributeValue,
} from './mode-manager/services/html-paste-sanitizer-service.js';

const POLICY_URL = '/static/note-html-policy.json';
const INTEGER_ATTRIBUTE_PATTERN = /^-?\d+$/;
const POSITIVE_INTEGER_ATTRIBUTE_PATTERN = /^\d+$/;
const IMAGE_DIMENSION_ATTRIBUTE_PATTERN = /^\d+(?:\.\d+)?$/;

let sanitizeWithPolicy = null;

function validatePolicy(policy) {
    if (policy === null || typeof policy !== 'object') {
        throw new Error('Note HTML sanitizer policy must be an object');
    }
    if (policy.version !== 1) {
        throw new Error(`Unsupported note HTML sanitizer policy version: ${policy.version}`);
    }
    if (!Array.isArray(policy.allowed_tags) || policy.allowed_tags.length === 0) {
        throw new Error('Note HTML sanitizer policy requires allowed_tags');
    }
    if (policy.allowed_attributes === null || typeof policy.allowed_attributes !== 'object') {
        throw new Error('Note HTML sanitizer policy requires allowed_attributes');
    }
    if (!Array.isArray(policy.clean_content_tags)) {
        throw new Error('Note HTML sanitizer policy requires clean_content_tags');
    }
    if (!Array.isArray(policy.allowed_url_schemes)) {
        throw new Error('Note HTML sanitizer policy requires allowed_url_schemes');
    }
}

function getUrlScheme(value) {
    const match = /^\s*([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(value);
    if (match === null) {
        return null;
    }
    return match[1].toLowerCase();
}

function sanitizePolicyUrl(rawValue, attributeName, policy) {
    const mode = attributeName === 'href' ? 'href' : 'src';
    const safeValue = sanitizeUrlAttributeValue(rawValue, mode);
    if (safeValue === null) {
        return null;
    }
    const scheme = getUrlScheme(safeValue);
    if (scheme !== null && !policy.allowed_url_schemes.includes(scheme)) {
        return null;
    }
    return safeValue;
}

function isAllowedAttribute(tagName, attributeName, policy) {
    const globalAttributes = policy.allowed_attributes['*'];
    if (Array.isArray(globalAttributes) && globalAttributes.includes(attributeName)) {
        return true;
    }
    const tagAttributes = policy.allowed_attributes[tagName];
    return Array.isArray(tagAttributes) && tagAttributes.includes(attributeName);
}

function sanitizeScalarAttribute(tagName, attributeName, rawValue) {
    const value = rawValue.trim();
    if ((attributeName === 'height' || attributeName === 'width') && tagName === 'img') {
        return IMAGE_DIMENSION_ATTRIBUTE_PATTERN.test(value) ? value : null;
    }
    if (attributeName === 'colspan' || attributeName === 'rowspan') {
        return POSITIVE_INTEGER_ATTRIBUTE_PATTERN.test(value) && Number.parseInt(value, 10) > 0
            ? value
            : null;
    }
    if ((attributeName === 'start' && tagName === 'ol') || (attributeName === 'value' && tagName === 'li')) {
        return INTEGER_ATTRIBUTE_PATTERN.test(value) ? value : null;
    }
    if (attributeName === 'type' && tagName === 'ol') {
        return new Set(['1', 'a', 'A', 'i', 'I']).has(value) ? value : null;
    }
    if (attributeName === 'scope' && tagName === 'th') {
        return new Set(['row', 'col', 'rowgroup', 'colgroup']).has(value.toLowerCase())
            ? value.toLowerCase()
            : null;
    }
    return rawValue;
}

export function sanitizeNoteAttribute(tagName, attributeName, rawValue, policy) {
    if (typeof tagName !== 'string' || typeof attributeName !== 'string' || typeof rawValue !== 'string') {
        throw new Error('sanitizeNoteAttribute requires string tag, attribute, and value');
    }
    validatePolicy(policy);
    const normalizedTagName = tagName.toLowerCase();
    const normalizedAttributeName = attributeName.toLowerCase();
    if (!isAllowedAttribute(normalizedTagName, normalizedAttributeName, policy)) {
        return null;
    }
    if (normalizedAttributeName === 'style') {
        return sanitizeStyleAttributeValue(rawValue, normalizedTagName);
    }
    if (normalizedAttributeName === 'href' || normalizedAttributeName === 'src') {
        return sanitizePolicyUrl(rawValue, normalizedAttributeName, policy);
    }
    return sanitizeScalarAttribute(normalizedTagName, normalizedAttributeName, rawValue);
}

function buildSanitizer(policy, purifier) {
    validatePolicy(policy);
    if (purifier === null || (typeof purifier !== 'object' && typeof purifier !== 'function')) {
        throw new Error('DOMPurify must be loaded before note HTML sanitizer initialization');
    }
    if (typeof purifier.addHook !== 'function' || typeof purifier.sanitize !== 'function') {
        throw new Error('Invalid DOMPurify instance');
    }

    purifier.addHook('uponSanitizeAttribute', (node, hookEvent) => {
        const tagName = node.nodeName.toLowerCase();
        const safeValue = sanitizeNoteAttribute(
            tagName,
            hookEvent.attrName,
            hookEvent.attrValue,
            policy,
        );
        if (safeValue === null) {
            hookEvent.keepAttr = false;
            return;
        }
        hookEvent.attrValue = safeValue;
    });

    const flattenedAttributes = Array.from(new Set(Object.values(policy.allowed_attributes).flat()));
    const purifierOptions = Object.freeze({
        ALLOWED_TAGS: policy.allowed_tags,
        ALLOWED_ATTR: flattenedAttributes,
        ALLOW_ARIA_ATTR: false,
        ALLOW_DATA_ATTR: false,
        FORBID_TAGS: policy.clean_content_tags,
        KEEP_CONTENT: true,
        RETURN_TRUSTED_TYPE: false,
    });

    return content => purifier.sanitize(content, purifierOptions);
}

async function loadPolicy() {
    const response = await fetch(POLICY_URL, {
        credentials: 'same-origin',
        cache: 'no-store',
    });
    if (!response.ok) {
        throw new Error(`Failed to load note HTML sanitizer policy: HTTP ${response.status}`);
    }
    return await response.json();
}

export async function initializeNoteHtmlSanitizer(options) {
    let requestedPolicy = null;
    let requestedPurifier = null;
    if (options !== undefined) {
        if (options === null || typeof options !== 'object') {
            throw new Error('initializeNoteHtmlSanitizer options must be an object');
        }
        if (!Object.hasOwn(options, 'policy') || !Object.hasOwn(options, 'purifier')) {
            throw new Error('initializeNoteHtmlSanitizer test options require policy and purifier');
        }
        requestedPolicy = options.policy;
        requestedPurifier = options.purifier;
    }
    const resolvedPolicy = requestedPolicy === null ? await loadPolicy() : requestedPolicy;
    const resolvedPurifier = requestedPurifier === null ? globalThis.DOMPurify : requestedPurifier;
    sanitizeWithPolicy = buildSanitizer(resolvedPolicy, resolvedPurifier);
}

export function sanitizeNoteHtmlForStorage(content) {
    if (typeof content !== 'string') {
        throw new Error('sanitizeNoteHtmlForStorage requires string content');
    }
    if (sanitizeWithPolicy === null) {
        throw new Error('Note HTML sanitizer has not been initialized');
    }
    return sanitizeWithPolicy(content);
}
