import {
    isRhsCalendarPinnedToNewest,
    scrollRhsCalendarToNewest,
} from './rhs-panel-service.js';

export function initializeScrollToTopButton(options) {
    const dependencies = resolveScrollToTopDependencies(options);
    const button = document.getElementById('scroll-to-top-button');
    if (!button) {
        throw new Error('scroll-to-top-button not found');
    }

    const SCROLL_PIXELS_PER_MS = 20;
    const MIN_SCROLL_DURATION_MS = 120;
    const MAX_SCROLL_DURATION_MS = 240;

    let activeAnimationFrame = null;

    let pendingFrame = null;
    let lastDisabled = null;

    const syncVisibility = () => {
        const pageAtTop = window.scrollY <= 0;
        const calendarPinnedToNewest = dependencies.isCalendarPinnedToNewest();
        const shouldDisable = pageAtTop && calendarPinnedToNewest;
        if (shouldDisable === lastDisabled) {
            return;
        }
        lastDisabled = shouldDisable;
        button.disabled = shouldDisable;
    };

    const scheduleSyncVisibility = () => {
        if (pendingFrame !== null) {
            return;
        }
        pendingFrame = window.requestAnimationFrame(() => {
            pendingFrame = null;
            syncVisibility();
        });
    };

    window.addEventListener('scroll', scheduleSyncVisibility, { passive: true });
    const rhsPanel = document.getElementById('rhs-panel');
    if (rhsPanel !== null) {
        if (typeof rhsPanel.addEventListener !== 'function') {
            throw new Error('rhs-panel must support addEventListener');
        }
        rhsPanel.addEventListener('scroll', scheduleSyncVisibility, { passive: true });
    }

    button.addEventListener('click', () => {
        dependencies.scrollCalendarToNewest();
        const startY = window.scrollY;
        if (startY <= 0) {
            syncVisibility();
            button.blur();
            return;
        }

        if (activeAnimationFrame !== null) {
            window.cancelAnimationFrame(activeAnimationFrame);
            activeAnimationFrame = null;
        }

        const prefersReducedMotion = window.matchMedia
            ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
            : false;

        if (prefersReducedMotion) {
            window.scrollTo(0, 0);
            syncVisibility();
            button.blur();
            return;
        }

        const distance = Math.max(0, Math.round(startY));
        const durationMs = Math.max(
            MIN_SCROLL_DURATION_MS,
            Math.min(MAX_SCROLL_DURATION_MS, Math.round(distance / SCROLL_PIXELS_PER_MS))
        );
        const startTime = performance.now();

        const tick = (now) => {
            const elapsed = now - startTime;
            const t = Math.max(0, Math.min(1, elapsed / durationMs));
            const eased = 1 - Math.pow(1 - t, 3);
            const nextY = Math.max(0, Math.round(startY * (1 - eased)));
            window.scrollTo(0, nextY);
            if (t < 1) {
                activeAnimationFrame = window.requestAnimationFrame(tick);
            } else {
                activeAnimationFrame = null;
                syncVisibility();
            }
        };

        activeAnimationFrame = window.requestAnimationFrame(tick);
        button.blur();
    });

    syncVisibility();
}

function resolveScrollToTopDependencies(options) {
    let scrollCalendarToNewest = scrollRhsCalendarToNewest;
    let isCalendarPinnedToNewest = isRhsCalendarPinnedToNewest;
    if (options !== undefined) {
        if (options === null || typeof options !== 'object') {
            throw new Error('initializeScrollToTopButton options must be an object');
        }
        if (Object.prototype.hasOwnProperty.call(options, 'scrollCalendarToNewest')) {
            if (typeof options.scrollCalendarToNewest !== 'function') {
                throw new Error('scrollCalendarToNewest option must be a function');
            }
            scrollCalendarToNewest = options.scrollCalendarToNewest;
        }
        if (Object.prototype.hasOwnProperty.call(options, 'isCalendarPinnedToNewest')) {
            if (typeof options.isCalendarPinnedToNewest !== 'function') {
                throw new Error('isCalendarPinnedToNewest option must be a function');
            }
            isCalendarPinnedToNewest = options.isCalendarPinnedToNewest;
        }
    }
    return {
        scrollCalendarToNewest,
        isCalendarPinnedToNewest,
    };
}
