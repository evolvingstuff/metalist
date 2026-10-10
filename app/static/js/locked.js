const actionButton = document.getElementById('locked-action');
const lockedPanel = document.getElementById('locked-panel');

// The heading and button fade out before the login page opens (its fields then
// fade in under the same logo), rather than vanishing at once.
const LEAVE_FADE_MS = 200;

function leaveTo(url) {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion || !lockedPanel) {
        window.location.href = url;
        return;
    }
    lockedPanel.dataset.leaving = 'true';
    window.setTimeout(() => {
        window.location.href = url;
    }, LEAVE_FADE_MS);
}

if (actionButton) {
    actionButton.addEventListener('click', () => {
        // Go to Login opens the login screen straight away (no white page in between).
        if (actionButton.dataset.target === 'login') {
            leaveTo('/?force_reauth=1');
            return;
        }
        leaveTo('/');
    });
}

// Safety: ensure we don't stay stranded on the locked page due to missing DOM.
setTimeout(() => {
    if (!actionButton) {
        window.location.href = '/';
    }
}, 5000);
