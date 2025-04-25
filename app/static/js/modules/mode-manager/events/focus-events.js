/**
 * Focus Events Handler for ModeManager
 * 
 * Handles focus/blur events throughout the application:
 * - Search field focus/blur only
 * - No note content focus handling (handled by click events instead)
 * 
 * Initially just observes and logs focus events but doesn't
 * interfere with existing state machine behavior.
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

/**
 * Initialize focus event handlers
 * @returns {void}
 */
export function initFocusEvents() {
  // Register handlers in capture phase to ensure they run before state machine
  document.addEventListener('focusin', handleFocus, { capture: true });
  document.addEventListener('focusout', handleBlur, { capture: true });
  
  Logger.logInit('Focus events handler (search only)');
}

/**
 * Handle focus events
 * @param {FocusEvent} event - DOM focusin event
 */
function handleFocus(event) {
  if (!event) {
    throw new Error('handleFocus called without an event object');
  }
  
  if (!event.target) {
    throw new Error('Focus event missing target element');
  }
  
  const searchField = event.target.closest('#search-input');
  
  if (searchField) {
    // We no longer handle search via focus events
    // All search interactions are now handled by click events in mouse-events.js
    // and through keyboard shortcuts
    Logger.logDebug('Search field focused (no state change)');
  }
  // Note: We explicitly ignore note content focus events
  // All note interactions are handled by click events in mouse-events.js
}

/**
 * Handle blur events
 * @param {FocusEvent} event - DOM focusout event
 */
function handleBlur(event) {
  if (!event) {
    throw new Error('handleBlur called without an event object');
  }
  
  if (!event.target) {
    throw new Error('Blur event missing target element');
  }
  
  const searchField = event.target.closest('#search-input');
  
  if (searchField) {
    // We no longer handle search via blur events
    // All search interactions are now handled by click events in mouse-events.js
    Logger.logDebug('Search field blurred (no state change)');
  }
  // Note: We explicitly ignore note content blur events
  // All note interactions are handled by mouse events
}