export const DEFAULT_AI_THINKING_LEVEL = 'low';

export const AI_THINKING_LEVEL_OPTIONS = Object.freeze([
    Object.freeze({ value: 'off', label: 'Thinking Off' }),
    Object.freeze({ value: 'low', label: 'Low Thinking' }),
    Object.freeze({ value: 'medium', label: 'Medium Thinking' }),
    Object.freeze({ value: 'high', label: 'High Thinking' }),
]);

const AI_THINKING_LEVEL_VALUES = new Set(
    AI_THINKING_LEVEL_OPTIONS.map((option) => option.value),
);


export function validateAiThinkingLevel(thinkingLevel) {
    if (typeof thinkingLevel !== 'string' || !AI_THINKING_LEVEL_VALUES.has(thinkingLevel)) {
        throw new Error(`Unsupported AI thinking level: ${thinkingLevel}`);
    }
    return thinkingLevel;
}


export function isGptOssModel(model) {
    if (typeof model !== 'string') {
        throw new Error('isGptOssModel requires model string');
    }
    return model.trim().toLowerCase().startsWith('gpt-oss');
}


export function isThinkingLevelAvailableForModel({ model, thinkingLevel }) {
    validateAiThinkingLevel(thinkingLevel);
    if (isGptOssModel(model) && thinkingLevel === 'off') {
        return false;
    }
    return true;
}


export function normalizeThinkingLevelForModel({ model, thinkingLevel }) {
    const validated = validateAiThinkingLevel(thinkingLevel);
    if (!isThinkingLevelAvailableForModel({ model, thinkingLevel: validated })) {
        return DEFAULT_AI_THINKING_LEVEL;
    }
    return validated;
}
