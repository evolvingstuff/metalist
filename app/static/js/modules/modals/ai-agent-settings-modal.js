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
        modalElement.innerHTML = `
            <div class="modal-content ai-agent-settings-modal-content">
                <h2>AI Agent Settings</h2>
                <p class="ai-agent-settings-description">Configure the temporary unmanaged Ollama connection used by standalone chat. Select the model and thinking level directly beside Send in the chat panel.</p>
                <div class="ai-agent-settings-controls">
                    <label for="ai-agent-provider">
                        <span>Provider</span>
                        <select id="ai-agent-provider" disabled>
                            <option value="ollama" selected>Ollama</option>
                        </select>
                    </label>
                    <label for="ai-agent-base-url">
                        <span>Ollama URL (loopback only)</span>
                        <input id="ai-agent-base-url" type="url" value="${escapeHtml(state.baseUrl)}" placeholder="http://127.0.0.1:11434">
                    </label>
                </div>
                <p class="error-message">${escapeHtml(state.error)}</p>
                <div class="form-actions">
                    <button type="button" class="primary-btn" id="ai-agent-save" data-modal-enter-action>Save</button>
                    <button type="button" class="secondary-btn" id="ai-agent-cancel">Cancel</button>
                </div>
            </div>
        `;
        this._setupControls();
    }

    _setupControls() {
        const baseUrlInput = document.getElementById('ai-agent-base-url');
        const saveButton = document.getElementById('ai-agent-save');
        const cancelButton = document.getElementById('ai-agent-cancel');
        if (!(baseUrlInput instanceof HTMLInputElement)) {
            throw new Error('AI settings URL input missing');
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
        saveButton.onclick = () => void this._handleSave();
        cancelButton.onclick = () => this.close();
    }

    async _handleSave() {
        const state = this.getModalState();
        await this._saveSettings({
            provider: 'ollama',
            baseUrl: state.baseUrl,
        });
        this.close();
    }
}
