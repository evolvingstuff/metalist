import assert from 'node:assert/strict';
import test from 'node:test';

import {
    cloudPrivacyPolicyToTextFields,
    emptyCloudPrivacyPolicy,
    parseCloudPrivacyTextFields,
    readCloudPrivacyPolicy,
    serializeCloudPrivacyPolicy,
} from '../../app/static/js/modules/ai-chat/cloud-privacy-policy.js';


test('cloud privacy policy round trips canonical namespace preference JSON', () => {
    const policy = {
        whitelistTags: ['project-one', 'project-two'],
        whitelistPhrases: ['allowed phrase'],
        blacklistTags: ['private'],
        blacklistPhrases: ['secret phrase'],
    };
    const serialized = serializeCloudPrivacyPolicy(policy);

    assert.equal(
        serialized,
        '{"blacklist_phrases":["secret phrase"],"blacklist_tags":["private"],'
            + '"whitelist_phrases":["allowed phrase"],'
            + '"whitelist_tags":["project-one","project-two"]}',
    );
    assert.deepEqual(readCloudPrivacyPolicy(() => serialized), policy);
});


test('cloud privacy text fields ignore blank lines and preserve ordered entries', () => {
    const policy = parseCloudPrivacyTextFields({
        whitelistTagsText: 'project-one\n\n project-two ',
        whitelistPhrasesText: '',
        blacklistTagsText: 'private',
        blacklistPhrasesText: 'secret phrase\n',
    });

    assert.deepEqual(policy, {
        whitelistTags: ['project-one', 'project-two'],
        whitelistPhrases: [],
        blacklistTags: ['private'],
        blacklistPhrases: ['secret phrase'],
    });
    assert.deepEqual(
        cloudPrivacyPolicyToTextFields(policy),
        {
            whitelistTagsText: 'project-one\nproject-two',
            whitelistPhrasesText: '',
            blacklistTagsText: 'private',
            blacklistPhrasesText: 'secret phrase',
        },
    );
});


test('cloud privacy policy defaults empty and rejects duplicate or illegal tags', () => {
    assert.deepEqual(readCloudPrivacyPolicy(() => null), emptyCloudPrivacyPolicy());
    assert.throws(
        () => parseCloudPrivacyTextFields({
            whitelistTagsText: '',
            whitelistPhrasesText: '',
            blacklistTagsText: 'private\nPRIVATE',
            blacklistPhrasesText: '',
        }),
        /duplicate entry/u,
    );
    assert.throws(
        () => parseCloudPrivacyTextFields({
            whitelistTagsText: 'bad tag',
            whitelistPhrasesText: '',
            blacklistTagsText: '',
            blacklistPhrasesText: '',
        }),
        /invalid MetaList tag/u,
    );
});
