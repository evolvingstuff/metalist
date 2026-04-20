import { BaseModal } from './base-modal.js';
import { CONFIG } from '../config.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';


const RESTORE_TRANSITION_SUPPRESS_MS = 30_000;
const RESTORE_TRANSITION_UNTIL_KEY = 'metalist_restore_transition_until_ms';
const SERVER_REACHABILITY_POLL_INTERVAL_MS = 300;
const SERVER_REACHABILITY_REQUEST_TIMEOUT_MS = 1000;
const RESTORE_RECONNECT_CURSOR_CLASS = 'restore-reconnect-loading';


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
            list: CONFIG.API.BACKUP.LIST,
            restore: CONFIG.API.BACKUP.RESTORE,
        };
    }

    getInitialModalState() {
        return {
            loading: true,
            restoring: false,
            confirming: false,
            restored: false,
            waitingForServer: false,
            restoredFilename: '',
            restoredTargetNamespace: '',
            activeNamespaceRestarted: false,
            openNamespaceSuggested: false,
            backups: [],
            selectedBackupId: '',
            targetNamespaceText: '',
            error: '',
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

    async onOpen() {
        await this.loadBackups();
    }

    onClose() {
        this._setReconnectCursor(false);
        this.updateModalState(this.getInitialModalState());
    }

    handleKeyDown(event) {
        const topModal = ModeContext.modalStack?.[ModeContext.modalStack.length - 1];
        if (topModal !== this.modalName) {
            return;
        }

        const state = this.getModalState();
        if (event.key === 'Escape') {
            if (state && state.restored && Boolean(state.activeNamespaceRestarted)) {
                event.preventDefault();
                event.stopPropagation();
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            this.close();
            return;
        }
        this.onKeyDown(event);
    }

    onKeyDown(event) {
        if (!(event instanceof KeyboardEvent)) {
            throw new Error('BackupRestoreModal.onKeyDown requires KeyboardEvent');
        }
        if (event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        const state = this.getModalState();
        if (state && state.restored && Boolean(state.activeNamespaceRestarted)) {
            this._beginPostRestoreReconnectAndReload();
            return;
        }
        void this.handleRestore();
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }

        const state = this.getModalState();
        const backups = Array.isArray(state.backups) ? state.backups : [];
        const selectedBackupId = typeof state.selectedBackupId === 'string' ? state.selectedBackupId : '';
        const targetNamespaceText = typeof state.targetNamespaceText === 'string' ? state.targetNamespaceText : '';
        const error = typeof state.error === 'string' ? state.error : '';
        const loading = Boolean(state.loading);
        const restoring = Boolean(state.restoring);
        const confirming = Boolean(state.confirming);
        const restored = Boolean(state.restored);
        const waitingForServer = Boolean(state.waitingForServer);
        const restoredFilename = typeof state.restoredFilename === 'string' ? state.restoredFilename : '';
        const restoredTargetNamespace = typeof state.restoredTargetNamespace === 'string' ? state.restoredTargetNamespace : '';
        const activeNamespaceRestarted = Boolean(state.activeNamespaceRestarted);
        const openNamespaceSuggested = Boolean(state.openNamespaceSuggested);

        if (restored) {
            if (restoredFilename.length === 0 || restoredTargetNamespace.length === 0) {
                throw new Error('Backup restore success state missing restored values');
            }
            if (activeNamespaceRestarted) {
                if (waitingForServer) {
                    modalElement.innerHTML = `
                        <div class="modal-content backup-restore-modal-content">
                            <h3>Restore Complete</h3>
                            <p>Backup restored successfully: <span class="backup-filename">${restoredFilename}</span></p>
                            <p>Reconnecting to restarted server. You will be redirected automatically.</p>
                        </div>
                    `;
                    return;
                }
                modalElement.innerHTML = `
                    <div class="modal-content backup-restore-modal-content">
                        <h3>Restore Complete</h3>
                        <p>Backup restored successfully: <span class="backup-filename">${restoredFilename}</span></p>
                        <p>Click OK to reload the app.</p>
                        <div class="form-actions">
                            <button type="button" class="primary-btn" id="backup-restore-success-ok-btn">OK</button>
                        </div>
                    </div>
                `;
                const okButton = document.getElementById('backup-restore-success-ok-btn');
                if (!(okButton instanceof HTMLButtonElement)) {
                    throw new Error('backup-restore-success-ok-btn missing');
                }
                okButton.onclick = () => this._beginPostRestoreReconnectAndReload();
                setTimeout(() => okButton.focus(), 50);
                return;
            }

            modalElement.innerHTML = `
                <div class="modal-content backup-restore-modal-content">
                    <h3>Restore Complete</h3>
                    <p>Backup restored successfully: <span class="backup-filename">${restoredFilename}</span></p>
                    <p>Restored into namespace <strong>${restoredTargetNamespace}</strong>.</p>
                    <p>${openNamespaceSuggested ? 'Use the namespace switcher to open it.' : 'You can continue using it now.'}</p>
                    <div class="form-actions">
                        <button type="button" class="primary-btn" id="backup-restore-finish-ok-btn">OK</button>
                    </div>
                </div>
            `;
            const finishButton = document.getElementById('backup-restore-finish-ok-btn');
            if (!(finishButton instanceof HTMLButtonElement)) {
                throw new Error('backup-restore-finish-ok-btn missing');
            }
            finishButton.onclick = () => this.close();
            setTimeout(() => finishButton.focus(), 50);
            return;
        }

        let selectedBackup = backups.find((backup) => backup.backup_id === selectedBackupId);
        if (typeof selectedBackup === 'undefined') {
            selectedBackup = null;
        }
        const selectSize = backups.length > 1 ? Math.min(backups.length, 8) : 1;
        const optionsHtml = backups.map((backup) => {
            if (!backup || typeof backup !== 'object') {
                throw new Error('Invalid backup list entry');
            }
            if (typeof backup.backup_id !== 'string' || backup.backup_id.length === 0) {
                throw new Error('Backup entry missing backup_id');
            }
            if (typeof backup.filename !== 'string' || backup.filename.length === 0) {
                throw new Error('Backup entry missing filename');
            }
            if (typeof backup.namespace !== 'string' || backup.namespace.length === 0) {
                throw new Error('Backup entry missing namespace');
            }
            if (typeof backup.created_at !== 'string' || backup.created_at.length === 0) {
                throw new Error('Backup entry missing created_at');
            }
            if (typeof backup.size_bytes !== 'number') {
                throw new Error('Backup entry missing size_bytes');
            }
            const sourceLabel = backup.source === 'google_drive' ? 'Google Drive' : 'Local';
            const isSelected = backup.backup_id === selectedBackupId ? 'selected' : '';
            const label = `${sourceLabel} · ${backup.namespace} · ${backup.filename} (${Math.round(backup.size_bytes / 1024)} KB, ${backup.created_at})`;
            return `<option value="${backup.backup_id}" ${isSelected}>${label}</option>`;
        }).join('');

        const selectedNamespace = selectedBackup && typeof selectedBackup.namespace === 'string' ? selectedBackup.namespace : '';

        modalElement.innerHTML = `
            <div class="modal-content backup-restore-modal-content">
                <h3>Restore From Backup</h3>
                <p>Select a backup snapshot and restore the workspace data.</p>
                <p><strong>Warning:</strong> restore overwrites the target namespace.</p>
                <p id="backup-modal-confirm-message">${confirming && selectedBackup ? `Confirm restore of "${selectedBackup.filename}" into namespace "${targetNamespaceText}"?` : ''}</p>

                <div class="form-group">
                    <label for="backup-select">Available Backups</label>
                    <select id="backup-select" size="${selectSize}" ${loading || restoring || confirming || backups.length === 0 ? 'disabled' : ''}>
                        ${optionsHtml}
                    </select>
                </div>

                <div class="form-group">
                    <label for="backup-target-namespace">Target namespace</label>
                    <input type="text" id="backup-target-namespace" value="${targetNamespaceText}" ${loading || restoring || backups.length === 0 ? 'disabled' : ''}>
                </div>

                <p>${selectedNamespace ? `Backup namespace: ${selectedNamespace}` : ''}</p>

                <div class="form-actions">
                    <button type="button" class="primary-btn" id="restore-backup-btn" ${loading || restoring || backups.length === 0 ? 'disabled' : ''}>${confirming ? 'Confirm Restore' : 'Restore Selected Backup'}</button>
                    <button type="button" class="secondary-btn" id="close-backup-modal-btn" ${restoring ? 'disabled' : ''}>${confirming ? 'Back' : 'Cancel'}</button>
                </div>

                <p id="backup-modal-status">${loading ? 'Loading backups...' : ''}${restoring ? ' Restoring backup...' : ''}</p>
                <p id="backup-modal-error" class="error-message">${error}</p>
            </div>
        `;

        this.setupFormEventListeners();
    }

    setupFormEventListeners() {
        const closeButton = document.getElementById('close-backup-modal-btn');
        if (closeButton instanceof HTMLButtonElement) {
            closeButton.onclick = () => {
                const state = this.getModalState();
                if (state.confirming) {
                    this.updateModalState({
                        confirming: false,
                        error: '',
                    });
                    this.renderModalContent();
                    return;
                }
                this.close();
            };
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
                const backups = this.getModalState().backups;
                const selectedBackup = Array.isArray(backups)
                    ? backups.find((backup) => backup.backup_id === select.value) || null
                    : null;
                const nextNamespace = selectedBackup && typeof selectedBackup.namespace === 'string'
                    ? selectedBackup.namespace
                    : '';
                this.updateModalState({
                    selectedBackupId: select.value,
                    targetNamespaceText: nextNamespace,
                    confirming: false,
                    error: '',
                });
                this.renderModalContent();
            };
        }

        const targetNamespaceInput = document.getElementById('backup-target-namespace');
        if (targetNamespaceInput instanceof HTMLInputElement) {
            targetNamespaceInput.oninput = () => {
                this.updateModalState({
                    targetNamespaceText: targetNamespaceInput.value,
                    confirming: false,
                    error: '',
                });
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
            confirming: false,
            restored: false,
            waitingForServer: false,
            restoredFilename: '',
            restoredTargetNamespace: '',
            activeNamespaceRestarted: false,
            openNamespaceSuggested: false,
            error: '',
            backups: [],
            selectedBackupId: '',
            targetNamespaceText: '',
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
        const firstBackup = backups.length > 0 ? backups[0] : null;
        const selectedBackupId = firstBackup && typeof firstBackup.backup_id === 'string' ? firstBackup.backup_id : '';
        const targetNamespaceText = firstBackup && typeof firstBackup.namespace === 'string' ? firstBackup.namespace : '';
        this.updateModalState({
            loading: false,
            backups,
            selectedBackupId,
            targetNamespaceText,
            error: '',
        });
        this.renderModalContent();
    }

    async handleRestore() {
        const state = this.getModalState();
        if (typeof state.selectedBackupId !== 'string' || state.selectedBackupId.length === 0) {
            this.updateModalState({ error: 'Select a backup first.' });
            this.renderModalContent();
            return;
        }

        const backups = Array.isArray(state.backups) ? state.backups : [];
        let selectedBackup = backups.find((backup) => backup.backup_id === state.selectedBackupId);
        if (typeof selectedBackup === 'undefined') {
            selectedBackup = null;
        }
        if (selectedBackup === null) {
            this.updateModalState({ error: 'Selected backup is missing.' });
            this.renderModalContent();
            return;
        }
        if (typeof state.targetNamespaceText !== 'string' || state.targetNamespaceText.trim().length === 0) {
            this.updateModalState({ error: 'Target namespace is required.' });
            this.renderModalContent();
            return;
        }

        if (!state.confirming) {
            this.updateModalState({
                confirming: true,
                error: '',
            });
            this.renderModalContent();
            return;
        }

        this.updateModalState({
            restoring: true,
            confirming: false,
            error: '',
        });
        this.renderModalContent();

        const payload = await this._authRequest(this.apiEndpoints.restore, 'POST', {
            backup_id: selectedBackup.backup_id,
            source: selectedBackup.source,
            backup_filename: selectedBackup.filename,
            backup_namespace: selectedBackup.namespace,
            target_namespace: state.targetNamespaceText.trim(),
        });
        if (!payload || typeof payload !== 'object') {
            throw new Error('Restore response missing body');
        }

        const activeNamespaceRestarted = payload.active_namespace_restarted === true;
        if (activeNamespaceRestarted) {
            this._markRestoreTransitionActive();
        }
        this.updateModalState({
            loading: false,
            restoring: false,
            confirming: false,
            restored: true,
            waitingForServer: false,
            restoredFilename: payload.backup_filename,
            restoredTargetNamespace: payload.target_namespace,
            activeNamespaceRestarted,
            openNamespaceSuggested: payload.open_namespace_suggested === true,
            error: '',
        });
        this.renderModalContent();
    }

    _markRestoreTransitionActive() {
        const transitionUntil = Date.now() + RESTORE_TRANSITION_SUPPRESS_MS;
        sessionStorage.setItem(RESTORE_TRANSITION_UNTIL_KEY, String(transitionUntil));
    }

    _beginPostRestoreReconnectAndReload() {
        const state = this.getModalState();
        if (!state || !state.restored || !state.activeNamespaceRestarted) {
            throw new Error('Cannot begin post-restore reconnect before active-namespace restore success');
        }
        if (state.waitingForServer) {
            return;
        }
        this._setReconnectCursor(true);
        this.updateModalState({
            waitingForServer: true,
            error: '',
        });
        this.renderModalContent();
        void this._waitForServerReachabilityThenReload();
    }

    async _waitForServerReachabilityThenReload() {
        while (true) {
            const reachable = await this._checkServerReachability();
            if (reachable) {
                this._setReconnectCursor(false);
                window.location.reload();
                return;
            }
            await this._sleep(SERVER_REACHABILITY_POLL_INTERVAL_MS);
        }
    }

    async _checkServerReachability() {
        const abortController = new AbortController();
        const timeoutId = setTimeout(() => abortController.abort(), SERVER_REACHABILITY_REQUEST_TIMEOUT_MS);
        const reachablePromise = fetch('/maintenance', {
            method: 'GET',
            cache: 'no-store',
            signal: abortController.signal,
        }).then(
            (response) => response.status >= 200 && response.status < 600,
            () => false,
        );
        const reachable = await reachablePromise;
        clearTimeout(timeoutId);
        return reachable;
    }

    _sleep(delayMs) {
        if (!Number.isInteger(delayMs) || delayMs < 0) {
            throw new Error(`delayMs must be a non-negative integer, got ${delayMs}`);
        }
        return new Promise((resolve) => setTimeout(resolve, delayMs));
    }

    _setReconnectCursor(active) {
        if (typeof active !== 'boolean') {
            throw new Error(`active must be a boolean, got ${typeof active}`);
        }
        if (!document.body) {
            throw new Error('document.body is required for reconnect cursor toggling');
        }
        if (active) {
            document.body.classList.add(RESTORE_RECONNECT_CURSOR_CLASS);
            return;
        }
        document.body.classList.remove(RESTORE_RECONNECT_CURSOR_CLASS);
    }
}
