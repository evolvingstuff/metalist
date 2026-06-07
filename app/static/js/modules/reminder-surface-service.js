import { ReminderStore } from './reminder-store.js';

const NON_IDLE_THROTTLE_MS = 30_000;
const ELAPSED_UPDATE_MS = 1_000;
const REMINDER_RENDER_ICON = '🔔';

function reminderDisplayTitle(reminder) {
    if (!reminder || typeof reminder !== 'object') {
        throw new Error('reminderDisplayTitle requires reminder');
    }
    if (typeof reminder.title === 'string' && reminder.title.length > 0) {
        return reminder.title;
    }
    return 'Reminder';
}

function reminderDetails(reminder) {
    if (!reminder || typeof reminder !== 'object') {
        throw new Error('reminderDetails requires reminder');
    }
    if (typeof reminder.details !== 'string') {
        return '';
    }
    return reminder.details.trim();
}

function formatElapsedSince(value, now) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error('formatElapsedSince requires value');
    }
    if (!(now instanceof Date)) {
        throw new Error('formatElapsedSince requires Date');
    }
    const dueAt = new Date(value);
    if (Number.isNaN(dueAt.getTime())) {
        throw new Error('formatElapsedSince requires valid datetime');
    }
    const elapsedSeconds = Math.max(0, Math.floor((now.getTime() - dueAt.getTime()) / 1000));
    if (elapsedSeconds < 1) {
        return 'Due now';
    }
    if (elapsedSeconds < 60) {
        return `Due ${elapsedSeconds} sec ago`;
    }
    const elapsedMinutes = Math.floor(elapsedSeconds / 60);
    const remainingSeconds = elapsedSeconds % 60;
    if (elapsedMinutes < 60) {
        return `Due ${elapsedMinutes} min ${remainingSeconds} sec ago`;
    }
    const elapsedHours = Math.floor(elapsedMinutes / 60);
    const remainingMinutes = elapsedMinutes % 60;
    if (elapsedHours < 24) {
        return `Due ${elapsedHours} hr ${remainingMinutes} min ago`;
    }
    const elapsedDays = Math.floor(elapsedHours / 24);
    const remainingHours = elapsedHours % 24;
    return `Due ${elapsedDays} day ${remainingHours} hr ago`;
}

function dateOnlySurfaceLabel(eventKind) {
    if (eventKind === 'missed') {
        return 'Overdue';
    }
    if (eventKind === 'due') {
        return 'Due today';
    }
    throw new Error(`Unsupported reminder event kind: ${eventKind}`);
}

class ReminderSurfaceService {
    constructor() {
        this._started = false;
        this._localDueTimer = null;
        this._isEvaluating = false;
        this._pendingEvaluationActivityKind = null;
        this._unsubscribeStore = null;
        this._shownOccurrenceKeys = new Set();
        this._elapsedTimers = new Map();
        this._lastNonIdleAt = 0;
        this._handleInteraction = this._handleInteraction.bind(this);
        this._handleVisibilityChange = this._handleVisibilityChange.bind(this);
        this._handleModalClosed = this._handleModalClosed.bind(this);
        this._handleStoreSnapshot = this._handleStoreSnapshot.bind(this);
    }

    start() {
        if (this._started) {
            return;
        }
        this._started = true;
        this._ensureContainer();
        document.addEventListener('pointerdown', this._handleInteraction, true);
        document.addEventListener('keydown', this._handleInteraction, true);
        document.addEventListener('visibilitychange', this._handleVisibilityChange);
        document.addEventListener('metalist:modal-closed', this._handleModalClosed);
        this._unsubscribeStore = ReminderStore.subscribe(this._handleStoreSnapshot);
        void this._refreshAndEvaluate('idle');
    }

    stop() {
        if (!this._started) {
            return;
        }
        this._started = false;
        document.removeEventListener('pointerdown', this._handleInteraction, true);
        document.removeEventListener('keydown', this._handleInteraction, true);
        document.removeEventListener('visibilitychange', this._handleVisibilityChange);
        document.removeEventListener('metalist:modal-closed', this._handleModalClosed);
        if (typeof this._unsubscribeStore === 'function') {
            this._unsubscribeStore();
            this._unsubscribeStore = null;
        }
        this._clearLocalDueTimer();
        this._clearElapsedTimers();
        this._shownOccurrenceKeys.clear();
    }

    async _handleInteraction() {
        if (document.visibilityState !== 'visible') {
            return;
        }
        const now = Date.now();
        if (now - this._lastNonIdleAt < NON_IDLE_THROTTLE_MS) {
            return;
        }
        this._lastNonIdleAt = now;
        await this._evaluate('non_idle_use');
    }

    _handleVisibilityChange() {
        if (document.visibilityState === 'visible') {
            void this._refreshAndEvaluate('idle');
        }
    }

    _handleModalClosed(event) {
        if (!event || typeof event !== 'object') {
            throw new Error('Reminder modal close event missing');
        }
        if (!event.detail || event.detail.modalName !== 'reminderModal') {
            return;
        }
        void this._refreshAndEvaluate('non_idle_use');
    }

    async _refreshAndEvaluate(activityKind) {
        if (activityKind !== 'idle' && activityKind !== 'non_idle_use') {
            throw new Error('Reminder refresh/evaluate activityKind invalid');
        }
        if (document.visibilityState !== 'visible') {
            return;
        }
        this._queueEvaluation(activityKind);
        await ReminderStore.refresh();
        await this._drainEvaluationQueue();
    }

    async _evaluate(activityKind) {
        if (activityKind !== 'idle' && activityKind !== 'non_idle_use') {
            throw new Error('Reminder evaluation activityKind invalid');
        }
        if (document.visibilityState !== 'visible') {
            return;
        }
        this._queueEvaluation(activityKind);
        await this._drainEvaluationQueue();
    }

    async evaluateFreshSnapshot(activityKind) {
        if (activityKind !== 'idle' && activityKind !== 'non_idle_use') {
            throw new Error('Reminder surface public evaluation activityKind invalid');
        }
        if (!this._started) {
            this.start();
        }
        await this._evaluate(activityKind);
    }

    _handleStoreSnapshot(snapshot) {
        if (!snapshot || typeof snapshot !== 'object') {
            throw new Error('Reminder store snapshot missing');
        }
        if (!Array.isArray(snapshot.reminders)) {
            throw new Error('Reminder store snapshot missing reminders');
        }
        if (!Array.isArray(snapshot.missed)) {
            throw new Error('Reminder store snapshot missing missed');
        }
        this._reconcileRenderedItems(snapshot);
        this._scheduleNextLocalDueTimer();
        if (document.visibilityState !== 'visible') {
            return;
        }
        void this._evaluate('non_idle_use');
    }

    _queueEvaluation(activityKind) {
        if (activityKind !== 'idle' && activityKind !== 'non_idle_use') {
            throw new Error('Reminder queue activityKind invalid');
        }
        if (activityKind === 'non_idle_use') {
            this._pendingEvaluationActivityKind = 'non_idle_use';
            return;
        }
        if (this._pendingEvaluationActivityKind === null) {
            this._pendingEvaluationActivityKind = 'idle';
        }
    }

    async _drainEvaluationQueue() {
        if (this._isEvaluating) {
            return;
        }
        if (this._pendingEvaluationActivityKind === null) {
            return;
        }
        const activityKind = this._pendingEvaluationActivityKind;
        this._pendingEvaluationActivityKind = null;
        this._isEvaluating = true;
        await (async () => {
            const events = this._localEvents(activityKind);
            for (const event of events) {
                this._renderEvent(event);
            }
        })().finally(() => {
            this._isEvaluating = false;
        });
        if (this._pendingEvaluationActivityKind !== null) {
            await this._drainEvaluationQueue();
        }
        this._scheduleNextLocalDueTimer();
    }

    _localEvents(activityKind) {
        if (activityKind !== 'idle' && activityKind !== 'non_idle_use') {
            throw new Error('Reminder local activityKind invalid');
        }
        const now = new Date();
        const today = this._localDate(now);
        const events = [];
        const snapshot = ReminderStore.snapshot();
        for (const reminder of snapshot.reminders) {
            const event = this._localEventForReminder(reminder, activityKind, now, today);
            if (event !== null) {
                events.push(event);
            }
        }
        return events;
    }

    _localEventForReminder(reminder, activityKind, now, today) {
        if (!reminder || typeof reminder !== 'object') {
            throw new Error('Reminder mirror entry must be object');
        }
        const occurrence = this._currentOccurrence(reminder, activityKind, now, today);
        if (occurrence === null) {
            return null;
        }
        return this._eventIfNotShown(reminder, occurrence.value, occurrence.isMissed);
    }

    _currentOccurrence(reminder, activityKind, now, today) {
        if (!reminder || typeof reminder !== 'object') {
            throw new Error('Reminder occurrence requires reminder');
        }
        if (activityKind !== 'idle' && activityKind !== 'non_idle_use') {
            throw new Error('Reminder occurrence activityKind invalid');
        }
        if (!(now instanceof Date)) {
            throw new Error('Reminder occurrence requires now Date');
        }
        if (typeof today !== 'string' || today.length === 0) {
            throw new Error('Reminder occurrence requires local date');
        }
        if (reminder.status !== 'active') {
            return null;
        }
        if (reminder.time_mode === 'date_time') {
            if (typeof reminder.next_fire_at !== 'string' || reminder.next_fire_at.length === 0) {
                return null;
            }
            const fireAt = new Date(reminder.next_fire_at);
            if (Number.isNaN(fireAt.getTime())) {
                throw new Error('Reminder mirror has invalid next_fire_at');
            }
            if (fireAt.getTime() > now.getTime()) {
                return null;
            }
            return {
                value: reminder.next_fire_at,
                isMissed: fireAt.getTime() < now.getTime(),
            };
        }
        if (activityKind !== 'non_idle_use') {
            return null;
        }
        if (typeof reminder.next_fire_date !== 'string' || reminder.next_fire_date.length === 0) {
            return null;
        }
        if (reminder.next_fire_date > today) {
            return null;
        }
        return {
            value: reminder.next_fire_date,
            isMissed: reminder.next_fire_date < today,
        };
    }

    _eventIfNotShown(reminder, occurrenceValue, isMissed) {
        if (typeof reminder.id !== 'string' || reminder.id.length === 0) {
            throw new Error('Reminder mirror entry missing id');
        }
        const occurrenceKey = `${reminder.id}:${occurrenceValue}`;
        if (this._shownOccurrenceKeys.has(occurrenceKey)) {
            return null;
        }
        this._shownOccurrenceKeys.add(occurrenceKey);
        return {
            kind: isMissed ? 'missed' : 'due',
            reminder,
            occurrenceValue,
        };
    }

    _scheduleNextLocalDueTimer() {
        this._clearLocalDueTimer();
        const delayMs = this._nextDateTimeDelayMs();
        if (delayMs === null) {
            return;
        }
        this._localDueTimer = window.setTimeout(() => {
            this._localDueTimer = null;
            void this._evaluate('idle');
        }, delayMs);
    }

    _clearLocalDueTimer() {
        if (this._localDueTimer === null) {
            return;
        }
        window.clearTimeout(this._localDueTimer);
        this._localDueTimer = null;
    }

    _nextDateTimeDelayMs() {
        const nowMs = Date.now();
        let nearestMs = null;
        const snapshot = ReminderStore.snapshot();
        for (const reminder of snapshot.reminders) {
            if (!reminder || typeof reminder !== 'object') {
                throw new Error('Reminder mirror entry must be object');
            }
            if (reminder.status !== 'active') {
                continue;
            }
            if (reminder.time_mode !== 'date_time') {
                continue;
            }
            if (typeof reminder.next_fire_at !== 'string' || reminder.next_fire_at.length === 0) {
                continue;
            }
            const fireAt = new Date(reminder.next_fire_at);
            if (Number.isNaN(fireAt.getTime())) {
                throw new Error('Reminder mirror has invalid next_fire_at');
            }
            const fireAtMs = fireAt.getTime();
            if (fireAtMs <= nowMs) {
                continue;
            }
            if (nearestMs === null || fireAtMs < nearestMs) {
                nearestMs = fireAtMs;
            }
        }
        if (nearestMs === null) {
            return null;
        }
        return nearestMs - nowMs;
    }

    _localDate(value) {
        if (!(value instanceof Date)) {
            throw new Error('_localDate requires Date');
        }
        const year = value.getFullYear();
        const month = String(value.getMonth() + 1).padStart(2, '0');
        const day = String(value.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    _ensureContainer() {
        let container = document.getElementById('reminder-surface');
        if (container) {
            return container;
        }
        container = document.createElement('div');
        container.id = 'reminder-surface';
        container.className = 'reminder-surface';
        document.body.appendChild(container);
        container.addEventListener('click', (event) => {
            void this._handleSurfaceClick(event);
        });
        return container;
    }

    _renderEvent(event) {
        if (!event || typeof event !== 'object') {
            throw new Error('Reminder event must be object');
        }
        const reminder = event.reminder;
        if (!reminder || typeof reminder !== 'object') {
            throw new Error('Reminder event missing reminder');
        }
        const container = this._ensureContainer();
        const item = document.createElement('div');
        item.className = 'reminder-surface-item';
        item.dataset.reminderId = reminder.id;
        item.dataset.occurrenceValue = event.occurrenceValue;
        this._renderSurfaceItemContent(item, event);
        container.appendChild(item);
    }

    _renderSurfaceItemContent(item, event) {
        if (!(item instanceof HTMLElement)) {
            throw new Error('_renderSurfaceItemContent requires item');
        }
        if (!event || typeof event !== 'object') {
            throw new Error('_renderSurfaceItemContent requires event');
        }
        const reminder = event.reminder;
        if (!reminder || typeof reminder !== 'object') {
            throw new Error('_renderSurfaceItemContent requires reminder');
        }
        const surfaceText = this._surfaceEventText(event);
        const details = reminderDetails(reminder);
        this._clearElapsedTimerForItem(item);
        item.innerHTML = `
            <div class="reminder-surface-text">
                <strong><span class="reminder-surface-icon" aria-hidden="true">${REMINDER_RENDER_ICON}</span> ${this._escape(reminderDisplayTitle(reminder))}</strong>
                ${details ? `<span class="reminder-surface-details">${this._escape(details)}</span>` : ''}
                <hr class="reminder-surface-rule">
            </div>
            <div class="reminder-surface-footer">
                <span class="reminder-surface-status" data-reminder-surface-text>${this._escape(surfaceText)}</span>
                <button type="button" data-reminder-surface-action="acknowledge" title="Clear this due or missed notice">Got it</button>
            </div>
        `;
        this._startElapsedTimerIfNeeded(item, event);
    }

    _reconcileRenderedItems(snapshot) {
        if (!snapshot || typeof snapshot !== 'object') {
            throw new Error('_reconcileRenderedItems requires snapshot');
        }
        if (!Array.isArray(snapshot.reminders)) {
            throw new Error('_reconcileRenderedItems requires reminders');
        }
        const container = this._ensureContainer();
        const items = Array.from(container.querySelectorAll('.reminder-surface-item'));
        if (items.length === 0) {
            return;
        }
        const activeOccurrenceEvents = this._activeOccurrenceEvents(snapshot.reminders);
        const activeOccurrenceKeys = new Set(activeOccurrenceEvents.keys());
        this._pruneShownOccurrenceKeys(activeOccurrenceKeys);
        for (const item of items) {
            if (!(item instanceof HTMLElement)) {
                throw new Error('Reminder surface query returned non-element');
            }
            const reminderId = item.dataset.reminderId;
            const occurrenceValue = item.dataset.occurrenceValue;
            if (typeof reminderId !== 'string' || reminderId.length === 0) {
                throw new Error('Reminder surface item missing reminder id');
            }
            if (typeof occurrenceValue !== 'string' || occurrenceValue.length === 0) {
                throw new Error('Reminder surface item missing occurrence value');
            }
            const occurrenceKey = `${reminderId}:${occurrenceValue}`;
            const activeEvent = activeOccurrenceEvents.get(occurrenceKey);
            if (activeEvent === undefined) {
                this._removeSurfaceItem(item);
                continue;
            }
            this._renderSurfaceItemContent(item, activeEvent);
        }
    }

    _activeOccurrenceEvents(reminders) {
        if (!Array.isArray(reminders)) {
            throw new Error('_activeOccurrenceEvents requires reminders');
        }
        const events = new Map();
        const now = new Date();
        const today = this._localDate(now);
        for (const reminder of reminders) {
            if (!reminder || typeof reminder !== 'object') {
                throw new Error('Reminder mirror entry must be object');
            }
            const occurrence = this._currentOccurrence(reminder, 'non_idle_use', now, today);
            if (occurrence === null) {
                continue;
            }
            if (typeof reminder.id !== 'string' || reminder.id.length === 0) {
                throw new Error('Reminder mirror entry missing id');
            }
            events.set(`${reminder.id}:${occurrence.value}`, {
                kind: occurrence.isMissed ? 'missed' : 'due',
                reminder,
                occurrenceValue: occurrence.value,
            });
        }
        return events;
    }

    _pruneShownOccurrenceKeys(activeOccurrenceKeys) {
        if (!(activeOccurrenceKeys instanceof Set)) {
            throw new Error('_pruneShownOccurrenceKeys requires Set');
        }
        for (const occurrenceKey of Array.from(this._shownOccurrenceKeys)) {
            if (!activeOccurrenceKeys.has(occurrenceKey)) {
                this._shownOccurrenceKeys.delete(occurrenceKey);
            }
        }
    }

    async _handleSurfaceClick(event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const item = target.closest('.reminder-surface-item');
        if (!(item instanceof HTMLElement)) {
            return;
        }
        const actionButton = target.closest('[data-reminder-surface-action]');
        if (!(actionButton instanceof HTMLElement)) {
            return;
        }
        const reminderId = item.dataset.reminderId;
        if (typeof reminderId !== 'string' || reminderId.length === 0) {
            throw new Error('Reminder surface item missing reminder id');
        }
        const actionName = actionButton.getAttribute('data-reminder-surface-action');
        if (typeof actionName !== 'string' || actionName.length === 0) {
            throw new Error('Reminder surface action missing');
        }
        await ReminderStore.action(reminderId, actionName);
        this._removeSurfaceItem(item);
    }

    _surfaceEventText(event) {
        if (!event || typeof event !== 'object') {
            throw new Error('Reminder surface text requires event');
        }
        const reminder = event.reminder;
        if (!reminder || typeof reminder !== 'object') {
            throw new Error('Reminder surface text requires reminder');
        }
        if (reminder.time_mode === 'date_time') {
            if (typeof event.occurrenceValue !== 'string' || event.occurrenceValue.length === 0) {
                throw new Error('date-time reminder event requires occurrenceValue');
            }
            return formatElapsedSince(event.occurrenceValue, new Date());
        }
        return dateOnlySurfaceLabel(event.kind);
    }

    _startElapsedTimerIfNeeded(item, event) {
        if (!(item instanceof HTMLElement)) {
            throw new Error('_startElapsedTimerIfNeeded requires HTMLElement');
        }
        if (!event || typeof event !== 'object') {
            throw new Error('_startElapsedTimerIfNeeded requires event');
        }
        const reminder = event.reminder;
        if (!reminder || typeof reminder !== 'object') {
            throw new Error('_startElapsedTimerIfNeeded requires reminder');
        }
        if (reminder.time_mode !== 'date_time') {
            return;
        }
        if (typeof event.occurrenceValue !== 'string' || event.occurrenceValue.length === 0) {
            throw new Error('date-time reminder event requires occurrenceValue');
        }
        const textElement = item.querySelector('[data-reminder-surface-text]');
        if (!(textElement instanceof HTMLElement)) {
            throw new Error('reminder surface text element missing');
        }
        const timerId = window.setInterval(() => {
            textElement.textContent = formatElapsedSince(event.occurrenceValue, new Date());
        }, ELAPSED_UPDATE_MS);
        this._elapsedTimers.set(item, timerId);
    }

    _removeSurfaceItem(item) {
        if (!(item instanceof HTMLElement)) {
            throw new Error('_removeSurfaceItem requires HTMLElement');
        }
        this._clearElapsedTimerForItem(item);
        item.remove();
    }

    _clearElapsedTimerForItem(item) {
        if (!(item instanceof HTMLElement)) {
            throw new Error('_clearElapsedTimerForItem requires HTMLElement');
        }
        const timerId = this._elapsedTimers.get(item);
        if (timerId !== undefined) {
            window.clearInterval(timerId);
            this._elapsedTimers.delete(item);
        }
    }

    _clearElapsedTimers() {
        for (const timerId of this._elapsedTimers.values()) {
            window.clearInterval(timerId);
        }
        this._elapsedTimers.clear();
    }

    _escape(value) {
        if (typeof value !== 'string') {
            return '';
        }
        return value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
}

export const ReminderSurface = new ReminderSurfaceService();
