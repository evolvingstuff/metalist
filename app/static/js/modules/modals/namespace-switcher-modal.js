import { BaseModal } from './base-modal.js';
import { CONFIG } from '../config.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';
import { ErrorHandler } from '../error-handler.js';
import { buildNamespaceLoadingPageHtml } from './namespace-loading-page.js';


const NAMESPACE_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;


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


function stringifyPort(portValue) {
    if (portValue === null) {
        return '';
    }
    if (!Number.isInteger(portValue)) {
        throw new Error('stringifyPort requires integer or null');
    }
    return String(portValue);
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


export class NamespaceSwitcherModal extends BaseModal {
    constructor() {
        super('namespaceSwitcherModal', 'namespace-switcher-modal');
        this.apiEndpoints = {
            list: CONFIG.API.AUTH.NAMESPACES.LIST,
            open: CONFIG.API.AUTH.NAMESPACES.OPEN,
        };
    }

    getInitialModalState() {
        return {
            loading: true,
            submitting: false,
            mode: 'existing',
            catalog: null,
            selectedNamespace: '',
            newNamespace: '',
            port: '',
            httpsPort: '',
            mcpPort: '',
            error: '',
            status: 'Loading namespaces...',
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
        await this.loadCatalog();
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
        const submitting = Boolean(state.submitting);
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            if (!submitting) {
                this.close();
            }
            return;
        }

        this.onKeyDown(event);
    }

    onKeyDown(event) {
        if (!(event instanceof KeyboardEvent)) {
            throw new Error('NamespaceSwitcherModal.onKeyDown requires KeyboardEvent');
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
        const catalog = state.catalog;
        const loading = Boolean(state.loading);
        const submitting = Boolean(state.submitting);
        const mode = typeof state.mode === 'string' ? state.mode : 'existing';
        const error = typeof state.error === 'string' ? state.error : '';
        const status = typeof state.status === 'string' ? state.status : '';
        const selectedNamespace = typeof state.selectedNamespace === 'string' ? state.selectedNamespace : '';
        const newNamespace = typeof state.newNamespace === 'string' ? state.newNamespace : '';
        const port = typeof state.port === 'string' ? state.port : '';
        const httpsPort = typeof state.httpsPort === 'string' ? state.httpsPort : '';
        const mcpPort = typeof state.mcpPort === 'string' ? state.mcpPort : '';

        if (loading || !catalog) {
            modalElement.innerHTML = `
                <div class="modal-content namespace-switcher-modal-content">
                    <h3>Switch Namespace</h3>
                    <p class="namespace-switcher-status">${escapeHtml(status)}</p>
                    <div class="form-actions namespace-switcher-actions">
                        <button type="button" class="secondary-btn" id="namespace-switcher-close-loading-btn">Cancel</button>
                    </div>
                    <p class="error-message" ${error.length === 0 ? 'style="display:none;"' : ''}>${escapeHtml(error)}</p>
                </div>
            `;
            const closeButton = document.getElementById('namespace-switcher-close-loading-btn');
            if (closeButton instanceof HTMLButtonElement) {
                closeButton.onclick = () => this.close();
            }
            return;
        }

        const namespaces = Array.isArray(catalog.namespaces) ? catalog.namespaces : [];
        const currentNamespace = typeof catalog.current_namespace === 'string' ? catalog.current_namespace : 'default';
        const supportsHttps = Boolean(catalog.supports_https);
        const selectedEntry = namespaces.find((entry) => entry.namespace === selectedNamespace) || null;
        const summaryHtml = this._renderSummary({
            mode,
            currentNamespace,
            selectedEntry,
            newNamespace,
        });
        const existingOptionsHtml = namespaces.map((entry) => {
            if (!entry || typeof entry !== 'object') {
                throw new Error('Invalid namespace catalog entry');
            }
            const namespace = entry.namespace;
            if (typeof namespace !== 'string' || namespace.length === 0) {
                throw new Error('Namespace catalog entry missing namespace');
            }
            const selected = namespace === selectedNamespace ? 'selected' : '';
            const suffix = entry.is_current ? ' (current)' : '';
            return `<option value="${escapeHtml(namespace)}" ${selected}>${escapeHtml(namespace + suffix)}</option>`;
        }).join('');

        modalElement.innerHTML = `
            <div class="modal-content namespace-switcher-modal-content">
                <h3>Switch Namespace</h3>
                <p>Open another namespace in a new browser tab, or create a new namespace with its own ports and database.</p>

                <div class="namespace-switcher-mode-row">
                    <button
                        type="button"
                        class="${mode === 'existing' ? 'primary-btn' : 'secondary-btn'}"
                        id="namespace-mode-existing-btn"
                        ${submitting ? 'disabled' : ''}
                    >Existing Namespace</button>
                    <button
                        type="button"
                        class="${mode === 'create' ? 'primary-btn' : 'secondary-btn'}"
                        id="namespace-mode-create-btn"
                        ${submitting ? 'disabled' : ''}
                    >Create New Namespace</button>
                </div>

                ${mode === 'existing' ? `
                    <div class="form-group">
                        <label for="namespace-switcher-select">Namespace</label>
                        <select id="namespace-switcher-select" ${submitting ? 'disabled' : ''}>
                            ${existingOptionsHtml}
                        </select>
                    </div>
                ` : `
                    <div class="form-group">
                        <label for="namespace-switcher-new-name">Namespace Name</label>
                        <input
                            id="namespace-switcher-new-name"
                            type="text"
                            value="${escapeHtml(newNamespace)}"
                            placeholder="work"
                            autocomplete="off"
                            autocorrect="off"
                            autocapitalize="off"
                            spellcheck="false"
                            ${submitting ? 'disabled' : ''}
                        />
                        <small class="form-help">Lowercase letters, digits, and hyphens only.</small>
                    </div>
                `}

                <div class="namespace-switcher-port-grid">
                    <div class="form-group">
                        <label for="namespace-switcher-port">HTTP Port</label>
                        <input
                            id="namespace-switcher-port"
                            type="number"
                            min="1"
                            max="65535"
                            value="${escapeHtml(port)}"
                            ${submitting ? 'disabled' : ''}
                        />
                    </div>
                    ${supportsHttps ? `
                        <div class="form-group">
                            <label for="namespace-switcher-https-port">HTTPS Port</label>
                            <input
                                id="namespace-switcher-https-port"
                                type="number"
                                min="1"
                                max="65535"
                                value="${escapeHtml(httpsPort)}"
                                ${submitting ? 'disabled' : ''}
                            />
                        </div>
                    ` : ''}
                    <div class="form-group">
                        <label for="namespace-switcher-mcp-port">MCP Port</label>
                        <input
                            id="namespace-switcher-mcp-port"
                            type="number"
                            min="1"
                            max="65535"
                            value="${escapeHtml(mcpPort)}"
                            ${submitting ? 'disabled' : ''}
                        />
                    </div>
                </div>

                ${summaryHtml}

                <div class="form-actions namespace-switcher-actions">
                    <button type="button" class="primary-btn" id="namespace-switcher-submit-btn" ${submitting ? 'disabled' : ''}>
                        ${mode === 'existing' ? 'Open Namespace' : 'Create and Open Namespace'}
                    </button>
                    <button type="button" class="secondary-btn" id="namespace-switcher-cancel-btn" ${submitting ? 'disabled' : ''}>Cancel</button>
                </div>

                <p class="namespace-switcher-status">${escapeHtml(status)}</p>
                <p class="error-message" ${error.length === 0 ? 'style="display:none;"' : ''}>${escapeHtml(error)}</p>
            </div>
        `;

        this.setupFormEventListeners();
    }

    _renderSummary({ mode, currentNamespace, selectedEntry, newNamespace }) {
        const summaryLines = [];
        summaryLines.push(`Current namespace: ${currentNamespace}`);
        if (mode === 'existing' && selectedEntry) {
            const databaseExists = selectedEntry.database_exists === true ? 'yes' : 'no';
            const savedPorts = selectedEntry.has_launch_profile === true ? 'yes' : 'no';
            summaryLines.push(`Database already exists: ${databaseExists}`);
            summaryLines.push(`Saved ports already exist: ${savedPorts}`);
        }
        if (mode === 'create' && typeof newNamespace === 'string' && newNamespace.trim().length > 0) {
            summaryLines.push(`New namespace: ${newNamespace.trim()}`);
        }
        return `
            <div class="namespace-switcher-summary">
                ${summaryLines.map((line) => `<p>${escapeHtml(line)}</p>`).join('')}
            </div>
        `;
    }

    setupFormEventListeners() {
        const existingButton = document.getElementById('namespace-mode-existing-btn');
        if (existingButton instanceof HTMLButtonElement) {
            existingButton.onclick = () => {
                this._switchMode('existing');
            };
        }

        const createButton = document.getElementById('namespace-mode-create-btn');
        if (createButton instanceof HTMLButtonElement) {
            createButton.onclick = () => {
                this._switchMode('create');
            };
        }

        const select = document.getElementById('namespace-switcher-select');
        if (select instanceof HTMLSelectElement) {
            select.onchange = () => {
                const namespace = select.value;
                const nextState = this._buildStateForExistingNamespace(namespace);
                this.updateModalState({
                    selectedNamespace: nextState.selectedNamespace,
                    port: nextState.port,
                    httpsPort: nextState.httpsPort,
                    mcpPort: nextState.mcpPort,
                    error: '',
                    status: '',
                });
                this.renderModalContent();
            };
        }

        const newNameInput = document.getElementById('namespace-switcher-new-name');
        if (newNameInput instanceof HTMLInputElement) {
            newNameInput.oninput = () => {
                this.updateModalState({
                    newNamespace: newNameInput.value,
                    error: '',
                    status: '',
                });
            };
        }

        const portInput = document.getElementById('namespace-switcher-port');
        if (portInput instanceof HTMLInputElement) {
            portInput.oninput = () => {
                this.updateModalState({
                    port: portInput.value,
                    error: '',
                    status: '',
                });
            };
        }

        const httpsPortInput = document.getElementById('namespace-switcher-https-port');
        if (httpsPortInput instanceof HTMLInputElement) {
            httpsPortInput.oninput = () => {
                this.updateModalState({
                    httpsPort: httpsPortInput.value,
                    error: '',
                    status: '',
                });
            };
        }

        const mcpPortInput = document.getElementById('namespace-switcher-mcp-port');
        if (mcpPortInput instanceof HTMLInputElement) {
            mcpPortInput.oninput = () => {
                this.updateModalState({
                    mcpPort: mcpPortInput.value,
                    error: '',
                    status: '',
                });
            };
        }

        const submitButton = document.getElementById('namespace-switcher-submit-btn');
        if (submitButton instanceof HTMLButtonElement) {
            submitButton.onclick = async () => {
                await this.handleSubmit();
            };
        }

        const cancelButton = document.getElementById('namespace-switcher-cancel-btn');
        if (cancelButton instanceof HTMLButtonElement) {
            cancelButton.onclick = () => {
                this.close();
            };
        }
    }

    async loadCatalog() {
        this.updateModalState({
            loading: true,
            submitting: false,
            error: '',
            status: 'Loading namespaces...',
        });
        this.renderModalContent();
        try {
            const catalog = await this._authRequest(this.apiEndpoints.list, 'GET', null);
            this._assertCatalogShape(catalog);
            const initialSelection = this._pickInitialExistingNamespace(catalog);
            const nextState = this._buildStateForExistingNamespace(initialSelection, catalog);
            this.updateModalState({
                loading: false,
                catalog,
                mode: 'existing',
                selectedNamespace: nextState.selectedNamespace,
                newNamespace: '',
                port: nextState.port,
                httpsPort: nextState.httpsPort,
                mcpPort: nextState.mcpPort,
                error: '',
                status: '',
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to load namespaces';
            this.updateModalState({
                loading: false,
                error: message,
                status: '',
            });
        }
        this.renderModalContent();
    }

    _pickInitialExistingNamespace(catalog) {
        const namespaces = Array.isArray(catalog.namespaces) ? catalog.namespaces : [];
        const firstNonCurrent = namespaces.find((entry) => entry.is_current !== true);
        if (firstNonCurrent && typeof firstNonCurrent.namespace === 'string') {
            return firstNonCurrent.namespace;
        }
        const firstEntry = namespaces[0];
        if (firstEntry && typeof firstEntry.namespace === 'string') {
            return firstEntry.namespace;
        }
        throw new Error('Namespace catalog returned no namespaces');
    }

    _buildStateForExistingNamespace(namespace, catalogOverride) {
        const state = this.getModalState();
        const catalog = catalogOverride || state.catalog;
        this._assertCatalogShape(catalog);
        if (typeof namespace !== 'string' || namespace.length === 0) {
            throw new Error('Existing namespace selection requires namespace');
        }
        const namespaces = Array.isArray(catalog.namespaces) ? catalog.namespaces : [];
        const entry = namespaces.find((candidate) => candidate.namespace === namespace);
        if (!entry) {
            throw new Error(`Unknown namespace: ${namespace}`);
        }
        const profile = entry.default_profile;
        this._assertProfileShape(profile);
        return {
            selectedNamespace: namespace,
            port: stringifyPort(profile.port),
            httpsPort: stringifyPort(profile.https_port),
            mcpPort: stringifyPort(profile.mcp_port),
        };
    }

    _buildStateForNewNamespace() {
        const state = this.getModalState();
        const catalog = state.catalog;
        this._assertCatalogShape(catalog);
        const profile = catalog.new_namespace_profile;
        this._assertProfileShape(profile);
        return {
            port: stringifyPort(profile.port),
            httpsPort: stringifyPort(profile.https_port),
            mcpPort: stringifyPort(profile.mcp_port),
        };
    }

    _switchMode(nextMode) {
        if (nextMode !== 'existing' && nextMode !== 'create') {
            throw new Error('Namespace switcher mode must be existing or create');
        }
        if (nextMode === 'existing') {
            const stateForExisting = this._buildStateForExistingNamespace(this.getModalState().selectedNamespace || this._pickInitialExistingNamespace(this.getModalState().catalog));
            this.updateModalState({
                mode: 'existing',
                selectedNamespace: stateForExisting.selectedNamespace,
                port: stateForExisting.port,
                httpsPort: stateForExisting.httpsPort,
                mcpPort: stateForExisting.mcpPort,
                error: '',
                status: '',
            });
        } else {
            const stateForNew = this._buildStateForNewNamespace();
            this.updateModalState({
                mode: 'create',
                newNamespace: '',
                port: stateForNew.port,
                httpsPort: stateForNew.httpsPort,
                mcpPort: stateForNew.mcpPort,
                error: '',
                status: '',
            });
        }
        this.renderModalContent();
    }

    _assertCatalogShape(catalog) {
        if (!catalog || typeof catalog !== 'object') {
            throw new Error('Namespace catalog response missing body');
        }
        if (!Array.isArray(catalog.namespaces)) {
            throw new Error('Namespace catalog response missing namespaces');
        }
        if (!catalog.new_namespace_profile || typeof catalog.new_namespace_profile !== 'object') {
            throw new Error('Namespace catalog response missing new_namespace_profile');
        }
    }

    _assertProfileShape(profile) {
        if (!profile || typeof profile !== 'object') {
            throw new Error('Namespace profile missing');
        }
        if (!Number.isInteger(profile.port)) {
            throw new Error('Namespace profile missing port');
        }
        if (profile.https_port !== null && !Number.isInteger(profile.https_port)) {
            throw new Error('Namespace profile missing https_port');
        }
        if (!Number.isInteger(profile.mcp_port)) {
            throw new Error('Namespace profile missing mcp_port');
        }
    }

    _validateSubmission() {
        const state = this.getModalState();
        const catalog = state.catalog;
        this._assertCatalogShape(catalog);
        const mode = typeof state.mode === 'string' ? state.mode : 'existing';
        const supportsHttps = Boolean(catalog.supports_https);

        let namespace = '';
        if (mode === 'existing') {
            if (typeof state.selectedNamespace !== 'string' || state.selectedNamespace.length === 0) {
                throw new Error('Select a namespace');
            }
            namespace = state.selectedNamespace;
        } else {
            if (typeof state.newNamespace !== 'string') {
                throw new Error('Enter a namespace name');
            }
            namespace = state.newNamespace.trim();
            if (namespace.length === 0) {
                throw new Error('Enter a namespace name');
            }
            if (!NAMESPACE_PATTERN.test(namespace)) {
                throw new Error("Namespace must contain only lowercase letters, digits, and '-'");
            }
            const duplicate = catalog.namespaces.find((entry) => entry.namespace === namespace);
            if (duplicate) {
                throw new Error('That namespace already exists. Use Existing Namespace instead.');
            }
        }

        const port = this._parsePort(state.port, 'HTTP port');
        const httpsPort = supportsHttps ? this._parsePort(state.httpsPort, 'HTTPS port') : null;
        const mcpPort = this._parsePort(state.mcpPort, 'MCP port');

        const localPorts = [
            { label: 'HTTP', value: port },
            { label: 'HTTPS', value: httpsPort },
            { label: 'MCP', value: mcpPort },
        ];
        const seenPorts = new Map();
        for (const localPort of localPorts) {
            if (localPort.value === null) {
                continue;
            }
            if (seenPorts.has(localPort.value)) {
                const otherLabel = seenPorts.get(localPort.value);
                throw new Error(`${localPort.label} port conflicts with ${otherLabel} port`);
            }
            seenPorts.set(localPort.value, localPort.label);
        }

        const reservations = Array.isArray(catalog.reserved_ports) ? catalog.reserved_ports : [];
        for (const reservation of reservations) {
            if (!reservation || typeof reservation !== 'object') {
                continue;
            }
            if (reservation.namespace === namespace) {
                continue;
            }
            for (const localPort of localPorts) {
                if (localPort.value === null) {
                    continue;
                }
                if (reservation.port === localPort.value) {
                    throw new Error(
                        `${localPort.label} port ${localPort.value} conflicts with ${reservation.service.toUpperCase()} port `
                        + `reserved for namespace ${reservation.namespace}`
                    );
                }
            }
        }

        return {
            namespace,
            port,
            https_port: httpsPort,
            mcp_port: mcpPort,
        };
    }

    _parsePort(rawValue, label) {
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
        const parsed = Number.parseInt(trimmed, 10);
        if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
            throw new Error(`${label} must be between 1 and 65535`);
        }
        return parsed;
    }

    async handleSubmit() {
        let payload;
        try {
            payload = this._validateSubmission();
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Invalid namespace settings';
            this.updateModalState({
                error: message,
                status: '',
            });
            this.renderModalContent();
            return;
        }

        const pendingTab = window.open('about:blank', '_blank');
        this._renderLoadingTab(pendingTab, payload.namespace);
        this.updateModalState({
            submitting: true,
            error: '',
            status: 'Opening namespace...',
        });
        this.renderModalContent();

        try {
            const response = await this._authRequest(this.apiEndpoints.open, 'POST', payload);
            if (!response || typeof response !== 'object') {
                throw new Error('Namespace open response missing body');
            }
            if (typeof response.url !== 'string' || response.url.length === 0) {
                throw new Error('Namespace open response missing url');
            }
            if (pendingTab && !pendingTab.closed) {
                pendingTab.location.replace(response.url);
            } else {
                window.open(response.url, '_blank', 'noopener,noreferrer');
            }
            if (typeof response.message === 'string' && response.message.length > 0) {
                ErrorHandler.showInfoBanner(response.message, 5000);
            }
            this.close();
        } catch (error) {
            if (pendingTab && !pendingTab.closed) {
                pendingTab.close();
            }
            const message = error instanceof Error ? error.message : 'Failed to open namespace';
            this.updateModalState({
                submitting: false,
                error: message,
                status: '',
            });
            this.renderModalContent();
        }
    }

    _renderLoadingTab(pendingTab, namespace) {
        if (!pendingTab || pendingTab.closed) {
            return;
        }
        try {
            const loadingHtml = buildNamespaceLoadingPageHtml(namespace);
            pendingTab.document.open();
            pendingTab.document.write(loadingHtml);
            pendingTab.document.close();
        } catch (error) {
            console.warn('Failed to render namespace loading tab:', error);
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

        if (payload === null) {
            throw new Error('Response payload missing');
        }
        return payload;
    }
}
