import assert from 'node:assert/strict';
import test from 'node:test';

import {
    AGENT_WEB_ACCESS_MODE_PREFERENCE_KEY,
    DEFAULT_AGENT_WEB_ACCESS_MODE,
    readAgentWebAccessMode,
    validateAgentWebAccessMode,
} from '../../app/static/js/modules/ai-chat/agent-web-settings.js';


test('web access defaults to none when the preference is absent', () => {
    assert.equal(readAgentWebAccessMode(() => null), DEFAULT_AGENT_WEB_ACCESS_MODE);
    assert.equal(DEFAULT_AGENT_WEB_ACCESS_MODE, 'none');
});


test('web access accepts all three product modes', () => {
    for (const mode of ['none', 'contextual', 'full']) {
        assert.equal(validateAgentWebAccessMode(mode), mode);
        assert.equal(
            readAgentWebAccessMode((key) => (
                key === AGENT_WEB_ACCESS_MODE_PREFERENCE_KEY ? mode : null
            )),
            mode,
        );
    }
});


test('web access rejects unknown modes', () => {
    for (const value of ['', 'off', 'context', 'FULL', ' full ', null]) {
        assert.throws(() => validateAgentWebAccessMode(value));
    }
});
