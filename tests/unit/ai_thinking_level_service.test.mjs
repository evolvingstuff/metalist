import assert from 'node:assert/strict';
import test from 'node:test';

import {
    AI_THINKING_LEVEL_OPTIONS,
    DEFAULT_AI_THINKING_LEVEL,
    isThinkingLevelAvailableForModel,
    normalizeThinkingLevelForModel,
    validateAiThinkingLevel,
} from '../../app/static/js/modules/ai-chat/ai-thinking-level-service.js';


test('AI thinking levels expose the product abstraction with low default', () => {
    assert.equal(DEFAULT_AI_THINKING_LEVEL, 'low');
    assert.deepEqual(
        AI_THINKING_LEVEL_OPTIONS.map((option) => option.value),
        ['off', 'low', 'medium', 'high'],
    );
    for (const thinkingLevel of ['off', 'low', 'medium', 'high']) {
        assert.equal(validateAiThinkingLevel(thinkingLevel), thinkingLevel);
    }
    assert.throws(() => validateAiThinkingLevel('max'), /Unsupported AI thinking level/);
});


test('GPT-OSS cannot select Off and normalizes it visibly to Low', () => {
    assert.equal(
        isThinkingLevelAvailableForModel({ model: 'gpt-oss:20b', thinkingLevel: 'off' }),
        false,
    );
    assert.equal(
        normalizeThinkingLevelForModel({ model: 'gpt-oss:20b', thinkingLevel: 'off' }),
        'low',
    );
    assert.equal(
        normalizeThinkingLevelForModel({ model: 'qwen3:8b', thinkingLevel: 'off' }),
        'off',
    );
});
