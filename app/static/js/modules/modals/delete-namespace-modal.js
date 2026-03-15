import { BaseModal } from './base-modal.js';
import { CONFIG } from '../config.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';
import {
    DELETE_NAMESPACE_CONFIRMATION_PHRASE,
    validateNamespaceDeletionSubmission,
} from './delete-namespace-validation.js';


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


export class DeleteNamespaceModal extends BaseModal {
    constructor() {
        super('deleteNamespaceModal', 'delete-namespace-modal');
        this.apiEndpoints = {
            status: CONFIG.API.AUTH.STATUS,
            deleteCurrent: CONFIG.API.AUTH.NAMESPACES.DELETE_CURRENT,
        };
    }

    getInitialModalState() {
        return {
            loading: true,
            deleting: false,
            namespace: '',
            hasPassword: false,
            confirmationText: '',
            currentPassword: '',
            error: '',
            status: 'Loading namespace settings...',
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
        await this.loadStatus();
    }

    onClose() {
        this.updateModalState(this.getInitialModalState());
    }

    handleKeyDown(event) {
        const topModal = ModeContext.modalStack?.[ModeContext.modalStack.length - 1];
        if (topModal !== this.modalName) {
            return;
        }

        const state = this.getModalState();
        const deleting = Boolean(state.deleting);
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            if (!deleting) {
                this.close();
            }
            return;
        }

        this.onKeyDown(event);
    }

    onKeyDown(event) {
        if (!(event instanceof KeyboardEvent)) {
            throw new Error('DeleteNamespaceModal.onKeyDown requires KeyboardEvent');
        }
        if (event.key !== 'Enter') {
            return;
        }
        const activeElement = document.activeElement;
        if (activeElement instanceof HTMLButtonElement) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        void this.handleSubmit();
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }

        const state = this.getModalState();
        const loading = Boolean(state.loading);
        const deleting = Boolean(state.deleting);
        const namespace = typeof state.namespace === 'string' ? state.namespace : '';
        const hasPassword = state.hasPassword === true;
        const confirmationText = typeof state.confirmationText === 'string' ? state.confirmationText : '';
        const currentPassword = typeof state.currentPassword === 'string' ? state.currentPassword : '';
        const error = typeof state.error === 'string' ? state.error : '';
        const status = typeof state.status === 'string' ? state.status : '';

        if (loading) {
            modalElement.innerHTML = `
                <div class="modal-content namespace-delete-modal-content">
                    <h3>Delete Current Namespace</h3>
                    <p class="namespace-delete-status">${escapeHtml(status)}</p>
                    <div class="form-actions">
                        <button type="button" class="secondary-btn" id="delete-namespace-cancel-loading-btn">Cancel</button>
                    </div>
                    <p class="error-message" ${error.length === 0 ? 'style="display:none;"' : ''}>${escapeHtml(error)}</p>
                </div>
            `;
            const cancelButton = document.getElementById('delete-namespace-cancel-loading-btn');
            if (cancelButton instanceof HTMLButtonElement) {
                cancelButton.onclick = () => this.close();
            }
            return;
        }

        if (namespace === 'default') {
            modalElement.innerHTML = `
                <div class="modal-content namespace-delete-modal-content">
                    <h3>Delete Current Namespace</h3>
                    <p>The default namespace cannot be deleted.</p>
                    <div class="form-actions">
                        <button type="button" class="secondary-btn" id="delete-namespace-default-close-btn">Close</button>
                    </div>
                </div>
            `;
            const closeButton = document.getElementById('delete-namespace-default-close-btn');
            if (closeButton instanceof HTMLButtonElement) {
                closeButton.onclick = () => this.close();
            }
            return;
        }

        modalElement.innerHTML = `
            <div class="modal-content namespace-delete-modal-content">
                <h3>Delete Current Namespace</h3>
                <div class="namespace-delete-warning">
                    <p>This permanently deletes the namespace, its notes database, file database, backups, and saved ports.</p>
                    <p class="namespace-delete-namespace">Namespace: <strong>${escapeHtml(namespace)}</strong></p>
                    <p>After deletion, this tab moves to a namespace-removal page that shows progress and lets you choose where to go next.</p>
                    <p>Type <span class="namespace-delete-phrase">${escapeHtml(DELETE_NAMESPACE_CONFIRMATION_PHRASE)}</span> to confirm.</p>
                </div>

                <div class="form-group">
                    <label for="delete-namespace-confirmation">Confirmation</label>
                    <input
                        id="delete-namespace-confirmation"
                        type="text"
                        value="${escapeHtml(confirmationText)}"
                        placeholder="${escapeHtml(DELETE_NAMESPACE_CONFIRMATION_PHRASE)}"
                        autocomplete="off"
                        autocorrect="off"
                        autocapitalize="off"
                        spellcheck="false"
                        ${deleting ? 'disabled' : ''}
                    />
                </div>

                ${hasPassword ? `
                    <div class="form-group">
                        <label for="delete-namespace-current-password">Current Password</label>
                        <input
                            id="delete-namespace-current-password"
                            type="password"
                            value="${escapeHtml(currentPassword)}"
                            autocomplete="current-password"
                            ${deleting ? 'disabled' : ''}
                        />
                    </div>
                ` : ''}

                <div class="form-actions">
                    <button type="button" class="danger-btn" id="delete-namespace-submit-btn" ${deleting ? 'disabled' : ''}>
                        Delete Namespace
                    </button>
                    <button type="button" class="secondary-btn" id="delete-namespace-cancel-btn" ${deleting ? 'disabled' : ''}>Cancel</button>
                </div>

                <p class="namespace-delete-status">${escapeHtml(status)}</p>
                <p class="error-message" ${error.length === 0 ? 'style="display:none;"' : ''}>${escapeHtml(error)}</p>
            </div>
        `;

        this.setupFormEventListeners();
    }

    setupFormEventListeners() {
        const confirmationInput = document.getElementById('delete-namespace-confirmation');
        if (confirmationInput instanceof HTMLInputElement) {
            confirmationInput.oninput = () => {
                this.updateModalState({
                    confirmationText: confirmationInput.value,
                    error: '',
                    status: '',
                });
            };
        }

        const passwordInput = document.getElementById('delete-namespace-current-password');
        if (passwordInput instanceof HTMLInputElement) {
            passwordInput.oninput = () => {
                this.updateModalState({
                    currentPassword: passwordInput.value,
                    error: '',
                    status: '',
                });
            };
        }

        const submitButton = document.getElementById('delete-namespace-submit-btn');
        if (submitButton instanceof HTMLButtonElement) {
            submitButton.onclick = async () => {
                await this.handleSubmit();
            };
        }

        const cancelButton = document.getElementById('delete-namespace-cancel-btn');
        if (cancelButton instanceof HTMLButtonElement) {
            cancelButton.onclick = () => {
                this.close();
            };
        }
    }

    async loadStatus() {
        this.updateModalState({
            loading: true,
            deleting: false,
            error: '',
            status: 'Loading namespace settings...',
        });
        this.renderModalContent();
        try {
            const status = await this._authRequest(this.apiEndpoints.status, 'GET', null);
            if (!status || typeof status !== 'object') {
                throw new Error('Namespace delete status response missing body');
            }
            if (typeof status.namespace !== 'string' || status.namespace.length === 0) {
                throw new Error('Namespace delete status response missing namespace');
            }
            if (typeof status.has_password !== 'boolean') {
                throw new Error('Namespace delete status response missing password state');
            }
            this.updateModalState({
                loading: false,
                namespace: status.namespace,
                hasPassword: status.has_password,
                confirmationText: '',
                currentPassword: '',
                error: '',
                status: '',
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to load namespace settings';
            this.updateModalState({
                loading: false,
                error: message,
                status: '',
            });
        }
        this.renderModalContent();
    }

    async handleSubmit() {
        const state = this.getModalState();
        let payload;
        try {
            payload = validateNamespaceDeletionSubmission({
                namespace: state.namespace,
                confirmationText: state.confirmationText,
                currentPassword: state.currentPassword,
                hasPassword: state.hasPassword === true,
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Invalid namespace deletion request';
            this.updateModalState({
                error: message,
                status: '',
            });
            this.renderModalContent();
            return;
        }

        this.updateModalState({
            deleting: true,
            error: '',
            status: 'Deleting namespace...',
        });
        this.renderModalContent();

        try {
            const response = await this._authRequest(this.apiEndpoints.deleteCurrent, 'POST', payload);
            if (!response || typeof response !== 'object') {
                throw new Error('Namespace delete response missing body');
            }
            if (typeof response.delete_job_id !== 'string' || response.delete_job_id.length === 0) {
                throw new Error('Namespace delete response missing delete_job_id');
            }
            if (typeof response.redirect_url !== 'string' || response.redirect_url.length === 0) {
                throw new Error('Namespace delete response missing redirect_url');
            }
            if (!response.redirect_url.includes(response.delete_job_id)) {
                throw new Error('Namespace delete response missing job redirect state');
            }
            window.location.replace(response.redirect_url);
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to delete namespace';
            this.updateModalState({
                deleting: false,
                error: message,
                status: '',
            });
            this.renderModalContent();
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
            throw new Error('_authRequest requires url string');
        }
        if (typeof method !== 'string' || method.length === 0) {
            throw new Error('_authRequest requires method string');
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
        return payload;
    }
}
