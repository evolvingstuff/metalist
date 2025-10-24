/**
 * Authentication module for handling login/logout and password management
 */
import { CONFIG } from './config.js';

export const Auth = {
    
    /**
     * Initialize authentication on page load
     * Returns true if OK to proceed with app initialization
     */
    async init() {
        this.setupEventListeners();
        return await this.checkAuthStatus();
    },
    
    /**
     * Check authentication status and show login if needed
     * Returns true if authenticated/no password, false if login required
     */
    async checkAuthStatus() {
        try {
            // Get stored token
            const token = localStorage.getItem('auth_token');
            console.log('[Auth] Checking status with token:', token ? token.substring(0, 10) + '...' : 'none');
            
            // Include token in request if we have one
            const headers = {};
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            
            const response = await fetch(CONFIG.API.AUTH.STATUS, { headers });
            const status = await response.json();
            
            console.log('[Auth] Status response:', status);
            
            // If password is required and we're not authenticated, show login
            if (status.has_password && !status.authenticated) {
                // Clear invalid token if we have one
                if (token) {
                    console.log('[Auth] Token is invalid, removing from storage');
                    localStorage.removeItem('auth_token');
                }
                this.showLoginModal();
                return false; // Block further initialization
            }
            
            return true; // OK to proceed
        } catch (error) {
            console.error('[Auth] Failed to check status:', error);
            return false; // Block on error
        }
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
        
        try {
            // Show waiting cursor
            document.body.classList.add('loading');
            
            const response = await fetch(CONFIG.API.AUTH.LOGIN, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ password })
            });
            
            if (response.ok) {
                const data = await response.json();
                
                // Store the token
                localStorage.setItem('auth_token', data.token);
                console.log('[Auth] Token stored in localStorage:', data.token.substring(0, 10) + '...');
                
                // Verify it was stored
                const storedToken = localStorage.getItem('auth_token');
                console.log('[Auth] Token verification - stored correctly:', storedToken === data.token);
                
                console.log('[Auth] Login successful');
                
                // Hide login modal
                this.hideLoginModal();
                
                // Initialize ModeManager now that we're authenticated
                console.log('[Auth] Login successful, initializing ModeManager');
                if (window.ModeManager) {
                    window.ModeManager.init();
                } else {
                    // Fallback: reload if ModeManager not available
                    window.location.reload();
                }
                
            } else {
                const error = await response.json();
                this.showLoginError(error.detail || 'Login failed');
                // Remove waiting cursor on error
                document.body.classList.remove('loading');
            }
        } catch (error) {
            console.error('[Auth] Login error:', error);
            this.showLoginError('Network error. Please try again.');
            // Remove waiting cursor on error
            document.body.classList.remove('loading');
        }
    },
    
    /**
     * Handle logout
     */
    async logout() {
        const token = localStorage.getItem('auth_token');
        
        if (token) {
            try {
                // Call logout endpoint to revoke token
                await fetch(CONFIG.API.AUTH.LOGOUT, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                });
            } catch (error) {
                console.error('[Auth] Logout API call failed:', error);
            }
        }
        
        // Clear token from storage
        localStorage.removeItem('auth_token');
        
        // Reload page to show login
        window.location.reload();
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
    }
};

// Make showLoginModal available globally for API client
window.showLoginModal = () => Auth.showLoginModal();
