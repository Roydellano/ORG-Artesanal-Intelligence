import { useEffect, useRef, useState } from 'react';
import type { Conversation } from '@elevenlabs/client';
import { Mic, Square } from 'lucide-react';
import './auditor-voice.css';
import { voiceRequest } from './voiceRequest';
import { checkMicrophone, microphoneError } from './microphone';

type Answer = { answer: string; evidence: string[]; mode: string; case_status: string };

export default function AuditorVoice({ base, synthetic, onAnswer }: {
  base: string; synthetic: boolean; onAnswer: (question: string, answer: Answer) => void;
}) {
  const [status, setStatus] = useState('disconnected');
  const [mode, setMode] = useState('listening');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState('');
  const [micStatus, setMicStatus] = useState('');
  const [testingMic, setTestingMic] = useState(false);
  const [transcript, setTranscript] = useState<{ role: string; message: string }[]>([]);
  const conversation = useRef<Conversation | null>(null);
  const epoch = useRef(0);
  const active = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const requests = useRef(new Set<AbortController>());
  const callback = useRef(onAnswer);
  callback.current = onAnswer;

  function stop() {
    epoch.current++;
    active.current = false;
    clearTimeout(timer.current);
    requests.current.forEach(c => c.abort());
    requests.current.clear();
    const current = conversation.current;
    conversation.current = null;
    if (current) void current.endSession().catch(() => {});
    setStatus('disconnected');
    setChecking(false);
  }
  useEffect(() => () => { stop(); }, [base]);
  useEffect(() => {
    let disposed = false;
    const media = navigator.mediaDevices;
    async function refresh() {
      try {
        const list = await media?.enumerateDevices();
        if (!disposed) setDevices((list || []).filter(d => d.kind === 'audioinput'));
      } catch { /* The explicit microphone check provides the recovery message. */ }
    }
    void refresh();
    media?.addEventListener('devicechange', refresh);
    return () => { disposed = true; media?.removeEventListener('devicechange', refresh); };
  }, []);

  async function testMicrophone() {
    setTestingMic(true); setError(''); setMicStatus('Checking microphone…');
    try {
      const mic = await checkMicrophone(deviceId);
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'audioinput'));
      setMicStatus(`Ready: ${mic.label}`);
    } catch (e) { setMicStatus(''); setError(microphoneError(e)); }
    finally { setTestingMic(false); }
  }

  async function start() {
    if (active.current || !synthetic) return;
    active.current = true;
    const attempt = ++epoch.current;
    const current = () => epoch.current === attempt;
    setError(''); setTranscript([]); setStatus('connecting');
    timer.current = setTimeout(() => {
      if (current()) { stop(); setError('Voice connection timed out. Check microphone permission and retry.'); }
    }, 30000);
    let calls = 0;
    let toolBusy = false;
    async function post(path: '/voice/session' | '/voice/ask', body?: unknown) {
      const controller = new AbortController();
      requests.current.add(controller);
      const timeout = setTimeout(() => controller.abort(), 65000);
      try {
        return await voiceRequest(base, path, controller.signal, body);
      } finally { clearTimeout(timeout); requests.current.delete(controller); }
    }
    try {
      const mic = await checkMicrophone(deviceId);
      if (!current()) return;
      setMicStatus(`Ready: ${mic.label}`);
      const session = await post('/voice/session');
      if (!current()) return;
      const { Conversation } = await import('@elevenlabs/client');
      if (!current()) return;
      const connected = await Conversation.startSession({
        signedUrl: session.signed_url, connectionType: 'websocket',
        inputDeviceId: mic.deviceId || undefined,
        onConnect: () => { if (current()) setStatus('connected'); },
        onDisconnect: details => {
          if (current()) {
            stop();
            if (details.reason === 'error') setError('Voice disconnected. Check ElevenLabs credits and connection, then retry.');
          }
        },
        onError: () => { if (current()) { stop(); setError('Voice failed. Check microphone permission, ElevenLabs configuration and credits.'); } },
        onModeChange: ({ mode }) => { if (current()) setMode(mode); },
        onMessage: ({ role, message }) => {
          if (current()) setTranscript(previous => [...previous, { role, message }].slice(-12));
        },
        clientTools: {
          ask_auditor: async (parameters: { question?: unknown }) => {
            if (!current()) return 'Session ended. Do not answer.';
            if (toolBusy) return 'The auditor is already reviewing a question. Wait for that result.';
            if (++calls > 8) return 'This demo reached its eight-question limit. End voice and start a new session.';
            const question = parameters?.question;
            if (typeof question !== 'string' || !question.trim() || question.length > 1000)
              return 'Ask a question of between 1 and 1000 characters.';
            toolBusy = true; setChecking(true);
            try {
              const result: Answer = await post('/voice/ask', { question });
              if (!current()) return 'Session ended. Do not answer.';
              callback.current(question, result);
              return JSON.stringify({ answer: result.answer, evidence: result.evidence, case_status: result.case_status });
            } catch (e) {
              if (current()) setError(e instanceof Error ? e.message : 'The auditor could not answer.');
              return 'The auditor could not answer. Tell the user to check the error on screen. Do not invent a response.';
            } finally { toolBusy = false; if (current()) setChecking(false); }
          },
        },
      });
      if (!current()) { await connected.endSession(); return; }
      conversation.current = connected;
      clearTimeout(timer.current);
      timer.current = setTimeout(stop, Math.min(session.max_seconds, 180) * 1000);
    } catch (e) {
      if (current()) { stop(); setError('Unable to start voice. ' + microphoneError(e)); }
    }
  }

  const connected = status !== 'disconnected';
  return <section className="auditor-voice" aria-label="Real-time voice auditor">
    <div className="voice-controls">
      <label>Microphone <select aria-label="Microphone" value={deviceId} disabled={connected || testingMic}
        onChange={e => { setDeviceId(e.target.value); setMicStatus(''); }}>
        <option value="">System default</option>
        {devices.filter(d => d.deviceId && d.deviceId !== 'default').map((d, i) =>
          <option key={d.deviceId} value={d.deviceId}>{d.label || `Microphone ${i + 1}`}</option>)}
      </select></label>
      <button type="button" disabled={connected || testingMic} onClick={testMicrophone}>Check microphone</button>
      {micStatus && <span role="status">{micStatus}</span>}
    </div>
    <div className="voice-controls">
      <button type="button" disabled={!synthetic || testingMic} onClick={connected ? stop : start}>
        {connected ? <Square size={16}/> : <Mic size={16}/>}
        {connected ? 'End voice' : 'Start voice'}
      </button>
      <span role="status">{status === 'connecting' ? 'Connecting…' : connected
        ? checking ? 'Reviewing case…' : mode === 'speaking' ? 'Auditor speaking — you can interrupt' : 'Listening…'
        : 'ElevenLabs · live voice'}</span>
    </div>
    <p>{synthetic ? 'Starting voice sends microphone audio to ElevenLabs. Use fictional case questions only. Sessions end after 3 minutes.'
      : 'Voice is available for app-generated fictional demos. Uploaded records remain in text chat.'}</p>
    {error && <p role="alert" className="voice-error">{error}</p>}
    {transcript.length > 0 && <details open><summary>Live conversation</summary><div className="voice-transcript" aria-live="polite">
      {transcript.map((line, i) => <p key={i}><strong>{line.role === 'user' ? 'You' : 'Voice auditor'}: </strong>{line.message}</p>)}
    </div><small>Voice paraphrases may differ. The cited auditor answers appear below.</small></details>}
  </section>;
}
