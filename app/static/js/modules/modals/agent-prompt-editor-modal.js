import { BaseModal } from './base-modal.js';
import {
    AiApiError,
    loadAgentPromptDefaults,
} from '../ai-chat/ai-chat-api.js';
import {
    MAX_AGENT_PROMPT_CHARACTERS,
    inspectAgentPromptSet,
    validateAgentPromptDefaultsPayload,
    validateAgentPromptSet,
} from '../ai-chat/agent-prompt-service.js';


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


function resolveEffectivePrompts(defaults, overrides) {
    const resolved = {};
    for (const key of ['systemPrompt', 'finalResponsePrompt', 'toolResultPrompt']) {
        const override = overrides[key];
        if (override !== null && typeof override !== 'string') {
            throw new Error(`Agent prompt override ${key} must be a string or null`);
        }
        resolved[key] = override === null ? defaults[key] : override;
    }
    return validateAgentPromptSet(resolved);
}


export class AgentPromptEditorModal extends BaseModal {
    constructor(readOverrides, saveOverrides, resetOverrides) {
        super('agentPromptEditorModal', 'agent-prompt-editor-modal');
        if (typeof readOverrides !== 'function') {
            throw new Error('AgentPromptEditorModal requires readOverrides');
        }
        if (typeof saveOverrides !== 'function') {
            throw new Error('AgentPromptEditorModal requires saveOverrides');
        }
        if (typeof resetOverrides !== 'function') {
            throw new Error('AgentPromptEditorModal requires resetOverrides');
        }
        this._readOverrides = readOverrides;
        this._saveOverrides = saveOverrides;
        this._resetOverrides = resetOverrides;
    }

    getInitialModalState() {
        return {
            systemPrompt: '',
            finalResponsePrompt: '',
            toolResultPrompt: '',
            isLoading: true,
            isSaving: false,
            hasOverrides: false,
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
        const disabled = state.isSaving ? 'disabled' : '';
        const sourceLabel = state.hasOverrides
            ? 'Using namespace-specific overrides.'
            : 'Using packaged defaults.';
        const editor = state.isLoading ? `
            <p class="agent-prompt-editor-loading" role="status">Loading packaged prompts…</p>
        ` : `
            <div class="agent-prompt-editor-fields">
                <details class="agent-prompt-editor-field" data-prompt="system" open>
                    <summary>Agent system prompt</summary>
                    <p>Defines the agent role, action loop, safety boundaries, and action-selection instructions.</p>
                    <textarea id="agent-prompt-system" maxlength="${MAX_AGENT_PROMPT_CHARACTERS}" spellcheck="false" ${disabled}>${escapeHtml(state.systemPrompt)}</textarea>
                </details>
                <details class="agent-prompt-editor-field" data-prompt="final-response">
                    <summary>Final-response control prompt</summary>
                    <p>Must contain exactly one <code>{basis}</code> placeholder. Use doubled braces for literal braces.</p>
                    <textarea id="agent-prompt-final-response" maxlength="${MAX_AGENT_PROMPT_CHARACTERS}" spellcheck="false" ${disabled}>${escapeHtml(state.finalResponsePrompt)}</textarea>
                </details>
                <details class="agent-prompt-editor-field" data-prompt="tool-result">
                    <summary>Tool-result wrapper prompt</summary>
                    <p>Must contain exactly one <code>{action_name}</code> and one <code>{payload_json}</code> placeholder. Use doubled braces for literal braces.</p>
                    <textarea id="agent-prompt-tool-result" maxlength="${MAX_AGENT_PROMPT_CHARACTERS}" spellcheck="false" ${disabled}>${escapeHtml(state.toolResultPrompt)}</textarea>
                </details>
            </div>
        `;
        modalElement.innerHTML = `
            <div class="modal-content agent-prompt-editor-modal-content">
                <h2>Agent Prompts</h2>
                <p class="agent-prompt-editor-description">
                    Inspect or override the prompts MetaList sends during agent runs. Overrides are
                    scoped to this namespace, apply to the next run, and are not conversation history.
                </p>
                <p class="agent-prompt-editor-source">${sourceLabel}</p>
                ${editor}
                <p class="error-message" role="alert">${escapeHtml(state.error)}</p>
                <div class="form-actions agent-prompt-editor-actions">
                    <button type="button" class="secondary-btn" id="agent-prompt-reset" ${state.isLoading || state.isSaving ? 'disabled' : ''}>Restore packaged defaults</button>
                    <button type="button" class="primary-btn" id="agent-prompt-save" data-modal-enter-action ${state.isLoading || state.isSaving ? 'disabled' : ''}>${state.isSaving ? 'Saving…' : 'Save overrides'}</button>
                </div>
            </div>
        `;
        this._setupControls();
    }

    _setupControls() {
        const state = this.getModalState();
        const resetButton = document.getElementById('agent-prompt-reset');
        const saveButton = document.getElementById('agent-prompt-save');
        if (!(resetButton instanceof HTMLButtonElement)) {
            throw new Error('Agent prompt reset button missing');
        }
        if (!(saveButton instanceof HTMLButtonElement)) {
            throw new Error('Agent prompt save button missing');
        }
        resetButton.onclick = () => void this._handleReset();
        saveButton.onclick = () => void this._handleSave();
        if (state.isLoading) {
            return;
        }
        const systemPrompt = document.getElementById('agent-prompt-system');
        const finalResponsePrompt = document.getElementById('agent-prompt-final-response');
        const toolResultPrompt = document.getElementById('agent-prompt-tool-result');
        if (!(systemPrompt instanceof HTMLTextAreaElement)) {
            throw new Error('Agent system prompt input missing');
        }
        if (!(finalResponsePrompt instanceof HTMLTextAreaElement)) {
            throw new Error('Agent final-response prompt input missing');
        }
        if (!(toolResultPrompt instanceof HTMLTextAreaElement)) {
            throw new Error('Agent tool-result prompt input missing');
        }
        systemPrompt.oninput = () => this.updateModalState({
            systemPrompt: systemPrompt.value,
            error: '',
        });
        finalResponsePrompt.oninput = () => this.updateModalState({
            finalResponsePrompt: finalResponsePrompt.value,
            error: '',
        });
        toolResultPrompt.oninput = () => this.updateModalState({
            toolResultPrompt: toolResultPrompt.value,
            error: '',
        });
    }

    onOpen() {
        void this._loadPrompts();
    }

    canRequestClose() {
        return this.getModalState().isSaving !== true;
    }

    async _loadPrompts() {
        let payload = null;
        let loadError = '';
        try {
            payload = await loadAgentPromptDefaults();
        } catch (error) {
            if (!(error instanceof AiApiError)) {
                throw error;
            }
            loadError = error.message;
        }
        if (!this.isOpen) {
            return;
        }
        if (loadError !== '') {
            this.updateModalState({
                isLoading: false,
                error: loadError,
            });
        }
        if (payload !== null) {
            const defaults = validateAgentPromptDefaultsPayload(payload);
            const overrides = this._readOverrides();
            const prompts = resolveEffectivePrompts(defaults, overrides);
            this.updateModalState({
                ...prompts,
                isLoading: false,
                hasOverrides: Object.values(overrides).some((value) => value !== null),
                error: '',
            });
        }
        this.renderModalContent();
    }

    async _handleSave() {
        const state = this.getModalState();
        const inspected = inspectAgentPromptSet({
            systemPrompt: state.systemPrompt,
            finalResponsePrompt: state.finalResponsePrompt,
            toolResultPrompt: state.toolResultPrompt,
        });
        if (inspected.error !== '') {
            this.updateModalState({ error: inspected.error });
            this.renderModalContent();
            return;
        }
        this.updateModalState({ isSaving: true, error: '' });
        this.renderModalContent();
        await this._saveOverrides(inspected.prompts);
        this.close();
    }

    async _handleReset() {
        this.updateModalState({ isSaving: true, error: '' });
        this.renderModalContent();
        await this._resetOverrides();
        this.close();
    }
}
