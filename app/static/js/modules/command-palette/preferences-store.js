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

    async setManyAndRemove(updates, keysToRemove) {
        if (!updates || typeof updates !== 'object' || Array.isArray(updates)) {
            throw new Error('PreferencesStore.setManyAndRemove requires updates object');
        }
        if (!Array.isArray(keysToRemove)) {
            throw new Error('PreferencesStore.setManyAndRemove requires removal keys array');
        }
        const updateEntries = Object.entries(updates);
        if (updateEntries.length === 0) {
            throw new Error('PreferencesStore.setManyAndRemove requires updates');
        }
        for (const [key, value] of updateEntries) {
            if (typeof key !== 'string' || key.length === 0 || typeof value !== 'string') {
                throw new Error('PreferencesStore.setManyAndRemove updates are invalid');
            }
        }
        if (new Set(keysToRemove).size !== keysToRemove.length) {
            throw new Error('PreferencesStore.setManyAndRemove removal keys must be unique');
        }
        for (const key of keysToRemove) {
            if (typeof key !== 'string' || key.length === 0) {
                throw new Error('PreferencesStore.setManyAndRemove removal key is invalid');
            }
            if (Object.prototype.hasOwnProperty.call(updates, key)) {
                throw new Error('PreferencesStore cannot update and remove the same key');
            }
        }
        const nextState = { ...this._state, ...updates };
        for (const key of keysToRemove) {
            delete nextState[key];
        }
        const persisted = await persistClientPreferences(nextState);
        if (
            !persisted
            || typeof persisted !== 'object'
            || Array.isArray(persisted)
            || !persisted.preferences
            || typeof persisted.preferences !== 'object'
            || Array.isArray(persisted.preferences)
        ) {
            throw new Error('Saved client preferences response is invalid');
        }
        this.replaceAll(persisted.preferences);
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
