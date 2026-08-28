import { CONFIG } from '../config.js';
import { buildSessionHeaders } from '../session-auth.js';
import { parseAiChatNdjsonBuffer } from './ai-chat-panel-service.js';
import { validateAiThinkingLevel } from './ai-thinking-level-service.js';


export class AiApiError extends Error {
    constructor(message) {
        super(message);
        this.name = 'AiApiError';
    }
}


async function fetchAi(url, options) {
    try {
        return await fetch(url, options);
    } catch (error) {
        if (error instanceof TypeError) {
            throw new AiApiError('Could not reach the MetaList AI service');
        }
        throw error;
    }
}


async function readJsonResponse(response, fallbackMessage) {
    if (!(response instanceof Response)) {
        throw new Error('readJsonResponse requires Response');
    }
    const responseText = await response.text();
    if (!response.ok) {
        let message = `${fallbackMessage} (${response.status})`;
        if (responseText !== '') {
            const payload = JSON.parse(responseText);
            if (payload && typeof payload.detail === 'string') {
                message = payload.detail;
            }
        }
        throw new AiApiError(message);
    }
    const payload = JSON.parse(responseText);
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error(`${fallbackMessage}: response payload missing`);
    }
    return payload;
}


export async function loadAiChatSession() {
    const response = await fetchAi(CONFIG.API.AI.SESSION, {
        headers: buildSessionHeaders(false),
        cache: 'no-store',
    });
    return await readJsonResponse(response, 'Failed to load AI chat session');
}


export async function clearAiChatSession() {
    const response = await fetchAi(CONFIG.API.AI.SESSION, {
        method: 'DELETE',
        headers: buildSessionHeaders(false),
    });
    return await readJsonResponse(response, 'Failed to clear AI chat session');
}


export async function listOllamaModels(settings) {
    if (!settings || typeof settings !== 'object') {
        throw new Error('listOllamaModels requires settings object');
    }
    const response = await fetchAi(CONFIG.API.AI.MODELS, {
        method: 'POST',
        headers: buildSessionHeaders(true),
        body: JSON.stringify({
            provider: settings.provider,
            base_url: settings.baseUrl,
        }),
    });
    return await readJsonResponse(response, 'Failed to list Ollama models');
}


export async function streamAiChat({ settings, message, onEvent }) {
    if (!settings || typeof settings !== 'object') {
        throw new Error('streamAiChat requires settings object');
    }
    if (typeof message !== 'string' || message.trim() === '') {
        throw new Error('streamAiChat requires non-empty message');
    }
    if (typeof onEvent !== 'function') {
        throw new Error('streamAiChat requires onEvent');
    }
    const thinkingLevel = validateAiThinkingLevel(settings.thinkingLevel);
    const response = await fetchAi(CONFIG.API.AI.CHAT, {
        method: 'POST',
        headers: buildSessionHeaders(true),
        body: JSON.stringify({
            provider: settings.provider,
            base_url: settings.baseUrl,
            model: settings.model,
            thinking_level: thinkingLevel,
            message,
        }),
    });
    if (!response.ok) {
        await readJsonResponse(response, 'Failed to start Ollama chat');
    }
    if (!(response.body instanceof ReadableStream)) {
        throw new Error('AI chat response is missing readable stream');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let didFinish = false;
    while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const parsed = parseAiChatNdjsonBuffer(buffer);
        buffer = parsed.remainder;
        for (const event of parsed.events) {
            onEvent(event);
            if (event.type === 'done' || event.type === 'error') {
                didFinish = true;
            }
        }
        if (done) {
            break;
        }
    }
    if (buffer !== '') {
        throw new Error('AI chat stream ended with incomplete JSON');
    }
    if (!didFinish) {
        throw new AiApiError('AI chat stream ended before completion');
    }
}
