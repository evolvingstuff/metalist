import { AiApiError } from '../ai-chat/ai-chat-api.js';
import { BaseModal } from './base-modal.js';


function escapeHtml(value) {
    if (typeof value !== 'string') {
        throw new Error('escapeHtml requires string');
    }
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}


function buildModelOptions(models, selectedModel) {
    if (!Array.isArray(models)) {
        throw new Error('buildModelOptions requires models array');
    }
    const options = [...models];
    if (selectedModel !== '' && !options.includes(selectedModel)) {
        options.unshift(selectedModel);
    }
    if (options.length === 0) {
        return '<option value="">Load models from Ollama</option>';
    }
    return options.map((model) => {
        if (typeof model !== 'string' || model === '') {
            throw new Error('AI model option must be a non-empty string');
        }
        const selected = model === selectedModel ? ' selected' : '';
        const safeModel = escapeHtml(model);
        return `<option value="${safeModel}"${selected}>${safeModel}</option>`;
    }).join('');
}


export class AiAgentSettingsModal extends BaseModal {
    constructor(readSettings, saveSettings, listModels) {
        super('aiAgentSettingsModal', 'ai-agent-settings-modal');
        if (typeof readSettings !== 'function') {
            throw new Error('AiAgentSettingsModal requires readSettings');
        }
        if (typeof saveSettings !== 'function') {
            throw new Error('AiAgentSettingsModal requires saveSettings');
        }
        if (typeof listModels !== 'function') {
            throw new Error('AiAgentSettingsModal requires listModels');
        }
        this._readSettings = readSettings;
        this._saveSettings = saveSettings;
        this._listModels = listModels;
    }

    getInitialModalState() {
        const settings = this._readSettings();
        return {
            provider: settings.provider,
            baseUrl: settings.baseUrl,
            model: settings.model,
            models: [],
            loading: false,
            error: '',
            connected: false,
        };
    }

    showModalElement() {
        let modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            modalElement = document.createElement('div');
            modalElement.id = this.modalElementId;
            modalElement.className = 'modal';
            modalElement.style.display = 'none';
            document.body.appendChild(modalElement);
        }
        this.renderModalContent();
        modalElement.style.display = 'block';
    }

    onOpen() {
        void this._loadModels();
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!(modalElement instanceof HTMLElement)) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }
        const state = this.getModalState();
        if (!Array.isArray(state.models)) {
            throw new Error('AI settings models state must be an array');
        }
        const loading = state.loading === true;
        const disabled = loading ? ' disabled' : '';
        const status = loading
            ? 'Connecting to Ollama…'
            : (state.connected ? `${state.models.length} model${state.models.length === 1 ? '' : 's'} available` : '');

        modalElement.innerHTML = `
            <div class="modal-content ai-agent-settings-modal-content">
                <h2>AI Agent Settings</h2>
                <p class="ai-agent-settings-description">Configure the temporary unmanaged Ollama connection used by standalone chat. Only loopback URLs are accepted, and MetaList note data is not sent to the model.</p>
                <div class="ai-agent-settings-controls">
                    <label for="ai-agent-provider">
                        <span>Provider</span>
                        <select id="ai-agent-provider" disabled>
                            <option value="ollama" selected>Ollama</option>
                        </select>
                    </label>
                    <label for="ai-agent-base-url">
                        <span>Ollama URL (loopback only)</span>
                        <input id="ai-agent-base-url" type="url" value="${escapeHtml(state.baseUrl)}" placeholder="http://127.0.0.1:11434"${disabled}>
                    </label>
                    <label for="ai-agent-model">
                        <span>Model</span>
                        <div class="ai-agent-model-row">
                            <select id="ai-agent-model"${disabled}>${buildModelOptions(state.models, state.model)}</select>
                            <button id="ai-agent-refresh-models" type="button"${disabled}>${loading ? 'Loading…' : 'Refresh'}</button>
                        </div>
                    </label>
                </div>
                <p class="ai-agent-connection-status">${escapeHtml(status)}</p>
                <p class="error-message">${escapeHtml(state.error)}</p>
                <div class="form-actions">
                    <button type="button" class="primary-btn" id="ai-agent-save" data-modal-enter-action${disabled}>Save</button>
                    <button type="button" class="secondary-btn" id="ai-agent-cancel"${disabled}>Cancel</button>
                </div>
            </div>
        `;
        this._setupControls();
    }

    _setupControls() {
        const baseUrlInput = document.getElementById('ai-agent-base-url');
        const modelSelect = document.getElementById('ai-agent-model');
        const refreshButton = document.getElementById('ai-agent-refresh-models');
        const saveButton = document.getElementById('ai-agent-save');
        const cancelButton = document.getElementById('ai-agent-cancel');
        if (!(baseUrlInput instanceof HTMLInputElement)) {
            throw new Error('AI settings URL input missing');
        }
        if (!(modelSelect instanceof HTMLSelectElement)) {
            throw new Error('AI settings model select missing');
        }
        if (!(refreshButton instanceof HTMLButtonElement)) {
            throw new Error('AI settings refresh button missing');
        }
        if (!(saveButton instanceof HTMLButtonElement)) {
            throw new Error('AI settings save button missing');
        }
        if (!(cancelButton instanceof HTMLButtonElement)) {
            throw new Error('AI settings cancel button missing');
        }

        baseUrlInput.oninput = () => {
            this.updateModalState({ baseUrl: baseUrlInput.value, connected: false, error: '' });
        };
        modelSelect.onchange = () => {
            this.updateModalState({ model: modelSelect.value, error: '' });
        };
        refreshButton.onclick = () => void this._loadModels();
        saveButton.onclick = () => void this._handleSave();
        cancelButton.onclick = () => this.close();
    }

    async _loadModels() {
        const state = this.getModalState();
        const listModels = this._listModels;
        this.updateModalState({ loading: true, error: '', connected: false });
        this.renderModalContent();
        try {
            const payload = await listModels({
                provider: 'ollama',
                baseUrl: state.baseUrl,
            });
            if (!payload || !Array.isArray(payload.models)) {
                throw new Error('Ollama model response missing models');
            }
            const selectedModel = payload.models.includes(state.model)
                ? state.model
                : (payload.models[0] ?? '');
            this.updateModalState({
                loading: false,
                models: payload.models,
                model: selectedModel,
                connected: true,
                error: payload.models.length === 0 ? 'Ollama is connected, but no models are installed.' : '',
            });
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            this.updateModalState({
                loading: false,
                connected: false,
                error: error.message,
            });
            this.renderModalContent();
            throw error;
        }
        this.renderModalContent();
    }

    async _handleSave() {
        const state = this.getModalState();
        if (typeof state.model !== 'string' || state.model === '') {
            this.updateModalState({ error: 'Select an installed Ollama model before saving.' });
            this.renderModalContent();
            return;
        }
        await this._saveSettings({
            provider: 'ollama',
            baseUrl: state.baseUrl,
            model: state.model,
        });
        this.close();
    }
}
