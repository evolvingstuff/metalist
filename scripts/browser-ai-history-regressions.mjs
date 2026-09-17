import assert from 'node:assert/strict';

export async function checkAiHistoryExport(page) {
  const empty = await page.evaluate(async () => {
    const {loadAiHistory} = await import('/static/js/modules/ai-chat/ai-chat-api.js');
    return await loadAiHistory();
  });
  assert.deepEqual(empty, []);
  const pairs = [
    [{request: {messages: [{role: 'user', content: 'First turn'}]}}, {status: 'complete', response: 'First answer'}],
    [{request: {messages: [{role: 'user', content: 'Second turn'}]}}, {status: 'error', response: 'Partial answer'}],
  ];
  const downloaded = await page.evaluate(async (recordedPairs) => {
    const {AgentDebugView} = await import('/static/js/modules/ai-chat/ai-agent-debug-view.js');
    await AgentDebugView.init();
    const originalFetch = window.fetch;
    const originalCreateUrl = URL.createObjectURL;
    const originalClick = HTMLAnchorElement.prototype.click;
    let blob;
    let filename;
    window.fetch = async (url, options) => {
      if (String(url).endsWith('/ai/history')) {
        if (options.cache !== 'no-store') throw new Error('History export must bypass caches');
        return new Response(JSON.stringify(recordedPairs), {headers: {'content-type': 'application/json'}});
      }
      return originalFetch(url, options);
    };
    URL.createObjectURL = (value) => {
      blob = value;
      return originalCreateUrl(value);
    };
    HTMLAnchorElement.prototype.click = function () { filename = this.download; };
    try {
      document.getElementById('ai-chat-export-history').click();
      for (let attempt = 0; attempt < 100 && !filename; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      if (!filename) throw new Error('Export button did not initiate a download');
      return {filename, pairs: JSON.parse(await blob.text())};
    } finally {
      window.fetch = originalFetch;
      URL.createObjectURL = originalCreateUrl;
      HTMLAnchorElement.prototype.click = originalClick;
    }
  }, pairs);
  assert.match(downloaded.filename, /^metalist-llm-history-\d+\.json$/);
  assert.deepEqual(downloaded.pairs, pairs);
  console.log('PASS session history endpoint and LLM input/output pair export button');
}
