import {
    AiApiError,
    clearAiChatSession,
    loadAiChatSession,
    streamAiChat,
} from './ai-chat-api.js';
import {
    calculateAiChatMaximumWidth,
    calculateAiChatPanelWidth,
} from './ai-chat-panel-service.js';


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
    for (const key of ['id', 'role', 'content', 'thinking', 'status', 'error', 'provider', 'model']) {
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
        this._isBusy = false;
        this._getSettings = null;
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

    async init({ getSettings, setVisible, openSettings }) {
        if (this._initialized) {
            return;
        }
        if (typeof getSettings !== 'function') {
            throw new Error('AiChatPanel.init requires getSettings');
        }
        if (typeof setVisible !== 'function') {
            throw new Error('AiChatPanel.init requires setVisible');
        }
        if (typeof openSettings !== 'function') {
            throw new Error('AiChatPanel.init requires openSettings');
        }
        this._getSettings = getSettings;
        this._setVisible = setVisible;
        this._openSettings = openSettings;
        this._elements = {
            panel: requireElement('ai-chat-panel', HTMLElement),
            resizer: requireElement('ai-chat-resizer', HTMLElement),
            messages: requireElement('ai-chat-messages', HTMLElement),
            form: requireElement('ai-chat-form', HTMLFormElement),
            input: requireElement('ai-chat-input', HTMLTextAreaElement),
            send: requireElement('ai-chat-send', HTMLButtonElement),
            status: requireElement('ai-chat-status', HTMLElement),
            modelLabel: requireElement('ai-chat-model-label', HTMLElement),
            clear: requireElement('ai-chat-clear', HTMLButtonElement),
            settings: requireElement('ai-chat-settings', HTMLButtonElement),
            close: requireElement('ai-chat-close', HTMLButtonElement),
            toggle: requireElement('chat-toggle-button', HTMLButtonElement),
        };
        this._bindEvents();
        this._initialized = true;
        this._syncSettingsLabel();
        this._syncResizerAria();
        this._syncToggleButton(document.body.classList.contains('pref-show-ai-chat'));
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
        }
    }

    _handleSettingsChanged() {
        this._syncSettingsLabel();
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

    _syncSettingsLabel() {
        const settings = this._getSettings();
        if (!settings || typeof settings !== 'object') {
            throw new Error('AI settings snapshot missing');
        }
        this._elements.modelLabel.textContent = settings.model === ''
            ? 'Ollama · not configured'
            : `Ollama · ${settings.model}`;
        this._elements.input.placeholder = settings.model === ''
            ? 'Configure Ollama to start chatting…'
            : `Message ${settings.model}…`;
    }

    async _loadSession() {
        try {
            const payload = await loadAiChatSession();
            if (!payload || !Array.isArray(payload.messages)) {
                throw new Error('AI chat session response missing messages');
            }
            this._messages = payload.messages.map(validateMessage);
            this._render();
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
        this._messages = [];
        this._setStatus('', false);
        this._render();
        this._elements.input.focus();
    }

    async _submitMessage() {
        if (this._isBusy) {
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
                thinking: '',
                status: 'complete',
                error: '',
                provider: settings.provider,
                model: settings.model,
            },
            {
                id: `${localTurnId}-assistant`,
                role: 'assistant',
                content: '',
                thinking: '',
                status: 'streaming',
                error: '',
                provider: settings.provider,
                model: settings.model,
            },
        );
        const assistantMessage = this._messages[this._messages.length - 1];
        this._elements.input.value = '';
        this._setBusy(true);
        this._setStatus('Thinking…', false);
        this._render();

        try {
            await streamAiChat({
                settings,
                message,
                onEvent: (event) => {
                    if (event.type === 'thinking_delta') {
                        assistantMessage.thinking += event.text;
                    } else if (event.type === 'content_delta') {
                        assistantMessage.content += event.text;
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
        this._elements.send.disabled = isBusy;
        this._elements.clear.disabled = isBusy;
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
                const thinking = document.createElement('details');
                thinking.className = 'ai-chat-thinking';
                thinking.open = message.status === 'streaming';
                const summary = document.createElement('summary');
                summary.textContent = 'Thinking';
                if (message.status === 'streaming') {
                    thinking.classList.add('is-streaming');
                    summary.setAttribute('aria-label', 'Thinking…');
                    const dots = document.createElement('span');
                    dots.className = 'ai-chat-thinking-dots';
                    dots.setAttribute('aria-hidden', 'true');
                    for (let index = 0; index < 3; index += 1) {
                        const dot = document.createElement('span');
                        dot.textContent = '.';
                        dots.appendChild(dot);
                    }
                    summary.appendChild(dots);
                }
                const thinkingText = document.createElement('pre');
                thinkingText.textContent = message.thinking === '' ? 'Waiting for reasoning…' : message.thinking;
                thinking.append(summary, thinkingText);
                article.appendChild(thinking);
            }

            if (message.content !== '') {
                const content = document.createElement('div');
                content.className = 'ai-chat-message-content';
                content.textContent = message.content;
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
