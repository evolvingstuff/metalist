/**
 * ModeLogger
 * 
 * Centralized logging utility for the ModeManager.
 * All logs are prefixed with '+++ ' for easy filtering in the console.
 */

/**
 * Log a message with mode manager data
 * @param {string} message - The message to log
 * @param {Object} data - Additional data to include in the log
 * @param {Object} modes - Current mode states
 */
export function logDebug(message, data = {}, modes = null) {
  console.log(`+++ ModeManager: ${message}`, {
    ...(modes && { modes }),
    ...data
  });
}

/**
 * Log the current state of the mode manager
 * @param {Object} state - Full state object containing modes, context, and event memory
 */
export function logState(state) {
  console.log('+++ ModeManager: Current State:', state);
}

/**
 * Log initialization of a component
 * @param {string} componentName - Name of the component being initialized
 */
export function logInit(componentName) {
  console.log(`+++ ModeManager: ${componentName} initialized`);
}

/**
 * Log an error with mode manager prefix
 * @param {string} message - Error message
 * @param {Error} error - Error object if available
 */
export function logError(message, error = null) {
  console.error(`+++ ModeManager ERROR: ${message}`, error || '');
}