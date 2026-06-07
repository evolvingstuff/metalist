import { BaseModal } from './base-modal.js';
import { CONFIG } from '../config.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';
import { buildSessionHeaders } from '../session-auth.js';
import { settleResult } from '../async-result.js';


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


function backupSourceLabel(source) {
    if (source === 'folder') {
        return 'Folder';
    }
    return 'Local';
}


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


function stringifyPort(portValue) {
    if (portValue === null) {
        return '';
    }
    if (!Number.isInteger(portValue)) {
        throw new Error('stringifyPort requires integer or null');
    }
    return String(portValue);
}


function parsePort(rawValue, label) {
    if (typeof rawValue !== 'string') {
        throw new Error(`${label} is required`);
    }
    const trimmed = rawValue.trim();
    if (trimmed.length === 0) {
        throw new Error(`${label} is required`);
    }
    if (!/^[0-9]+$/.test(trimmed)) {
        throw new Error(`${label} must be numeric`);
    }
    const port = Number.parseInt(trimmed, 10);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
        throw new Error(`${label} must be between 1 and 65535`);
    }
    return port;
}


function validatePortsDoNotOverlap(profile) {
    const pairs = [
        ['HTTP', profile.port],
        ['HTTPS', profile.https_port],
        ['MCP', profile.mcp_port],
    ];
    const seen = new Map();
    for (const [service, port] of pairs) {
        if (port === null) {
            continue;
        }
        if (seen.has(port)) {
            throw new Error(`${service} port ${port} conflicts with ${seen.get(port)} port`);
        }
        seen.set(port, service);
    }
}


export class BackupRestoreModal extends BaseModal {
    constructor() {
        super('backupRestoreModal', 'backup-restore-modal');
        this.apiEndpoints = {
            list: CONFIG.API.BACKUP.LIST,
            restore: CONFIG.API.BACKUP.RESTORE,
            restorePreflight: CONFIG.API.BACKUP.RESTORE_PREFLIGHT,
            restoreImport: CONFIG.API.BACKUP.RESTORE_IMPORT,
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
            preflight: null,
            portDraft: null,
            overwriteConfirmText: '',
            targetPassword: '',
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
        const topModal = ModeContext.topModal;
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
        const overwriteConfirmText = typeof state.overwriteConfirmText === 'string' ? state.overwriteConfirmText : '';
        const targetPassword = typeof state.targetPassword === 'string' ? state.targetPassword : '';
        const preflight = state.preflight && typeof state.preflight === 'object' ? state.preflight : null;
        const portDraft = state.portDraft && typeof state.portDraft === 'object' ? state.portDraft : null;
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
            const sourceLabel = backupSourceLabel(backup.source);
            const isSelected = backup.backup_id === selectedBackupId ? 'selected' : '';
            const label = `${sourceLabel} · ${backup.namespace} · ${backup.filename} (${Math.round(backup.size_bytes / 1024)} KB, ${backup.created_at})`;
            return `<option value="${escapeHtml(backup.backup_id)}" ${isSelected}>${escapeHtml(label)}</option>`;
        }).join('');

        const selectedNamespace = selectedBackup && typeof selectedBackup.namespace === 'string' ? selectedBackup.namespace : '';
        const isImport = Boolean(preflight && preflight.same_namespace === false);
        const targetExists = Boolean(preflight && preflight.target_exists === true);
        const targetRequiresPassword = Boolean(preflight && preflight.target_requires_password === true);
        const portConflicts = preflight && Array.isArray(preflight.port_conflicts) ? preflight.port_conflicts : [];
        const conflictHtml = portConflicts.length > 0
            ? `<ul>${portConflicts.map((conflict) => `<li>${escapeHtml(String(conflict))}</li>`).join('')}</ul>`
            : '';
        const overwriteWarningHtml = confirming && isImport && targetExists ? `
            <div class="namespace-delete-warning backup-restore-danger-warning">
                <p><strong>BIG WARNING:</strong> this will overwrite existing namespace <span class="namespace-delete-namespace">${escapeHtml(targetNamespaceText.trim())}</span> with backup data from <span class="namespace-delete-namespace">${escapeHtml(selectedNamespace)}</span>.</p>
                <p>This is not the normal same-name restore path. Type <strong>${escapeHtml(targetNamespaceText.trim())}</strong> to enable the import.</p>
                <input type="text" id="backup-overwrite-confirmation" value="${escapeHtml(overwriteConfirmText)}" placeholder="Type target namespace">
                ${targetRequiresPassword ? `
                    <label class="backup-restore-target-password-label" for="backup-target-password">Target namespace password</label>
                    <input type="password" id="backup-target-password" value="${escapeHtml(targetPassword)}" autocomplete="current-password" placeholder="Password for ${escapeHtml(targetNamespaceText.trim())}">
                ` : ''}
            </div>
        ` : '';
        const portConfigHtml = confirming && isImport && portDraft ? `
            <div class="backup-restore-port-config">
                <h4>Launch Ports For Imported Namespace</h4>
                ${portConflicts.length > 0 ? `<p>The restored backup uses ports already reserved by another namespace. Choose replacement ports before importing.</p>${conflictHtml}` : '<p>Review the launch ports that will be saved for the imported namespace.</p>'}
                <div class="namespace-ports-table-wrap">
                    <table class="namespace-ports-table">
                        <thead>
                            <tr>
                                <th scope="col">Namespace</th>
                                <th scope="col">HTTP</th>
                                ${portDraft.httpsPort !== null ? '<th scope="col">HTTPS</th>' : ''}
                                <th scope="col">MCP</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <th scope="row">${escapeHtml(targetNamespaceText.trim())}</th>
                                <td><input class="backup-restore-port-input" data-field="port" type="number" min="1" max="65535" value="${escapeHtml(portDraft.port)}" ${restoring ? 'disabled' : ''}></td>
                                ${portDraft.httpsPort !== null ? `<td><input class="backup-restore-port-input" data-field="httpsPort" type="number" min="1" max="65535" value="${escapeHtml(portDraft.httpsPort)}" ${restoring ? 'disabled' : ''}></td>` : ''}
                                <td><input class="backup-restore-port-input" data-field="mcpPort" type="number" min="1" max="65535" value="${escapeHtml(portDraft.mcpPort)}" ${restoring ? 'disabled' : ''}></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        ` : '';
        let restoreButtonLabel = 'Restore Selected Backup';
        if (confirming && isImport && targetExists) {
            restoreButtonLabel = 'Import And Overwrite Namespace';
        } else if (confirming && isImport) {
            restoreButtonLabel = 'Confirm Import';
        } else if (confirming) {
            restoreButtonLabel = 'Confirm Restore';
        }
        const restoreButtonClass = confirming && isImport && targetExists ? 'danger-btn' : 'primary-btn';

        if (confirming) {
            if (selectedBackup === null) {
                throw new Error('Confirming restore without selected backup');
            }
            let confirmationSummaryHtml = '';
            if (isImport) {
                const targetStatus = targetExists ? 'existing namespace' : 'new namespace';
                confirmationSummaryHtml = `
                    <p>Import backup <span class="backup-filename">${escapeHtml(selectedBackup.filename)}</span></p>
                    <p>From namespace <strong>${escapeHtml(selectedNamespace)}</strong> into ${targetStatus} <strong>${escapeHtml(targetNamespaceText.trim())}</strong>.</p>
                `;
            } else {
                confirmationSummaryHtml = `
                    <p>Restore backup <span class="backup-filename">${escapeHtml(selectedBackup.filename)}</span></p>
                    <p>This will overwrite namespace <strong>${escapeHtml(targetNamespaceText.trim())}</strong>.</p>
                `;
            }
            const sameNamespaceWarningHtml = !isImport ? `
                <div class="namespace-delete-warning backup-restore-danger-warning">
                    <p><strong>Warning:</strong> this restore overwrites the target namespace.</p>
                </div>
            ` : '';
            modalElement.innerHTML = `
                <div class="modal-content backup-restore-modal-content">
                    <h3>${isImport ? 'Import Backup' : 'Restore From Backup'}</h3>
                    ${confirmationSummaryHtml}
                    ${sameNamespaceWarningHtml}
                    ${overwriteWarningHtml}
                    ${portConfigHtml}

                    <div class="form-actions">
                        <button type="button" class="${restoreButtonClass}" id="restore-backup-btn" ${restoring || backups.length === 0 ? 'disabled' : ''}>${restoreButtonLabel}</button>
                        <button type="button" class="secondary-btn" id="close-backup-modal-btn" ${restoring ? 'disabled' : ''}>Back</button>
                    </div>

                    <p id="backup-modal-status">${restoring ? 'Restoring backup...' : ''}</p>
                    <p id="backup-modal-error" class="error-message">${escapeHtml(error)}</p>
                </div>
            `;
            this.setupFormEventListeners();
            return;
        }

        modalElement.innerHTML = `
            <div class="modal-content backup-restore-modal-content">
                <h3>Restore From Backup</h3>
                <p>Select a backup snapshot and restore the workspace data.</p>
                <p>Same-name restores overwrite that namespace. Different-name imports create a namespace unless the target already exists.</p>

                <div class="form-group">
                    <label for="backup-select">Available Backups</label>
                    <select id="backup-select" size="${selectSize}" ${loading || restoring || confirming || backups.length === 0 ? 'disabled' : ''}>
                        ${optionsHtml}
                    </select>
                </div>

                <div class="form-group">
                    <label for="backup-target-namespace">Target namespace</label>
                    <input type="text" id="backup-target-namespace" value="${escapeHtml(targetNamespaceText)}" ${loading || restoring || confirming || backups.length === 0 ? 'disabled' : ''}>
                </div>

                <p>${selectedNamespace ? `Backup namespace: ${escapeHtml(selectedNamespace)}` : ''}</p>

                <div class="form-actions">
                    <button type="button" class="${restoreButtonClass}" id="restore-backup-btn" ${loading || restoring || backups.length === 0 ? 'disabled' : ''}>${restoreButtonLabel}</button>
                    <button type="button" class="secondary-btn" id="close-backup-modal-btn" ${restoring ? 'disabled' : ''}>${confirming ? 'Back' : 'Cancel'}</button>
                </div>

                <p id="backup-modal-status">${loading ? 'Loading backups...' : ''}${restoring ? ' Restoring backup...' : ''}</p>
                <p id="backup-modal-error" class="error-message">${escapeHtml(error)}</p>
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
                        preflight: null,
                        portDraft: null,
                        overwriteConfirmText: '',
                        targetPassword: '',
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
                    preflight: null,
                    portDraft: null,
                    overwriteConfirmText: '',
                    targetPassword: '',
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
                    preflight: null,
                    portDraft: null,
                    overwriteConfirmText: '',
                    targetPassword: '',
                    error: '',
                });
            };
        }

        const overwriteInput = document.getElementById('backup-overwrite-confirmation');
        if (overwriteInput instanceof HTMLInputElement) {
            overwriteInput.oninput = () => {
                this.updateModalState({
                    overwriteConfirmText: overwriteInput.value,
                    error: '',
                });
            };
        }

        const targetPasswordInput = document.getElementById('backup-target-password');
        if (targetPasswordInput instanceof HTMLInputElement) {
            targetPasswordInput.oninput = () => {
                this.updateModalState({
                    targetPassword: targetPasswordInput.value,
                    error: '',
                });
            };
        }

        const portInputs = document.querySelectorAll('.backup-restore-port-input');
        portInputs.forEach((input) => {
            if (!(input instanceof HTMLInputElement)) {
                return;
            }
            input.oninput = () => {
                const field = input.dataset.field;
                if (field !== 'port' && field !== 'httpsPort' && field !== 'mcpPort') {
                    throw new Error('Backup restore port input missing field');
                }
                const state = this.getModalState();
                const portDraft = state.portDraft && typeof state.portDraft === 'object' ? state.portDraft : null;
                if (portDraft === null) {
                    throw new Error('Backup restore port draft missing');
                }
                this.updateModalState({
                    portDraft: {
                        ...portDraft,
                        [field]: input.value,
                    },
                    error: '',
                });
            };
        });
    }

    _buildAuthHeaders(includeContentType) {
        return buildSessionHeaders(includeContentType);
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
            preflight: null,
            portDraft: null,
            overwriteConfirmText: '',
            targetPassword: '',
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
            preflight: null,
            portDraft: null,
            overwriteConfirmText: '',
            targetPassword: '',
            error: '',
        });
        this.renderModalContent();
    }

    _buildRestoreBasePayload(selectedBackup, targetNamespace) {
        if (!selectedBackup || typeof selectedBackup !== 'object') {
            throw new Error('Selected backup is missing');
        }
        return {
            backup_id: selectedBackup.backup_id,
            source: selectedBackup.source,
            backup_filename: selectedBackup.filename,
            backup_namespace: selectedBackup.namespace,
            target_namespace: targetNamespace,
        };
    }

    _buildPortProfileFromDraft() {
        const state = this.getModalState();
        const portDraft = state.portDraft && typeof state.portDraft === 'object' ? state.portDraft : null;
        if (portDraft === null) {
            throw new Error('Launch ports must be configured before importing');
        }
        const profile = {
            port: parsePort(portDraft.port, 'HTTP port'),
            https_port: portDraft.httpsPort === null ? null : parsePort(portDraft.httpsPort, 'HTTPS port'),
            mcp_port: parsePort(portDraft.mcpPort, 'MCP port'),
        };
        validatePortsDoNotOverlap(profile);
        return profile;
    }

    _portDraftFromProfile(profile) {
        if (!profile || typeof profile !== 'object') {
            throw new Error('Restore preflight missing suggested launch profile');
        }
        if (!Number.isInteger(profile.port)) {
            throw new Error('Restore preflight suggested profile missing HTTP port');
        }
        if (profile.https_port !== null && !Number.isInteger(profile.https_port)) {
            throw new Error('Restore preflight suggested profile missing HTTPS port');
        }
        if (!Number.isInteger(profile.mcp_port)) {
            throw new Error('Restore preflight suggested profile missing MCP port');
        }
        return {
            port: stringifyPort(profile.port),
            httpsPort: profile.https_port === null ? null : stringifyPort(profile.https_port),
            mcpPort: stringifyPort(profile.mcp_port),
        };
    }

    _findSelectedBackup(state) {
        const backups = Array.isArray(state.backups) ? state.backups : [];
        let selectedBackup = backups.find((backup) => backup.backup_id === state.selectedBackupId);
        if (typeof selectedBackup === 'undefined') {
            selectedBackup = null;
        }
        return selectedBackup;
    }

    _validateRestoreSelection(state) {
        if (typeof state.selectedBackupId !== 'string' || state.selectedBackupId.length === 0) {
            throw new Error('Select a backup first.');
        }
        const selectedBackup = this._findSelectedBackup(state);
        if (selectedBackup === null) {
            throw new Error('Selected backup is missing.');
        }
        if (typeof state.targetNamespaceText !== 'string' || state.targetNamespaceText.trim().length === 0) {
            throw new Error('Target namespace is required.');
        }
        return {
            selectedBackup,
            targetNamespace: state.targetNamespaceText.trim(),
        };
    }

    async _prepareRestoreConfirmation() {
        const state = this.getModalState();
        const selection = this._validateRestoreSelection(state);
        this.updateModalState({ error: '' });
        this.renderModalContent();
        const preflight = await this._authRequest(
            this.apiEndpoints.restorePreflight,
            'POST',
            this._buildRestoreBasePayload(selection.selectedBackup, selection.targetNamespace),
        );
        if (!preflight || typeof preflight !== 'object') {
            throw new Error('Restore preflight response missing body');
        }
        const sameNamespace = preflight.same_namespace === true;
        let portDraft = null;
        if (!sameNamespace) {
            const suggestedProfile = preflight.suggested_profile;
            portDraft = this._portDraftFromProfile(suggestedProfile);
        }
        this.updateModalState({
            confirming: true,
            preflight,
            portDraft,
            overwriteConfirmText: '',
            targetPassword: '',
            error: '',
        });
        this.renderModalContent();
    }

    async _submitConfirmedRestore() {
        const state = this.getModalState();
        const selection = this._validateRestoreSelection(state);
        const preflight = state.preflight && typeof state.preflight === 'object' ? state.preflight : null;
        if (preflight === null) {
            throw new Error('Restore preflight is required before restore');
        }
        const sameNamespace = preflight.same_namespace === true;
        const targetExists = preflight.target_exists === true;
        if (!sameNamespace && targetExists) {
            const confirmation = typeof state.overwriteConfirmText === 'string'
                ? state.overwriteConfirmText.trim()
                : '';
            if (confirmation !== selection.targetNamespace) {
                throw new Error(`Type ${selection.targetNamespace} to confirm overwriting that namespace`);
            }
            if (preflight.target_requires_password === true) {
                const targetPassword = typeof state.targetPassword === 'string' ? state.targetPassword : '';
                if (targetPassword.length === 0) {
                    throw new Error(`Enter the password for ${selection.targetNamespace}`);
                }
            }
        }
        this.updateModalState({
            restoring: true,
            error: '',
        });
        this.renderModalContent();

        const basePayload = this._buildRestoreBasePayload(selection.selectedBackup, selection.targetNamespace);
        let payload = null;
        if (sameNamespace) {
            payload = await this._authRequest(this.apiEndpoints.restore, 'POST', basePayload);
        } else {
            payload = await this._authRequest(this.apiEndpoints.restoreImport, 'POST', {
                ...basePayload,
                overwrite_existing_target: targetExists,
                target_password: typeof state.targetPassword === 'string' ? state.targetPassword : '',
                launch_profile: this._buildPortProfileFromDraft(),
            });
        }
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
            preflight: null,
            portDraft: null,
            overwriteConfirmText: '',
            targetPassword: '',
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

    async handleRestore() {
        const restoreResult = await settleResult(async () => {
            const state = this.getModalState();
            if (!state.confirming) {
                await this._prepareRestoreConfirmation();
                return;
            }
            await this._submitConfirmedRestore();
        });
        if (!restoreResult.ok) {
            const error = restoreResult.error;
            const message = error instanceof Error ? error.message : 'Restore failed';
            this.updateModalState({
                restoring: false,
                error: message,
            });
            this.renderModalContent();
        }
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
