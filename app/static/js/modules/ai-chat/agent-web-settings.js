export const AGENT_WEB_ACCESS_MODE_PREFERENCE_KEY = 'pref.ai.web_access_mode';
export const AGENT_WEB_ACCESS_MODES = Object.freeze(['none', 'contextual', 'full']);
export const DEFAULT_AGENT_WEB_ACCESS_MODE = 'none';


export function validateAgentWebAccessMode(value) {
    if (typeof value !== 'string' || !AGENT_WEB_ACCESS_MODES.includes(value)) {
        throw new Error(`Unsupported agent web access mode: ${value}`);
    }
    return value;
}


export function readAgentWebAccessMode(getPreference) {
    if (typeof getPreference !== 'function') {
        throw new Error('readAgentWebAccessMode requires getPreference');
    }
    const stored = getPreference(AGENT_WEB_ACCESS_MODE_PREFERENCE_KEY);
    if (stored === null) return DEFAULT_AGENT_WEB_ACCESS_MODE;
    return validateAgentWebAccessMode(stored);
}
