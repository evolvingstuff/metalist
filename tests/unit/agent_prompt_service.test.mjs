import assert from 'node:assert/strict';
import test from 'node:test';

import {
    AgentPromptValidationError,
    validateAgentInstructionSet,
    validateAgentPromptDefaultsPayload,
    validateAgentPromptSet,
} from '../../app/static/js/modules/ai-chat/agent-prompt-service.js';


const VALID_PROMPTS = Object.freeze({
    systemPrompt: 'You are the MetaList agent.',
    finalResponsePrompt: 'FINAL\n{basis}',
    toolResultPrompt: 'TOOL {action_name}\n{payload_json}',
});

const VALID_SKILL = Object.freeze({
    skillId: 'search_notes',
    title: 'Search notes',
    description: 'Generate a focused MetaList query.',
    triggerAction: 'search_notes',
    preferenceKey: 'pref.ai.skill.search_notes',
    content: 'Use positive search terms.',
});


test('validateAgentPromptSet accepts the editable runtime prompt set', () => {
    assert.deepEqual(validateAgentPromptSet(VALID_PROMPTS), VALID_PROMPTS);
});


test('validateAgentPromptDefaultsPayload converts the API field names', () => {
    assert.deepEqual(validateAgentPromptDefaultsPayload({
        system_prompt: VALID_PROMPTS.systemPrompt,
        final_response_prompt: VALID_PROMPTS.finalResponsePrompt,
        tool_result_prompt: VALID_PROMPTS.toolResultPrompt,
        skills: [{
            skill_id: VALID_SKILL.skillId,
            title: VALID_SKILL.title,
            description: VALID_SKILL.description,
            trigger_action: VALID_SKILL.triggerAction,
            preference_key: VALID_SKILL.preferenceKey,
            content: VALID_SKILL.content,
        }],
    }), {
        ...VALID_PROMPTS,
        skills: [VALID_SKILL],
    });
});


test('validateAgentInstructionSet validates editable skill content', () => {
    const instructions = {
        ...VALID_PROMPTS,
        skills: [VALID_SKILL],
    };

    assert.deepEqual(validateAgentInstructionSet(instructions), instructions);
    assert.throws(
        () => validateAgentInstructionSet({
            ...instructions,
            skills: [{ ...VALID_SKILL, content: '  ' }],
        }),
        AgentPromptValidationError,
    );
});


test('agent prompt validation rejects blank and oversized text', () => {
    assert.throws(
        () => validateAgentPromptSet({ ...VALID_PROMPTS, systemPrompt: '  ' }),
        AgentPromptValidationError,
    );
    assert.throws(
        () => validateAgentPromptSet({ ...VALID_PROMPTS, systemPrompt: 'x'.repeat(32_001) }),
        AgentPromptValidationError,
    );
});


test('final-response template requires exactly one basis placeholder', () => {
    for (const finalResponsePrompt of [
        'Missing',
        '{basis} {basis}',
        '{basis} {unknown}',
        '{basis!r}',
    ]) {
        assert.throws(
            () => validateAgentPromptSet({ ...VALID_PROMPTS, finalResponsePrompt }),
            AgentPromptValidationError,
        );
    }
});


test('tool-result template requires exactly its two supported placeholders', () => {
    for (const toolResultPrompt of [
        '{action_name}',
        '{payload_json}',
        '{action_name} {payload_json} {extra}',
        '{action_name:>10} {payload_json}',
    ]) {
        assert.throws(
            () => validateAgentPromptSet({ ...VALID_PROMPTS, toolResultPrompt }),
            AgentPromptValidationError,
        );
    }
});


test('escaped braces remain literal and do not count as placeholders', () => {
    assert.throws(
        () => validateAgentPromptSet({
            ...VALID_PROMPTS,
            finalResponsePrompt: '{{basis}}',
        }),
        /exactly one \{basis\}/,
    );
    assert.deepEqual(validateAgentPromptSet({
        ...VALID_PROMPTS,
        finalResponsePrompt: '{{literal}} {basis}',
    }).finalResponsePrompt, '{{literal}} {basis}');
});
