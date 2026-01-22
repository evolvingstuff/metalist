const USAGE_KEY = 'metalist.command_palette.usage.v1';

function parseUsageState(raw) {
    if (raw === null) {
        return {};
    }
    if (typeof raw !== 'string') {
        throw new Error('Usage state must be a string or null');
    }

    let parsed;
    try {
        parsed = JSON.parse(raw);
    } catch (err) {
        throw new Error(`Usage state JSON parse failed: ${err}`);
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Usage state must be an object');
    }
    return parsed;
}

function serializeUsageState(state) {
    if (!state || typeof state !== 'object' || Array.isArray(state)) {
        throw new Error('Usage state must be an object');
    }
    return JSON.stringify(state);
}

export class UsageStore {
    getUsageSnapshot() {
        const raw = localStorage.getItem(USAGE_KEY);
        return parseUsageState(raw);
    }

    recordUse(endpointId, queryTokens) {
        if (typeof endpointId !== 'string' || endpointId.length === 0) {
            throw new Error('UsageStore.recordUse requires endpointId string');
        }
        if (!Array.isArray(queryTokens)) {
            throw new Error('UsageStore.recordUse requires queryTokens array');
        }
        for (const token of queryTokens) {
            if (typeof token !== 'string') {
                throw new Error('UsageStore.recordUse queryTokens must be strings');
            }
        }

        const now = Date.now();
        const state = this.getUsageSnapshot();
        const previous = Object.prototype.hasOwnProperty.call(state, endpointId) ? state[endpointId] : null;
        const nextCount = previous && typeof previous.count === 'number' ? previous.count + 1 : 1;
        state[endpointId] = {
            count: nextCount,
            lastUsedAt: now,
            lastQueryTokens: queryTokens,
        };
        localStorage.setItem(USAGE_KEY, serializeUsageState(state));
    }
}

