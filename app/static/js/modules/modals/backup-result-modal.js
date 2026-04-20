import { BaseModal } from './base-modal.js';


function _assertString(value, fieldName) {
    if (typeof value !== 'string') {
        throw new Error(`${fieldName} must be a string`);
    }
}


function _assertNonNegativeInteger(value, fieldName) {
    if (!Number.isInteger(value) || value < 0) {
        throw new Error(`${fieldName} must be a non-negative integer`);
    }
}


export class BackupResultModal extends BaseModal {
    constructor() {
        super('backupResultModal', 'backup-result-modal');
        this._pendingResolve = null;
        this._context = null;
    }

    getInitialModalState() {
        if (this._context === null) {
            throw new Error('BackupResultModal requires context before initialization');
        }
        return {
            results: this._context.results,
        };
    }

    shouldCloseOnClickOutside() {
        return false;
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

    openWithResult(context) {
        this._validateContext(context);
        if (this.isOpen) {
            throw new Error('BackupResultModal is already open');
        }
        if (this._pendingResolve !== null) {
            throw new Error('BackupResultModal already has a pending promise');
        }
        this._context = {
            results: context.results,
        };
        this.open();
        return new Promise((resolve) => {
            this._pendingResolve = resolve;
        });
    }

    onClose() {
        const resolve = this._pendingResolve;
        this._pendingResolve = null;
        this._context = null;
        if (resolve !== null) {
            resolve();
        }
    }

    onKeyDown(event) {
        if (!(event instanceof KeyboardEvent)) {
            throw new Error('BackupResultModal.onKeyDown requires KeyboardEvent');
        }
        if (event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        this.close();
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }

        const state = this.getModalState();
        if (!Array.isArray(state.results) || state.results.length === 0) {
            throw new Error('BackupResultModal requires results');
        }

        const resultsHtml = state.results.map((result) => {
            if (!result || typeof result !== 'object') {
                throw new Error('BackupResultModal result entry must be an object');
            }
            _assertString(result.destination, 'destination');
            if (typeof result.success !== 'boolean') {
                throw new Error('success must be a boolean');
            }
            _assertString(result.created_filename, 'created_filename');
            _assertNonNegativeInteger(result.deleted_count, 'deleted_count');
            _assertNonNegativeInteger(result.remaining_count, 'remaining_count');
            _assertString(result.message, 'message');

            const title = result.destination === 'google_drive' ? 'Google Drive' : 'Local';
            const filenameLine = result.created_filename.length > 0
                ? `<p>Created: <span class="backup-filename">${result.created_filename}</span></p>`
                : '';
            const retentionLine = result.success
                ? `<p>Deleted older backups: <strong>${result.deleted_count}</strong> · Remaining: <strong>${result.remaining_count}</strong></p>`
                : '';
            return `
                <div class="form-group">
                    <p><strong>${title}</strong> · ${result.success ? 'Success' : 'Failed'}</p>
                    ${filenameLine}
                    ${retentionLine}
                    <p>${result.message}</p>
                </div>
            `;
        }).join('');

        modalElement.innerHTML = `
            <div class="modal-content backup-result-modal-content">
                <h3>Backup Result</h3>
                ${resultsHtml}
                <div class="form-actions">
                    <button type="button" class="primary-btn" id="backup-result-ok-btn">OK</button>
                </div>
            </div>
        `;

        const okButton = document.getElementById('backup-result-ok-btn');
        if (!(okButton instanceof HTMLButtonElement)) {
            throw new Error('backup-result-ok-btn missing');
        }
        okButton.onclick = () => this.close();
        setTimeout(() => okButton.focus(), 50);
    }

    _validateContext(context) {
        if (!context || typeof context !== 'object') {
            throw new Error('BackupResultModal context must be an object');
        }
        if (!Array.isArray(context.results) || context.results.length === 0) {
            throw new Error('BackupResultModal context missing results');
        }
    }
}
