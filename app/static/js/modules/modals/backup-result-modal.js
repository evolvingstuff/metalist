import { BaseModal } from './base-modal.js';


function _assertNonEmptyString(value, fieldName) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`${fieldName} must be a non-empty string`);
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
            createdFilename: this._context.createdFilename,
            deletedCount: this._context.deletedCount,
            remainingCount: this._context.remainingCount,
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
            createdFilename: context.createdFilename,
            deletedCount: context.deletedCount,
            remainingCount: context.remainingCount,
        };

        this.open();

        return new Promise((resolve) => {
            this._pendingResolve = resolve;
        });
    }

    onOpen() {
        if (this._context === null) {
            throw new Error('BackupResultModal missing open context');
        }
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
        _assertNonEmptyString(state.createdFilename, 'createdFilename');
        _assertNonNegativeInteger(state.deletedCount, 'deletedCount');
        _assertNonNegativeInteger(state.remainingCount, 'remainingCount');

        const retentionMessage = state.deletedCount > 0
            ? `Removed ${state.deletedCount} older backup(s).`
            : 'No older backups were removed.';

        modalElement.innerHTML = `
            <div class="modal-content backup-result-modal-content">
                <h3>Backup Complete</h3>
                <p>Created backup: <span class="backup-filename">${state.createdFilename}</span></p>
                <p>${retentionMessage}</p>
                <p>Total backups now: <strong>${state.remainingCount}</strong></p>
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
        _assertNonEmptyString(context.createdFilename, 'createdFilename');
        _assertNonNegativeInteger(context.deletedCount, 'deletedCount');
        _assertNonNegativeInteger(context.remainingCount, 'remainingCount');
    }
}
