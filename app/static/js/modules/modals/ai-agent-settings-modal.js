import { BaseModal } from './base-modal.js';
import {
    AiApiError,
    listOllamaModels,
    pullOllamaModel,
} from '../ai-chat/ai-chat-api.js';


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


function renderInstalledModelOptions(state) {
    if (!Array.isArray(state.installedModels)) {
        throw new Error('AI settings installed models must be an array');
    }
    if (state.isLoadingModels) {
        return '<option value="">Loading models…</option>';
    }
    if (state.installedModels.length === 0) {
        return '<option value="">No downloaded models</option>';
    }
    const hasSelectedModel = state.installedModels.includes(state.model);
    const placeholderSelected = hasSelectedModel ? '' : 'selected';
    let options = `<option value="" disabled ${placeholderSelected}>Select model</option>`;
    for (const model of state.installedModels) {
        if (typeof model !== 'string' || model === '') {
            throw new Error('AI settings installed model name is invalid');
        }
        const selected = model === state.model ? 'selected' : '';
        options += `<option value="${escapeHtml(model)}" ${selected}>${escapeHtml(model)}</option>`;
    }
    return options;
}


export class AiAgentSettingsModal extends BaseModal {
    constructor(readSettings, saveSettings) {
        super('aiAgentSettingsModal', 'ai-agent-settings-modal');
        if (typeof readSettings !== 'function') {
            throw new Error('AiAgentSettingsModal requires readSettings');
        }
        if (typeof saveSettings !== 'function') {
            throw new Error('AiAgentSettingsModal requires saveSettings');
        }
        this._readSettings = readSettings;
        this._saveSettings = saveSettings;
    }

    getInitialModalState() {
        const settings = this._readSettings();
        return {
            provider: settings.provider,
            baseUrl: settings.baseUrl,
            model: settings.model,
            installedModels: [],
            isLoadingModels: false,
            downloadModel: '',
            isDownloading: false,
            downloadStatus: '',
            downloadCompleted: 0,
            downloadTotal: 0,
            error: '',
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

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!(modalElement instanceof HTMLElement)) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }
        const state = this.getModalState();
        const disabledAttribute = state.isDownloading ? 'disabled' : '';
        const progressHiddenAttribute = state.downloadTotal > 0 ? '' : 'hidden';
        const progressMaximum = state.downloadTotal > 0 ? state.downloadTotal : 1;
        const installedModelOptions = renderInstalledModelOptions(state);
        const modelSelectDisabled = (
            state.isDownloading
            || state.isLoadingModels
            || state.installedModels.length === 0
        ) ? 'disabled' : '';
        const saveDisabled = (
            state.isDownloading
            || state.isLoadingModels
            || !state.installedModels.includes(state.model)
        ) ? 'disabled' : '';
        modalElement.innerHTML = `
            <div class="modal-content ai-agent-settings-modal-content">
                <h2>AI Agent Settings</h2>
                <div class="ai-agent-settings-controls">
                    <label for="ai-agent-provider">
                        <span>Provider</span>
                        <select id="ai-agent-provider" disabled>
                            <option value="ollama" selected>Ollama</option>
                        </select>
                    </label>
                    <label for="ai-agent-base-url">
                        <span>Ollama URL (loopback only)</span>
                        <input id="ai-agent-base-url" type="url" value="${escapeHtml(state.baseUrl)}" placeholder="http://127.0.0.1:11434" ${disabledAttribute}>
                    </label>
                    <label for="ai-agent-installed-model">
                        <span>Downloaded model</span>
                        <select id="ai-agent-installed-model" ${modelSelectDisabled}>
                            ${installedModelOptions}
                        </select>
                    </label>
                </div>
                <section class="ai-agent-model-download" aria-labelledby="ai-agent-model-download-title">
                    <h3 id="ai-agent-model-download-title">Download an Ollama model</h3>
                    <p>
                        Find the exact model and size in the
                        <a href="https://ollama.com/library" target="_blank" rel="noopener noreferrer">Ollama model library</a>,
                        then download it to this Ollama installation.
                    </p>
                    <div class="ai-agent-model-download-row">
                        <label for="ai-agent-download-model">
                            <span>Model name</span>
                            <input id="ai-agent-download-model" type="text" value="${escapeHtml(state.downloadModel)}" placeholder="gemma3:4b" maxlength="200" autocomplete="off" ${disabledAttribute}>
                        </label>
                        <button type="button" class="secondary-btn" id="ai-agent-download" ${disabledAttribute}>${state.isDownloading ? 'Downloading…' : 'Download'}</button>
                    </div>
                    <progress
                        id="ai-agent-download-progress"
                        max="${progressMaximum}"
                        value="${state.downloadCompleted}"
                        ${progressHiddenAttribute}
                    ></progress>
                    <p id="ai-agent-download-status" class="ai-agent-download-status" role="status">${escapeHtml(state.downloadStatus)}</p>
                </section>
                <p class="error-message">${escapeHtml(state.error)}</p>
                <div class="form-actions">
                    <button type="button" class="primary-btn" id="ai-agent-save" data-modal-enter-action ${saveDisabled}>Save</button>
                    <button type="button" class="secondary-btn" id="ai-agent-cancel" ${disabledAttribute}>Cancel</button>
                </div>
            </div>
        `;
        this._setupControls();
    }

    _setupControls() {
        const baseUrlInput = document.getElementById('ai-agent-base-url');
        const installedModelSelect = document.getElementById('ai-agent-installed-model');
        const modelInput = document.getElementById('ai-agent-download-model');
        const downloadButton = document.getElementById('ai-agent-download');
        const saveButton = document.getElementById('ai-agent-save');
        const cancelButton = document.getElementById('ai-agent-cancel');
        if (!(baseUrlInput instanceof HTMLInputElement)) {
            throw new Error('AI settings URL input missing');
        }
        if (!(modelInput instanceof HTMLInputElement)) {
            throw new Error('AI settings download model input missing');
        }
        if (!(installedModelSelect instanceof HTMLSelectElement)) {
            throw new Error('AI settings installed model selector missing');
        }
        if (!(downloadButton instanceof HTMLButtonElement)) {
            throw new Error('AI settings download button missing');
        }
        if (!(saveButton instanceof HTMLButtonElement)) {
            throw new Error('AI settings save button missing');
        }
        if (!(cancelButton instanceof HTMLButtonElement)) {
            throw new Error('AI settings cancel button missing');
        }

        baseUrlInput.oninput = () => {
            this.updateModalState({ baseUrl: baseUrlInput.value, error: '' });
        };
        baseUrlInput.onchange = () => void this._loadInstalledModels();
        installedModelSelect.onchange = () => {
            this.updateModalState({ model: installedModelSelect.value, error: '' });
            this.renderModalContent();
        };
        modelInput.oninput = () => {
            this.updateModalState({ downloadModel: modelInput.value, error: '' });
        };
        downloadButton.onclick = () => void this._handleDownload();
        saveButton.onclick = () => void this._handleSave();
        cancelButton.onclick = () => this.requestClose();
    }

    onOpen() {
        void this._loadInstalledModels();
    }

    canRequestClose() {
        const state = this.getModalState();
        return state.isDownloading !== true;
    }

    async _loadInstalledModels() {
        const state = this.getModalState();
        if (state.isLoadingModels) {
            return;
        }
        this.updateModalState({ isLoadingModels: true, error: '' });
        this.renderModalContent();
        try {
            const payload = await listOllamaModels({
                provider: 'ollama',
                baseUrl: state.baseUrl,
            });
            if (!payload || !Array.isArray(payload.models)) {
                throw new Error('Ollama model response missing models');
            }
            let model = state.model;
            if (!payload.models.includes(model)) {
                model = '';
            }
            this.updateModalState({ installedModels: payload.models, model });
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            this.updateModalState({ installedModels: [], model: '', error: error.message });
        } finally {
            this.updateModalState({ isLoadingModels: false });
            this.renderModalContent();
        }
    }

    _updateDownloadProgress(event) {
        if (!event || typeof event !== 'object' || Array.isArray(event)) {
            throw new Error('Download progress event must be an object');
        }
        if (event.type === 'error') {
            this.updateModalState({
                error: event.message,
                downloadStatus: '',
                downloadCompleted: 0,
                downloadTotal: 0,
            });
        } else if (event.type === 'progress' || event.type === 'done') {
            this.updateModalState({
                error: '',
                downloadStatus: event.status,
                downloadCompleted: event.completed,
                downloadTotal: event.total,
            });
        } else {
            throw new Error(`Unknown download progress event: ${event.type}`);
        }
        const state = this.getModalState();
        const progress = document.getElementById('ai-agent-download-progress');
        const status = document.getElementById('ai-agent-download-status');
        const error = document.querySelector('#ai-agent-settings-modal .error-message');
        if (!(progress instanceof HTMLProgressElement)) {
            throw new Error('AI settings download progress missing');
        }
        if (!(status instanceof HTMLElement)) {
            throw new Error('AI settings download status missing');
        }
        if (!(error instanceof HTMLElement)) {
            throw new Error('AI settings error message missing');
        }
        progress.hidden = state.downloadTotal === 0;
        if (state.downloadTotal > 0) {
            progress.max = state.downloadTotal;
            progress.value = state.downloadCompleted;
        }
        status.textContent = state.downloadStatus;
        error.textContent = state.error;
    }

    async _handleDownload() {
        const state = this.getModalState();
        const model = state.downloadModel.trim();
        if (model === '') {
            this.updateModalState({ error: 'Enter an Ollama model name to download.' });
            this.renderModalContent();
            return;
        }
        this.updateModalState({
            isDownloading: true,
            downloadStatus: 'Starting download…',
            downloadCompleted: 0,
            downloadTotal: 0,
            error: '',
        });
        this.renderModalContent();
        let didComplete = false;
        try {
            await pullOllamaModel({
                settings: {
                    provider: 'ollama',
                    baseUrl: state.baseUrl,
                },
                model,
                onEvent: (event) => {
                    this._updateDownloadProgress(event);
                    if (event.type === 'done') {
                        didComplete = true;
                    }
                },
            });
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            this.updateModalState({
                error: error.message,
                downloadStatus: '',
                downloadCompleted: 0,
                downloadTotal: 0,
            });
        } finally {
            this.updateModalState({ isDownloading: false });
            this.renderModalContent();
        }
        if (didComplete) {
            await this._loadInstalledModels();
            this.updateModalState({
                downloadStatus: `Downloaded ${model}. Select it above when ready.`,
                downloadCompleted: 0,
                downloadTotal: 0,
            });
            this.renderModalContent();
        }
    }

    async _handleSave() {
        const state = this.getModalState();
        if (!state.installedModels.includes(state.model)) {
            throw new Error('AI settings require a downloaded model selection');
        }
        await this._saveSettings({
            provider: 'ollama',
            baseUrl: state.baseUrl,
            model: state.model,
        });
        this.close();
    }
}
