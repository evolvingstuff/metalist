/**
 * PasswordModal - Password management modal with three modes
 * 
 * Modes:
 * - create: Set initial password (when none exists)
 * - change: Change existing password 
 * - remove: Remove password protection
 */

import { BaseModal } from './base-modal.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';
import { CONFIG } from '../config.js';

export class PasswordModal extends BaseModal {
    constructor() {
        super('passwordModal', 'password-modal');
        this.apiEndpoints = {
            status: CONFIG.API.AUTH.STATUS,
            create: CONFIG.API.AUTH.SETTINGS.PASSWORD.CREATE,
            change: CONFIG.API.AUTH.SETTINGS.PASSWORD.CHANGE,
            remove: CONFIG.API.AUTH.SETTINGS.PASSWORD.REMOVE
        };
    }
    
    /**
     * Initialize modal state based on current auth status
     */
    getInitialModalState() {
        return {
            mode: null, // Will be determined by API call
            currentStep: 1,
            isProcessing: false,
            error: null,
            formData: {
                currentPassword: '',
                newPassword: '',
                confirmPassword: ''
            }
        };
    }
    
    /**
     * Called after modal opens - determine mode and setup UI
     */
    async onOpen() {
        try {
            // Determine which mode we should be in
            const response = await fetch(this.apiEndpoints.status);
            const status = await response.json();
            
            const mode = status.has_password ? 'change' : 'create';
            this.updateModalState({ mode });
            
            // Setup the UI for the determined mode
            this.renderModalContent();
            
        } catch (error) {
            console.error('Failed to determine password modal mode:', error);
            this.updateModalState({ 
                error: 'Failed to load password settings. Please try again.' 
            });
            this.renderError();
        }
    }
    
    /**
     * Called before modal closes - cleanup form data
     */
    onClose() {
        // Clear sensitive form data
        this.updateModalState({
            formData: {
                currentPassword: '',
                newPassword: '',
                confirmPassword: ''
            },
            error: null,
            isProcessing: false
        });
    }
    
    /**
     * Handle modal-specific keyboard shortcuts
     */
    onKeyDown(event) {
        const state = this.getModalState();
        
        // Enter to submit (if not processing)
        if (event.key === 'Enter' && !state.isProcessing) {
            event.preventDefault();
            this.handleSubmit();
        }
        
        // Escape handled by BaseModal (will close modal)
    }
    
    /**
     * Render the modal content based on current mode
     */
    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        const state = this.getModalState();
        
        if (!modalElement) {
            throw new Error(`Modal element not found: ${this.modalElementId}`);
        }
        
        const content = this.generateContentHTML(state);
        modalElement.innerHTML = content;
        
        // Setup form event listeners
        this.setupFormEventListeners();
    }
    
    /**
     * Generate HTML content based on modal state
     */
    generateContentHTML(state) {
        if (state.error) {
            return this.generateErrorHTML(state.error);
        }
        
        switch (state.mode) {
            case 'create':
                return this.generateCreatePasswordHTML();
            case 'change':
                return this.generateChangePasswordHTML();
            case 'remove':
                return this.generateRemovePasswordHTML();
            default:
                return this.generateLoadingHTML();
        }
    }
    
    generateCreatePasswordHTML() {
        return `
            <div class="modal-content">
                <h3>Create Password</h3>
                <p>Set a password to encrypt your notes. This password will be required to access your notes in the future.</p>
                
                <form id="password-form">
                    <div class="form-group">
                        <label for="new-password">New Password:</label>
                        <input type="password" id="new-password" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="confirm-password">Confirm Password:</label>
                        <input type="password" id="confirm-password" required>
                    </div>
                    
                    <div class="form-actions">
                        <button type="submit" class="primary-btn">Create Password</button>
                        <button type="button" class="secondary-btn" id="cancel-btn">Cancel</button>
                    </div>
                </form>
                
                <div id="progress-section" style="display: none;">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 0%"></div>
                    </div>
                    <p id="progress-text">Encrypting notes...</p>
                </div>
            </div>
        `;
    }
    
    generateChangePasswordHTML() {
        return `
            <div class="modal-content">
                <h3>Change Password</h3>
                <p>Enter your current password and choose a new one.</p>
                
                <form id="password-form" autocomplete="off">
                    <div class="form-group">
                        <label for="current-password">Current Password:</label>
                        <input type="password" id="current-password" autocomplete="current-password" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="new-password">New Password:</label>
                        <input type="password" id="new-password" autocomplete="new-password" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="confirm-password">Confirm New Password:</label>
                        <input type="password" id="confirm-password" autocomplete="new-password" required>
                    </div>
                    
                    <div class="form-actions">
                        <button type="submit" class="primary-btn">Change Password</button>
                        <button type="button" class="secondary-btn" id="cancel-btn">Cancel</button>
                        <button type="button" class="danger-btn" id="remove-password-btn">Remove Password</button>
                    </div>
                </form>
                
                <div id="progress-section" style="display: none;">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 0%"></div>
                    </div>
                    <p id="progress-text">Updating password...</p>
                </div>
            </div>
        `;
    }
    
    generateRemovePasswordHTML() {
        return `
            <div class="modal-content">
                <h3>Remove Password</h3>
                <p><strong>Warning:</strong> This will decrypt all your notes and remove password protection. Your notes will be stored in plaintext.</p>
                
                <form id="password-form">
                    <div class="form-group">
                        <label for="current-password">Current Password:</label>
                        <input type="password" id="current-password" required>
                    </div>
                    
                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="confirm-remove" required>
                            I understand that my notes will no longer be encrypted
                        </label>
                    </div>
                    
                    <div class="form-actions">
                        <button type="submit" class="danger-btn">Remove Password</button>
                        <button type="button" class="secondary-btn" id="cancel-btn">Cancel</button>
                        <button type="button" class="primary-btn" id="change-password-btn">Change Password Instead</button>
                    </div>
                </form>
                
                <div id="progress-section" style="display: none;">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 0%"></div>
                    </div>
                    <p id="progress-text">Decrypting notes...</p>
                </div>
            </div>
        `;
    }
    
    generateLoadingHTML() {
        return `
            <div class="modal-content">
                <h3>Loading...</h3>
                <p>Checking password settings...</p>
            </div>
        `;
    }
    
    generateErrorHTML(error) {
        return `
            <div class="modal-content">
                <h3>Error</h3>
                <p class="error-message">${error}</p>
                <div class="form-actions">
                    <button type="button" class="secondary-btn" id="close-btn">Close</button>
                </div>
            </div>
        `;
    }
    
    /**
     * Setup form event listeners after content is rendered
     */
    setupFormEventListeners() {
        const form = document.getElementById('password-form');
        const cancelBtn = document.getElementById('cancel-btn');
        const closeBtn = document.getElementById('close-btn');
        const removePasswordBtn = document.getElementById('remove-password-btn');
        const changePasswordBtn = document.getElementById('change-password-btn');
        const newPasswordInput = document.getElementById('new-password');
        const confirmPasswordInput = document.getElementById('confirm-password');
        
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleSubmit();
            });
        }
        
        // Real-time password matching validation
        if (newPasswordInput && confirmPasswordInput) {
            const checkPasswordMatch = () => {
                const newPw = newPasswordInput.value;
                const confirmPw = confirmPasswordInput.value;
                
                // Only check if confirm field has content
                if (confirmPw) {
                    let isMatch = false;
                    
                    if (confirmPw.length < newPw.length) {
                        // Check if newPw starts with confirmPw (still typing)
                        isMatch = newPw.startsWith(confirmPw);
                    } else if (confirmPw.length === newPw.length) {
                        // Same length - must be exact match
                        isMatch = (newPw === confirmPw);
                    } else {
                        // confirmPw is longer than newPw - always wrong
                        isMatch = false;
                    }
                    
                    if (!isMatch) {
                        confirmPasswordInput.style.borderColor = 'var(--error-color)';
                        confirmPasswordInput.style.backgroundColor = '#ffebee';
                    } else {
                        confirmPasswordInput.style.borderColor = '';
                        confirmPasswordInput.style.backgroundColor = '';
                    }
                } else {
                    // Reset styles if confirm field is empty
                    confirmPasswordInput.style.borderColor = '';
                    confirmPasswordInput.style.backgroundColor = '';
                }
            };
            
            confirmPasswordInput.addEventListener('input', checkPasswordMatch);
            newPasswordInput.addEventListener('input', checkPasswordMatch);
        }
        
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.close());
        }
        
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }
        
        if (removePasswordBtn) {
            removePasswordBtn.addEventListener('click', () => {
                this.updateModalState({ mode: 'remove' });
                this.renderModalContent();
            });
        }
        
        if (changePasswordBtn) {
            changePasswordBtn.addEventListener('click', () => {
                this.updateModalState({ mode: 'change' });
                this.renderModalContent();
            });
        }
    }
    
    /**
     * Handle form submission based on current mode
     */
    async handleSubmit() {
        const state = this.getModalState();
        
        if (state.isProcessing) {
            return; // Prevent double submission
        }
        
        try {
            this.updateModalState({ isProcessing: true, error: null });
            this.showProcessingState();
            
            // Show waiting cursor
            document.body.classList.add('loading');
            
            const formData = this.collectFormData();
            
            // Validate form data
            const validation = this.validateFormData(formData, state.mode);
            if (!validation.valid) {
                throw new Error(validation.error);
            }
            
            // Submit to appropriate endpoint
            await this.submitPasswordOperation(state.mode, formData);
            
            // Success - close modal
            this.close();
            
            // Refresh the app to reflect new encryption state
            window.location.reload();
            
        } catch (error) {
            console.error('Password operation failed:', error);
            
            // Remove waiting cursor on error
            document.body.classList.remove('loading');
            
            this.updateModalState({ 
                error: error.message || 'Password operation failed. Please try again.',
                isProcessing: false 
            });
            this.renderModalContent();
        }
    }
    
    /**
     * Collect form data from current form inputs
     */
    collectFormData() {
        return {
            currentPassword: document.getElementById('current-password')?.value || '',
            newPassword: document.getElementById('new-password')?.value || '',
            confirmPassword: document.getElementById('confirm-password')?.value || ''
        };
    }
    
    /**
     * Validate form data based on mode
     */
    validateFormData(formData, mode) {
        switch (mode) {
            case 'create':
                if (!formData.newPassword) {
                    return { valid: false, error: 'Please enter a new password' };
                }
                if (formData.newPassword !== formData.confirmPassword) {
                    return { valid: false, error: 'Passwords do not match' };
                }
                if (formData.newPassword.length < 4) {
                    return { valid: false, error: 'Password must be at least 4 characters' };
                }
                break;
                
            case 'change':
                if (!formData.currentPassword) {
                    return { valid: false, error: 'Please enter your current password' };
                }
                if (!formData.newPassword) {
                    return { valid: false, error: 'Please enter a new password' };
                }
                if (formData.newPassword !== formData.confirmPassword) {
                    return { valid: false, error: 'New passwords do not match' };
                }
                if (formData.newPassword.length < 4) {
                    return { valid: false, error: 'New password must be at least 4 characters' };
                }
                break;
                
            case 'remove':
                if (!formData.currentPassword) {
                    return { valid: false, error: 'Please enter your current password' };
                }
                const confirmCheckbox = document.getElementById('confirm-remove');
                if (!confirmCheckbox || !confirmCheckbox.checked) {
                    return { valid: false, error: 'Please confirm that you understand the risks' };
                }
                break;
        }
        
        return { valid: true };
    }
    
    /**
     * Submit password operation to server
     */
    async submitPasswordOperation(mode, formData) {
        let endpoint, body, method;
        
        switch (mode) {
            case 'create':
                endpoint = this.apiEndpoints.create;
                body = { password: formData.newPassword };
                method = 'POST';
                break;
                
            case 'change':
                endpoint = this.apiEndpoints.change;
                body = { 
                    current_password: formData.currentPassword,
                    new_password: formData.newPassword
                };
                method = 'PUT';
                break;
                
            case 'remove':
                endpoint = this.apiEndpoints.remove;
                body = { current_password: formData.currentPassword };
                method = 'DELETE';
                break;
                
            default:
                throw new Error(`Unknown password operation mode: ${mode}`);
        }
        
        const token = localStorage.getItem('auth_token');
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        const response = await fetch(endpoint, {
            method,
            headers,
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Server error: ${response.status}`);
        }
        
        return await response.json();
    }
    
    /**
     * Show processing state with progress indication
     */
    showProcessingState() {
        const form = document.getElementById('password-form');
        const progressSection = document.getElementById('progress-section');
        
        if (form) {
            form.style.display = 'none';
        }
        
        if (progressSection) {
            progressSection.style.display = 'block';
        }
        
        // TODO: Implement SSE progress updates for real progress tracking
        // For now, just show indeterminate progress
        this.simulateProgress();
    }
    
    /**
     * Simulate progress for bulk operations (temporary until SSE implemented)
     */
    simulateProgress() {
        const progressFill = document.querySelector('.progress-fill');
        if (!progressFill) return;
        
        let progress = 0;
        const interval = setInterval(() => {
            progress += Math.random() * 10;
            if (progress >= 90) {
                progress = 90; // Stop at 90% to show we're waiting for completion
                clearInterval(interval);
            }
            progressFill.style.width = `${progress}%`;
        }, 200);
    }
    
    /**
     * Don't close on click outside for password modal (security)
     */
    shouldCloseOnClickOutside() {
        return false;
    }
}
