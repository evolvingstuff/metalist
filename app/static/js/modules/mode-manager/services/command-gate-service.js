import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { CONFIG } from '../../config.js';

const WATCHDOG_TIMEOUT_MS = 15000;

let busy = false;
let busyName = null;
let busyStartedAt = null;
let watchdogId = null;
let activeCommandServerCallCount = 0;

function clearWatchdog() {
    if (watchdogId === null) {
        return;
    }
    clearTimeout(watchdogId);
    watchdogId = null;
}

function armWatchdog(timeoutMs) {
    clearWatchdog();
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
        return;
    }
    watchdogId = setTimeout(() => {
        if (!busy) {
            return;
        }
        const elapsedMs = busyStartedAt === null ? null : performance.now() - busyStartedAt;
        throw new Error(
            `CommandGate watchdog: command stuck busy name=${busyName} elapsedMs=${elapsedMs}`
        );
    }, timeoutMs);
}

export const CommandGate = {
    isBusy() {
        return busy;
    },

    markCommandServerCall() {
        if (!busy) {
            return;
        }
        activeCommandServerCallCount += 1;
    },

    run(name, asyncFn, options) {
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('CommandGate.run requires non-empty name');
        }
        if (typeof asyncFn !== 'function') {
            throw new Error('CommandGate.run requires async function');
        }

        let resolvedOptions = null;
        if (options !== undefined) {
            resolvedOptions = options;
        }

        if (
            resolvedOptions !== null
            && (typeof resolvedOptions !== 'object' || Array.isArray(resolvedOptions))
        ) {
            throw new Error('CommandGate.run options must be an object or null');
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
        if (resolvedOptions !== null && resolvedOptions.showLoadingImmediately === true) {
            document.body.classList.add(CONFIG.CLASSES.LOADING);
        }
        busy = true;
        busyName = name;
        busyStartedAt = performance.now();
        activeCommandServerCallCount = 0;
        let watchdogTimeoutMs = WATCHDOG_TIMEOUT_MS;
        if (resolvedOptions !== null && resolvedOptions.disableWatchdog === true) {
            watchdogTimeoutMs = 0;
        } else if (resolvedOptions !== null && Number.isFinite(resolvedOptions.timeoutMs)) {
            watchdogTimeoutMs = resolvedOptions.timeoutMs;
        }
        armWatchdog(watchdogTimeoutMs);

        Logger.logAction('command_gate.start', { name });

        return Promise.resolve()
            .then(() => asyncFn())
            .finally(() => {
                Logger.logAction('command_gate.finish', { name });
                busy = false;
                busyName = null;
                busyStartedAt = null;
                activeCommandServerCallCount = 0;
                clearWatchdog();
                if (ModeContext.isLoading) {
                    ModeContext.setLoading(false);
                }
            });
    },
};
