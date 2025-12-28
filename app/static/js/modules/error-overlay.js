let installed = false;

function ensureOverlay() {
  let overlay = document.getElementById('fatal-error-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'fatal-error-overlay';
    Object.assign(overlay.style, {
      position: 'fixed',
      top: '0',
      left: '0',
      right: '0',
      background: '#8b0000',
      color: '#fff',
      padding: '10px 14px',
      fontFamily: 'monospace',
      fontSize: '13px',
      zIndex: '10000',
      whiteSpace: 'pre-wrap',
      borderBottom: '2px solid #550000',
      maxHeight: '40vh',
      overflowY: 'auto',
    });
    document.body.appendChild(overlay);
  }
  return overlay;
}

export function showFatalError(message, details) {
  const overlay = ensureOverlay();
  const time = new Date().toISOString();
  const lines = [
    `[${time}] FATAL: ${String(message)}`,
    details ? String(details) : '',
  ].filter(Boolean);
  overlay.textContent = lines.join('\n');
}

export function installGlobalErrorOverlay() {
  if (installed) return;
  installed = true;

  window.addEventListener('error', (event) => {
    const msg = event?.error?.message || event?.message || 'Uncaught error';
    const stack = event?.error?.stack || '';
    showFatalError(msg, stack);
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event?.reason;
    const msg = (reason && (reason.message || String(reason))) || 'Unhandled promise rejection';
    const stack = reason && reason.stack ? reason.stack : '';
    showFatalError(msg, stack);
  });
}

