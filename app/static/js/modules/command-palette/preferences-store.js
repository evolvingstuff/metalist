const STORAGE_PREFIX = 'metalist.command_palette.pref.';

export class PreferencesStore {
    getRaw(key) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PreferencesStore.getRaw requires non-empty key');
        }
        return localStorage.getItem(`${STORAGE_PREFIX}${key}`);
    }

    setRaw(key, value) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PreferencesStore.setRaw requires non-empty key');
        }
        if (typeof value !== 'string') {
            throw new Error('PreferencesStore.setRaw requires string value');
        }
        localStorage.setItem(`${STORAGE_PREFIX}${key}`, value);
    }

    remove(key) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PreferencesStore.remove requires non-empty key');
        }
        localStorage.removeItem(`${STORAGE_PREFIX}${key}`);
    }

    clearAll() {
        const keysToRemove = [];
        for (let idx = 0; idx < localStorage.length; idx += 1) {
            const storageKey = localStorage.key(idx);
            if (typeof storageKey === 'string' && storageKey.startsWith(STORAGE_PREFIX)) {
                keysToRemove.push(storageKey);
            }
        }
        for (const storageKey of keysToRemove) {
            localStorage.removeItem(storageKey);
        }
    }
}

