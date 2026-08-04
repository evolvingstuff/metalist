function escapeHtml(value) {
    if (typeof value !== 'string') {
        throw new Error('escapeHtml requires string');
    }
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}


export function buildNamespaceLoadingPageHtml(namespace) {
    if (typeof namespace !== 'string' || namespace.trim().length === 0) {
        throw new Error('buildNamespaceLoadingPageHtml requires namespace');
    }
    const normalizedNamespace = namespace.trim();
    const escapedNamespace = escapeHtml(normalizedNamespace);
    const escapedTitle = escapeHtml(`Loading namespace ${normalizedNamespace}...`);
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapedTitle}</title>
    <style>
        :root {
            color-scheme: dark;
        }
        html, body {
            cursor: wait !important;
        }
        body, body * {
            cursor: wait !important;
        }
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            background:
                radial-gradient(circle at top, rgba(37, 99, 235, 0.22), transparent 38%),
                linear-gradient(160deg, #06070a 0%, #10141d 55%, #0b1220 100%);
            color: #f5f7fb;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        }
        .namespace-loading-shell {
            width: min(560px, calc(100vw - 48px));
            padding: 32px 28px;
            border-radius: 18px;
            background: rgba(8, 12, 20, 0.86);
            border: 1px solid rgba(148, 163, 184, 0.24);
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.48);
        }
        .namespace-loading-label {
            margin: 0 0 14px;
            color: #8ea4c7;
            font-size: 12px;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }
        .namespace-loading-title {
            margin: 0;
            font-size: clamp(30px, 6vw, 42px);
            line-height: 1.05;
        }
        .namespace-loading-namespace {
            display: inline-block;
            margin-top: 10px;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(37, 99, 235, 0.16);
            color: #b7ceff;
            font-size: 15px;
        }
        .namespace-loading-copy {
            margin: 20px 0 0;
            color: #d3deef;
            line-height: 1.6;
            font-size: 15px;
        }
        .namespace-loading-progress {
            margin-top: 28px;
            height: 10px;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.18);
            overflow: hidden;
        }
        .namespace-loading-progress::before {
            content: "";
            display: block;
            width: 38%;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #60a5fa 0%, #2563eb 100%);
            animation: namespace-loading-slide 1.2s ease-in-out infinite;
        }
        .namespace-loading-hint {
            margin: 14px 0 0;
            color: #8ea4c7;
            font-size: 13px;
        }
        @keyframes namespace-loading-slide {
            0% { transform: translateX(-110%); }
            100% { transform: translateX(330%); }
        }
    </style>
</head>
<body>
    <main class="namespace-loading-shell">
        <p class="namespace-loading-label">MetaList Namespace</p>
        <h1 class="namespace-loading-title">Loading namespace</h1>
        <div class="namespace-loading-namespace">${escapedNamespace}</div>
        <p class="namespace-loading-copy">
            Starting the MetaList process and waiting for it to become ready.
            This tab will redirect automatically as soon as the namespace responds.
        </p>
        <div class="namespace-loading-progress" aria-hidden="true"></div>
        <p class="namespace-loading-hint">You can leave this tab open while the namespace boots.</p>
    </main>
</body>
</html>`;
}


export function renderNamespaceLoadingTab(pendingTab, namespace) {
    if (!pendingTab || typeof pendingTab !== 'object' || pendingTab.closed) {
        throw new Error('renderNamespaceLoadingTab requires an open pending tab');
    }
    if (!pendingTab.document || typeof pendingTab.document.open !== 'function') {
        throw new Error('renderNamespaceLoadingTab requires pending tab document');
    }
    const loadingHtml = buildNamespaceLoadingPageHtml(namespace);
    pendingTab.document.open();
    pendingTab.document.write(loadingHtml);
    pendingTab.document.close();
}
