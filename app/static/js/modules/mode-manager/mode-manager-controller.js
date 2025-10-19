console.log('+++ ModeManager: Module loaded');

import { ModeContextInstance as ModeContext } from './mode-context.js';
import * as Logger from './mode-logger.js';

import { initKeyboardEvents } from './events/keyboard-events.js';
import { initMouseEvents } from './events/mouse-events.js';
import { initInputEvents } from './events/input-events.js';
import { initFocusEvents } from './events/focus-events.js';
import { initContentAutoSave } from './events/inactivity-events.js';
import { initializeSearchEvents } from './events/search-events.js';
import { startPolling } from './services/polling-service.js';
import { startInfiniteScrollMonitor, resetInfiniteScrollState } from './services/infinite-scroll-service.js';

const DEFAULT_CONFIG = {};

const ModeManager = {
        
    async init(config = {}) {
                
        console.log('+++ ModeManager: init() called');
                
        try {
            Logger.logInit('Controller');

            const mergedConfig = {
                ...DEFAULT_CONFIG,
                ...config
            };

            await this._registerEventListeners(mergedConfig);

            ModeContext.addListener(this._handleModeChange.bind(this));

            document.addEventListener('visibilitychange', this._handleVisibilityChange.bind(this));
                        
            console.log('+++ ModeManager: init completed successfully');
            return this;
        } catch (error) {
            console.error('+++ ModeManager: Error during initialization', error);
            throw error;
        }
    },

    async _registerEventListeners(config) {
        try {
                        
            initKeyboardEvents();
            initMouseEvents();
            initInputEvents();
            initFocusEvents();
            initContentAutoSave();
            await initializeSearchEvents();
            startPolling();
            startInfiniteScrollMonitor();
                        
            Logger.logDebug('Event handlers registered', { config });
        } catch (error) {
            console.error('+++ ModeManager: Error registering event listeners', error);
            throw error;
        }
    },

    _handleVisibilityChange(event) {
        Logger.logDebug('Page visibility: ' + (document.hidden ? 'hidden' : 'visible'));
    },

    _handleModeChange(property, newValue) {
        Logger.logDebug(`Mode change: ${property}`, { [property]: newValue });
        if (property === 'searchQuery') {
            resetInfiniteScrollState();
        }
    },

    debugState() {
        const state = ModeContext.getFullState();
        Logger.logState(state);
        return this;
    },

    get isEditing() { return ModeContext.isEditing; },
    get isSearching() { return ModeContext.isSearching; },
    get isIdle() { return ModeContext.isIdle; },
    get isActive() { return ModeContext.isActive; }
};

console.log('+++ ModeManager: Exporting ModeManager object');

export { ModeManager };
