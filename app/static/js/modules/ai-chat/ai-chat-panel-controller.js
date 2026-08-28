import {
    AiApiError,
    clearAiChatSession,
    listOllamaModels,
    loadAiChatSession,
    streamAiChat,
} from './ai-chat-api.js';
import {
    calculateAiChatMaximumWidth,
    calculateAiChatPanelWidth,
} from './ai-chat-panel-service.js';
import {
    queueMermaidDiagramRendering,
} from '../mode-manager/services/mermaid-render-service.js';
import {
    AI_THINKING_LEVEL_OPTIONS,
    isThinkingLevelAvailableForModel,
    normalizeThinkingLevelForModel,
} from './ai-thinking-level-service.js';


function requireElement(id, constructor) {
    const element = document.getElementById(id);
    if (!(element instanceof constructor)) {
        throw new Error(`AI chat element missing: ${id}`);
    }
    return element;
}


function validateMessage(message) {
    if (!message || typeof message !== 'object' || Array.isArray(message)) {
        throw new Error('AI chat message must be an object');
    }
    for (const key of [
        'id',
        'role',
        'content',
        'rendered_content',
        'thinking',
        'rendered_thinking',
        'status',
        'error',
        'provider',
        'model',
    ]) {
        if (typeof message[key] !== 'string') {
            throw new Error(`AI chat message ${key} must be a string`);
        }
    }
    if (!['user', 'assistant'].includes(message.role)) {
        throw new Error('AI chat message role is invalid');
    }
    if (!['complete', 'streaming', 'error'].includes(message.status)) {
        throw new Error('AI chat message status is invalid');
    }
    return message;
}


class AiChatPanelController {
    constructor() {
        this._initialized = false;
        this._messages = [];
        this._expandedThinkingMessageIds = new Set();
        this._isBusy = false;
        this._thinkingStartedAtMs = 0;
        this._thinkingTimerId = 0;
        this._models = [];
        this._isLoadingModels = false;
        this._getSettings = null;
        this._saveSettings = null;
        this._setVisible = null;
        this._openSettings = null;
        this._elements = null;

        this._handleVisibilityChanged = this._handleVisibilityChanged.bind(this);
        this._handleSettingsChanged = this._handleSettingsChanged.bind(this);
        this._handlePointerMove = this._handlePointerMove.bind(this);
        this._handlePointerUp = this._handlePointerUp.bind(this);
        this._handleResizerKeydown = this._handleResizerKeydown.bind(this);
        this._handleWindowResize = this._handleWindowResize.bind(this);
    }

    async init({ getSettings, saveSettings, setVisible, openSettings }) {
        if (this._initialized) {
            return;
        }
        if (typeof getSettings !== 'function') {
            throw new Error('AiChatPanel.init requires getSettings');
        }
        if (typeof saveSettings !== 'function') {
            throw new Error('AiChatPanel.init requires saveSettings');
        }
        if (typeof setVisible !== 'function') {
            throw new Error('AiChatPanel.init requires setVisible');
        }
        if (typeof openSettings !== 'function') {
            throw new Error('AiChatPanel.init requires openSettings');
        }
        this._getSettings = getSettings;
        this._saveSettings = saveSettings;
        this._setVisible = setVisible;
        this._openSettings = openSettings;
        this._elements = {
            panel: requireElement('ai-chat-panel', HTMLElement),
            resizer: requireElement('ai-chat-resizer', HTMLElement),
            messages: requireElement('ai-chat-messages', HTMLElement),
            form: requireElement('ai-chat-form', HTMLFormElement),
            input: requireElement('ai-chat-input', HTMLTextAreaElement),
            send: requireElement('ai-chat-send', HTMLButtonElement),
            model: requireElement('ai-chat-model', HTMLSelectElement),
            thinkingLevel: requireElement('ai-chat-thinking-level', HTMLSelectElement),
            status: requireElement('ai-chat-status', HTMLElement),
            clear: requireElement('ai-chat-clear', HTMLButtonElement),
            settings: requireElement('ai-chat-settings', HTMLButtonElement),
            close: requireElement('ai-chat-close', HTMLButtonElement),
            toggle: requireElement('chat-toggle-button', HTMLButtonElement),
        };
        this._bindEvents();
        this._initialized = true;
        this._syncSettingsControls();
        this._syncResizerAria();
        this._syncToggleButton(document.body.classList.contains('pref-show-ai-chat'));
        if (document.body.classList.contains('pref-show-ai-chat')) {
            await this._loadModels();
        }
        await this._loadSession();
    }

    _bindEvents() {
        const elements = this._elements;
        elements.form.addEventListener('submit', (event) => {
            event.preventDefault();
            void this._submitMessage();
        });
        elements.input.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
                return;
            }
            event.preventDefault();
            elements.form.requestSubmit();
        });
        elements.model.addEventListener('change', () => void this._selectModel());
        elements.thinkingLevel.addEventListener(
            'change',
            () => void this._selectThinkingLevel(),
        );
        elements.close.addEventListener('click', () => void this._setVisible(false));
        elements.toggle.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            const isVisible = document.body.classList.contains('pref-show-ai-chat');
            void this._setVisible(!isVisible);
        });
        elements.settings.addEventListener('click', () => void this._openSettings());
        elements.clear.addEventListener('click', () => void this._clearSession());
        elements.resizer.addEventListener('pointerdown', (event) => {
            if (event.button !== 0) {
                return;
            }
            event.preventDefault();
            document.body.classList.add('ai-chat-resizing');
            window.addEventListener('pointermove', this._handlePointerMove);
            window.addEventListener('pointerup', this._handlePointerUp, { once: true });
            window.addEventListener('pointercancel', this._handlePointerUp, { once: true });
        });
        elements.resizer.addEventListener('keydown', this._handleResizerKeydown);
        window.addEventListener('resize', this._handleWindowResize);
        document.addEventListener('metalist:ai-chat-visibility-changed', this._handleVisibilityChanged);
        document.addEventListener('metalist:ai-settings-changed', this._handleSettingsChanged);
    }

    _handleVisibilityChanged(event) {
        if (!event || !event.detail || typeof event.detail.isVisible !== 'boolean') {
            throw new Error('AI chat visibility event is malformed');
        }
        this._syncToggleButton(event.detail.isVisible);
        if (event.detail.isVisible) {
            this._syncResizerAria();
            this._elements.input.focus();
            void this._loadModels();
        }
    }

    _handleSettingsChanged(event) {
        if (!event || !event.detail || typeof event.detail.reloadModels !== 'boolean') {
            throw new Error('AI settings event is malformed');
        }
        this._syncSettingsControls();
        if (
            event.detail.reloadModels
            && document.body.classList.contains('pref-show-ai-chat')
        ) {
            void this._loadModels();
        }
    }

    _syncToggleButton(isVisible) {
        if (typeof isVisible !== 'boolean') {
            throw new Error('_syncToggleButton requires boolean visibility');
        }
        const actionLabel = isVisible ? 'Hide chat' : 'Show chat';
        this._elements.toggle.setAttribute('aria-pressed', String(isVisible));
        this._elements.toggle.setAttribute('aria-label', actionLabel);
        this._elements.toggle.title = actionLabel;
    }

    _handlePointerMove(event) {
        const width = calculateAiChatPanelWidth({
            pointerClientX: event.clientX,
            viewportWidth: window.innerWidth,
        });
        this._applyPanelWidth(width);
    }

    _handleResizerKeydown(event) {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            return;
        }
        event.preventDefault();
        const currentWidth = this._elements.panel.getBoundingClientRect().width;
        let requestedWidth = currentWidth;
        if (event.key === 'ArrowLeft') {
            requestedWidth += 24;
        } else if (event.key === 'ArrowRight') {
            requestedWidth -= 24;
        } else if (event.key === 'Home') {
            requestedWidth = 280;
        } else {
            requestedWidth = calculateAiChatMaximumWidth(window.innerWidth);
        }
        const width = calculateAiChatPanelWidth({
            pointerClientX: window.innerWidth - requestedWidth,
            viewportWidth: window.innerWidth,
        });
        this._applyPanelWidth(width);
    }

    _handleWindowResize() {
        this._syncResizerAria();
    }

    _applyPanelWidth(width) {
        if (!Number.isFinite(width) || width <= 0) {
            throw new Error('_applyPanelWidth requires positive finite width');
        }
        document.documentElement.style.setProperty('--ai-chat-width', `${width}px`);
        this._elements.resizer.setAttribute('aria-valuenow', String(width));
        this._elements.resizer.setAttribute('aria-valuemin', '280');
        this._elements.resizer.setAttribute(
            'aria-valuemax',
            String(calculateAiChatMaximumWidth(window.innerWidth)),
        );
    }

    _syncResizerAria() {
        let requestedWidth = this._elements.panel.getBoundingClientRect().width;
        if (requestedWidth <= 0) {
            requestedWidth = window.innerWidth / 3;
        }
        const width = calculateAiChatPanelWidth({
            pointerClientX: window.innerWidth - requestedWidth,
            viewportWidth: window.innerWidth,
        });
        this._applyPanelWidth(width);
    }

    _handlePointerUp() {
        document.body.classList.remove('ai-chat-resizing');
        window.removeEventListener('pointermove', this._handlePointerMove);
        window.removeEventListener('pointerup', this._handlePointerUp);
        window.removeEventListener('pointercancel', this._handlePointerUp);
    }

    _syncSettingsControls() {
        const settings = this._getSettings();
        if (!settings || typeof settings !== 'object') {
            throw new Error('AI settings snapshot missing');
        }
        this._elements.model.replaceChildren();
        if (this._models.length === 0) {
            const option = document.createElement('option');
            option.value = settings.model;
            option.textContent = settings.model === '' ? 'No models' : settings.model;
            this._elements.model.appendChild(option);
        } else {
            for (const model of this._models) {
                if (typeof model !== 'string' || model === '') {
                    throw new Error('Ollama model list contains invalid model');
                }
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                this._elements.model.appendChild(option);
            }
            this._elements.model.value = settings.model;
        }

        const thinkingLevel = normalizeThinkingLevelForModel({
            model: settings.model,
            thinkingLevel: settings.thinkingLevel,
        });
        this._elements.thinkingLevel.replaceChildren();
        for (const thinkingOption of AI_THINKING_LEVEL_OPTIONS) {
            const option = document.createElement('option');
            option.value = thinkingOption.value;
            option.textContent = thinkingOption.label;
            option.disabled = !isThinkingLevelAvailableForModel({
                model: settings.model,
                thinkingLevel: thinkingOption.value,
            });
            this._elements.thinkingLevel.appendChild(option);
        }
        this._elements.thinkingLevel.value = thinkingLevel;
        this._elements.input.placeholder = settings.model === ''
            ? 'Connect Ollama to start chatting…'
            : `Message ${settings.model}…`;
        this._syncComposerControlsDisabled();
    }

    _syncComposerControlsDisabled() {
        const settings = this._getSettings();
        const hasModel = settings.model !== '';
        let isModelDisabled = this._isBusy;
        if (this._isLoadingModels) {
            isModelDisabled = true;
        }
        if (this._models.length === 0) {
            isModelDisabled = true;
        }
        this._elements.model.disabled = isModelDisabled;

        let isThinkingLevelDisabled = this._isBusy;
        if (this._isLoadingModels) {
            isThinkingLevelDisabled = true;
        }
        if (!hasModel) {
            isThinkingLevelDisabled = true;
        }
        this._elements.thinkingLevel.disabled = isThinkingLevelDisabled;

        let isSendDisabled = this._isBusy;
        if (this._isLoadingModels) {
            isSendDisabled = true;
        }
        if (this._models.length === 0) {
            isSendDisabled = true;
        }
        this._elements.send.disabled = isSendDisabled;
    }

    async _loadModels() {
        if (this._isLoadingModels || this._isBusy) {
            return;
        }
        this._isLoadingModels = true;
        this._syncComposerControlsDisabled();
        const settings = this._getSettings();
        try {
            const payload = await listOllamaModels(settings);
            if (!payload || !Array.isArray(payload.models)) {
                throw new Error('Ollama model response missing models');
            }
            this._models = payload.models;
            if (this._models.length === 0) {
                this._setStatus('Ollama is connected, but no models are installed.', true);
                return;
            }
            let model = settings.model;
            if (!this._models.includes(model)) {
                model = this._models[0];
            }
            const thinkingLevel = normalizeThinkingLevelForModel({
                model,
                thinkingLevel: settings.thinkingLevel,
            });
            if (model !== settings.model || thinkingLevel !== settings.thinkingLevel) {
                await this._saveSettings({
                    provider: settings.provider,
                    baseUrl: settings.baseUrl,
                    model,
                    thinkingLevel,
                });
            }
            this._setStatus('', false);
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            this._models = [];
            this._setStatus(error.message, true);
        } finally {
            this._isLoadingModels = false;
            this._syncSettingsControls();
        }
    }

    async _selectModel() {
        const settings = this._getSettings();
        const model = this._elements.model.value;
        if (model === '') {
            throw new Error('AI model selection must not be empty');
        }
        const thinkingLevel = normalizeThinkingLevelForModel({
            model,
            thinkingLevel: settings.thinkingLevel,
        });
        await this._saveSettings({
            provider: settings.provider,
            baseUrl: settings.baseUrl,
            model,
            thinkingLevel,
        });
        this._elements.input.focus();
    }

    async _selectThinkingLevel() {
        const settings = this._getSettings();
        const thinkingLevel = normalizeThinkingLevelForModel({
            model: settings.model,
            thinkingLevel: this._elements.thinkingLevel.value,
        });
        await this._saveSettings({
            provider: settings.provider,
            baseUrl: settings.baseUrl,
            model: settings.model,
            thinkingLevel,
        });
        this._elements.input.focus();
    }

    async _loadSession() {
        try {
            const payload = await loadAiChatSession();
            if (!payload || !Array.isArray(payload.messages)) {
                throw new Error('AI chat session response missing messages');
            }
            this._expandedThinkingMessageIds.clear();
            this._messages = payload.messages.map(validateMessage);
            this._render();
            await queueMermaidDiagramRendering(this._elements.messages);
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            this._setStatus(error.message, true);
            throw error;
        }
    }

    async _clearSession() {
        if (this._isBusy) {
            return;
        }
        try {
            await clearAiChatSession();
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            this._setStatus(error.message, true);
            throw error;
        }
        this._expandedThinkingMessageIds.clear();
        this._messages = [];
        this._setStatus('', false);
        this._render();
        this._elements.input.focus();
    }

    async _submitMessage() {
        if (this._isBusy) {
            return;
        }
        if (this._isLoadingModels) {
            return;
        }
        if (this._models.length === 0) {
            this._setStatus('No installed Ollama models are available.', true);
            return;
        }
        const message = this._elements.input.value;
        if (message.trim() === '') {
            return;
        }
        const settings = this._getSettings();
        if (settings.model === '') {
            this._setStatus('Configure an Ollama model first.', true);
            await this._openSettings();
            return;
        }

        const localTurnId = `local-${Date.now()}`;
        this._messages.push(
            {
                id: `${localTurnId}-user`,
                role: 'user',
                content: message,
                rendered_content: '',
                thinking: '',
                rendered_thinking: '',
                status: 'complete',
                error: '',
                provider: settings.provider,
                model: settings.model,
            },
            {
                id: `${localTurnId}-assistant`,
                role: 'assistant',
                content: '',
                rendered_content: '',
                thinking: '',
                rendered_thinking: '',
                status: 'streaming',
                error: '',
                provider: settings.provider,
                model: settings.model,
            },
        );
        const assistantMessage = this._messages[this._messages.length - 1];
        this._elements.input.value = '';
        this._setBusy(true);
        this._startThinkingFeedback();
        this._setStatus('Thinking…', false);
        this._render();

        try {
            await streamAiChat({
                settings,
                message,
                onEvent: (event) => {
                    if (event.type === 'thinking_delta') {
                        assistantMessage.thinking += event.text;
                        assistantMessage.rendered_thinking = event.rendered_text;
                    } else if (event.type === 'content_delta') {
                        this._stopThinkingFeedback();
                        if (assistantMessage.content === '') {
                            this._expandedThinkingMessageIds.delete(assistantMessage.id);
                        }
                        assistantMessage.content += event.text;
                        assistantMessage.rendered_content = event.rendered_text;
                    } else if (event.type === 'done') {
                        assistantMessage.status = 'complete';
                    } else if (event.type === 'error') {
                        assistantMessage.status = 'error';
                        assistantMessage.error = event.message;
                    } else {
                        throw new Error(`Unknown AI chat event: ${event.type}`);
                    }
                    this._render();
                },
            });
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            assistantMessage.status = 'error';
            assistantMessage.error = error.message;
            this._render();
            this._setStatus(error.message, true);
            throw error;
        } finally {
            this._stopThinkingFeedback();
            this._setBusy(false);
        }
        this._setStatus(assistantMessage.status === 'error' ? assistantMessage.error : '', assistantMessage.status === 'error');
        await this._loadSession();
        this._elements.input.focus();
    }

    _setBusy(isBusy) {
        if (typeof isBusy !== 'boolean') {
            throw new Error('_setBusy requires boolean');
        }
        this._isBusy = isBusy;
        this._elements.input.disabled = isBusy;
        this._elements.clear.disabled = isBusy;
        this._syncComposerControlsDisabled();
    }

    _startThinkingFeedback() {
        if (this._thinkingTimerId !== 0 || this._thinkingStartedAtMs !== 0) {
            throw new Error('Thinking feedback timer is already running');
        }
        this._thinkingStartedAtMs = Date.now();
        this._thinkingTimerId = window.setInterval(() => {
            this._syncThinkingElapsed();
        }, 1000);
    }

    _stopThinkingFeedback() {
        if (this._thinkingTimerId !== 0) {
            window.clearInterval(this._thinkingTimerId);
        }
        this._thinkingTimerId = 0;
        this._thinkingStartedAtMs = 0;
    }

    _formatThinkingElapsed() {
        if (this._thinkingStartedAtMs === 0) {
            return '';
        }
        const elapsedSeconds = Math.floor((Date.now() - this._thinkingStartedAtMs) / 1000);
        return elapsedSeconds < 1 ? '' : `${elapsedSeconds}s`;
    }

    _syncThinkingElapsed() {
        const elapsed = this._formatThinkingElapsed();
        for (const element of this._elements.messages.querySelectorAll('.ai-chat-thinking-elapsed')) {
            element.textContent = elapsed;
        }
    }

    _setStatus(message, isError) {
        if (typeof message !== 'string' || typeof isError !== 'boolean') {
            throw new Error('_setStatus requires message and isError');
        }
        this._elements.status.textContent = message;
        this._elements.status.classList.toggle('is-error', isError);
    }

    _render() {
        this._elements.messages.replaceChildren();
        for (const message of this._messages) {
            validateMessage(message);
            const article = document.createElement('article');
            article.className = `ai-chat-message ai-chat-message-${message.role}`;

            if (message.role === 'assistant' && (message.thinking !== '' || message.status === 'streaming')) {
                const hasThinkingText = message.thinking !== '';
                const isActivelyThinking = message.status === 'streaming' && message.content === '';
                const thinking = document.createElement(hasThinkingText ? 'details' : 'div');
                thinking.className = 'ai-chat-thinking';
                if (hasThinkingText) {
                    let shouldOpenThinking = isActivelyThinking;
                    if (this._expandedThinkingMessageIds.has(message.id)) {
                        shouldOpenThinking = true;
                    }
                    thinking.open = shouldOpenThinking;
                    thinking.addEventListener('toggle', () => {
                        if (isActivelyThinking) {
                            return;
                        }
                        if (thinking.open) {
                            this._expandedThinkingMessageIds.add(message.id);
                        } else {
                            this._expandedThinkingMessageIds.delete(message.id);
                        }
                    });
                }
                const heading = document.createElement(hasThinkingText ? 'summary' : 'div');
                heading.className = 'ai-chat-thinking-heading';
                heading.textContent = 'Thinking';
                if (isActivelyThinking) {
                    thinking.classList.add('is-streaming');
                    heading.setAttribute('aria-label', 'Thinking…');
                    const dots = document.createElement('span');
                    dots.className = 'ai-chat-thinking-dots';
                    dots.setAttribute('aria-hidden', 'true');
                    for (let index = 0; index < 3; index += 1) {
                        const dot = document.createElement('span');
                        dot.textContent = '.';
                        dots.appendChild(dot);
                    }
                    heading.appendChild(dots);
                    const elapsed = document.createElement('span');
                    elapsed.className = 'ai-chat-thinking-elapsed';
                    elapsed.textContent = this._formatThinkingElapsed();
                    elapsed.setAttribute('aria-hidden', 'true');
                    heading.appendChild(elapsed);
                }
                thinking.appendChild(heading);
                if (hasThinkingText) {
                    const thinkingText = document.createElement('div');
                    thinkingText.className = 'ai-chat-thinking-content meta-markdown';
                    thinkingText.setAttribute('data-markdown-rendered', 'true');
                    if (message.rendered_thinking === '') {
                        thinkingText.textContent = message.thinking;
                    } else {
                        thinkingText.innerHTML = message.rendered_thinking;
                    }
                    thinking.appendChild(thinkingText);
                }
                article.appendChild(thinking);
            }

            if (message.content !== '') {
                const content = document.createElement('div');
                content.className = 'ai-chat-message-content';
                if (message.role === 'assistant' && message.rendered_content !== '') {
                    content.classList.add('meta-markdown');
                    content.setAttribute('data-markdown-rendered', 'true');
                    content.innerHTML = message.rendered_content;
                } else {
                    content.textContent = message.content;
                }
                article.appendChild(content);
            }
            if (message.status === 'error') {
                const error = document.createElement('div');
                error.className = 'ai-chat-message-error';
                error.textContent = message.error;
                article.appendChild(error);
            }
            this._elements.messages.appendChild(article);
        }
        let isClearDisabled = this._isBusy;
        if (this._messages.length === 0) {
            isClearDisabled = true;
        }
        this._elements.clear.disabled = isClearDisabled;
        this._elements.messages.scrollTop = this._elements.messages.scrollHeight;
    }
}


export const AiChatPanel = new AiChatPanelController();
