import { persistClientPreferences } from '../client-state-api.js';

export class PreferencesStore {
    constructor() {
        this._state = {};
    }

    replaceAll(rawPreferences) {
        if (!rawPreferences || typeof rawPreferences !== 'object' || Array.isArray(rawPreferences)) {
            throw new Error('PreferencesStore.replaceAll requires preferences object');
        }

        const nextState = {};
        for (const [key, value] of Object.entries(rawPreferences)) {
            if (typeof key !== 'string' || key.length === 0) {
                throw new Error('PreferencesStore.replaceAll requires non-empty string keys');
            }
            if (typeof value !== 'string') {
                throw new Error('PreferencesStore.replaceAll requires string values');
            }
            nextState[key] = value;
        }
        this._state = nextState;
    }

    _snapshot() {
        return { ...this._state };
    }

    getRaw(key) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PreferencesStore.getRaw requires non-empty key');
        }
        if (!Object.prototype.hasOwnProperty.call(this._state, key)) {
            return null;
        }
        return this._state[key];
    }

    async setRaw(key, value) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PreferencesStore.setRaw requires non-empty key');
        }
        if (typeof value !== 'string') {
            throw new Error('PreferencesStore.setRaw requires string value');
        }
        this._state[key] = value;
        await persistClientPreferences(this._snapshot());
    }

    async setMany(updates) {
        if (!updates || typeof updates !== 'object' || Array.isArray(updates)) {
            throw new Error('PreferencesStore.setMany requires updates object');
        }
        const entries = Object.entries(updates);
        if (entries.length === 0) {
            throw new Error('PreferencesStore.setMany requires at least one update');
        }
        for (const [key, value] of entries) {
            if (typeof key !== 'string' || key.length === 0) {
                throw new Error('PreferencesStore.setMany requires non-empty keys');
            }
            if (typeof value !== 'string') {
                throw new Error('PreferencesStore.setMany requires string values');
            }
        }
        Object.assign(this._state, updates);
        await persistClientPreferences(this._snapshot());
    }

    async remove(key) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PreferencesStore.remove requires non-empty key');
        }
        delete this._state[key];
        await persistClientPreferences(this._snapshot());
    }

    async removeMany(keys) {
        if (!Array.isArray(keys) || keys.length === 0) {
            throw new Error('PreferencesStore.removeMany requires non-empty keys array');
        }
        const uniqueKeys = new Set(keys);
        if (uniqueKeys.size !== keys.length) {
            throw new Error('PreferencesStore.removeMany requires unique keys');
        }
        for (const key of keys) {
            if (typeof key !== 'string' || key.length === 0) {
                throw new Error('PreferencesStore.removeMany requires non-empty string keys');
            }
        }
        const nextState = this._snapshot();
        for (const key of keys) {
            delete nextState[key];
        }
        await persistClientPreferences(nextState);
        this._state = nextState;
    }

    async clearAll() {
        this._state = {};
        await persistClientPreferences(this._snapshot());
    }
}
