import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const { outputText } = ts.transpileModule(readFileSync(new URL('../src/voiceRequest.ts', import.meta.url), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
});
const { voiceRequest } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('voice session and case questions use the API prefix', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push([url, options]);
    return Response.json({ signed_url: 'wss://api.elevenlabs.io/test', max_seconds: 180 });
  });
  const signal = new AbortController().signal;
  await voiceRequest('/datasets/demo', '/voice/session', signal);
  await voiceRequest('/datasets/demo', '/voice/ask', signal, { question: 'Why?' });
  assert.equal(calls[0][0], '/api/datasets/demo/voice/session');
  assert.equal(calls[1][0], '/api/datasets/demo/voice/ask');
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].body, '{"question":"Why?"}');
  assert.equal(calls[0][1].signal, signal);
});

test('empty responses and API errors have actionable messages', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 404 }));
  const ask = () => voiceRequest('/datasets/demo', '/voice/session', new AbortController().signal);
  await assert.rejects(ask, /empty response \(HTTP 404\)/);
  fetch.mock.mockImplementation(async () => Response.json({ detail: 'Dataset session expired' }, { status: 404 }));
  await assert.rejects(ask, /Dataset session expired/);
  fetch.mock.mockImplementation(async () => Response.json({}));
  await assert.rejects(ask, /incomplete session/);
});
