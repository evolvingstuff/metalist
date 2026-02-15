import { BaseModal } from './base-modal.js';
import { CONFIG } from '../config.js';


function parseResponseError(responseBody, statusCode) {
    if (responseBody && typeof responseBody === 'object') {
        if (typeof responseBody.detail === 'string' && responseBody.detail.length > 0) {
            return `Request failed (${statusCode}): ${responseBody.detail}`;
        }
        if (typeof responseBody.message === 'string' && responseBody.message.length > 0) {
            return `Request failed (${statusCode}): ${responseBody.message}`;
        }
    }
    return `Request failed (${statusCode})`;
}


export class BackupRestoreModal extends BaseModal {
    constructor() {
        super('backupRestoreModal', 'backup-restore-modal');
        this.apiEndpoints = {
            list: CONFIG.API.AUTH.BACKUP.LIST,
            restore: CONFIG.API.AUTH.BACKUP.RESTORE,
        };
    }

    getInitialModalState() {
        return {
            loading: true,
            restoring: false,
            backups: [],
            selectedFilename: '',
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

    async onOpen() {
        await this.loadBackups();
    }

    onClose() {
        this.updateModalState(this.getInitialModalState());
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }

        const state = this.getModalState();
        const backups = Array.isArray(state.backups) ? state.backups : [];
        const selectedFilename = typeof state.selectedFilename === 'string' ? state.selectedFilename : '';
        const error = typeof state.error === 'string' ? state.error : '';
        const loading = Boolean(state.loading);
        const restoring = Boolean(state.restoring);
        const selectSize = backups.length > 1 ? Math.min(backups.length, 8) : 1;

        const optionsHtml = backups.map((backup) => {
            if (!backup || typeof backup !== 'object') {
                throw new Error('Invalid backup list entry');
            }
            if (typeof backup.filename !== 'string' || backup.filename.length === 0) {
                throw new Error('Backup entry missing filename');
            }
            if (typeof backup.created_at !== 'string' || backup.created_at.length === 0) {
                throw new Error('Backup entry missing created_at');
            }
            if (typeof backup.size_bytes !== 'number') {
                throw new Error('Backup entry missing size_bytes');
            }

            const isSelected = backup.filename === selectedFilename ? 'selected' : '';
            const label = `${backup.filename} (${Math.round(backup.size_bytes / 1024)} KB, ${backup.created_at})`;
            return `<option value="${backup.filename}" ${isSelected}>${label}</option>`;
        }).join('');

        modalElement.innerHTML = `
            <div class="modal-content backup-restore-modal-content">
                <h3>Restore From Backup</h3>
                <p>Select a backup snapshot and restore the database.</p>
                <p><strong>Warning:</strong> restore replaces your current data.</p>

                <div class="form-group">
                    <label for="backup-select">Available Backups</label>
                    <select id="backup-select" size="${selectSize}" ${loading || restoring || backups.length === 0 ? 'disabled' : ''}>
                        ${optionsHtml}
                    </select>
                </div>

                <div class="form-actions">
                    <button type="button" class="primary-btn" id="restore-backup-btn" ${loading || restoring || backups.length === 0 ? 'disabled' : ''}>Restore Selected Backup</button>
                    <button type="button" class="secondary-btn" id="close-backup-modal-btn" ${restoring ? 'disabled' : ''}>Cancel</button>
                </div>

                <p id="backup-modal-status">${loading ? 'Loading backups...' : ''}${restoring ? 'Restoring backup...' : ''}</p>
                <p id="backup-modal-error" class="error-message">${error}</p>
            </div>
        `;

        this.setupFormEventListeners();
    }

    setupFormEventListeners() {
        const closeButton = document.getElementById('close-backup-modal-btn');
        if (closeButton instanceof HTMLButtonElement) {
            closeButton.onclick = () => this.close();
        }

        const restoreButton = document.getElementById('restore-backup-btn');
        if (restoreButton instanceof HTMLButtonElement) {
            restoreButton.onclick = async () => {
                await this.handleRestore();
            };
        }

        const select = document.getElementById('backup-select');
        if (select instanceof HTMLSelectElement) {
            select.onchange = () => {
                this.updateModalState({ selectedFilename: select.value, error: '' });
            };
        }
    }

    _buildAuthHeaders(includeContentType) {
        if (typeof includeContentType !== 'boolean') {
            throw new Error('_buildAuthHeaders requires boolean includeContentType');
        }

        const tabId = sessionStorage.getItem('metalist_tab_id');
        if (typeof tabId !== 'string' || tabId.length === 0) {
            throw new Error('metalist_tab_id missing from sessionStorage');
        }

        const token = localStorage.getItem('auth_token');
        if (typeof token !== 'string' || token.length === 0) {
            throw new Error('auth_token missing from localStorage');
        }

        const headers = {
            Authorization: `Bearer ${token}`,
            'X-Metalist-Tab-Id': tabId,
        };

        if (includeContentType) {
            headers['Content-Type'] = 'application/json';
        }

        return headers;
    }

    async _authRequest(url, method, bodyObject) {
        if (typeof url !== 'string' || url.length === 0) {
            throw new Error('_authRequest requires url');
        }
        if (typeof method !== 'string' || method.length === 0) {
            throw new Error('_authRequest requires method');
        }
        if (bodyObject !== null && typeof bodyObject !== 'object') {
            throw new Error('_authRequest bodyObject must be object or null');
        }

        const hasBody = bodyObject !== null;
        const response = await fetch(url, {
            method,
            headers: this._buildAuthHeaders(hasBody),
            body: hasBody ? JSON.stringify(bodyObject) : undefined,
        });

        let payload = null;
        const contentType = response.headers.get('content-type');
        if (typeof contentType === 'string' && contentType.includes('application/json')) {
            payload = await response.json();
        }

        if (!response.ok) {
            throw new Error(parseResponseError(payload, response.status));
        }
        if (payload === null) {
            throw new Error('Response payload missing');
        }
        return payload;
    }

    async loadBackups() {
        this.updateModalState({
            loading: true,
            restoring: false,
            error: '',
            backups: [],
            selectedFilename: '',
        });
        this.renderModalContent();

        const payload = await this._authRequest(this.apiEndpoints.list, 'GET', null);
        if (!payload || typeof payload !== 'object') {
            throw new Error('Backup list response missing body');
        }
        if (!Array.isArray(payload.backups)) {
            throw new Error('Backup list response missing backups array');
        }

        const backups = payload.backups;
        const selectedFilename = backups.length > 0 ? backups[0].filename : '';
        this.updateModalState({
            loading: false,
            restoring: false,
            error: '',
            backups,
            selectedFilename,
        });
        this.renderModalContent();
    }

    async handleRestore() {
        const state = this.getModalState();
        if (typeof state.selectedFilename !== 'string' || state.selectedFilename.length === 0) {
            this.updateModalState({ error: 'Select a backup first.' });
            this.renderModalContent();
            return;
        }

        const confirmed = window.confirm(
            `Restore backup "${state.selectedFilename}"? This will replace current data.`
        );
        if (!confirmed) {
            return;
        }

        this.updateModalState({
            restoring: true,
            error: '',
        });
        this.renderModalContent();

        await this._authRequest(this.apiEndpoints.restore, 'POST', {
            filename: state.selectedFilename,
        });
        window.alert('Backup restored. The app will reload now.');
        window.location.reload();
    }
}
