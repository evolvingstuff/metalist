import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

const WATCHDOG_TIMEOUT_MS = 15000;

let busy = false;
let busyName = null;
let busyStartedAt = null;
let watchdogId = null;

function clearWatchdog() {
    if (watchdogId === null) {
        return;
    }
    clearTimeout(watchdogId);
    watchdogId = null;
}

function armWatchdog() {
    clearWatchdog();
    watchdogId = setTimeout(() => {
        if (!busy) {
            return;
        }
        const elapsedMs = busyStartedAt === null ? null : performance.now() - busyStartedAt;
        throw new Error(
            `CommandGate watchdog: command stuck busy name=${busyName} elapsedMs=${elapsedMs}`
        );
    }, WATCHDOG_TIMEOUT_MS);
}

export const CommandGate = {
    isBusy() {
        return busy;
    },

    run(name, asyncFn) {
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('CommandGate.run requires non-empty name');
        }
        if (typeof asyncFn !== 'function') {
            throw new Error('CommandGate.run requires async function');
        }

        if (busy) {
            Logger.logNoop('Command dropped while busy', {
                requested: name,
                busyName,
            });
            return Promise.resolve(null);
        }
        if (ModeContext.isLoading) {
            throw new Error(`CommandGate.run called while ModeContext.isLoading (name=${name})`);
        }

        ModeContext.setLoading(true);
        busy = true;
        busyName = name;
        busyStartedAt = performance.now();
        armWatchdog();

        Logger.logAction('command_gate.start', { name });

        return Promise.resolve()
            .then(() => asyncFn())
            .finally(() => {
                Logger.logAction('command_gate.finish', { name });
                busy = false;
                busyName = null;
                busyStartedAt = null;
                clearWatchdog();
                if (ModeContext.isLoading) {
                    ModeContext.setLoading(false);
                }
            });
    },
};

