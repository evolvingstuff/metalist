import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

const POLL_INTERVAL_MS = 500;
const ROOT_BUFFER_THRESHOLD = 25;

let pollTimer = null;
let pendingFetch = false;
let noMoreRoots = false;
let lastKnownCount = 0;
let lastFetchTime = 0;

export function startInfiniteScrollMonitor() {
    if (pollTimer) {
        return;
    }
    pollTimer = setInterval(handlePoll, POLL_INTERVAL_MS);
    Logger.logInit('Infinite scroll poller started');
}

export function stopInfiniteScrollMonitor() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
        Logger.logDebug('Infinite scroll poller stopped');
    }
}

export function resetInfiniteScrollState() {
    noMoreRoots = false;
    lastKnownCount = ModeContext.knownRootCount;
    lastFetchTime = 0;
    pendingFetch = false;
    refreshOverlayMetrics();
}

function collectRootVisibility() {
    const rootElements = document.querySelectorAll('.note');
    const viewportHeight = window.innerHeight;
    const visible = [];
    const past = [];

    for (const element of rootElements) {
        const noteId = element.dataset.noteId;
        if (!noteId) {
            continue;
        }
        const parentId = element.dataset.parentId;
        const isRoot = !parentId || parentId === 'null' || parentId === 'undefined';
        if (!isRoot && element.hasAttribute('data-parent-id')) {
            continue;
        }

        const rect = element.getBoundingClientRect();
        if (rect.bottom < 0) {
            past.push(noteId);
        } else if (rect.top <= viewportHeight) {
            visible.push(noteId);
        }
    }

    return { visible, past };
}

async function handlePoll() {
    if (document.hidden) {
        return;
    }

    try {
        const { visible, past } = collectRootVisibility();
        const changed = ModeContext.markRootsAsSeen([...visible, ...past]);
        if (changed) {
            refreshOverlayMetrics();
        }

        const knownCount = ModeContext.knownRootCount;
        if (knownCount === 0) {
            return;
        }

        if (knownCount > lastKnownCount) {
            lastKnownCount = knownCount;
            noMoreRoots = false;
        }

        const unseenCount = ModeContext.getUnseenRootCount();
        if (unseenCount <= ROOT_BUFFER_THRESHOLD) {
            await maybeFetchMore(knownCount);
        }
    } catch (error) {
        Logger.logError('Infinite scroll poller error', error);
    }
}

async function maybeFetchMore(previousKnownCount) {
    if (pendingFetch) {
        return;
    }

    const now = Date.now();
    if (now - lastFetchTime < POLL_INTERVAL_MS) {
        return;
    }

    if (noMoreRoots) {
        return;
    }

    pendingFetch = true;
    lastFetchTime = now;

    try {
        const { actionRefreshAndMaybeSelect } = await import('../actions/ui-actions.js');
        await actionRefreshAndMaybeSelect();  //asdf asdf
        const currentKnown = ModeContext.knownRootCount;
        if (currentKnown <= previousKnownCount) {
            noMoreRoots = true;
        } else {
            lastKnownCount = currentKnown;
            refreshOverlayMetrics();
        }
    } catch (error) {
        Logger.logError('Infinite scroll fetch failed', error);
    } finally {
        pendingFetch = false;
    }
}

//TODO: asdf asdf do we need this?
export function refreshOverlayMetrics() {
    const overlay = document.getElementById('perf-overlay');
    if (!overlay) {
        return;
    }

    const rows = overlay.querySelectorAll('tbody tr');
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length !== 2) {
            continue;
        }
        const label = cells[0].textContent.trim().toLowerCase();
        if (label === 'root notes known') {
            cells[1].textContent = `${ModeContext.knownRootCount}`;
        }
        if (label === 'root notes seen') {
            cells[1].textContent = `${ModeContext.seenRootCount}`;
        }
    }
}
