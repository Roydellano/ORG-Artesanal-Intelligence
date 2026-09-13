import { ArrowUpRight, FileSearch, ShieldCheck } from 'lucide-react';
import { money } from './money';
import './investigation-insights.css';

type RecordView = Record<string, any>;
const dispositions = [
  { label: 'Substantiated', states: ['substantiated'], color: '#b96145' },
  { label: 'Needs evidence', states: ['inconclusive', 'deferred'], color: '#bc933c' },
  { label: 'Dismissed', states: ['dismissed'], color: '#238294' },
  { label: 'In review', states: ['pending', 'investigating'], color: '#8998ac' },
];

export default function InvestigationInsights({ leads, findings, selectedId, onSelect, onEvidence }: {
  leads: RecordView[]; findings: RecordView[]; selectedId: string;
  onSelect: (id: string) => void; onEvidence: (ref: string) => void;
}) {
  const groups = dispositions.map(group => ({ ...group, count: leads.filter(lead => group.states.includes(lead.state)).length }));
  const other = leads.length - groups.reduce((sum, group) => sum + group.count, 0);
  const segments = other ? [...groups, { label: 'Other', states: [], color: '#c6cbc8', count: other }] : groups;
  let offset = 0;
  const selected = findings.find(f => f.id === selectedId) ?? findings[0];
  const calc = selected?.calculation;
  const rows = selected?.rule === 'excess-settlement-v1' ? [
    { label: 'Allocated payments', value: calc?.payments_centavos, tone: 'paid' },
    { label: 'Refunds returned', value: calc?.refunds_centavos, tone: 'refund' },
    { label: 'Recorded obligation', value: calc?.obligation_centavos, tone: 'obligation' },
    { label: 'Verified excess', value: selected.amount_centavos, tone: 'excess' },
  ] : [];
  // Integer arithmetic for monetary comparisons; only the final drawing percentage is a number.
  const cents = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) ? BigInt(value) : typeof value === 'string' && /^\d+$/.test(value) ? BigInt(value) : null;
  const maximum = rows.reduce((max, row) => { const value = cents(row.value); return value !== null && value > max ? value : max; }, 0n);
  return <div className="insights">
    <section className="insight-overview panel">
      <div className="insight-intro"><span className="tiny-label">EVIDENCE AT A GLANCE</span><h2>Where the records disagree.</h2><p>Follow a verified discrepancy from the amount to the records that support it.</p><div className="insight-counts"><span><b>{findings.length}</b> verified findings</span><span><b>{leads.length}</b> leads examined or queued</span></div></div>
      <div className="disposition-chart">
        <svg viewBox="0 0 120 120" role="img" aria-label={`Lead dispositions: ${segments.map(g => `${g.count} ${g.label}`).join(', ')}`}>
          <circle cx="60" cy="60" r="46" fill="none" stroke="#e2edf2" strokeWidth="12" />
          {segments.map(group => { const portion = leads.length ? group.count / leads.length * 100 : 0; const start = offset; offset += portion; return <circle key={group.label} cx="60" cy="60" r="46" fill="none" stroke={group.color} strokeWidth="12" pathLength="100" strokeDasharray={`${portion} ${100 - portion}`} strokeDashoffset={-start} transform="rotate(-90 60 60)"><title>{group.label}: {group.count}</title></circle>; })}
          <text x="60" y="59" textAnchor="middle" className="ring-number">{leads.length}</text><text x="60" y="76" textAnchor="middle" className="ring-label">LEADS</text>
        </svg>
        <div className="disposition-legend">{segments.map(group => <div key={group.label}><i style={{ background: group.color }} /><span>{group.label}</span><b>{group.count}</b></div>)}</div>
      </div>
    </section>
    <section className="panel discrepancy-panel">
      <div className="panel-title"><h2>Discrepancy explorer</h2><span className="small-label">VERIFIED FINDINGS ONLY</span></div>
      {selected ? <div className="discrepancy-layout">
        <div className="finding-picker" aria-label="Choose a discrepancy">{findings.map((finding, index) => <button key={finding.id} aria-pressed={selected.id === finding.id} className={selected.id === finding.id ? 'selected' : ''} onClick={() => onSelect(finding.id)}><span className="finding-index">{String(index + 1).padStart(2, '0')}</span><span><b>{finding.title}</b><small>{finding.supplier_name || finding.invoice_id || finding.id}</small><strong>{money(finding.amount_centavos, finding.currency)}</strong></span><ArrowUpRight size={16}/></button>)}</div>
        <article className="discrepancy-detail">
          <div className="discrepancy-heading"><span><ShieldCheck size={14}/> Evidence validated</span><small>{selected.id}</small></div>
          <h3>{selected.title}</h3><p>{selected.claim}</p>
          {rows.length > 0 && <div className="reconciliation-chart" aria-label="Payment reconciliation">{rows.map(row => { const value = cents(row.value); const width = maximum > 0n && value !== null && value > 0n ? Number(value * 10000n / maximum) / 100 : 0; return <div className={`reconciliation-row ${row.tone}`} key={row.label}><div><span>{row.label}</span><b>{money(row.value, selected.currency)}</b></div><div className="amount-track"><span style={{ width: `${width}%` }}/></div></div>; })}</div>}
          <div className="insight-formula"><span className="tiny-label">EXACT CALCULATION · CENTAVOS</span><code>{calc?.calculation || 'No calculation provided.'}</code><small>{String(selected.amount_type || 'Supported amount').replaceAll('_', ' ')} · Amounts across findings are not additive.</small></div>
          <div className="insight-evidence">{(selected.evidence || []).map((ref: string) => <button key={ref} onClick={() => onEvidence(ref)}><FileSearch size={13}/>{ref}</button>)}</div>
          {!!selected.alternatives?.length && <details className="insight-alternatives"><summary>Alternative explanations checked ({selected.alternatives.length})</summary><ul>{selected.alternatives.map((item: string, i: number) => <li key={i}>{item}</li>)}</ul></details>}
        </article>
      </div> : <div className="insight-empty"><FileSearch size={28}/><div><h3>No verified discrepancy yet</h3><p>Leads stay separate until the evidence and calculation pass validation. Check the lead register for pending or unresolved questions.</p></div></div>}
    </section>
  </div>;
}
