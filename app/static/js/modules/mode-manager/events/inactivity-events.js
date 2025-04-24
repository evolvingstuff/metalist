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
  if (!options) {
    throw new Error('initInactivityEvents called with null/undefined options');
  }

  // Store configuration for use throughout the module
  currentConfig = { ...options };
  
  if (!currentConfig.inactivityTimeout) {
    throw new Error('Missing required inactivityTimeout in configuration');
  }
  
  if (typeof currentConfig.inactivityTimeout !== 'number' || currentConfig.inactivityTimeout <= 0) {
    throw new Error(`Invalid inactivityTimeout: ${currentConfig.inactivityTimeout}`);
  }
  
  if (currentConfig.autosaveTimeout && (typeof currentConfig.autosaveTimeout !== 'number' || currentConfig.autosaveTimeout <= 0)) {
    throw new Error(`Invalid autosaveTimeout: ${currentConfig.autosaveTimeout}`);
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
  if (!currentConfig) {
    throw new Error('Activity detection registered before configuration was set');
  }

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
  if (!event) {
    throw new Error('handleUserActivity called without an event object');
  }
  
  if (!currentConfig) {
    throw new Error('User activity detected but configuration is missing');
  }
  
  // Update last activity time
  lastActivityTime = Date.now();
  
  // If user was previously inactive, mark them as active again
  if (!isActive) {
    isActive = true;
    if (typeof ModeContext.setActive !== 'function') {
      throw new Error('ModeContext missing setActive method');
    }
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
  if (!currentConfig) {
    throw new Error('Cannot start activity tracking without configuration');
  }
  
  if (!currentConfig.inactivityTimeout) {
    throw new Error('Cannot start activity tracking without inactivityTimeout');
  }
  
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
    if (!currentConfig.inactivityTimeout) {
      throw new Error('Cannot reset activity timer without inactivityTimeout');
    }
    
    activityTimer = setTimeout(() => {
      handleUserInactivity();
    }, currentConfig.inactivityTimeout);
  }
}

/**
 * Handle user inactivity
 */
function handleUserInactivity() {
  if (!currentConfig) {
    throw new Error('User inactivity detected but configuration is missing');
  }
  
  // Mark user as inactive
  isActive = false;
  if (typeof ModeContext.setActive !== 'function') {
    throw new Error('ModeContext missing setActive method');
  }
  ModeContext.setActive(false);
  
  Logger.logDebug('User inactive', { 
    inactiveSince: new Date(lastActivityTime).toISOString(),
    inactiveDuration: Date.now() - lastActivityTime
  });
  
  // Start autosave timer if editing
  if (ModeContext.isEditing === undefined) {
    throw new Error('ModeContext missing isEditing property');
  }
  
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
  if (ModeContext.isEditing === undefined) {
    throw new Error('ModeContext missing isEditing property');
  }
  
  if (ModeContext.currentNoteId === undefined) {
    throw new Error('ModeContext missing currentNoteId property');
  }
  
  // Only auto-save if we're editing and have a note ID
  if (ModeContext.isEditing && ModeContext.currentNoteId) {
    // Mark that we're calling the API
    if (typeof ModeContext.setCallingApi !== 'function') {
      throw new Error('ModeContext missing setCallingApi method');
    }
    
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
  if (!currentConfig) {
    throw new Error('Cannot resume activity tracking without configuration');
  }
  
  // Reset last activity time
  lastActivityTime = Date.now();
  
  // Start new timer
  resetActivityTimer();
  
  Logger.logDebug('Activity tracking resumed');
}