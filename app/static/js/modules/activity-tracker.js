/**
 * Activity Tracker - Tracks user activity for token refresh
 */

import { ModeContextInstance as ModeContext } from './mode-manager/mode-context.js';

function markUserActivity() {
    // Only set to true if it's currently false to avoid redundant state changes
    if (!ModeContext.userActivity) {
        ModeContext.setUserActivity(true);
    }
}

export const ActivityTracker = {
    
    /**
     * Start tracking user activity to refresh auth tokens
     */
    start() {
        // Track keyboard activity
        document.addEventListener('keydown', markUserActivity, { passive: true });
        document.addEventListener('keyup', markUserActivity, { passive: true });
        
        // Track mouse activity
        document.addEventListener('mousemove', markUserActivity, { passive: true });
        document.addEventListener('mousedown', markUserActivity, { passive: true });
        document.addEventListener('mouseup', markUserActivity, { passive: true });
        document.addEventListener('click', markUserActivity, { passive: true });
        
        // Track scroll and other interactions
        document.addEventListener('scroll', markUserActivity, { passive: true });
        document.addEventListener('wheel', markUserActivity, { passive: true });
        
        console.log('[ActivityTracker] Started tracking user activity for token refresh');
    }
};

// Make available globally
window.ActivityTracker = ActivityTracker;