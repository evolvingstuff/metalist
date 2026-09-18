import assert from 'node:assert/strict';

export async function checkAiPrivacyPreview(page) {
    const ids = await page.evaluate(async () => {
        const {NotesAPI} = await import('/static/js/modules/api-client.js');
        const {CommandPalette} = await import('/static/js/modules/command-palette/command-palette-controller.js');
        const {serializeCloudPrivacyPolicy} = await import('/static/js/modules/ai-chat/cloud-privacy-policy.js');
        const ids = {};
        for (const [name, tags] of [['allowed', 'shared'], ['blacklisted', 'shared private'], ['notWhitelisted', 'personal']]) {
            const note = await NotesAPI.createNote(null, '');
            await NotesAPI.saveNote(note.id, `<p>${name} privacy preview fixture</p>`, tags);
            ids[name] = note.id;
        }
        const child = await NotesAPI.createChild(ids.blacklisted, '');
        await NotesAPI.saveNote(child.id, '<p>Excluded descendant inherits privacy</p>', 'shared');
        ids.child = child.id;
        await NotesAPI.setCollapsedBulk([ids.blacklisted], false);
        await CommandPalette.applyPreference('pref.ai.cloud_privacy_policy', serializeCloudPrivacyPolicy({
            whitelistTags: ['shared'], whitelistPhrases: [], blacklistTags: ['private'], blacklistPhrases: [],
        }));
        await CommandPalette.applyPreference('pref.show_ai_chat', true);
        return ids;
    });
    await page.reload();
    await page.waitForSelector('[data-app-ready="true"]');
    for (const theme of ['light', 'dark']) {
        await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
        for (let repeat = 0; repeat < 2; repeat++) {
            await page.hover('#ai-chat-input');
            await page.waitForFunction(ids => ['blacklisted', 'notWhitelisted', 'child'].every(key =>
                document.querySelector(`[data-note-id="${ids[key]}"]`).classList.contains('cloud-ai-private-preview')), {}, ids);
            const styles = await page.evaluate(ids => Object.fromEntries(Object.entries(ids).map(([key, id]) => {
                const note = document.querySelector(`[data-note-id="${id}"]`);
                const icon = getComputedStyle(note, '::after');
                return [key, {noteFilter: getComputedStyle(note).filter,
                    contentFilter: getComputedStyle(note.querySelector(':scope > .note-content')).filter,
                    icon: icon.content,
                    childrenFilter: note.querySelector(':scope > .note-children')
                        ? getComputedStyle(note.querySelector(':scope > .note-children')).filter : 'none'}];
            })), ids);
            for (const key of ['blacklisted', 'notWhitelisted', 'child']) {
                assert.equal(styles[key].contentFilter, 'blur(4px)', `${theme}: ${key}`);
                assert.equal(styles[key].noteFilter, 'none');
                assert.equal(styles[key].childrenFilter, 'none');
                assert.equal(styles[key].icon, 'none');
            }
            assert.equal(styles.allowed.contentFilter, 'none');
            assert.equal(styles.allowed.icon, 'none');
            if (repeat === 0) await page.screenshot({path: `/tmp/metalist-ai-privacy-${theme}.png`});
            await page.mouse.move(2, 2);
            await page.waitForFunction(() => !document.querySelector('.cloud-ai-private-preview'));
            const cleared = await page.evaluate(ids => Object.values(ids).every(id => {
                const note = document.querySelector(`[data-note-id="${id}"]`);
                return getComputedStyle(note, '::after').content === 'none'
                    && getComputedStyle(note.querySelector(':scope > .note-content')).filter === 'none';
            }), ids);
            assert.equal(cleared, true);
        }
    }
    console.log('PASS privacy hover blur without lock icons for blacklist, whitelist exclusion and descendants, both themes, repeated enter/leave');
}
