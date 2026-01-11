import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

const POLL_INTERVAL_MS = 800;
const ROOT_BUFFER_THRESHOLD = 25;

let pollTimer = null;

const tabPollState = {};

const ROOT_PARENT_SENTINELS = new Set(['', 'null', 'undefined', 'none']);

function getActiveTabState() {
    let tabId = ModeContext.activeTabId;
    if (!tabId) {
        tabId = '0';
    }
    const searchKey = (ModeContext.searchQuery || '').toString();
    const key = `${tabId}::${searchKey}`;
    if (!tabPollState[key]) {
        tabPollState[key] = {
            pendingFetch: false,
            lastKnownCount: 0,
            lastFetchTime: 0,
        };
    }
    return tabPollState[key];
}

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
    const state = getActiveTabState();
    state.lastKnownCount = ModeContext.knownRootCount;
    state.lastFetchTime = 0;
    state.pendingFetch = false;
    refreshOverlayMetrics();
}

export function handleTabSwitch() {
    const state = getActiveTabState();
    state.pendingFetch = false;
    state.lastKnownCount = ModeContext.knownRootCount;
    refreshOverlayMetrics();
}

function collectRootVisibility() {
    const rootElements = document.querySelectorAll('.note');
    const viewportHeight = window.innerHeight;
    const visible = [];
    const past = [];

    for (const element of rootElements) {
        const noteId = element.dataset.noteId;
        if (!noteId) continue;

        const rawParent = element.getAttribute('data-parent-id');
        const normalized = (typeof rawParent === 'string' ? rawParent : '').trim().toLowerCase();
        const isRoot = ROOT_PARENT_SENTINELS.has(normalized);
        if (!isRoot) continue;

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
    if (document.hidden) return;
    if (ModeContext.isLoading) return;

    const state = getActiveTabState();
    const { visible, past } = collectRootVisibility();
    if (visible.length > 0) {
        const anchorId = visible[visible.length - 1];
        ModeContext.setRootAnchorId(anchorId);
    }

    const changed = ModeContext.markRootsAsSeen([...visible, ...past]);
    if (changed) refreshOverlayMetrics();

    const knownCount = ModeContext.knownRootCount;
    if (knownCount === 0) return;
    if (state.lastKnownCount === 0 || state.lastKnownCount > knownCount) {
        state.lastKnownCount = knownCount;
    } else if (knownCount > state.lastKnownCount) {
        state.lastKnownCount = knownCount;
    }

    const anchorId = visible.length > 0 ? visible[visible.length - 1] : null;
    const nearEnd = anchorId ? ModeContext.isAnchorNearEnd(anchorId, ROOT_BUFFER_THRESHOLD) : false;
    const unseenCount = ModeContext.getUnseenRootCount();
    // Be conservative: only fetch when user is at the end AND we have low buffer
    if (nearEnd && unseenCount <= ROOT_BUFFER_THRESHOLD) {
        await maybeFetchMore(state, knownCount, nearEnd);
    }
}

async function maybeFetchMore(state, previousKnownCount, nearEndFlag) {
    if (state.pendingFetch) return;

    const now = Date.now();
    if (now - state.lastFetchTime < POLL_INTERVAL_MS) return;

    state.pendingFetch = true;
    state.lastFetchTime = now;

    const startedAt = performance.now();
    const tabOrder = ModeContext.tabOrder;
    if (!Array.isArray(tabOrder) || tabOrder.length === 0) {
        throw new Error('ModeContext.tabOrder must be a non-empty array');
    }
    const activeIndex = tabOrder.indexOf(ModeContext.activeTabId);
    if (activeIndex === -1) {
        throw new Error(`activeTabId not present in ModeContext.tabOrder: ${ModeContext.activeTabId}`);
    }
    const context = `infiniteScroll tab#${activeIndex + 1}`;

    const { actionRefreshAndMaybeSelect } = await import('../actions/ui-actions.js');
    await actionRefreshAndMaybeSelect({ startedAt, context });
    const currentKnown = ModeContext.knownRootCount;
    if (currentKnown > previousKnownCount) {
        state.lastKnownCount = currentKnown;
        refreshOverlayMetrics();
    } else if (nearEndFlag) {
        // Fail fast: at visual end, but server did not extend
        throw new Error('Infinite scroll blocked: near end but server returned no new roots');
    }
    state.pendingFetch = false;
}

//TODO: this is hacky but apparently we need it
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
