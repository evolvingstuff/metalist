import assert from 'node:assert/strict';
import test from 'node:test';

import {
    selectNamespacePortsEditorProfile,
} from '../../app/static/js/modules/modals/namespace-ports-profile.js';


test('namespace ports editor shows the saved next-launch profile for the running namespace', () => {
    const profile = selectNamespacePortsEditorProfile({
        saved_profile: {
            namespace: 'recovered',
            port: 9000,
            https_port: 9443,
        },
        default_profile: {
            namespace: 'recovered',
            port: 9100,
            https_port: 9543,
        },
    });

    assert.deepEqual(profile, {
        namespace: 'recovered',
        port: 9000,
        https_port: 9443,
    });
});


test('namespace ports editor uses suggested defaults when no profile has been saved', () => {
    const profile = selectNamespacePortsEditorProfile({
        saved_profile: null,
        default_profile: {
            namespace: 'new-namespace',
            port: 8002,
            https_port: 8445,
        },
    });

    assert.deepEqual(profile, {
        namespace: 'new-namespace',
        port: 8002,
        https_port: 8445,
    });
});
