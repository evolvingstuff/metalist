const actionButton = document.getElementById('locked-action');

if (actionButton) {
    actionButton.addEventListener('click', () => {
        window.location.href = '/';
    });
}

// Safety: ensure we don't stay stranded on the locked page due to missing DOM.
setTimeout(() => {
    if (!actionButton) {
        window.location.href = '/';
    }
}, 5000);
