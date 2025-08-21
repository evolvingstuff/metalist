/**
 * Error Handler - Centralized error handling for authentication and network errors
 */

import { ModeContextInstance as ModeContext } from './mode-manager/mode-context.js';

export const ErrorHandler = {
    
    /**
     * Handle different types of API errors with appropriate UX
     */
    handleApiError(error, response = null) {
        console.error('[ErrorHandler] Handling error:', error, response);
        
        if (response) {
            // HTTP response error
            if (response.status === 401) {
                this.handleAuthError('Your session has expired. Please log in again.');
            } else if (response.status >= 500) {
                this.handleNetworkError(`Server error (${response.status}). Please try again.`);
            } else if (response.status >= 400) {
                this.handleNetworkError(`Request failed (${response.status}). Please check your input and try again.`);
            } else {
                this.handleNetworkError(`Unexpected error (${response.status}). Please try again.`);
            }
        } else {
            // Network/connection error (fetch throws)
            if (error.name === 'TypeError' && (
                error.message.includes('fetch') || 
                error.message.includes('Network request failed') ||
                error.message.includes('Failed to fetch')
            )) {
                this.handleNetworkError('Cannot reach server. Please check your internet connection.');
            } else if (error.name === 'AbortError') {
                this.handleNetworkError('Request timed out. Please try again.');
            } else {
                this.handleNetworkError(`Network error: ${error.message || 'Unknown error'}. Please try again.`);
            }
        }
    },
    
    /**
     * Handle authentication errors (401) - show login screen
     */
    handleAuthError(message = 'Authentication required. Please log in again.') {
        console.log('[ErrorHandler] Auth error:', message);
        
        // Clear invalid token
        localStorage.removeItem('auth_token');
        
        // Show login screen with error message
        if (window.Auth) {
            window.Auth.showLoginModal();
            if (message !== 'Your session has expired. Please log in again.') {
                // Show custom message if it's not the default
                window.Auth.showLoginError(message);
            }
        } else {
            // Fallback: reload page
            console.warn('[ErrorHandler] Auth module not available, reloading page');
            window.location.reload();
        }
    },
    
    /**
     * Handle network errors - show error banner but keep interface visible
     */
    handleNetworkError(message = 'Network error. Please try again.') {
        console.log('[ErrorHandler] Network error:', message);
        
        // Check if we're already showing a connection error banner
        if (!ModeContext.connectionErrorBannerVisible) {
            // First network error - show banner and set disconnected state
            if (ModeContext.isConnected) {
                ModeContext.setConnected(false);
            }
            ModeContext.setConnectionErrorBannerVisible(true);
            this.showPersistentErrorBanner(message);
            this.disableEditingUI();
        }
        // If banner is already visible, don't create a new one
    },
    
    /**
     * Handle successful connection - hide error banner if showing
     */
    handleConnectionRestored() {
        // Only process if we were actually disconnected
        if (!ModeContext.isConnected || ModeContext.connectionErrorBannerVisible) {
            console.log('[ErrorHandler] Connection restored');
            
            if (!ModeContext.isConnected) {
                ModeContext.setConnected(true);
            }
            
            if (ModeContext.connectionErrorBannerVisible) {
                ModeContext.setConnectionErrorBannerVisible(false);
                this.hideErrorBanner();
                this.showSuccessBanner('Connection restored', 3000);
                this.enableEditingUI();
            }
        }
        // If already connected, do nothing silently
    },
    
    /**
     * Disable all contenteditable elements when disconnected
     */
    disableEditingUI() {
        // Find all potentially editable elements (both active and inactive)
        const editableElements = document.querySelectorAll('.note-content');
        
        editableElements.forEach(element => {
            // Save original state
            if (element.getAttribute('contenteditable') === 'true') {
                element.setAttribute('data-was-contenteditable', 'true');
            }
            
            // Disable editing and apply disconnected styling
            element.setAttribute('contenteditable', 'false');
            element.classList.add('disconnected-state');
            element.style.cursor = 'not-allowed';
            element.style.opacity = '0.7';
            element.style.pointerEvents = 'none'; // Prevent any interaction
        });
        
        // Exit edit mode immediately without server calls if currently editing
        if (ModeContext.isEditing) {
            // Force exit edit mode without saving (server is down anyway)
            ModeContext.setEditing(false);
            ModeContext.setCurrentNoteId(null);
            ModeContext.setCurrentContent(null);
            console.log('[ErrorHandler] Force-exited edit mode due to disconnection');
        }
    },
    
    /**
     * Re-enable contenteditable elements when connection restored
     */
    enableEditingUI() {
        // Re-enable all note content elements
        document.querySelectorAll('.note-content.disconnected-state').forEach(element => {
            // Remove disconnected styling
            element.classList.remove('disconnected-state');
            element.style.cursor = '';
            element.style.opacity = '';
            element.style.pointerEvents = '';
            
            // Restore contenteditable state if it was previously editable
            if (element.getAttribute('data-was-contenteditable') === 'true') {
                element.removeAttribute('data-was-contenteditable');
                // Don't set contenteditable back to true - let the app manage that
            } else {
                // Make sure it's set to false for non-editing elements
                element.setAttribute('contenteditable', 'false');
            }
        });
    },
    
    /**
     * Show persistent error banner (no auto-hide, no close button)
     */
    showPersistentErrorBanner(message, type = 'error') {
        this.showErrorBanner(message, type, 0, false); // duration = 0 means no auto-hide, showClose = false
    },
    
    /**
     * Show error banner at top of screen
     */
    showErrorBanner(message, type = 'error', duration = 8000, showClose = true) {
        // Remove any existing banner
        this.hideErrorBanner();
        
        // Create banner element
        const banner = document.createElement('div');
        banner.id = 'error-banner';
        banner.className = `error-banner error-banner-${type}`;
        
        const closeButton = showClose ? 
            `<button class="error-banner-close" onclick="ErrorHandler.hideErrorBanner()" aria-label="Close">×</button>` : '';
            
        banner.innerHTML = `
            <div class="error-banner-content">
                <span class="error-banner-icon">${type === 'error' ? '⚠️' : type === 'success' ? '✅' : 'ℹ️'}</span>
                <span class="error-banner-message">${message}</span>
                ${closeButton}
            </div>
        `;
        
        // Add to page
        document.body.insertBefore(banner, document.body.firstChild);
        
        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => this.hideErrorBanner(), duration);
        }
        
        // Animate in
        setTimeout(() => banner.classList.add('error-banner-visible'), 10);
    },
    
    /**
     * Hide error banner
     */
    hideErrorBanner() {
        const banner = document.getElementById('error-banner');
        if (banner) {
            banner.classList.remove('error-banner-visible');
            setTimeout(() => {
                if (banner.parentNode) {
                    banner.parentNode.removeChild(banner);
                }
            }, 300);
        }
    },
    
    /**
     * Show success message banner
     */
    showSuccessBanner(message, duration = 4000) {
        this.showErrorBanner(message, 'success', duration);
    },
    
    /**
     * Show info message banner  
     */
    showInfoBanner(message, duration = 6000) {
        this.showErrorBanner(message, 'info', duration);
    }
};

// Make available globally
window.ErrorHandler = ErrorHandler;