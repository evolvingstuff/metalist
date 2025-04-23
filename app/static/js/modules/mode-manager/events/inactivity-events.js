/**
 * Inactivity Events Handler for ModeManager
 * 
 * Handles user inactivity detection and related actions:
 * - Tracking user activity timeouts
 * - Auto-saving content after inactivity
 * - Session management
 * 
 * Initially just observes and logs inactivity but doesn't
 * interfere with existing state machine behavior.
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

// Activity tracking variables
let activityTimer = null;
let autosaveTimer = null;
let lastActivityTime = Date.now();
let isActive = true;
let currentConfig = null;

/**
 * Initialize inactivity event handlers
 * @param {Object} options - Configuration options
 * @param {number} options.inactivityTimeout - Timeout in ms to consider user inactive
 * @param {number} options.autosaveTimeout - Timeout in ms to auto-save
 * @returns {void}
 */
export function initInactivityEvents(options = {}) {
  // Store configuration for use throughout the module
  currentConfig = { ...options };
  
  if (!currentConfig.inactivityTimeout) {
    Logger.logError('Missing inactivityTimeout in configuration');
    return;
  }
  
  // Register activity detection
  registerActivityDetection();
  
  // Start initial timer
  startActivityTracking();
  
  Logger.logInit('Inactivity events handler');
  Logger.logDebug('Inactivity monitoring started', { 
    inactivityTimeout: currentConfig.inactivityTimeout,
    autosaveTimeout: currentConfig.autosaveTimeout
  });
}

/**
 * Register all event listeners that indicate user activity
 */
function registerActivityDetection() {
  // These events all reset the inactivity timer
  const activityEvents = [
    'mousedown', 'mousemove', 'keydown', 
    'scroll', 'touchstart', 'click'
  ];
  
  activityEvents.forEach(eventType => {
    document.addEventListener(eventType, handleUserActivity, { 
      passive: true,  // Performance optimization
      capture: false  // No need to capture, bubbling is fine for activity detection
    });
  });
}

/**
 * Handle any user activity
 * @param {Event} event - DOM event indicating activity
 */
function handleUserActivity(event) {
  // Update last activity time
  lastActivityTime = Date.now();
  
  // If user was previously inactive, mark them as active again
  if (!isActive) {
    isActive = true;
    ModeContext.setActive(true);
    Logger.logDebug('User activity resumed');
  }
  
  // Reset inactivity timer
  resetActivityTimer();
}

/**
 * Start tracking user activity
 */
function startActivityTracking() {
  // Clear any existing timers
  resetActivityTimer();
  
  // Start inactivity detection timer
  activityTimer = setTimeout(() => {
    handleUserInactivity();
  }, currentConfig.inactivityTimeout);
}

/**
 * Reset the activity timer
 */
function resetActivityTimer() {
  // Clear existing timer
  if (activityTimer) {
    clearTimeout(activityTimer);
    activityTimer = null;
  }
  
  // Clear autosave timer if exists
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
    autosaveTimer = null;
  }
  
  // Start a new timer (if tracking is active)
  if (isActive && currentConfig) {
    activityTimer = setTimeout(() => {
      handleUserInactivity();
    }, currentConfig.inactivityTimeout);
  }
}

/**
 * Handle user inactivity
 */
function handleUserInactivity() {
  // Mark user as inactive
  isActive = false;
  ModeContext.setActive(false);
  
  Logger.logDebug('User inactive', { 
    inactiveSince: new Date(lastActivityTime).toISOString(),
    inactiveDuration: Date.now() - lastActivityTime
  });
  
  // Start autosave timer if editing
  if (ModeContext.isEditing && currentConfig.autosaveTimeout) {
    Logger.logDebug('Starting auto-save timer');
    
    autosaveTimer = setTimeout(() => {
      handleAutoSave();
    }, currentConfig.autosaveTimeout);
  }
}

/**
 * Handle auto-save when user is inactive
 */
function handleAutoSave() {
  // Only auto-save if we're editing and have a note ID
  if (ModeContext.isEditing && ModeContext.currentNoteId) {
    // Mark that we're calling the API
    ModeContext.setCallingApi(true);
    
    Logger.logDebug('Auto-saving note due to inactivity', {
      noteId: ModeContext.currentNoteId
    });
    
    // In the future, we would call the actual save API here
    // For now, we just simulate it with a timeout
    setTimeout(() => {
      ModeContext.setCallingApi(false);
      Logger.logDebug('Auto-save completed');
    }, 500);
  }
}

/**
 * Pause activity tracking (e.g., when app is in background)
 */
export function pauseActivityTracking() {
  // Clear existing timers
  if (activityTimer) {
    clearTimeout(activityTimer);
    activityTimer = null;
  }
  
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
    autosaveTimer = null;
  }
  
  Logger.logDebug('Activity tracking paused');
}

/**
 * Resume activity tracking (e.g., when app returns to foreground)
 */
export function resumeActivityTracking() {
  // Reset last activity time
  lastActivityTime = Date.now();
  
  // Start new timer
  resetActivityTimer();
  
  Logger.logDebug('Activity tracking resumed');
}