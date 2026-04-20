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


function escapeHtml(value) {
    if (typeof value !== 'string') {
        return '';
    }
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}


export class BackupSettingsModal extends BaseModal {
    constructor() {
        super('backupSettingsModal', 'backup-settings-modal');
        this._pendingResolve = null;
        this._closeResult = { action: 'cancel' };
        this._connectPollGeneration = 0;
    }

    _errorMessage(error) {
        if (error instanceof Error) {
            return error.message;
        }
        return String(error);
    }

    getInitialModalState() {
        return {
            loading: true,
            saving: false,
            connecting: false,
            localEnabled: true,
            googleDriveEnabled: false,
            retentionCountText: '30',
            googleDriveStatus: 'disconnected',
            googleDriveAccountEmail: '',
            googleDriveRootFolderName: '',
            googleDriveConnected: false,
            googleDriveAvailable: false,
            statusMessage: '',
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

    openForBackup() {
        if (this.isOpen) {
            throw new Error('BackupSettingsModal is already open');
        }
        if (this._pendingResolve !== null) {
            throw new Error('BackupSettingsModal already has a pending promise');
        }
        this._closeResult = { action: 'cancel' };
        this.open();
        return new Promise((resolve) => {
            this._pendingResolve = resolve;
        });
    }

    async onOpen() {
        await this.loadSettings();
    }

    onClose() {
        this._connectPollGeneration += 1;
        const resolve = this._pendingResolve;
        const closeResult = this._closeResult;
        this._pendingResolve = null;
        this._closeResult = { action: 'cancel' };
        if (resolve !== null) {
            resolve(closeResult);
        }
    }

    onKeyDown(event) {
        if (!(event instanceof KeyboardEvent)) {
            throw new Error('BackupSettingsModal.onKeyDown requires KeyboardEvent');
        }
        if (event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        void this.handleRunBackup();
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }
        const state = this.getModalState();
        const loading = Boolean(state.loading);
        const saving = Boolean(state.saving);
        const connecting = Boolean(state.connecting);
        const localEnabled = Boolean(state.localEnabled);
        const googleDriveEnabled = Boolean(state.googleDriveEnabled);
        const retentionCountText = typeof state.retentionCountText === 'string' ? state.retentionCountText : '';
        const googleDriveStatus = typeof state.googleDriveStatus === 'string' ? state.googleDriveStatus : 'disconnected';
        const googleDriveAccountEmail = typeof state.googleDriveAccountEmail === 'string' ? state.googleDriveAccountEmail : '';
        const googleDriveRootFolderName = typeof state.googleDriveRootFolderName === 'string' ? state.googleDriveRootFolderName : '';
        const googleDriveConnected = Boolean(state.googleDriveConnected);
        const googleDriveAvailable = Boolean(state.googleDriveAvailable);
        const statusMessage = typeof state.statusMessage === 'string' ? state.statusMessage : '';
        const error = typeof state.error === 'string' ? state.error : '';

        const driveStatusText = googleDriveConnected
            ? `Connected${googleDriveAccountEmail ? ` as ${googleDriveAccountEmail}` : ''}${googleDriveRootFolderName ? ` · Folder: ${googleDriveRootFolderName}` : ''}`
            : `Status: ${googleDriveStatus}`;
        const googleDriveHelpText = googleDriveAvailable
            ? 'Click Connect Google Drive, choose a Google account, and approve access for this namespace.'
            : 'Google Drive connect is unavailable until this MetaList build is started with a Google Desktop app client ID.';
        let effectiveStatusMessage = statusMessage;
        if (effectiveStatusMessage.length === 0 && loading) {
            effectiveStatusMessage = 'Loading backup settings...';
        }
        if (effectiveStatusMessage.length === 0 && connecting) {
            effectiveStatusMessage = 'Waiting for Google Drive authorization...';
        }

        modalElement.innerHTML = `
            <div class="modal-content backup-retention-modal-content">
                <h3>Backup Settings</h3>
                <p>Choose where manual backups should go and how many snapshots to retain per destination.</p>

                <div class="form-group">
                    <label class="backup-settings-checkbox-row"><input type="checkbox" id="backup-settings-local-enabled" ${localEnabled ? 'checked' : ''} ${loading || saving ? 'disabled' : ''}><span>Save local backup</span></label>
                </div>

                <div class="form-group">
                    <label class="backup-settings-checkbox-row"><input type="checkbox" id="backup-settings-drive-enabled" ${googleDriveEnabled ? 'checked' : ''} ${loading || saving ? 'disabled' : ''}><span>Save backup to Google Drive</span></label>
                </div>

                <div class="form-group">
                    <label for="backup-settings-retention-count">Backups to retain per destination</label>
                    <input type="number" id="backup-settings-retention-count" min="1" step="1" value="${retentionCountText}" ${loading || saving ? 'disabled' : ''}>
                </div>

                <div class="form-group">
                    <p><strong>Google Drive:</strong> ${escapeHtml(driveStatusText)}</p>
                    <p>${escapeHtml(googleDriveHelpText)}</p>
                    <div class="form-actions">
                        <button type="button" class="secondary-btn" id="backup-settings-connect-drive-btn" ${loading || saving || connecting || !googleDriveAvailable ? 'disabled' : ''}>${googleDriveConnected ? 'Reconnect Google Drive' : 'Connect Google Drive'}</button>
                        <button type="button" class="secondary-btn" id="backup-settings-disconnect-drive-btn" ${loading || saving || connecting || !googleDriveConnected ? 'disabled' : ''}>Disconnect</button>
                    </div>
                </div>

                <div class="form-actions">
                    <button type="button" class="primary-btn" id="backup-settings-run-btn" ${loading || saving || connecting ? 'disabled' : ''}>${saving ? 'Saving...' : 'Back Up Now'}</button>
                    <button type="button" class="secondary-btn" id="backup-settings-cancel-btn" ${saving || connecting ? 'disabled' : ''}>Cancel</button>
                </div>

                <p id="backup-settings-status">${escapeHtml(effectiveStatusMessage)}</p>
                <p id="backup-settings-error" class="error-message">${escapeHtml(error)}</p>
            </div>
        `;

        this.setupFormEventListeners();
    }

    setupFormEventListeners() {
        const cancelButton = document.getElementById('backup-settings-cancel-btn');
        if (cancelButton instanceof HTMLButtonElement) {
            cancelButton.onclick = () => {
                this._closeResult = { action: 'cancel' };
                this.close();
            };
        }

        const localCheckbox = document.getElementById('backup-settings-local-enabled');
        if (localCheckbox instanceof HTMLInputElement) {
            localCheckbox.onchange = () => {
                this.updateModalState({
                    localEnabled: localCheckbox.checked,
                    error: '',
                });
            };
        }

        const driveCheckbox = document.getElementById('backup-settings-drive-enabled');
        if (driveCheckbox instanceof HTMLInputElement) {
            driveCheckbox.onchange = () => {
                this.updateModalState({
                    googleDriveEnabled: driveCheckbox.checked,
                    error: '',
                });
            };
        }

        const retentionInput = document.getElementById('backup-settings-retention-count');
        if (retentionInput instanceof HTMLInputElement) {
            retentionInput.oninput = () => {
                this.updateModalState({
                    retentionCountText: retentionInput.value,
                    error: '',
                });
            };
        }

        const connectButton = document.getElementById('backup-settings-connect-drive-btn');
        if (connectButton instanceof HTMLButtonElement) {
            connectButton.onclick = async () => {
                await this.connectGoogleDrive();
            };
        }

        const disconnectButton = document.getElementById('backup-settings-disconnect-drive-btn');
        if (disconnectButton instanceof HTMLButtonElement) {
            disconnectButton.onclick = async () => {
                await this.disconnectGoogleDrive();
            };
        }

        const runButton = document.getElementById('backup-settings-run-btn');
        if (runButton instanceof HTMLButtonElement) {
            runButton.onclick = async () => {
                await this.handleRunBackup();
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

    async _authRequest(url, method, payload) {
        if (typeof url !== 'string' || url.length === 0) {
            throw new Error('_authRequest requires url');
        }
        if (typeof method !== 'string' || method.length === 0) {
            throw new Error('_authRequest requires method');
        }
        const includeContentType = payload !== null;
        const response = await fetch(url, {
            method,
            headers: this._buildAuthHeaders(includeContentType),
            body: payload === null ? undefined : JSON.stringify(payload),
        });

        let responseBody = null;
        const contentType = response.headers.get('content-type');
        if (typeof contentType === 'string' && contentType.includes('application/json')) {
            responseBody = await response.json();
        }
        if (!response.ok) {
            throw new Error(parseResponseError(responseBody, response.status));
        }
        if (responseBody === null) {
            throw new Error('Response payload missing');
        }
        return responseBody;
    }

    _sleep(milliseconds) {
        if (!Number.isInteger(milliseconds) || milliseconds < 0) {
            throw new Error('_sleep requires a non-negative integer');
        }
        return new Promise((resolve) => {
            window.setTimeout(resolve, milliseconds);
        });
    }

    _buildSettingsPayload() {
        const state = this.getModalState();
        return {
            local_enabled: Boolean(state.localEnabled),
            google_drive_enabled: Boolean(state.googleDriveEnabled),
            retention_count: this._parseRetentionCount(),
        };
    }

    async loadSettings() {
        this.updateModalState({
            loading: true,
            connecting: false,
            statusMessage: 'Loading backup settings...',
            error: '',
        });
        this.renderModalContent();
        const settled = await this._authRequest(CONFIG.API.BACKUP.SETTINGS, 'GET', null).then(
            (payload) => ({ ok: true, payload }),
            (error) => ({ ok: false, error }),
        );
        if (!settled.ok) {
            this.updateModalState({
                loading: false,
                statusMessage: '',
                error: this._errorMessage(settled.error),
            });
            this.renderModalContent();
            return;
        }
        const payload = settled.payload;
        this.updateModalState({
            loading: false,
            localEnabled: payload.local_enabled,
            googleDriveEnabled: payload.google_drive_enabled,
            retentionCountText: String(payload.retention_count),
            googleDriveStatus: payload.google_drive_status,
            googleDriveAccountEmail: payload.google_drive_account_email,
            googleDriveRootFolderName: payload.google_drive_root_folder_name,
            googleDriveConnected: payload.google_drive_connected,
            googleDriveAvailable: payload.google_drive_available,
            statusMessage: '',
            error: '',
        });
        this.renderModalContent();
    }

    _parseRetentionCount() {
        const state = this.getModalState();
        const raw = typeof state.retentionCountText === 'string' ? state.retentionCountText.trim() : '';
        if (!/^[0-9]+$/.test(raw)) {
            throw new Error('Retention count must be a whole number.');
        }
        const retentionCount = Number.parseInt(raw, 10);
        if (!Number.isInteger(retentionCount) || retentionCount <= 0) {
            throw new Error('Retention count must be greater than zero.');
        }
        return retentionCount;
    }

    async connectGoogleDrive() {
        const connectPollGeneration = this._connectPollGeneration + 1;
        this._connectPollGeneration = connectPollGeneration;
        this.updateModalState({
            connecting: true,
            statusMessage: 'Opening Google sign-in...',
            error: '',
        });
        this.renderModalContent();
        const settled = await this._authRequest(
            CONFIG.API.BACKUP.GOOGLE_DRIVE.CONNECT_START,
            'POST',
            {},
        ).then(
            (payload) => ({ ok: true, payload }),
            (error) => ({ ok: false, error }),
        );
        if (!settled.ok) {
            this.updateModalState({
                connecting: false,
                statusMessage: '',
                error: this._errorMessage(settled.error),
            });
            this.renderModalContent();
            return;
        }
        const payload = settled.payload;
        if (!payload || typeof payload !== 'object') {
            this.updateModalState({
                connecting: false,
                statusMessage: '',
                error: 'Connect Google Drive response missing body',
            });
            this.renderModalContent();
            return;
        }
        if (typeof payload.request_id !== 'string' || payload.request_id.length === 0) {
            this.updateModalState({
                connecting: false,
                statusMessage: '',
                error: 'Connect Google Drive response missing request_id',
            });
            this.renderModalContent();
            return;
        }
        if (typeof payload.authorization_url !== 'string' || payload.authorization_url.length === 0) {
            this.updateModalState({
                connecting: false,
                statusMessage: '',
                error: 'Connect Google Drive response missing authorization_url',
            });
            this.renderModalContent();
            return;
        }
        const popup = window.open(payload.authorization_url, 'metalist-google-drive-connect', 'width=640,height=720');
        if (popup === null) {
            this.updateModalState({
                connecting: false,
                statusMessage: '',
                error: 'Popup was blocked. Allow popups and try again.',
            });
            this.renderModalContent();
            return;
        }
        const pollResult = await this._pollGoogleDriveConnectStatus(payload.request_id, popup, connectPollGeneration);
        if (this._connectPollGeneration !== connectPollGeneration || !this.isOpen) {
            return;
        }
        if (!pollResult.ok) {
            this.updateModalState({
                connecting: false,
                statusMessage: '',
                error: this._errorMessage(pollResult.error),
            });
            this.renderModalContent();
            return;
        }
        await this.loadSettings();
    }

    async disconnectGoogleDrive() {
        this.updateModalState({
            loading: true,
            statusMessage: 'Disconnecting Google Drive...',
            error: '',
        });
        this.renderModalContent();
        const settled = await this._authRequest(CONFIG.API.BACKUP.GOOGLE_DRIVE.DISCONNECT, 'POST', {}).then(
            () => ({ ok: true }),
            (error) => ({ ok: false, error }),
        );
        if (!settled.ok) {
            this.updateModalState({
                loading: false,
                statusMessage: '',
                error: this._errorMessage(settled.error),
            });
            this.renderModalContent();
            return;
        }
        await this.loadSettings();
    }

    async _pollGoogleDriveConnectStatus(requestId, popup, connectPollGeneration) {
        if (typeof requestId !== 'string' || requestId.length === 0) {
            throw new Error('_pollGoogleDriveConnectStatus requires requestId');
        }
        if (!popup || typeof popup !== 'object') {
            throw new Error('_pollGoogleDriveConnectStatus requires popup window');
        }
        let attempt = 0;
        while (this._connectPollGeneration === connectPollGeneration && this.isOpen) {
            attempt += 1;
            const settled = await this._authRequest(
                CONFIG.API.BACKUP.GOOGLE_DRIVE.CONNECT_STATUS(requestId),
                'GET',
                null,
            ).then(
                (payload) => ({ ok: true, payload }),
                (error) => ({ ok: false, error }),
            );
            if (!settled.ok) {
                return { ok: false, error: settled.error };
            }
            const payload = settled.payload;
            if (!payload || typeof payload !== 'object') {
                return { ok: false, error: new Error('Google Drive connect status response missing body') };
            }
            if (typeof payload.status !== 'string' || payload.status.length === 0) {
                return { ok: false, error: new Error('Google Drive connect status missing status') };
            }
            if (typeof payload.message !== 'string') {
                return { ok: false, error: new Error('Google Drive connect status missing message') };
            }
            this.updateModalState({
                statusMessage: payload.message,
                error: '',
            });
            this.renderModalContent();
            if (payload.status === 'success') {
                return { ok: true };
            }
            if (payload.status === 'error' || payload.status === 'expired') {
                return { ok: false, error: new Error(payload.message) };
            }
            if (payload.status !== 'pending') {
                return { ok: false, error: new Error(`Unexpected Google Drive connect status: ${payload.status}`) };
            }
            if (attempt >= 600) {
                return { ok: false, error: new Error('Google Drive authorization timed out. Start again.') };
            }
            if (typeof popup.closed === 'boolean' && popup.closed) {
                this.updateModalState({
                    statusMessage: 'Browser closed. Waiting for Google Drive result...',
                    error: '',
                });
                this.renderModalContent();
            }
            await this._sleep(1000);
        }
        return { ok: false, error: new Error('Google Drive authorization was interrupted.') };
    }

    async handleRunBackup() {
        const state = this.getModalState();
        const localEnabled = Boolean(state.localEnabled);
        const googleDriveEnabled = Boolean(state.googleDriveEnabled);
        const googleDriveConnected = Boolean(state.googleDriveConnected);
        let retentionCount = 0;
        if (!localEnabled && !googleDriveEnabled) {
            this.updateModalState({
                error: 'Enable local, Google Drive, or both before running a backup.',
            });
            this.renderModalContent();
            return;
        }
        if (googleDriveEnabled && !googleDriveConnected) {
            this.updateModalState({
                error: 'Connect Google Drive before enabling Drive backups.',
            });
            this.renderModalContent();
            return;
        }
        const retentionResult = await Promise.resolve()
            .then(() => this._parseRetentionCount())
            .then(
                (value) => ({ ok: true, value }),
                (error) => ({ ok: false, error }),
            );
        if (!retentionResult.ok) {
            this.updateModalState({
                error: this._errorMessage(retentionResult.error),
            });
            this.renderModalContent();
            return;
        }
        retentionCount = retentionResult.value;

        this.updateModalState({
            saving: true,
            error: '',
        });
        this.renderModalContent();

        const settled = await this._authRequest(CONFIG.API.BACKUP.SETTINGS, 'PUT', {
            local_enabled: localEnabled,
            google_drive_enabled: googleDriveEnabled,
            retention_count: retentionCount,
        }).then(
            () => ({ ok: true }),
            (error) => ({ ok: false, error }),
        );
        if (!settled.ok) {
            this.updateModalState({
                saving: false,
                error: this._errorMessage(settled.error),
            });
            this.renderModalContent();
            return;
        }

        this._closeResult = { action: 'run_backup' };
        this.close();
    }
}
