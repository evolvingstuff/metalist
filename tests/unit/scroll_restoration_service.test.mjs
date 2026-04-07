import assert from 'node:assert/strict';
import test from 'node:test';

import { computeScrollYToRevealRect } from '../../app/static/js/modules/mode-manager/services/scroll-restoration-service.js';

test('computeScrollYToRevealRect uses bottom alignment for below-viewport nearest scrolling', () => {
    const target = computeScrollYToRevealRect({
        rectTop: 700,
        rectBottom: 760,
        currentScrollY: 1000,
        viewportTop: 100,
        viewportBottom: 600,
        scrollMaxY: 5000,
        align: 'nearest',
    });

    assert.equal(target, 1160);
});

test('computeScrollYToRevealRect uses top alignment for above-viewport nearest scrolling', () => {
    const target = computeScrollYToRevealRect({
        rectTop: 40,
        rectBottom: 120,
        currentScrollY: 1000,
        viewportTop: 100,
        viewportBottom: 600,
        scrollMaxY: 5000,
        align: 'nearest',
    });

    assert.equal(target, 940);
});

test('computeScrollYToRevealRect preserves top alignment when explicitly requested', () => {
    const target = computeScrollYToRevealRect({
        rectTop: 700,
        rectBottom: 760,
        currentScrollY: 1000,
        viewportTop: 100,
        viewportBottom: 600,
        scrollMaxY: 5000,
        align: 'top',
    });

    assert.equal(target, 1600);
});
