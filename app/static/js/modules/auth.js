/**
 * Authentication module for handling login/logout and password management
 */
import { CONFIG } from './config.js';

export const Auth = {
    hasPassword: null,
    _forcingLogout: false,
    _tabId: null,
    
    /**
     * Initialize authentication on page load
     * Returns true if OK to proceed with app initialization
     */
    async init() {
        this._ensureTabId();
        this.setupEventListeners();
        return await this.checkAuthStatus();
    },
    
    /**
     * Check authentication status and show login if needed
     * Returns true if authenticated/no password, false if login required
     */
    async checkAuthStatus() {
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
            return true;
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
    
    /**
     * Show the login page and hide main app
     */
    showLoginModal() {
        const loginPage = document.getElementById('login-page');
        const mainApp = document.getElementById('main-app');
        const passwordInput = document.getElementById('login-password');
        
        // Hide main app and show login page
        mainApp.style.display = 'none';
        loginPage.style.display = 'flex';
        
        // Focus password input after a short delay
        setTimeout(() => {
            passwordInput.focus();
        }, 100);
        
        // Clear any previous errors
        const errorDiv = document.getElementById('login-error');
        errorDiv.style.display = 'none';
        errorDiv.textContent = '';
    },
    
    /**
     * Hide the login page and show main app
     */
    hideLoginModal() {
        const loginPage = document.getElementById('login-page');
        const mainApp = document.getElementById('main-app');
        
        // Show main app and hide login page
        loginPage.style.display = 'none';
        mainApp.style.display = 'block';
        
        // Clear the password input
        document.getElementById('login-password').value = '';
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

        await (async () => {
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

                this.hideLoginModal();

                console.log('[Auth] Login successful, initializing ModeManager');
                if (window.ModeManager) {
                    window.ModeManager.init({});
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
        })().finally(() => {
            document.body.classList.remove('loading');
        });
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
            tabId = crypto.randomUUID();
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
