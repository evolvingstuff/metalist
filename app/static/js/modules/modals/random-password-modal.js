import { BaseModal } from './base-modal.js';
import {
    DEFAULT_PASSWORD_CHARSET,
    DEFAULT_PASSWORD_LENGTH,
    generateRandomPassword,
    normalizePasswordCharset,
} from '../password-generator.js';
import { rememberGeneratedPasswordCopy } from '../mode-manager/services/password-clipboard-service.js';

const COPY_HINT_DEFAULT = 'Copy to clipboard. Pasting into an empty note will add @password automatically.';

export class RandomPasswordModal extends BaseModal {
    constructor() {
        super('randomPasswordModal', 'random-password-modal');
    }

    getInitialModalState() {
        return {
            length: DEFAULT_PASSWORD_LENGTH,
            charsetInput: DEFAULT_PASSWORD_CHARSET,
            result: '',
            error: '',
            copyStatus: '',
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
        this.renderModalContent();
        this.regeneratePassword();
    }

    onClose() {
        this.updateModalState(this.getInitialModalState());
    }

    onKeyDown(event) {
        if (!(event instanceof KeyboardEvent)) {
            throw new Error('RandomPasswordModal.onKeyDown requires KeyboardEvent');
        }
        if (event.key !== 'Enter') {
            return;
        }

        const target = event.target;
        if (target instanceof HTMLTextAreaElement) {
            return;
        }
        if (target instanceof HTMLButtonElement) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        this.regeneratePassword();
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }

        const state = this.getModalState();
        const lengthValue = Number.isInteger(state.length) ? state.length : DEFAULT_PASSWORD_LENGTH;
        const charsetInput = typeof state.charsetInput === 'string' ? state.charsetInput : DEFAULT_PASSWORD_CHARSET;
        const result = typeof state.result === 'string' ? state.result : '';
        const error = typeof state.error === 'string' ? state.error : '';
        const copyStatus = typeof state.copyStatus === 'string' && state.copyStatus.length > 0
            ? state.copyStatus
            : COPY_HINT_DEFAULT;

        modalElement.innerHTML = `
            <div class="modal-content random-password-modal-content">
                <div class="random-password-modal-header">
                    <p class="random-password-modal-eyebrow">Utility</p>
                    <h3>Generate Random Password</h3>
                    <p class="random-password-modal-description">
                        Adjust the length or character set, then copy the result into a note when you need it.
                    </p>
                </div>

                <div class="random-password-modal-top-row">
                    <div class="form-group random-password-length-group">
                        <label for="password-length-input">Password length</label>
                        <input
                            type="number"
                            id="password-length-input"
                            min="1"
                            max="1024"
                            step="1"
                            inputmode="numeric"
                        >
                    </div>
                    <div class="random-password-summary-card" aria-hidden="true">
                        <span class="random-password-summary-label">Characters</span>
                        <strong>${lengthValue}</strong>
                    </div>
                </div>

                <div class="form-group">
                    <label for="password-charset-input">Character set</label>
                    <textarea id="password-charset-input" rows="5" spellcheck="false"></textarea>
                    <small class="form-help">Line breaks are ignored; every other character can be used.</small>
                </div>

                <div class="form-group">
                    <label for="password-result-output">Generated password</label>
                    <div class="random-password-result-row">
                        <input
                            type="text"
                            id="password-result-output"
                            readonly
                            spellcheck="false"
                            autocomplete="off"
                        >
                        <button
                            type="button"
                            class="secondary-btn random-password-copy-btn"
                            id="password-copy-btn"
                            ${result.length === 0 ? 'disabled' : ''}
                        >
                            Copy
                        </button>
                    </div>
                    <small id="password-result-copy-hint" class="form-help">${copyStatus}</small>
                </div>

                <div class="form-actions random-password-modal-actions">
                    <button type="button" class="primary-btn" id="password-regenerate-btn">Regenerate</button>
                    <button type="button" class="secondary-btn" id="password-close-btn">Close</button>
                </div>

                <p id="password-generator-error" class="error-message">${error}</p>
            </div>
        `;

        const lengthInput = document.getElementById('password-length-input');
        if (!(lengthInput instanceof HTMLInputElement)) {
            throw new Error('password-length-input missing');
        }
        lengthInput.value = String(lengthValue);

        const charsetTextArea = document.getElementById('password-charset-input');
        if (!(charsetTextArea instanceof HTMLTextAreaElement)) {
            throw new Error('password-charset-input missing');
        }
        charsetTextArea.value = charsetInput;

        const resultOutput = document.getElementById('password-result-output');
        if (!(resultOutput instanceof HTMLInputElement)) {
            throw new Error('password-result-output missing');
        }
        resultOutput.value = result;

        this.setupFormEventListeners();
    }

    setupFormEventListeners() {
        const regenerateButton = document.getElementById('password-regenerate-btn');
        if (regenerateButton instanceof HTMLButtonElement) {
            regenerateButton.onclick = () => this.regeneratePassword();
        }

        const copyButton = document.getElementById('password-copy-btn');
        if (copyButton instanceof HTMLButtonElement) {
            copyButton.onclick = async () => {
                await this.copyResultToClipboard();
            };
        }

        const closeButton = document.getElementById('password-close-btn');
        if (closeButton instanceof HTMLButtonElement) {
            closeButton.onclick = () => this.close();
        }

        const resultOutput = document.getElementById('password-result-output');
        if (resultOutput instanceof HTMLInputElement) {
            resultOutput.onclick = () => {
                resultOutput.focus();
                resultOutput.select();
            };
            resultOutput.onfocus = () => {
                resultOutput.select();
            };
        }
    }

    async copyResultToClipboard() {
        const resultOutput = document.getElementById('password-result-output');
        if (!(resultOutput instanceof HTMLInputElement)) {
            throw new Error('password-result-output missing');
        }
        const value = resultOutput.value;
        if (value.length === 0) {
            return;
        }

        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            await navigator.clipboard.writeText(value);
        } else {
            resultOutput.focus();
            resultOutput.select();
            const copied = document.execCommand('copy');
            if (!copied) {
                throw new Error('Clipboard copy failed');
            }
        }

        rememberGeneratedPasswordCopy(value);
        resultOutput.focus();
        resultOutput.select();
        this.updateModalState({ copyStatus: 'Copied. Pasting into an empty note will add @password.' });

        const hint = document.getElementById('password-result-copy-hint');
        if (hint instanceof HTMLElement) {
            hint.textContent = 'Copied. Pasting into an empty note will add @password.';
        }
    }

    regeneratePassword() {
        const lengthInput = document.getElementById('password-length-input');
        const charsetInput = document.getElementById('password-charset-input');
        const resultOutput = document.getElementById('password-result-output');
        const errorOutput = document.getElementById('password-generator-error');

        if (!(lengthInput instanceof HTMLInputElement)) {
            throw new Error('password-length-input missing');
        }
        if (!(charsetInput instanceof HTMLTextAreaElement)) {
            throw new Error('password-charset-input missing');
        }
        if (!(resultOutput instanceof HTMLInputElement)) {
            throw new Error('password-result-output missing');
        }
        if (!(errorOutput instanceof HTMLElement)) {
            throw new Error('password-generator-error missing');
        }

        const copyHintOutput = document.getElementById('password-result-copy-hint');
        if (!(copyHintOutput instanceof HTMLElement)) {
            throw new Error('password-result-copy-hint missing');
        }

        const copyButton = document.getElementById('password-copy-btn');
        if (!(copyButton instanceof HTMLButtonElement)) {
            throw new Error('password-copy-btn missing');
        }

        const lengthValue = Number.parseInt(lengthInput.value, 10);
        const charsetValue = charsetInput.value;
        if (!Number.isInteger(lengthValue) || lengthValue <= 0) {
            errorOutput.textContent = 'Password length must be a positive integer.';
            resultOutput.value = '';
            copyButton.disabled = true;
            this.updateModalState({
                length: lengthValue,
                charsetInput: charsetValue,
                result: '',
                error: 'Password length must be a positive integer.',
                copyStatus: COPY_HINT_DEFAULT,
            });
            copyHintOutput.textContent = COPY_HINT_DEFAULT;
            return;
        }
        if (lengthValue > 1024) {
            errorOutput.textContent = 'Password length must be 1024 or less.';
            resultOutput.value = '';
            copyButton.disabled = true;
            this.updateModalState({
                length: lengthValue,
                charsetInput: charsetValue,
                result: '',
                error: 'Password length must be 1024 or less.',
                copyStatus: COPY_HINT_DEFAULT,
            });
            copyHintOutput.textContent = COPY_HINT_DEFAULT;
            return;
        }

        const charsetWithoutLineBreaks = charsetValue.replace(/\r/g, '').replace(/\n/g, '');
        if (charsetWithoutLineBreaks.length === 0) {
            errorOutput.textContent = 'Character set must not be empty.';
            resultOutput.value = '';
            copyButton.disabled = true;
            this.updateModalState({
                length: lengthValue,
                charsetInput: charsetValue,
                result: '',
                error: 'Character set must not be empty.',
                copyStatus: COPY_HINT_DEFAULT,
            });
            copyHintOutput.textContent = COPY_HINT_DEFAULT;
            return;
        }

        const normalizedCharset = normalizePasswordCharset(charsetValue);
        const generated = generateRandomPassword(lengthValue, normalizedCharset, null);
        resultOutput.value = generated;
        copyButton.disabled = false;
        copyHintOutput.textContent = COPY_HINT_DEFAULT;
        errorOutput.textContent = '';
        this.updateModalState({
            length: lengthValue,
            charsetInput: charsetValue,
            result: generated,
            error: '',
            copyStatus: COPY_HINT_DEFAULT,
        });
    }
}
