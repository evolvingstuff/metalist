/**
 * Activity Monitor
 * 
 * Tracks user activity and emits timeout events to the state machine.
 * Manages inactivity timers and cleanup.
 */
export class ActivityMonitor {
    constructor(stateMachine) {
        this.stateMachine = stateMachine;
        this.timer = null;
        this.TIMEOUT = 100000000;  //TODO
    }

    startMonitoring() {
        console.log('⏰ [ACTIVITY] Start monitoring');
        this.resetTimer();
    }

    stopMonitoring() {
        console.log('⏰ [ACTIVITY] Stop monitoring');
        this.clearTimer();
    }

    resetTimer() {
        this.clearTimer();
        this.timer = setTimeout(() => {
            console.log('⏰ [ACTIVITY] Timeout triggered');
            this.stateMachine.handleMappedEvent({
                type: 'INACTIVITY_TIMEOUT',
                data: this.stateMachine.data
            });
        }, this.TIMEOUT);
    }

    clearTimer() {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }

    handleActivity() {
        if (this.timer) {
            console.log('⏰ [ACTIVITY] Activity detected, resetting timer');
            this.resetTimer();
        }
    }
}
