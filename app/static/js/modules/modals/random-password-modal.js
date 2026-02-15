import { BaseModal } from './base-modal.js';
import {
    DEFAULT_PASSWORD_CHARSET,
    DEFAULT_PASSWORD_LENGTH,
    generateRandomPassword,
    normalizePasswordCharset,
} from '../password-generator.js';


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

        modalElement.innerHTML = `
            <div class="modal-content random-password-modal-content">
                <h3>Random Password Generator Utility</h3>

                <div class="form-group">
                    <label for="password-length-input">Password Length:</label>
                    <input type="number" id="password-length-input" min="1" step="1" value="${lengthValue}">
                </div>

                <div class="form-group">
                    <label for="password-charset-input">Valid Character Set:</label>
                    <textarea id="password-charset-input" rows="5">${charsetInput}</textarea>
                </div>

                <div class="form-group">
                    <label for="password-result-output">Result:</label>
                    <textarea id="password-result-output" rows="3" readonly>${result}</textarea>
                </div>

                <div class="form-actions">
                    <button type="button" class="primary-btn" id="password-regenerate-btn">Regenerate</button>
                    <button type="button" class="secondary-btn" id="password-close-btn">Close</button>
                </div>

                <p id="password-generator-error" class="error-message">${error}</p>
            </div>
        `;

        this.setupFormEventListeners();
    }

    setupFormEventListeners() {
        const regenerateButton = document.getElementById('password-regenerate-btn');
        if (regenerateButton instanceof HTMLButtonElement) {
            regenerateButton.onclick = () => this.regeneratePassword();
        }

        const closeButton = document.getElementById('password-close-btn');
        if (closeButton instanceof HTMLButtonElement) {
            closeButton.onclick = () => this.close();
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
        if (!(resultOutput instanceof HTMLTextAreaElement)) {
            throw new Error('password-result-output missing');
        }
        if (!(errorOutput instanceof HTMLElement)) {
            throw new Error('password-generator-error missing');
        }

        const lengthValue = Number.parseInt(lengthInput.value, 10);
        const charsetValue = charsetInput.value;
        if (!Number.isInteger(lengthValue) || lengthValue <= 0) {
            errorOutput.textContent = 'Password length must be a positive integer.';
            resultOutput.value = '';
            this.updateModalState({
                length: lengthValue,
                charsetInput: charsetValue,
                result: '',
                error: 'Password length must be a positive integer.',
            });
            return;
        }
        if (lengthValue > 1024) {
            errorOutput.textContent = 'Password length must be 1024 or less.';
            resultOutput.value = '';
            this.updateModalState({
                length: lengthValue,
                charsetInput: charsetValue,
                result: '',
                error: 'Password length must be 1024 or less.',
            });
            return;
        }

        const charsetWithoutLineBreaks = charsetValue.replace(/\r/g, '').replace(/\n/g, '');
        if (charsetWithoutLineBreaks.length === 0) {
            errorOutput.textContent = 'Character set must not be empty.';
            resultOutput.value = '';
            this.updateModalState({
                length: lengthValue,
                charsetInput: charsetValue,
                result: '',
                error: 'Character set must not be empty.',
            });
            return;
        }

        const normalizedCharset = normalizePasswordCharset(charsetValue);
        const generated = generateRandomPassword(lengthValue, normalizedCharset, null);
        resultOutput.value = generated;
        errorOutput.textContent = '';
        this.updateModalState({
            length: lengthValue,
            charsetInput: charsetValue,
            result: generated,
            error: '',
        });
    }
}
