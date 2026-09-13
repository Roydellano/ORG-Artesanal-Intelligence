import { useEffect, useState } from 'react';

async function call(path: string, options?: RequestInit) {
  const response = await fetch(`/api/integrity${path}`, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || 'Integrity request failed');
  return body;
}

export default function IntegrityPanel({ kind, identity, running = false }: {
  kind: 'datasets' | 'estates'; identity: string; running?: boolean;
}) {
  const [state, setState] = useState<Record<string, any>>({ status: 'not_anchored' });
  const [config, setConfig] = useState<Record<string, any>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploaded, setUploaded] = useState('');
  const base = `/${kind}/${identity}`;
  useEffect(() => {
    let disposed = false;
    setState({ status: 'not_anchored' }); setError(''); setUploaded('');
    const refresh = async () => {
      try {
        const [next, configuration] = await Promise.all([call(base), call('/config')]);
        if (!disposed) { setState(next); setConfig(configuration); }
      } catch (e) { if (!disposed) setError(String(e)); }
    };
    void refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [base]);
  async function action(name: string) {
    setBusy(true); setError('');
    try { setState(await call(`${base}/${name}`, { method: 'POST' })); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  const pending = ['anchoring', 'submitted'].includes(state.status);
  return <section className="panel" style={{ padding: 20, margin: '16px 0' }}>
    <h3>Case integrity · Solana Devnet</h3>
    <p>Seal a frozen masked report and its source fingerprint. Only a randomized commitment is published. Integrity does not establish that records or findings are true. Devnet is a test network and may reset.</p>
    <p role="status"><b>{state.status.replaceAll('_', ' ')}</b>{state.message ? ` · ${state.message}` : ''}</p>
    {state.current_report_matches === false && <p role="alert">The current report differs from the sealed snapshot. The downloaded bundle retains the original snapshot.</p>}
    {config.signer && <details><summary>Auditor wallet</summary><code style={{ overflowWrap: 'anywhere' }}>{config.signer}</code></details>}
    {!config.configured && <p>Devnet wallet setup required: <code>python -m tools.setup_solana --airdrop</code></p>}
    <div className="export-actions">
      <button className="secondary" disabled={busy || running || pending || !config.configured || !['not_anchored', 'failed'].includes(state.status)} onClick={() => action('anchor')}>Seal on Devnet</button>
      <button className="secondary" disabled={busy || running || !state.proof?.signature} onClick={() => action('verify')}>Verify integrity</button>
      {state.proof?.signature && <>
        <a className="secondary" href={`/api/integrity${base}/bundle`}>Download proof bundle</a>
        <a className="secondary" href={`https://explorer.solana.com/tx/${encodeURIComponent(state.proof.signature)}?cluster=devnet`} target="_blank" rel="noreferrer">View transaction</a>
      </>}
    </div>
    <p><small>The bundle contains the masked report and private verification nonce. Keep it with your case exports; session deletion removes the local receipt. Later case changes do not update this seal.</small></p>
    <label>Verify a downloaded proof bundle <input type="file" accept=".json" disabled={busy} onChange={async e => {
      const file = e.target.files?.[0]; e.target.value = ''; if (!file) return;
      setBusy(true); setError(''); setUploaded('');
      try {
        const form = new FormData(); form.append('file', file);
        const result = await call('/verify', { method: 'POST', body: form });
        setUploaded(`${result.status}: ${result.message}`);
      } catch (error) { setError(String(error)); }
      finally { setBusy(false); }
    }}/></label>
    {uploaded && <p role="status">{uploaded}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
