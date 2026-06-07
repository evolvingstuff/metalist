import { ReminderStore } from './reminder-store.js';

const NON_IDLE_THROTTLE_MS = 30_000;

function reminderDisplayTitle(reminder) {
    if (!reminder || typeof reminder !== 'object') {
        throw new Error('reminderDisplayTitle requires reminder');
    }
    if (typeof reminder.title === 'string' && reminder.title.length > 0) {
        return reminder.title;
    }
    return 'Reminder';
}

class ReminderSurfaceService {
    constructor() {
        this._started = false;
        this._localDueTimer = null;
        this._isEvaluating = false;
        this._pendingEvaluationActivityKind = null;
        this._unsubscribeStore = null;
        this._shownOccurrenceKeys = new Set();
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
            return this._eventIfNotShown(reminder, reminder.next_fire_at, fireAt.getTime() < now.getTime());
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
        return this._eventIfNotShown(reminder, reminder.next_fire_date, reminder.next_fire_date < today);
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
        item.innerHTML = `
            <div class="reminder-surface-text">
                <strong>${this._escape(reminderDisplayTitle(reminder))}</strong>
                <span>${this._escape(event.kind === 'missed' ? 'Missed reminder' : 'Reminder due')}</span>
            </div>
            <div class="reminder-surface-actions">
                <button type="button" data-reminder-surface-action="acknowledge" title="Clear this due or missed notice">Got it</button>
            </div>
        `;
        container.appendChild(item);
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
        item.remove();
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
