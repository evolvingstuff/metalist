import assert from 'node:assert/strict';
import test from 'node:test';

import {
    validateSearchSuggestionStatistics,
} from '../../app/static/js/modules/mode-manager/services/search-suggestion-statistics-service.js';


test('search suggestion statistics validate and copy daily tag credits', () => {
    const payload = {
        retentionPopulatedDayLimit: 365,
        days: [
            {
                date: '2026-08-20',
                totalTagCredits: 3,
                tags: [
                    { tag: 'journal', count: 2 },
                    { tag: 'workday', count: 1 },
                ],
            },
        ],
    };

    const validated = validateSearchSuggestionStatistics(payload);

    assert.deepEqual(validated, payload);
    assert.notEqual(validated, payload);
    assert.notEqual(validated.days, payload.days);
    assert.notEqual(validated.days[0].tags, payload.days[0].tags);
});


test('search suggestion statistics reject inconsistent totals', () => {
    assert.throws(
        () => validateSearchSuggestionStatistics({
            retentionPopulatedDayLimit: 365,
            days: [
                {
                    date: '2026-08-20',
                    totalTagCredits: 4,
                    tags: [{ tag: 'journal', count: 2 }],
                },
            ],
        }),
        /totalTagCredits/,
    );
});
