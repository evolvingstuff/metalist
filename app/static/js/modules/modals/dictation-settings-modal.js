import { ApplicationState } from '../application-state.js';
import { BaseModal } from './base-modal.js';
import { isValidDictationTagPhrase } from '../mode-manager/services/dictation-note-paste.js';

const PHRASE_INPUT_ID = 'dictation-tag-phrase';

// Dictation settings: the phrase that, in dictated text pasted into a note
// ("start tags" by default), starts the tags (docs/ui/dictation-paste.md).
export class DictationSettingsModal extends BaseModal {
    constructor(readPhrase, savePhrase) {
        super('dictationSettingsModal', 'dictation-settings-modal');
        if (typeof readPhrase !== 'function') {
            throw new Error('DictationSettingsModal requires readPhrase');
        }
        if (typeof savePhrase !== 'function') {
            throw new Error('DictationSettingsModal requires savePhrase');
        }
        this._readPhrase = readPhrase;
        this._savePhrase = savePhrase;

        ApplicationState.own(this, 'DictationSettingsModal', new.target === DictationSettingsModal);
    }

    getInitialModalState() {
        return { phrase: this._readPhrase(), error: '', saving: false };
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
        const input = document.getElementById(PHRASE_INPUT_ID);
        if (input instanceof HTMLInputElement) {
            input.focus();
            input.select();
        }
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }
        const state = this.getModalState();
        let disabled = '';
        if (state.saving === true) disabled = ' disabled';
        let errorHtml = '';
        if (state.error !== '') errorHtml = `<p class="dictation-settings-error" role="alert">${state.error}</p>`;
        modalElement.innerHTML = `
            <div class="modal-content dictation-settings-modal-content">
                <h2>Dictation Settings</h2>
                <p class="note-layout-description">When you paste dictated text into a note, say this phrase
                    to start the tags: everything after it is added to the note's tags. For example
                    "Here is my content. Start tags. Neural network." adds the content and the tag neural-network.</p>
                <label class="dictation-settings-field" for="${PHRASE_INPUT_ID}">Phrase that starts tags</label>
                <input type="text" id="${PHRASE_INPUT_ID}" spellcheck="false" autocomplete="off"${disabled}>
                ${errorHtml}
                <div class="form-actions">
                    <button type="button" class="save-btn" data-dictation-save data-modal-enter-action${disabled}>Save</button>
                </div>
            </div>
        `;
        // Set as a property, never as markup: a rejected entry may hold any character.
        document.getElementById(PHRASE_INPUT_ID).value = state.phrase;
        const saveButton = modalElement.querySelector('[data-dictation-save]');
        if (!(saveButton instanceof HTMLButtonElement)) {
            throw new Error('Dictation settings Save button missing');
        }
        saveButton.onclick = async () => this._handleSave();
    }

    async _handleSave() {
        const input = document.getElementById(PHRASE_INPUT_ID);
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('Dictation phrase input missing');
        }
        const phrase = input.value.trim().replace(/\s+/g, ' ');
        if (!isValidDictationTagPhrase(phrase)) {
            this.updateModalState({
                phrase,
                error: 'Use words of letters only (2 to 64 characters), such as "start tags" or "armadillo".',
            });
            this.renderModalContent();
            const shown = document.getElementById(PHRASE_INPUT_ID);
            shown.focus();
            shown.select();
            return;
        }
        this.updateModalState({ phrase, error: '', saving: true });
        this.renderModalContent();
        await this._savePhrase(phrase);
        this.close();
    }
}
