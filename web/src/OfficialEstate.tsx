import { useEffect, useRef, useState } from 'react';

type Json = Record<string, any>;
async function call(path: string, init?: RequestInit) {
  const response = await fetch('/api/estates' + path, init);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || 'Estate request failed');
  return body;
}

export default function OfficialEstate() {
  const [seed, setSeed] = useState('2026');
  const [company, setCompany] = useState('');
  const [mode, setMode] = useState('offline');
  const [rate, setRate] = useState('');
  const [fxSource, setFxSource] = useState('');
  const [sid, setSid] = useState('');
  const [coverage, setCoverage] = useState<Json>({});
  const [caseFile, setCase] = useState<Json>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<Json | null>(null);
  const [source, setSource] = useState<Json | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    if (!sid) return;
    let disposed = false;
    const refresh = async () => {
      try {
        const result = await call(`/${sid}/case?reveal=${reveal}`);
        if (!disposed) setCase(result);
      } catch (e) { if (!disposed) setError(String(e)); }
    };
    refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [sid, reveal]);
  async function upload(file: File | undefined, replay = false) {
    if (!file) return;
    if (!replay && (!company.trim() || !/^\d+$/.test(seed))) {
      setError('Enter the estate seed and audited company RFC before uploading.'); return;
    }
    setBusy(true); setError(''); setAnswer(null); setSource(null);
    try {
      if (sid) await call(`/${sid}`, { method: 'DELETE' });
      setSid(''); setCase({});
      const form = new FormData(); form.append('file', file);
      const result = await call(replay ? '/replay' : `/upload?seed=${encodeURIComponent(seed)}&company_rfc=${encodeURIComponent(company.trim())}`, { method: 'POST', body: form });
      setCoverage(result.coverage); setSid(result.session_id); setCase({ status: result.status }); setReveal(false);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  async function action(name: string) {
    setError(''); setBusy(true);
    try {
      const params = name === 'run' ? `?mode=${mode}&usd_mxn_rate=${encodeURIComponent(rate)}&fx_source=${encodeURIComponent(fxSource)}` : '';
      await call(`/${sid}/${name}${params}`, { method: 'POST' });
      setCase(await call(`/${sid}/case?reveal=${reveal}`));
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  const running = caseFile.status === 'running';
  const complete = Array.isArray(caseFile.findings);
  const url = (kind: string, original = reveal) => `/api/estates/${sid}/export/${kind}?reveal=${original}`;
  return <section className="official-estate">
    <h2>Judge estate · official SQLite format</h2>
    <p>Upload the eight-table estate from the student materials. Choose deterministic offline review or masked AI tool scheduling. Saved cases replay without a network call.</p>
    <div className="official-controls">
      <label>Estate seed <input aria-label="Official estate seed" value={seed} onChange={e => setSeed(e.target.value)} disabled={busy || running}/></label>
      <label>Audited company RFC <input aria-label="Audited company RFC" value={company} placeholder="RFC from your estate" onChange={e => setCompany(e.target.value)} disabled={busy || running}/></label>
      <label>Review mode <select aria-label="Official review mode" value={mode} onChange={e => setMode(e.target.value)} disabled={busy || running}><option value="offline">Offline evidence review</option><option value="ai">AI · eligible non-free model</option></select></label>
      {mode === 'ai' && <><label>USD/MXN rate <input value={rate} onChange={e => setRate(e.target.value)} placeholder="Supplied rate"/></label><label>Rate source/date <input value={fxSource} onChange={e => setFxSource(e.target.value)} placeholder="Source and quoted date"/></label><small>Uses your configured eligible model. Uploaded estates cannot use the free endpoint. Provider usage cost and your supplied exchange rate determine MXN cost.</small></>}
      <label className="official-upload">Upload estate .db <input aria-label="Upload official SQLite estate" type="file" accept=".db,.sqlite,.sqlite3" disabled={busy || running} onChange={e => { upload(e.target.files?.[0]); e.target.value = ''; }}/></label>
      <label className="official-upload">Replay completed run <input aria-label="Upload completed replay" type="file" accept=".zip" disabled={busy || running} onChange={e => { upload(e.target.files?.[0], true); e.target.value = ''; }}/></label>
    </div>
    {error && <p role="alert">{error}</p>}
    {sid && <>
      <p><b>{caseFile.status}</b> · {Object.entries(coverage).map(([table, count]) => `${table}: ${count}`).join(' · ')}</p>
      <div className="official-controls">
        <button disabled={busy || running || complete} onClick={() => action('run')}>Investigate estate</button>
        {running && <button onClick={() => action('cancel')}>Cancel investigation</button>}
        <button disabled={busy} onClick={async () => { try { await call(`/${sid}`, { method: 'DELETE' }); setSid(''); setCase({}); setSource(null); } catch (e) { setError(String(e)); } }}>Delete estate session</button>
        <label><input type="checkbox" checked={reveal} onChange={e => { generation.current++; setReveal(e.target.checked); setAnswer(null); setSource(null); }}/> Reveal original identities locally</label>
      </div>
      {complete && <>
        <p>{caseFile.findings.length} supported findings · {caseFile.leads_not_pursued.length} declined leads · {caseFile.run_metadata.llm_calls} model calls · MXN {caseFile.run_metadata.mxn_cost ?? 'unavailable'} cost · {caseFile.run_metadata.wall_clock_seconds}s</p>
        <div className="official-controls">
          <a href={url('html')} target="_blank" rel="noreferrer">Open standalone case file</a>
          <a href={url('json')}>Download {reveal ? 'official judge' : 'masked'} JSON</a>
          {reveal && <a href={url('replay', true)}>Save original estate + offline replay</a>}
        </div>
        <p><small>The judge JSON and replay require original identities. Enable local reveal to export them. Masked JSON uses aliases and will not resolve against the original estate.</small></p>
        <iframe title="Official forensic case file" sandbox="allow-same-origin" src={url('html')}/>
        {reveal && <details><summary>Inspect original finding exhibits</summary>
          {caseFile.findings.flatMap((f: Json) => f.exhibits).map((ex: Json) => <button key={ex.exhibit_id} onClick={async () => {
            const current = generation.current;
            try { const result = await call(`/${sid}/evidence/${ex.source_table}/${encodeURIComponent(ex.record_id)}?reveal=true`); if (current === generation.current) setSource(result); }
            catch (e) { setError(String(e)); }
          }}>{ex.exhibit_id} · {ex.source_table}</button>)}
          {source && <pre>{JSON.stringify(source, null, 2)}</pre>}
        </details>}
        <form onSubmit={async e => { e.preventDefault(); setError(''); const current = generation.current;
          try { const result = await call(`/${sid}/ask?reveal=${reveal}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) }); if (current === generation.current) setAnswer(result); }
          catch (err) { setError(String(err)); }
        }}><label>Ask the saved case <input aria-label="Ask official case" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Why was L0004 declined?" required maxLength={1000}/></label><button>Ask auditor</button></form>
        {answer && <div role="status"><p>{answer.answer}</p><small>{answer.evidence.join(' · ')}</small></div>}
      </>}
    </>}
  </section>;
}
