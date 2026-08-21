import assert from 'node:assert/strict';
import test from 'node:test';


function createStorage() {
    const entries = new Map();
    return {
        getItem: (key) => entries.has(key) ? entries.get(key) : null,
        setItem: (key, value) => entries.set(key, String(value)),
        removeItem: (key) => entries.delete(key),
    };
}


globalThis.sessionStorage = createStorage();
globalThis.localStorage = createStorage();
globalThis.window = {};

const {
    SearchSuggestionStatisticsModal,
} = await import('../../app/static/js/modules/modals/search-suggestion-statistics-modal.js');


function installModalStateHarness(modal, initialState) {
    let state = { ...initialState };
    let renderCount = 0;
    modal.getModalState = () => state;
    modal.updateModalState = (updates) => {
        state = { ...state, ...updates };
    };
    modal.renderModalContent = () => {
        renderCount += 1;
    };
    modal.isOpen = true;
    return {
        getState: () => state,
        getRenderCount: () => renderCount,
    };
}


test('statistics modal resets activity and reloads its empty state', async () => {
    let loadCount = 0;
    let resetCount = 0;
    const modal = new SearchSuggestionStatisticsModal(
        async () => {
            loadCount += 1;
            return { retentionPopulatedDayLimit: 365, days: [] };
        },
        () => [1, 7, 30],
        async () => {
            resetCount += 1;
            return true;
        },
    );
    const harness = installModalStateHarness(modal, {
        loading: false,
        resetting: false,
        confirmingReset: true,
        statistics: {
            retentionPopulatedDayLimit: 365,
            days: [{
                date: '2026-08-21',
                totalTagCredits: 1,
                tags: [{ tag: 'journal', count: 1 }],
            }],
        },
    });

    await modal._resetActivity();

    assert.equal(resetCount, 1);
    assert.equal(loadCount, 1);
    assert.equal(harness.getState().resetting, false);
    assert.equal(harness.getState().confirmingReset, false);
    assert.deepEqual(harness.getState().statistics.days, []);
    assert.equal(harness.getRenderCount(), 2);
});


test('statistics modal keeps its displayed activity when reset is cancelled', async () => {
    let loadCount = 0;
    const statistics = {
        retentionPopulatedDayLimit: 365,
        days: [{
            date: '2026-08-21',
            totalTagCredits: 1,
            tags: [{ tag: 'journal', count: 1 }],
        }],
    };
    const modal = new SearchSuggestionStatisticsModal(
        async () => {
            loadCount += 1;
            return { retentionPopulatedDayLimit: 365, days: [] };
        },
        () => [1, 7, 30],
        async () => false,
    );
    const harness = installModalStateHarness(modal, {
        loading: false,
        resetting: false,
        confirmingReset: true,
        statistics,
    });

    await modal._resetActivity();

    assert.equal(loadCount, 0);
    assert.equal(harness.getState().resetting, false);
    assert.equal(harness.getState().confirmingReset, false);
    assert.equal(harness.getState().statistics, statistics);
    assert.equal(harness.getRenderCount(), 2);
});


test('statistics modal enters an in-app reset confirmation before deleting activity', () => {
    let resetCount = 0;
    const modal = new SearchSuggestionStatisticsModal(
        async () => ({ retentionPopulatedDayLimit: 365, days: [] }),
        () => [1, 7, 30],
        async () => {
            resetCount += 1;
            return true;
        },
    );
    const harness = installModalStateHarness(modal, {
        loading: false,
        resetting: false,
        confirmingReset: false,
        statistics: { retentionPopulatedDayLimit: 365, days: [] },
    });

    modal._requestResetConfirmation();

    assert.equal(resetCount, 0);
    assert.equal(harness.getState().confirmingReset, true);
    assert.equal(harness.getRenderCount(), 1);
});
