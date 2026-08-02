import assert from 'node:assert/strict';
import test from 'node:test';

import {
    ADD_STYLE_OPTIONS,
    appendStyleTagToken,
    buildStyleApplicationPlan,
    chooseStyleScope,
} from '../../app/static/js/modules/mode-manager/services/add-style-service.js';


test('Add Style exposes the supported formatting and renderer tags', () => {
    const tags = ADD_STYLE_OPTIONS.map((option) => option.tag);
    assert.equal(tags.includes('@heading'), true);
    assert.equal(tags.includes('@red'), true);
    assert.equal(tags.includes('@blue'), true);
    assert.equal(tags.includes('@markdown'), true);
    assert.equal(tags.includes('@csv'), true);
});


test('whole-note style plan adds an unscoped tag', () => {
    assert.deepEqual(
        buildStyleApplicationPlan({
            styleTag: '@red',
            contentText: 'scarlet',
            tagBarText: '',
            hasSelection: false,
        }),
        {
            styleTag: '@red',
            tagToken: '@red',
            openToken: '',
            closeToken: '',
        },
    );
});


test('selected style prefers single curly braces', () => {
    assert.deepEqual(
        buildStyleApplicationPlan({
            styleTag: '@red',
            contentText: 'my content has scarlet',
            tagBarText: '',
            hasSelection: true,
        }),
        {
            styleTag: '@red',
            tagToken: '{@red}',
            openToken: '{',
            closeToken: '}',
        },
    );
});


test('scope selection avoids symbols already used by content or tag bar', () => {
    assert.deepEqual(chooseStyleScope('uses {curly}', ''), {
        opener: '[',
        closer: ']',
        depth: 1,
        openToken: '[',
        closeToken: ']',
    });
    assert.deepEqual(chooseStyleScope('uses {curly} and [square]', '(existing)'), {
        opener: '{',
        closer: '}',
        depth: 2,
        openToken: '{{',
        closeToken: '}}',
    });
});


test('scope selection fails loudly after all supported delimiters are exhausted', () => {
    const allDelimiters = '{}[]() {{}} [[]] (()) {{{}}} [[[]]] ((()))';
    assert.throws(
        () => chooseStyleScope(allDelimiters, ''),
        /No unused style scope delimiter/,
    );
});


test('style tag append preserves wrappers and avoids exact duplicates', () => {
    assert.equal(appendStyleTagToken('@blue {{@red @bold}}', '{@italic}'), '@blue {{@red @bold}} {@italic}');
    assert.equal(appendStyleTagToken('@blue /* note */', '@blue'), '@blue /* note */');
});
