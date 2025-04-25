import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

let activityTimer = null;
let autosaveTimer = null;
let lastActivityTime = Date.now();
let isActive = true;
let currentConfig = null;

export function initInactivityEvents(options = {}) {
    if (!options) {
        throw new Error('initInactivityEvents called with null/undefined options');
    }

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

    registerActivityDetection();

    startActivityTracking();
        
    Logger.logInit('Inactivity events handler');
    Logger.logDebug('Inactivity monitoring started', { 
        inactivityTimeout: currentConfig.inactivityTimeout,
        autosaveTimeout: currentConfig.autosaveTimeout
    });
}

function registerActivityDetection() {
    if (!currentConfig) {
        throw new Error('Activity detection registered before configuration was set');
    }

    const activityEvents = [
        'mousedown', 'mousemove', 'keydown', 
        'scroll', 'touchstart', 'click'
    ];
        
    activityEvents.forEach(eventType => {
        document.addEventListener(eventType, handleUserActivity, { 
            passive: true,  
            capture: false  
        });
    });
}

function handleUserActivity(event) {
    if (!event) {
        throw new Error('handleUserActivity called without an event object');
    }
        
    if (!currentConfig) {
        throw new Error('User activity detected but configuration is missing');
    }

    lastActivityTime = Date.now();

    if (!isActive) {
        isActive = true;
        if (typeof ModeContext.setActive !== 'function') {
            throw new Error('ModeContext missing setActive method');
        }
        ModeContext.setActive(true);
        Logger.logDebug('User activity resumed');
    }

    resetActivityTimer();
}

function startActivityTracking() {
    if (!currentConfig) {
        throw new Error('Cannot start activity tracking without configuration');
    }
        
    if (!currentConfig.inactivityTimeout) {
        throw new Error('Cannot start activity tracking without inactivityTimeout');
    }

    resetActivityTimer();

    activityTimer = setTimeout(() => {
        handleUserInactivity();
    }, currentConfig.inactivityTimeout);
}

function resetActivityTimer() {
        
    if (activityTimer) {
        clearTimeout(activityTimer);
        activityTimer = null;
    }

    if (autosaveTimer) {
        clearTimeout(autosaveTimer);
        autosaveTimer = null;
    }

    if (isActive && currentConfig) {
        if (!currentConfig.inactivityTimeout) {
            throw new Error('Cannot reset activity timer without inactivityTimeout');
        }
                
        activityTimer = setTimeout(() => {
            handleUserInactivity();
        }, currentConfig.inactivityTimeout);
    }
}

function handleUserInactivity() {
    if (!currentConfig) {
        throw new Error('User inactivity detected but configuration is missing');
    }

    isActive = false;
    if (typeof ModeContext.setActive !== 'function') {
        throw new Error('ModeContext missing setActive method');
    }
    ModeContext.setActive(false);
        
    Logger.logDebug('User inactive', { 
        inactiveSince: new Date(lastActivityTime).toISOString(),
        inactiveDuration: Date.now() - lastActivityTime
    });

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

function handleAutoSave() {
    if (ModeContext.isEditing === undefined) {
        throw new Error('ModeContext missing isEditing property');
    }
        
    if (ModeContext.currentNoteId === undefined) {
        throw new Error('ModeContext missing currentNoteId property');
    }

    if (ModeContext.isEditing && ModeContext.currentNoteId) {
                
        if (typeof ModeContext.setCallingApi !== 'function') {
            throw new Error('ModeContext missing setCallingApi method');
        }
                
        ModeContext.setCallingApi(true);
                
        Logger.logDebug('Auto-saving note due to inactivity', {
            noteId: ModeContext.currentNoteId
        });

        setTimeout(() => {
            ModeContext.setCallingApi(false);
            Logger.logDebug('Auto-save completed');
        }, 500);
    }
}

export function pauseActivityTracking() {
        
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

export function resumeActivityTracking() {
    if (!currentConfig) {
        throw new Error('Cannot resume activity tracking without configuration');
    }

    lastActivityTime = Date.now();

    resetActivityTimer();
        
    Logger.logDebug('Activity tracking resumed');
}