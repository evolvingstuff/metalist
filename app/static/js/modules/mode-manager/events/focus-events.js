import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

export function initFocusEvents() {
        
    document.addEventListener('focusin', handleFocus, { capture: true });
    document.addEventListener('focusout', handleBlur, { capture: true });
        
    Logger.logInit('Focus events handler (search only)');
}

function handleFocus(event) {
    if (!event) {
        throw new Error('handleFocus called without an event object');
    }
        
    if (!event.target) {
        throw new Error('Focus event missing target element');
    }
    
    // Skip during loading state
    if (ModeContext.isLoading) {
        Logger.logNoop('Focus event ignored while system is loading', {
            targetElement: event.target.tagName,
            isLoading: true
        });
        return;
    }
        
    const searchField = event.target.closest('#search-input');
        
    if (searchField) {

        Logger.logDebug('Search field focused (no state change)');
    }
}

function handleBlur(event) {
    if (!event) {
        throw new Error('handleBlur called without an event object');
    }
        
    if (!event.target) {
        throw new Error('Blur event missing target element');
    }
    
    // Skip during loading state
    if (ModeContext.isLoading) {
        Logger.logNoop('Blur event ignored while system is loading', {
            targetElement: event.target.tagName,
            isLoading: true
        });
        return;
    }
        
    const searchField = event.target.closest('#search-input');
        
    if (searchField) {

        Logger.logDebug('Search field blurred (no state change)');
    }
}