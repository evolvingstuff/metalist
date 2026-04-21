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

    async remove(key) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PreferencesStore.remove requires non-empty key');
        }
        delete this._state[key];
        await persistClientPreferences(this._snapshot());
    }

    async clearAll() {
        this._state = {};
        await persistClientPreferences(this._snapshot());
    }
}
