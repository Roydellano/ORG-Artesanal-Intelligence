import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const { outputText } = ts.transpileModule(readFileSync(new URL('../src/microphone.ts', import.meta.url), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
});
const { checkMicrophone, microphoneError } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('microphone preflight selects the requested device and releases its tracks', async () => {
  let stopped = 0;
  const track = { label: 'USB headset', getSettings: () => ({ deviceId: 'usb' }), stop: () => stopped++ };
  const media = { getUserMedia: async constraints => {
    assert.deepEqual(constraints, { audio: { deviceId: { exact: 'usb' } } });
    return { getAudioTracks: () => [track], getTracks: () => [track] };
  } };
  assert.deepEqual(await checkMicrophone('usb', media), { deviceId: 'usb', label: 'USB headset' });
  assert.equal(stopped, 1);
});

test('missing, blocked and busy microphones give different recovery instructions', () => {
  assert.match(microphoneError(new DOMException('', 'NotFoundError')), /No microphone was found/);
  assert.match(microphoneError(new DOMException('', 'NotAllowedError')), /access is blocked/);
  assert.match(microphoneError(new DOMException('', 'NotReadableError')), /Close other apps/);
  assert.match(microphoneError(new DOMException('', 'OverconstrainedError')), /System default/);
});
