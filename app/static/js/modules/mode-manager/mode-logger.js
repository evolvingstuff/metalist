/**
 * ModeLogger
 * 
 * Centralized logging utility for the Note Manager.
 * Categories allow filtering for specific types of events:
 * - ACTION: High-level user actions (selectNote, deselectNote)
 * - STATE: Individual state changes (editing, currentNoteId)
 * - EVENT: Raw DOM events (click, keypress)
 * - INIT: Component initialization
 * - ERROR: Errors and exceptions
 */

/**
 * Log categories for filtering
 * @enum {string}
 */
export const LogCategory = {
  ACTION: 'ACTION',
  STATE: 'STATE',
  EVENT: 'EVENT',
  INIT: 'INIT',
  ERROR: 'ERROR',
  NOOP: 'NOOP',  // No Operation - when an event was processed but intentionally ignored
  DEBUG: 'DEBUG'  // Detailed debugging information
};

/**
 * Log a message with note manager data
 * @param {string} message - The message to log
 * @param {Object} data - Additional data to include in the log
 * @param {LogCategory} category - The category of log (ACTION, STATE, EVENT, etc.)
 * @param {Object} modes - Current mode states
 */
export function logDebug(message, data = {}, category = LogCategory.EVENT, modes = null) {
  console.log(`[${category}]: ${message}`, {
    ...(modes && { modes }),
    ...data
  });
}

/**
 * Log an action (high-level user interaction)
 * @param {string} actionName - Name of the action (selectNote, deselectNote)
 * @param {Object} data - Additional data about the action
 */
export function logAction(actionName, data = {}) {
  console.log(`[${LogCategory.ACTION}]: ${actionName}`, data);
}

/**
 * Log a state change
 * @param {string} property - The property that changed
 * @param {any} newValue - The new value
 * @param {any} oldValue - The previous value
 */
export function logState(property, newValue, oldValue = undefined) {
  console.log(`[${LogCategory.STATE}]: ${property} changed`, {
    from: oldValue,
    to: newValue
  });
}

/**
 * Log the complete state object
 * @param {Object} stateObj - Full state object containing modes, context, and event memory
 */
export function logFullState(stateObj) {
  console.log(`[${LogCategory.STATE}]: Current State:`, stateObj);
}

/**
 * Log initialization of a component
 * @param {string} componentName - Name of the component being initialized
 */
export function logInit(componentName) {
  console.log(`[${LogCategory.INIT}]: ${componentName} initialized`);
}

/**
 * Log an error with category prefix
 * @param {string} message - Error message to log
 * @param {Error|Object} error - Error object or data
 */
export function logError(message, error = {}) {
  console.error(`[${LogCategory.ERROR}]: ${message}`, error);
}

/**
 * Log a no-operation event (when an event was intentionally ignored)
 * @param {string} message - Description of what was skipped and why
 * @param {Object} data - Additional data about the skipped operation
 */
export function logNoop(message, data = {}) {
  console.log(`[${LogCategory.NOOP}]: ${message}`, data);
}