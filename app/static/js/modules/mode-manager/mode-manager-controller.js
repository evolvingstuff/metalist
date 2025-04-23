/**
 * ModeManager Controller
 * 
 * Coordinates the mode-based state management system.
 * This is a progressive replacement for the state machine architecture,
 * designed to be simpler, more maintainable, and more flexible.
 * 
 * Key differences from state machine approach:
 * - Uses boolean flags instead of exclusive states
 * - Multiple modes can be active simultaneously
 * - Simplified event handling with straightforward logic
 * - No complex transition system
 */

// Add immediate console log to see if module is loading
console.log('+++ ModeManager: Module loaded');

import { ModeContextInstance as ModeContext } from './mode-context.js';
import * as Logger from './mode-logger.js';
// Import event handlers
import { initKeyboardEvents } from './events/keyboard-events.js';
import { initMouseEvents } from './events/mouse-events.js';
import { initInactivityEvents, pauseActivityTracking, resumeActivityTracking } from './events/inactivity-events.js';

// Configuration options
const DEFAULT_CONFIG = {
  inactivity: {
    enabled: true,
    inactivityTimeout: 30000, // 30 seconds
    autosaveTimeout: 5000     // 5 seconds after inactivity
  }
};

// Create the ModeManager object
const ModeManager = {
  /**
   * Initialize the mode manager system
   * This should be called BEFORE state machine initialization
   * @param {Object} config - Optional configuration options
   */
  init(config = {}) {
    // Direct console.log for debugging
    console.log('+++ ModeManager: init() called');
    
    try {
      Logger.logInit('Controller');
      
      // Merge default config with provided config
      const mergedConfig = {
        ...DEFAULT_CONFIG,
        ...config,
        inactivity: {
          ...DEFAULT_CONFIG.inactivity,
          ...(config.inactivity || {})
        }
      };
      
      // Set up event listeners through dedicated handlers
      this._registerEventListeners(mergedConfig);
      
      // Watch for mode changes
      ModeContext.addListener(this._handleModeChange.bind(this));
      
      // Handle page visibility changes
      document.addEventListener('visibilitychange', this._handleVisibilityChange.bind(this));
      
      console.log('+++ ModeManager: init completed successfully');
      return this;
    } catch (error) {
      console.error('+++ ModeManager: Error during initialization', error);
      throw error;
    }
  },
  
  /**
   * Register all event listeners
   * These run in capture phase to ensure they execute before state machine
   * @private
   * @param {Object} config - Configuration options
   */
  _registerEventListeners(config) {
    try {
      // Initialize event handlers from dedicated modules
      initKeyboardEvents();
      initMouseEvents();
      
      // Initialize inactivity tracking if enabled
      if (config.inactivity.enabled) {
        initInactivityEvents({
          inactivityTimeout: config.inactivity.inactivityTimeout,
          autosaveTimeout: config.inactivity.autosaveTimeout
        });
      }
      
      Logger.logDebug('Event handlers registered', { config });
    } catch (error) {
      console.error('+++ ModeManager: Error registering event listeners', error);
      throw error;
    }
  },
  
  /**
   * Handle visibility change (browser tab focus/blur)
   * @param {Event} event - Visibility change event
   * @private
   */
  _handleVisibilityChange(event) {
    if (document.hidden) {
      // Page is hidden (tab inactive, etc)
      pauseActivityTracking();
      Logger.logDebug('Page visibility: hidden');
    } else {
      // Page is visible
      resumeActivityTracking();
      Logger.logDebug('Page visibility: visible');
    }
  },
  
  /**
   * Handle mode changes (when a listener triggers a state change)
   * @param {string} property - Name of the property that changed
   * @param {any} newValue - New value of the property
   * @private
   */
  _handleModeChange(property, newValue) {
    Logger.logDebug(`Mode change: ${property}`, { [property]: newValue });
  },
  
  /**
   * Log current state to console (for debugging)
   */
  debugState() {
    const state = ModeContext.getFullState();
    Logger.logState(state);
    return this;
  },
  
  // Public getters that expose mode state
  get isEditing() { return ModeContext.isEditing; },
  get isSearching() { return ModeContext.isSearching; },
  get isCallingApi() { return ModeContext.isCallingApi; },
  get isIdle() { return ModeContext.isIdle; },
  get isActive() { return ModeContext.isActive; }
};

console.log('+++ ModeManager: Exporting ModeManager object');

// Export the ModeManager object
export { ModeManager };