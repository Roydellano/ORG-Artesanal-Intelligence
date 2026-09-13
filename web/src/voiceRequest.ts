export async function voiceRequest(base: string, path: '/voice/session' | '/voice/ask',
  signal: AbortSignal, body?: unknown) {
  const response = await fetch(`/api${base}${path}`, {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let result;
  try {
    result = JSON.parse(text);
  } catch {
    throw new Error(`Voice API returned ${text.trim() ? 'an invalid' : 'an empty'} response (HTTP ${response.status}). Check that the backend is running and refresh the page.`);
  }
  if (!response.ok) throw new Error(typeof result?.detail === 'string' ? result.detail : `Voice request failed (HTTP ${response.status}).`);
  if (!result || typeof result !== 'object') throw new Error('Voice API returned an invalid response.');
  if (path === '/voice/session' && (typeof result.conversation_token !== 'string' || !result.conversation_token.trim() ||
      !Number.isFinite(result.max_seconds) || result.max_seconds <= 0))
    throw new Error('Voice API returned an incomplete session. Check the backend version.');
  return result;
}
