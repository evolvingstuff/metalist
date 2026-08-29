export const AGENT_PROMPT_PREFERENCE_KEYS = Object.freeze({
    systemPrompt: 'pref.ai.prompt.system',
    finalResponsePrompt: 'pref.ai.prompt.final_response',
    toolResultPrompt: 'pref.ai.prompt.tool_result',
});

export const MAX_AGENT_PROMPT_CHARACTERS = 32_000;


export class AgentPromptValidationError extends Error {
    constructor(message) {
        super(message);
        this.name = 'AgentPromptValidationError';
    }
}


function inspectPromptText(label, value) {
    if (typeof value !== 'string') {
        throw new Error(`${label} must be a string`);
    }
    if (value.trim() === '') {
        return `${label} cannot be blank.`;
    }
    if (value.length > MAX_AGENT_PROMPT_CHARACTERS) {
        return `${label} cannot exceed ${MAX_AGENT_PROMPT_CHARACTERS.toLocaleString()} characters.`;
    }
    return '';
}


function parseTemplateFields(label, value) {
    const fields = [];
    for (let index = 0; index < value.length; index += 1) {
        const character = value[index];
        const nextCharacter = value[index + 1];
        if (character === '{' && nextCharacter === '{') {
            index += 1;
            continue;
        }
        if (character === '}' && nextCharacter === '}') {
            index += 1;
            continue;
        }
        if (character === '}') {
            return {
                fields,
                error: `${label} has an unmatched closing brace.`,
            };
        }
        if (character !== '{') {
            continue;
        }
        const closingIndex = value.indexOf('}', index + 1);
        if (closingIndex === -1) {
            return {
                fields,
                error: `${label} has an unmatched opening brace.`,
            };
        }
        const fieldName = value.slice(index + 1, closingIndex);
        if (fieldName === '' || fieldName.includes('{')) {
            return {
                fields,
                error: `${label} has an invalid placeholder.`,
            };
        }
        fields.push(fieldName);
        index = closingIndex;
    }
    return { fields, error: '' };
}


function inspectTemplate(label, value, requiredFields) {
    const textError = inspectPromptText(label, value);
    if (textError !== '') {
        return textError;
    }
    const parsed = parseTemplateFields(label, value);
    if (parsed.error !== '') {
        return parsed.error;
    }
    const fields = parsed.fields;
    for (const field of fields) {
        if (!requiredFields.includes(field)) {
            return `${label} has an unsupported placeholder: {${field}}.`;
        }
    }
    for (const requiredField of requiredFields) {
        const count = fields.filter((field) => field === requiredField).length;
        if (count !== 1) {
            return `${label} must contain exactly one {${requiredField}} placeholder.`;
        }
    }
    return '';
}


export function inspectAgentPromptSet(settings) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
        throw new Error('inspectAgentPromptSet requires settings object');
    }
    const prompts = {
        systemPrompt: settings.systemPrompt,
        finalResponsePrompt: settings.finalResponsePrompt,
        toolResultPrompt: settings.toolResultPrompt,
    };
    let error = inspectPromptText('System prompt', prompts.systemPrompt);
    if (error === '') {
        error = inspectTemplate(
            'Final-response prompt',
            prompts.finalResponsePrompt,
            ['basis'],
        );
    }
    if (error === '') {
        error = inspectTemplate(
            'Tool-result prompt',
            prompts.toolResultPrompt,
            ['action_name', 'payload_json'],
        );
    }
    return { prompts, error };
}


export function validateAgentPromptSet(settings) {
    const inspected = inspectAgentPromptSet(settings);
    if (inspected.error !== '') {
        throw new AgentPromptValidationError(inspected.error);
    }
    return inspected.prompts;
}


export function validateAgentPromptDefaultsPayload(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error('Agent prompt defaults response must be an object');
    }
    return validateAgentPromptSet({
        systemPrompt: payload.system_prompt,
        finalResponsePrompt: payload.final_response_prompt,
        toolResultPrompt: payload.tool_result_prompt,
    });
}
