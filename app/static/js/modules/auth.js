/**
 * Authentication module for handling login/logout and password management
 */
import { CONFIG } from './config.js';
import { createUuid } from './uuid.js';
import { CommandPalette } from './command-palette/command-palette-controller.js';
import { consumeBooleanQueryFlag } from './location-flags.js';

export const Auth = {
    hasPassword: null,
    _forcingLogout: false,
    _tabId: null,
    _startupIntroPromise: null,
    _startupIntroResolved: false,

    _isStartupIntroEnabled() {
        return CONFIG.STARTUP.ENABLE_LOGIN_INTRO === true;
    },
    
    /**
     * Initialize authentication on page load
     * Returns true if OK to proceed with app initialization
     */
    async init() {
        this._ensureTabId();
        this.setupEventListeners();
        if (this._isStartupIntroEnabled()) {
            this._startStartupIntro();
        } else {
            this._startupIntroResolved = true;
            this._startupIntroPromise = Promise.resolve();
        }
        return await this.checkAuthStatus();
    },
    
    /**
     * Check authentication status and show login if needed
     * Returns true if authenticated/no password, false if login required
     */
    async checkAuthStatus() {
        const forceReauth = consumeBooleanQueryFlag({
            location: window.location,
            history: window.history,
            flagName: 'force_reauth',
        });
        if (forceReauth) {
            console.log('[Auth] force_reauth requested, clearing local session state');
            this.clearSessionState();
        }

        const token = localStorage.getItem('auth_token');
        console.log('[Auth] Checking status with token:', token ? token.substring(0, 10) + '...' : 'none');
        const activeOwner = localStorage.getItem('auth_owner');
        const ownerMismatch = Boolean(token && activeOwner && activeOwner !== this._tabId);
        const missingOwner = Boolean(token && !activeOwner);

        const headers = {};
        headers['X-Metalist-Tab-Id'] = this._tabId;
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(CONFIG.API.AUTH.STATUS, { headers });
        if (!response.ok) {
            throw new Error(`Status request failed with ${response.status}`);
        }

        const status = await response.json();
        this.hasPassword = Boolean(status.has_password);
        console.log('[Auth] Status response:', status);

        if (this.hasPassword) {
            if (!status.authenticated || ownerMismatch || missingOwner) {
                if (token) {
                    console.log('[Auth] Clearing token for password-protected mismatch');
                    this.clearSessionState();
                }
                this.showLoginModal();
                return false;
            }
            if (this._isStartupIntroEnabled()) {
                this.showStartupSplash('Opening encrypted workspace…', 'Preparing your encrypted workspace…');
            }
            return true;
        }

        if (this._isStartupIntroEnabled()) {
            this.showStartupSplash('Opening workspace…', 'Preparing workspace…');
        }

        if (ownerMismatch || missingOwner || !status.authenticated) {
            if (ownerMismatch || missingOwner) {
                console.log('[Auth] Passwordless takeover detected, clearing local token');
                this.clearSessionState();
            }
            await this.claimPasswordlessSession();
        }

        return true;
    },

    async claimPasswordlessSession() {
        console.log('[Auth] Claiming passwordless session');
        const response = await fetch(CONFIG.API.AUTH.SESSION, {
            method: 'POST',
            headers: {
                'X-Metalist-Tab-Id': this._tabId
            }
        });

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`Failed to claim session: ${response.status} ${detail}`);
        }

        const data = await response.json();
        if (!data.token) {
            throw new Error('Session response missing token');
        }

        this._setTokenForThisTab(data.token);
        console.log('[Auth] Passwordless session established');
        return data.token;
    },

    _requireElement(id) {
        const element = document.getElementById(id);
        if (element === null) {
            throw new Error(`Missing required auth element: ${id}`);
        }
        return element;
    },

    _setLoginSubtitle(text) {
        if (typeof text !== 'string' || text.length === 0) {
            throw new Error('Auth._setLoginSubtitle requires text string');
        }
        const subtitle = this._requireElement('login-subtitle');
        subtitle.textContent = text;
    },

    _setStartupMessage(text) {
        if (typeof text !== 'string' || text.length === 0) {
            throw new Error('Auth._setStartupMessage requires text string');
        }
        const startupMessage = this._requireElement('startup-message');
        startupMessage.textContent = text;
    },

    _clearLoginError() {
        const errorDiv = this._requireElement('login-error');
        errorDiv.style.display = 'none';
        errorDiv.textContent = '';
    },

    _resetHydrationUI() {
        const message = this._requireElement('login-loading-message');
        const bar = this._requireElement('login-progress-bar');
        const firstLoad = this._requireElement('login-loading-first');
        message.textContent = '';
        bar.style.width = '0%';
        firstLoad.style.display = 'none';
    },

    _startStartupIntro() {
        if (this._startupIntroPromise !== null) {
            return;
        }
        if (!this._isStartupIntroEnabled()) {
            throw new Error('Startup intro is disabled');
        }

        const loginPage = this._requireElement('login-page');
        const mainApp = this._requireElement('main-app');
        const video = this._requireElement('login-startup-video');

        loginPage.style.display = 'flex';
        mainApp.style.display = 'none';
        this.showStartupSplash('Opening workspace…', 'Preparing workspace…');

        this._startupIntroPromise = new Promise((resolve) => {
            const finishIntro = () => {
                if (this._startupIntroResolved) {
                    return;
                }
                this._startupIntroResolved = true;
                video.pause();
                resolve();
            };

            video.addEventListener('ended', finishIntro, { once: true });
            video.addEventListener('error', finishIntro, { once: true });

            const playPromise = video.play();
            if (playPromise !== undefined && playPromise !== null && typeof playPromise.then === 'function') {
                playPromise.catch((error) => {
                    console.warn('[Auth] Startup intro playback failed:', error);
                    finishIntro();
                });
            }
        });
    },

    async waitForStartupIntro() {
        if (this._startupIntroPromise === null) {
            throw new Error('Startup intro not initialized');
        }
        await this._startupIntroPromise;
    },

    showStartupSplash(subtitle, message) {
        if (typeof subtitle !== 'string' || subtitle.length === 0) {
            throw new Error('Auth.showStartupSplash requires subtitle string');
        }
        if (typeof message !== 'string' || message.length === 0) {
            throw new Error('Auth.showStartupSplash requires message string');
        }
        if (!this._isStartupIntroEnabled()) {
            throw new Error('Startup splash requested while startup intro is disabled');
        }

        const loginPage = this._requireElement('login-page');
        const mainApp = this._requireElement('main-app');
        const startupSplash = this._requireElement('startup-splash');
        const loginForm = this._requireElement('login-form');
        const loadingPanel = this._requireElement('login-loading');

        mainApp.style.display = 'none';
        loginPage.style.display = 'flex';
        startupSplash.style.display = 'flex';
        loginForm.style.display = 'none';
        loadingPanel.style.display = 'none';
        this._setLoginSubtitle(subtitle);
        this._setStartupMessage(message);
        this._resetHydrationUI();
        this._clearLoginError();
    },
    
    /**
     * Show the login page and hide main app
     */
    showLoginModal() {
        const loginPage = this._requireElement('login-page');
        const mainApp = this._requireElement('main-app');
        const passwordInput = this._requireElement('login-password');
        const startupSplash = this._requireElement('startup-splash');
        const loginForm = this._requireElement('login-form');
        const loadingPanel = this._requireElement('login-loading');

        mainApp.style.display = 'none';
        loginPage.style.display = 'flex';
        startupSplash.style.display = 'none';
        loginForm.style.display = 'block';
        loadingPanel.style.display = 'none';
        this._setLoginSubtitle('Authentication Required');
        this._resetHydrationUI();
        this._clearLoginError();

        setTimeout(() => {
            passwordInput.focus();
        }, 100);
    },
    
    /**
     * Hide the login page and show main app
     */
    revealMainApp() {
        const loginPage = this._requireElement('login-page');
        const mainApp = this._requireElement('main-app');
        const passwordInput = this._requireElement('login-password');

        loginPage.style.display = 'none';
        mainApp.style.display = 'block';
        this._resetHydrationUI();
        this._clearLoginError();
        passwordInput.value = '';
    },

    _showHydrationUI() {
        const startupSplash = this._requireElement('startup-splash');
        const loginForm = this._requireElement('login-form');
        const loadingPanel = this._requireElement('login-loading');

        this._resetHydrationUI();
        startupSplash.style.display = 'none';
        loginForm.style.display = 'none';
        loadingPanel.style.display = 'block';
        this._setLoginSubtitle('Loading encrypted data…');
        this._clearLoginError();
    },

    _updateHydrationUI(status) {
        const message = document.getElementById('login-loading-message');
        const bar = document.getElementById('login-progress-bar');
        const firstLoad = document.getElementById('login-loading-first');

        if (message) {
            if (typeof status.message === 'string') {
                const trimmed = status.message.trim();
                if (trimmed.length > 0) {
                    const needsEllipsis = !(trimmed.endsWith('...') || trimmed.endsWith('…'));
                    message.textContent = needsEllipsis ? `${trimmed}...` : trimmed;
                } else {
                    message.textContent = '';
                }
            } else {
                message.textContent = '';
            }
        }
        if (firstLoad) {
            firstLoad.style.display = status.first_load ? 'block' : 'none';
        }
        if (typeof status.overall_percent === 'number') {
            let percent = Math.floor(status.overall_percent);
            if (percent > 100) {
                percent = 100;
            }
            if (percent < 0) {
                percent = 0;
            }
            if (bar) {
                bar.style.width = `${percent}%`;
            }
        } else if (typeof status.total === 'number' && status.total > 0) {
            const percent = Math.min(100, Math.floor((status.processed / status.total) * 100));
            if (bar) {
                bar.style.width = `${percent}%`;
            }
        } else {
            if (bar) {
                bar.style.width = '0%';
            }
        }
    },

    async _runHydrationFlow() {
        this._showHydrationUI();

        const token = localStorage.getItem('auth_token');
        if (!token) {
            throw new Error('Missing auth token for hydration');
        }

        const headers = {
            'Authorization': `Bearer ${token}`,
            'X-Metalist-Tab-Id': this._tabId,
        };

        const startResponse = await fetch(CONFIG.API.AUTH.HYDRATE, {
            method: 'POST',
            headers,
        });

        if (!startResponse.ok) {
            const detail = await startResponse.text();
            throw new Error(`Failed to start hydration: ${startResponse.status} ${detail}`);
        }

        let status = await startResponse.json();
        this._updateHydrationUI(status);

        while (status.status !== 'ready') {
            if (status.status === 'error') {
                if (typeof status.error === 'string' && status.error.length > 0) {
                    throw new Error(status.error);
                }
                throw new Error('Hydration failed');
            }
            await new Promise((resolve) => setTimeout(resolve, 200));
            const pollResponse = await fetch(CONFIG.API.AUTH.HYDRATION_STATUS, { headers });
            if (!pollResponse.ok) {
                const detail = await pollResponse.text();
                throw new Error(`Hydration status failed: ${pollResponse.status} ${detail}`);
            }
            status = await pollResponse.json();
            this._updateHydrationUI(status);
        }
    },
    
    /**
     * Show error message in login modal
     */
    showLoginError(message) {
        const errorDiv = document.getElementById('login-error');
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    },
    
    /**
     * Handle login form submission
     */
    async handleLogin(event) {
        event.preventDefault();
        
        const passwordInput = document.getElementById('login-password');
        const password = passwordInput.value;
        
        if (!password) {
            this.showLoginError('Please enter a password');
            return;
        }
        
        document.body.classList.add('loading');

        try {
            const response = await fetch(CONFIG.API.AUTH.LOGIN, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Metalist-Tab-Id': this._tabId,
                },
                body: JSON.stringify({ password })
            });

            if (response.ok) {
                const data = await response.json();

                if (!data || typeof data !== 'object') {
                    throw new Error('Login response missing body');
                }
                if (typeof data.token !== 'string' || data.token.length === 0) {
                    throw new Error('Login response missing token');
                }

                this._setTokenForThisTab(data.token);
                console.log('[Auth] Token stored in localStorage:', data.token.substring(0, 10) + '...');

                const storedToken = localStorage.getItem('auth_token');
                console.log('[Auth] Token verification - stored correctly:', storedToken === data.token);

                console.log('[Auth] Login successful');

                if (data.hydration_required) {
                    await this._runHydrationFlow();
                }

                console.log('[Auth] Login successful, initializing ModeManager');
                if (window.ModeManager) {
                    window.ModeManager.init({});
                    await CommandPalette.init();
                    await this.waitForStartupIntro();
                    this.revealMainApp();
                } else {
                    window.location.reload();
                }
                return;
            }

            const errorBody = await response.json();
            if (!errorBody || typeof errorBody !== 'object') {
                throw new Error('Login error response missing body');
            }
            if (typeof errorBody.detail !== 'string') {
                throw new Error('Login error response missing detail');
            }
            this.showLoginError(errorBody.detail);
        } catch (error) {
            this.showLoginModal();
            if (error instanceof Error) {
                this.showLoginError(error.message);
            }
            if (!(error instanceof Error)) {
                this.showLoginError('Login failed');
                throw new Error('Login failed');
            }
            throw error;
        } finally {
            document.body.classList.remove('loading');
        }
    },
    
    /**
     * Handle logout
     */
    async logout() {
        const token = localStorage.getItem('auth_token');
        
        if (token) {
            await fetch(CONFIG.API.AUTH.LOGOUT, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                    'X-Metalist-Tab-Id': this._tabId,
                }
            }).finally(() => {
                this.clearSessionState();
                window.location.reload();
            });
            return;
        }
        
        this.clearSessionState();
        window.location.reload();
    },

    clearSessionState() {
        localStorage.removeItem('auth_token');
        sessionStorage.removeItem('metalist_client_id');
        localStorage.removeItem('auth_owner');
    },

    forceLogout(message) {
        if (typeof message !== 'string' || message.length === 0) {
            throw new Error('Auth.forceLogout requires message string');
        }
        if (this._forcingLogout) {
            return;
        }
        this._forcingLogout = true;
        console.warn('[Auth] Forcing logout:', message);
        this.clearSessionState();

        if (document.body) {
            document.body.replaceChildren();
        }

        window.location.replace('/locked');
    },

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Login form submission
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }
        
        // Close modal when clicking outside
        window.addEventListener('click', (event) => {
            const loginModal = document.getElementById('login-modal');
            if (event.target === loginModal) {
                // Don't allow closing login modal by clicking outside if auth is required
                // this.hideLoginModal();
            }
        });
        
        // ESC key to close modal (but only if auth is not required)
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                // Don't close login modal with ESC if auth is required
                // this.hideLoginModal();
            }
        });

        window.addEventListener('storage', (event) => {
            if (!event) {
                return;
            }

            if (event.key === 'auth_owner') {
                const activeOwner = localStorage.getItem('auth_owner');
                if (!activeOwner) {
                    this.forceLogout('Session ended.');
                    return;
                }
                if (activeOwner !== this._tabId) {
                    this.forceLogout('Session moved to another tab.');
                }
                return;
            }

            if (event.key === 'auth_token' && event.newValue === null) {
                this.forceLogout('Session ended.');
            }
        });
    },

    _ensureTabId() {
        if (this._tabId) {
            return;
        }
        let tabId = sessionStorage.getItem('metalist_tab_id');
        if (!tabId) {
            tabId = createUuid();
            sessionStorage.setItem('metalist_tab_id', tabId);
        }
        this._tabId = tabId;
    },

    _setTokenForThisTab(token) {
        if (!token) {
            throw new Error('Cannot store empty auth token');
        }
        localStorage.setItem('auth_token', token);
        localStorage.setItem('auth_owner', this._tabId);
    }
};

// Make showLoginModal available globally for API client
window.showLoginModal = () => Auth.showLoginModal();
window.Auth = Auth;
