import { useEffect, useRef, useState } from "react";
import { money } from "./money";
import AuditorMarkdown from "./AuditorMarkdown";
import AuditorVoice from "./AuditorVoice";
import IntegrityPanel from "./IntegrityPanel";
import InvestigationInsights from "./InvestigationInsights";
import traceBlockLogo from "./assets/TraceBlock.png";
import traceBlockCompact from "./assets/TraceBlockCompact.png";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  CircleHelp,
  Clock,
  Database,
  FileCheck2,
  Fingerprint,
  FolderOpen,
  GitBranch,
  History,
  LayoutDashboard,
  LoaderCircle,
  Play,
  RotateCw,
  Search,
  Send,
  ShieldCheck,
  Square,
  Upload,
  X,
  Zap,
} from "lucide-react";

type Json = Record<string, any>;
type Dataset = {
  session_id: string;
  dataset_id: string;
  coverage: Record<string, number>;
  warnings: string[];
  files: string[];
  synthetic?: boolean;
  kind?: "official";
};
type Case = {
  status: string;
  mode: string;
  leads: Json[];
  findings: Json[];
  totals: Record<string, number>;
  timeline: Json[];
  limitations: string[];
  completion_reason?: string;
  error_type?: string;
  can_resume?: boolean;
  recovery?: string;
  elapsed_seconds: number;
  model_calls: number;
  totals_by_category?: Record<string, Record<string, number>>;
  total_definition?: string;
  discovery?: Json;
};
type View =
  | "Overview"
  | "Investigation"
  | "Case file"
  | "Source records"
  | "Ask the auditor"
  | "Saved analyses";
const nav: [View, typeof Search][] = [
  ["Overview", LayoutDashboard],
  ["Investigation", GitBranch],
  ["Case file", FileCheck2],
  ["Source records", Database],
  ["Ask the auditor", CircleHelp],
  ["Saved analyses", History],
];
const toolNames: Record<string, string> = {
  lookup_supplier: "Linked supplier & ownership",
  reconcile: "Reconciled invoice and payments",
  check_support: "Inspected delivery records",
  trace_funds: "Traced observed transfers",
  test_alternative: "Tested benign explanations",
  conclude: "Recorded a disposition",
  answer_question: "Answered from the case",
};
const active = (c: Case | null) =>
  c && ["queued", "running"].includes(c.status);
async function request(path: string, options?: RequestInit) {
  const response = await fetch(`/api${path}`, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Request failed. Check the API connection and input format.",
    );
  return body;
}
const post = (path: string, data: Json = {}) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
function Badge({ value }: { value: string }) {
  return <span className={`badge ${value}`}>{value.replaceAll("_", " ")}</span>;
}

function MoneyGraph({
  entries,
  onEvidence,
  highlightedEvidence = [],
}: {
  entries: Json[];
  onEvidence: (ref: string) => void;
  highlightedEvidence?: string[];
}) {
  const edges: Json[] = [
    ...new Map<string, Json>(
      entries
        .filter((entry) => entry.tool === "trace_funds")
        // Trace tools emit bank evidence in the same order as their edges.
        // Use those references because masked record IDs and evidence aliases differ.
        .flatMap((entry) => (entry.result?.edges || []).map((edge: Json, index: number) => ({ ...edge, evidenceRef: entry.result.evidence?.[index] })))
        .filter((edge) => typeof edge.evidenceRef === "string")
        .map((e: Json): [string, Json] => [e.id, e]),
    ).values(),
  ].slice(0, 24);
  const nodes = [
    ...new Set<string>(
      edges.flatMap((e) => [e.source_account, e.destination_account]),
    ),
  ];
  const coords = new Map(
    nodes.map((node, i) => {
      const angle = (Math.PI * 2 * i) / nodes.length - Math.PI / 2;
      return [
        node,
        { x: 340 + Math.cos(angle) * 225, y: 180 + Math.sin(angle) * 120 },
      ];
    }),
  );
  if (!edges.length)
    return (
      <div className="graph-empty">
        <GitBranch size={38} />
        <h3>Every transfer starts with a source.</h3>
        <p>
          Run an investigation to trace the bank records.
          <br />
          Observed transfers will appear here.
        </p>
      </div>
    );
  return (
    <>
      <svg
        className="money-graph"
        viewBox="0 0 680 370"
        role="img"
        aria-label="Observed money transfers. Select an edge to inspect its bank record."
      >
        <defs>
          <marker
            id="arrow"
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L0,6 L7,3 z" fill="#238294" />
          </marker>
        </defs>
        {edges.map((edge, i) => {
          const a = coords.get(edge.source_account)!,
            b = coords.get(edge.destination_account)!;
          const dx = b.x - a.x,
            dy = b.y - a.y,
            length = Math.max(1, Math.hypot(dx, dy));
          const offset = 20 + (i % 3) * 22;
          const midX = (a.x + b.x) / 2 - (dy / length) * offset,
            midY = (a.y + b.y) / 2 + (dx / length) * offset;
          return (
            <g
              key={edge.id}
              className="graph-edge"
              role="button"
              tabIndex={0}
              aria-label={`Inspect transfer ${edge.id}: ${money(edge.amount, edge.currency)}`}
              onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onEvidence(edge.evidenceRef); } }}
              onClick={() => onEvidence(edge.evidenceRef)}
            >
              <path
                d={`M${a.x},${a.y} Q${midX},${midY} ${b.x - (dx / length) * 18},${b.y - (dy / length) * 18}`}
                fill="none"
                stroke={highlightedEvidence.includes(edge.evidenceRef) ? '#d9534f' : '#238294'}
                strokeWidth={highlightedEvidence.includes(edge.evidenceRef) ? 4 : 2}
                markerEnd="url(#arrow)"
              />
              <text
                x={(a.x + b.x + 2 * midX) / 4}
                y={(a.y + b.y + 2 * midY) / 4 - 5}
                textAnchor="middle"
              >
                {money(edge.amount, edge.currency)}
              </text>
              <title>
                {edge.id} · {edge.timestamp}
              </title>
            </g>
          );
        })}
        {nodes.map((node) => {
          const point = coords.get(node)!;
          return (
            <g key={node}>
              <circle
                cx={point.x}
                cy={point.y}
                r="14"
                fill="#0c2a4c"
                stroke="#fff"
                strokeWidth="4"
              />
              <text
                x={point.x}
                y={point.y + 32}
                textAnchor="middle"
                className="node-label"
              >
                {node}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="transfer-list" aria-label="Observed transfer sources">
        {edges.map((edge) => (
          <button
            key={edge.id}
            onClick={() => onEvidence(edge.evidenceRef)}
            aria-label={`Inspect ${edge.id}: ${money(edge.amount, edge.currency)}`}
          >
            <span>{edge.id}</span>
            <b>{money(edge.amount, edge.currency)}</b>
            <ArrowRight size={12} />
          </button>
        ))}
      </div>
      <p className="caption">
        Terracotta lines are cited by the selected finding. Select a transfer to inspect its source. First 24 observed edges; paths
        do not prove kickbacks or attribution of the same funds.
      </p>
    </>
  );
}

export default function App() {
  const [view, setView] = useState<View>("Overview");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [rate, setRate] = useState("");
  const [fxSource, setFxSource] = useState("");
  const [caseFile, setCase] = useState<Case | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState('');
  const [mode, setMode] = useState("offline");
  const [seed, setSeed] = useState(2026);
  const [clean, setClean] = useState(false);
  const [scenario, setScenario] = useState("all");
  const [configuration, setConfiguration] = useState<Json>({});
  const [modelStatus, setModelStatus] = useState("");
  const [evidenceRef, setEvidenceRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [evidence, setEvidence] = useState<Json | null>(null);
  const [table, setTable] = useState("invoices");
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<Json>({ rows: [], total: 0 });
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Json[]>([]);
  const [answerMode, setAnswerMode] = useState("ai");
  const [archive, setArchive] = useState<Json>({ items: [] });
  const [savedCase, setSavedCase] = useState<Json | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const sessionRef = useRef<string | null>(null);
  const closeEvidence = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const running = !!active(caseFile);
  const estate = dataset?.kind === "official";
  const base = dataset ? estate ? `/estates/${dataset.session_id}/workspace` : `/datasets/${dataset.session_id}` : "";

  useEffect(() => { request("/config").then(setConfiguration).catch(e => setError(e.message)); }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    if (view === "Saved analyses") refreshArchive();
  }, [view]);

  useEffect(() => {
    if (!dataset || !running) return;
    let stopped = false;
    const interval = window.setInterval(() => {
      request(`${base}/case`)
        .then((data) => {
          if (!stopped) setCase(data);
        })
        .catch((e) => {
          if (!stopped) setError(e.message);
        });
    }, 800);
    return () => {
      stopped = true;
      window.clearInterval(interval);
    };
  }, [dataset, running, base]);
  useEffect(() => {
    if (!dataset) return;
    let stopped = false;
    request(`${base}/records/${table}?offset=${offset}`)
      .then((data) => {
        if (!stopped) setRecords(data);
      })
      .catch((e) => {
        if (!stopped) setError(e.message);
      });
    return () => {
      stopped = true;
    };
  }, [dataset, table, offset, base]);
  useEffect(() => {
    if (!evidence) return;
    closeEvidence.current?.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape") setEvidence(null);
      // Keep native tab order so the explicit source reveal action is keyboard accessible.
    };
    window.addEventListener("keydown", handle);
    return () => {
      window.removeEventListener("keydown", handle);
      opener.current?.focus();
    };
  }, [evidence]);

  async function perform(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }
  function load(data: Dataset) {
    sessionRef.current = data.session_id;
    setDataset(data);
    setCase(null);
    setSelectedFindingId("");
    setTable("invoices");
    setQuestion("");
    setAnswers([]);
    setEvidence(null);
    setOffset(0);
    setRecords({ rows: [], total: 0 });
  }
  async function demo() {
    await perform(async () =>
      load(await post("/datasets/demo", { seed, clean, scenario })),
    );
  }
  async function upload(file?: File) {
    if (!file) return;
    await perform(async () => {
      const form = new FormData();
      form.append("file", file);
      const result = await request(`/datasets/upload?seed=${seed}`, { method: "POST", body: form });
      if (result.kind === "official") {
        load({ ...result, dataset_id: result.estate_sha256, files: Object.keys(result.coverage).map(name => `${name}.csv`), warnings: [] });
      } else {
        load(result);
      }
    });
  }
  async function investigate() {
    await perform(async () => {
      setCase(await post(`${base}/investigate`, estate ? { mode, usd_mxn_rate: rate, fx_source: fxSource } : { mode }));
      setView("Investigation");
    });
  }
  async function resumeInvestigation(nextMode: string, seconds = 180) {
    await perform(async () => {
      setCase(await post(`${base}/investigate`, { mode: nextMode, resume: true, seconds }));
      setMode(nextMode);
      setView("Investigation");
    });
  }
  async function showEvidence(ref: string, reveal = false) {
    opener.current = document.activeElement as HTMLElement;
    const id = dataset?.session_id;
    try {
      const row = await request(
        `${base}/evidence?ref=${encodeURIComponent(ref)}&reveal=${reveal}`,
      );
      if (id === sessionRef.current) { setEvidence(row); setEvidenceRef(ref); }
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function ask(text = question) {
    if (!text.trim()) return;
    const requestedSession = sessionRef.current;
    await perform(async () => {
      const response = await post(`${base}/ask`, { question: text, mode: answerMode });
      if (requestedSession !== sessionRef.current) return;
      setAnswers((previous) => [...previous, { question: text, ...response }]);
      setQuestion("");
    });
  }
  function saveJson(content: Json, filename: string) {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(content, null, 2)], {
        type: "application/json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function downloadJson() {
    await perform(async () => {
      saveJson(await request(`${base}/export/json`), "case-file.json");
    });
  }
  async function refreshArchive() {
    await perform(async () => setArchive(await request("/analyses")));
  }
  async function openSaved(id: string) {
    await perform(async () => setSavedCase(await request(`/analyses/${id}`)));
  }
  async function deleteSaved(id: string) {
    if (!window.confirm("Delete this saved analysis from Tiger Data? This cannot be undone.")) return;
    await perform(async () => {
      await request(`/analyses/${id}`, { method: "DELETE" });
      if (savedCase?.id === id) setSavedCase(null);
      setArchive(await request("/analyses"));
    });
  }
  const EvidenceLinks = ({ refs }: { refs: string[] }) => (
    <div className="evidence-links">
      {refs.map((ref) => (
        <button key={ref} onClick={() => showEvidence(ref)}>
          <Fingerprint size={12} />
          {ref}
        </button>
      ))}
    </div>
  );
  const verified = caseFile?.findings.length || 0;
  const unresolved =
    caseFile?.leads.filter((l) =>
      ["inconclusive", "deferred"].includes(l.state),
    ).length || 0;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("Overview");
          }}
          title="TraceBlock"
        >
          <img
            src={traceBlockLogo}
            alt="TraceBlock Forensic Audit Solutions"
            className="brand-logo"
          />
        </a>
        <div className="workspace-label">
          AUDIT WORKSPACE <span>MVP</span>
        </div>
        <nav aria-label="Main navigation">
          {nav.map(([name, Icon]) => (
            <button
              key={name}
              className={view === name ? "selected" : ""}
              onClick={() => setView(name)}
            >
              <Icon size={18} />
              {name}
              {name === "Case file" && verified > 0 && (
                <span className="nav-count">{verified}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-case">
          <div className="tiny-label">CURRENT DATASET</div>
          <FolderOpen size={22} />
          <strong>{dataset ? "Company records" : "No dataset loaded"}</strong>
          <span>
            {dataset
              ? `${dataset.dataset_id.slice(0, 12)}…`
              : "A clear trail starts here."}
          </span>
          {dataset && (
            <div className="local-indicator">
              <span />{" "}
              {Object.values(dataset.coverage).reduce((a, b) => a + b, 0)}{" "}
              source records
            </div>
          )}
        </div>
        <div className="sidebar-bottom">
          <ShieldCheck size={19} />
          <div>
            Evidence before conclusions.
            <small>HackMTY 2026 · Infosys challenge</small>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            Workspace <ChevronRight size={14} />
            <strong>{view}</strong>
          </div>
          <span className="environment">
            <span /> LOCAL WORKSPACE
          </span>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                TRACEBLOCK /{" "}
                {view === "Overview" ? "WORKSPACE 01" : view.toUpperCase()}
              </div>
              <h1>{view === "Overview" ? "Follow the money." : view}</h1>
              <p>
                {
                  {
                    Overview: "Turn unfamiliar records into a defensible case.",
                    Investigation:
                      "Watch the evidence develop. Keep every conclusion accountable.",
                    "Case file":
                      "Supported findings, reproducible amounts, and the leads left open.",
                    "Source records":
                      "Original records are always one click away.",
                    "Ask the auditor":
                      "Answers extracted from this case, with the evidence to inspect.",
                    "Saved analyses":
                      "Masked case files from earlier runs, stored in Tiger Data.",
                  }[view]
                }
              </p>
            </div>
            <div className="heading-actions">
              {caseFile && <Badge value={caseFile.status} />}
              <button
                className="primary"
                disabled={!dataset || busy || running || (estate && !!caseFile && !["failed"].includes(caseFile.status))}
                onClick={investigate}
              >
                {busy ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Play size={15} />
                )}{" "}
                {estate && caseFile && caseFile.status !== "failed" ? "Investigation started" : caseFile ? "Run again" : "Start investigation"}
              </button>
            </div>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {caseFile?.status === "incomplete" && (
            <div className="warning-banner">
              <div>
                <strong>Investigation incomplete.</strong> {caseFile.completion_reason}{" "}
                Published findings passed validation, but coverage is unfinished.
              </div>
              {caseFile.can_resume && (
                <div className="banner-actions">
                  <button
                    className="primary"
                    disabled={busy || running}
                    onClick={() => resumeInvestigation("ai", 180)}
                    title="Grant 180 seconds to continue AI investigation"
                  >
                    <Clock size={14} /> Continue with more time (+180s)
                  </button>
                  <button
                    disabled={busy || running}
                    onClick={() => resumeInvestigation("ai", 180)}
                    title="Retry connection and continue AI review"
                  >
                    <RotateCw size={14} /> {caseFile.error_type === "connection_error" ? "Retry connection" : "Continue AI review"}
                  </button>
                  <button
                    disabled={busy || running}
                    onClick={() => resumeInvestigation("offline")}
                    title="Finish remaining leads deterministically without network calls"
                  >
                    <ShieldCheck size={14} /> Finish remaining review offline
                  </button>
                </div>
              )}
            </div>
          )}
          {caseFile?.recovery && caseFile.status !== "incomplete" && (
            <p className="mode-note">{caseFile.recovery}. Prior validated findings and tool results were preserved.</p>
          )}
          {caseFile?.status === "cancelled" && (
            <div className="warning-banner">
              Investigation cancelled. Remaining leads are deferred; the case is
              partial.
            </div>
          )}

          {view === "Overview" && (
            <>
              <section className="hero">
                <div className="hero-copy">
                  <span className="hero-kicker">
                    <span /> BUILT FOR EVIDENCE, NOT ASSUMPTIONS
                  </span>
                  <h2>
                    The records tell a story.
                    <br />
                    <em>Make it stand up.</em>
                  </h2>
                  <p>
                    Connect invoices, bank movements, and supplier records.
                    <br />
                    Separate what you can prove from what needs another look.
                  </p>
                  <button
                    onClick={() => fileInput.current?.click()}
                    disabled={busy || running}
                  >
                    Upload company records <ArrowRight size={16} />
                  </button>
                </div>
                <div className="hero-art" aria-hidden="true">
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                  <div className="orbit orbit-three" />
                  <div className="art-center">
                    <Fingerprint size={68} strokeWidth={1} />
                  </div>
                  <span className="art-chip chip-one">
                    <FileCheck2 size={16} /> Invoice
                  </span>
                  <span className="art-chip chip-two">
                    <GitBranch size={16} /> Transfer
                  </span>
                  <span className="art-chip chip-three">
                    <Check size={16} /> Evidence
                  </span>
                  <span className="cross cross-one">+</span>
                  <span className="cross cross-two">+</span>
                </div>
              </section>
              <div className="metrics">
                <Metric
                  label="SOURCE RECORDS"
                  value={
                    dataset
                      ? Object.values(dataset.coverage)
                          .reduce((a, b) => a + b, 0)
                          .toString()
                      : "—"
                  }
                  detail={
                    dataset
                      ? `${dataset.files.length} validated CSV files`
                      : "Upload a dataset to begin"
                  }
                  icon={<Database size={18} />}
                />
                <Metric
                  label="VERIFIED FINDINGS"
                  value={caseFile ? String(verified) : "—"}
                  detail="Evidence gate passed"
                  icon={<ShieldCheck size={18} />}
                />
                <Metric
                  label={estate ? "DOCUMENTED EXPOSURE" : "EXCESS SETTLEMENT"}
                  value={caseFile ? money(caseFile.totals.MXN || 0) : "—"}
                  detail="MXN exposure · not demonstrated loss"
                  icon={<FileCheck2 size={18} />}
                />
              </div>
              <div className="overview-grid">
                <section className="panel">
                  <PanelHeading
                    number="01"
                    title="Bring the records"
                    subtitle="Your investigation begins with the source."
                  />
                  <div
                    className="upload-area"
                    role="button"
                    tabIndex={running || busy ? -1 : 0}
                    aria-disabled={running || busy}
                    onClick={() => {
                      if (!running && !busy) fileInput.current?.click();
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !running && !busy)
                        fileInput.current?.click();
                    }}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (!running && !busy) upload(e.dataTransfer.files[0]);
                    }}
                  >
                    <span className="upload-icon">
                      <Upload size={23} />
                    </span>
                    <strong>Drop your company dataset here</strong>
                    <span>
                      or <u>browse files</u> to upload
                    </span>
                    <small>estate_csv.zip · 8 CSV tables · up to 20 MB</small>
                  </div>
                  <p className="mode-note">vendors, invoices, ledger, bank_txns, purchase_orders, contracts, employees, and efos_list. Original demo CSV bundles are also supported.</p>
                  <div className="dataset-summary">
                    {dataset ? (
                      <>
                        <Check size={17} />
                        <span>
                          <b>Dataset validated</b>
                          <small>
                            {dataset.files.length} files · SHA-256{" "}
                            {dataset.dataset_id.slice(0, 12)}
                          </small>
                        </span>
                        <button onClick={() => setView("Source records")}>
                          Inspect <ArrowRight size={14} />
                        </button>
                      </>
                    ) : (
                      <>
                        <ShieldCheck size={17} />
                        <span>
                          Original values and source hashes are preserved.
                        </span>
                      </>
                    )}
                  </div>
                </section>
                <section className="panel">
                  <PanelHeading
                    number="02"
                    title="Choose how to investigate"
                    subtitle="Same evidence gate. Two ways to explore."
                  />
                  <div className="mode-options">
                    {[
                      [
                        "offline",
                        "Offline evidence review",
                        "Deterministic tools. No API calls.",
                        ShieldCheck,
                      ],
                      [
                        "ai",
                        "AI investigation",
                        "OpenRouter directs a bounded tool loop.",
                        Zap,
                      ],
                    ].map(([value, title, description, Icon]: any) => (
                      <label
                        key={value}
                        className={`mode-option ${mode === value ? "chosen" : ""}`}
                      >
                        <input
                          type="radio"
                          name="mode"
                          value={value}
                          checked={mode === value}
                          onChange={() => setMode(value)}
                          disabled={running}
                        />
                        <Icon size={20} />
                        <span>
                          <b>{title}</b>
                          <small>{description}</small>
                        </span>
                        <span className="radio-mark">
                          {mode === value && <span />}
                        </span>
                      </label>
                    ))}
                  </div>
                  <p className="mode-note">
                    {mode === "ai"
                      ? "AI receives pseudonymous lead summaries only. Up to 60 tool steps / 180 seconds. Free endpoints are available only for app-generated fictional demos."
                      : "Offline review is labeled separately from an AI investigation. Findings still require verified relationships and exact calculations."}
                  </p>
                  {estate && mode === "ai" && <div className="panel-actions"><label>USD/MXN rate <input value={rate} onChange={e => setRate(e.target.value)} disabled={running} /></label><label>Rate source and date <input value={fxSource} onChange={e => setFxSource(e.target.value)} disabled={running} /></label></div>}
                  <p className="mode-note">Model: {configuration.model || "Not configured"}. {configuration.configured ? "Server key configured." : "Server API key is missing."}</p>
                  <div className="panel-actions">
                    <button className="secondary" disabled={busy || running} onClick={() => perform(async () => {
                      const result = await post("/check-model", {}); setConfiguration(result); setModelStatus("Connection successful. No accounting records were sent.");
                    })}>Check model connection</button>
                    {dataset && <button className="secondary" disabled={busy} onClick={() => perform(async () => {
                      await request(base, {method: "DELETE"}); sessionRef.current = null; setDataset(null); setCase(null); setEvidence(null); setAnswers([]); setRecords({rows: [], total: 0});
                    })}>Delete dataset from memory</button>}
                  </div>
                  {modelStatus && <p className="mode-note">{modelStatus}</p>}
                  <div className="demo-row">
                    <span>Explore fictional records</span>
                    <div>
                      <label className="sr-only" htmlFor="seed">
                        Demo seed
                      </label>
                      <input
                        id="seed"
                        type="number"
                        min="0"
                        max="2147483647"
                        value={seed}
                        onChange={(e) => setSeed(Number(e.target.value))}
                        disabled={running}
                      />
                      <button
                        className="secondary"
                        onClick={demo}
                        disabled={busy || running}
                      >
                        Load demo <ArrowRight size={14} />
                      </button>
                    </div>
                  </div>
                  <label className="scenario-option">Fictional scenario <select value={scenario} onChange={e => setScenario(e.target.value)} disabled={running}>
                    {["all", "excess", "service", "return", "sale", "cycle"].map(value => <option key={value} value={value}>{value}</option>)}
                  </select></label>
                  <label className="clean-option">
                    <input
                      type="checkbox"
                      checked={clean}
                      onChange={(e) => setClean(e.target.checked)}
                      disabled={running}
                    />{" "}
                    Clean control dataset
                  </label>
                  <a
                    className="text-link"
                    href={`/api/demo.zip?seed=${seed}&clean=${clean}&scenario=${scenario}`}
                  >
                    Download these CSV records <ArrowDownToLine size={13} />
                  </a>
                </section>
              </div>
              {dataset && dataset.warnings.length > 0 && (
                <details className="coverage-notes">
                  <summary>Coverage notes · {dataset.warnings.length}</summary>
                  {dataset.warnings.map((warning, i) => (
                    <p key={i}>{warning}</p>
                  ))}
                </details>
              )}
              <div className="principles">
                <span>
                  <Fingerprint size={16} /> Traceable to original records
                </span>
                <span>
                  <Check size={16} /> Exact centavo calculations
                </span>
                <span>
                  <ShieldCheck size={16} /> No unsupported accusations
                </span>
              </div>
            </>
          )}

          {view === "Investigation" && (
            <>
              {!caseFile ? (
                <Empty
                  icon={<Search size={32} />}
                  title="Ready when the records are."
                  detail="Load a dataset in Overview, then start an investigation."
                  action={() => setView("Overview")}
                  label="Go to overview"
                />
              ) : (
                <>
                  <div className="run-banner">
                    <span className={running ? "pulse" : "status-dot"} />
                    <div>
                      <strong>
                        {running
                          ? "Following the evidence…"
                          : caseFile.mode === "offline"
                            ? "Offline evidence review"
                            : "AI investigation"}
                      </strong>
                      <small>
                        {caseFile.completion_reason ||
                          "Each tool result is recorded below."}
                      </small>
                    </div>
                    <span>
                      {caseFile.timeline.length} tool events ·{" "}
                      {caseFile.model_calls} model calls
                    </span>
                    {running ? (
                      <button
                        className="secondary"
                        onClick={() =>
                          perform(async () => {
                            await post(`${base}/cancel`);
                          })
                        }
                        disabled={busy}
                      >
                        <Square size={13} /> Cancel
                      </button>
                    ) : caseFile.status === "incomplete" && caseFile.can_resume ? (
                      <div className="banner-actions" style={{ marginLeft: "auto" }}>
                        <button
                          className="primary"
                          disabled={busy || running}
                          onClick={() => resumeInvestigation("ai", 180)}
                          title="Grant 180 seconds to continue AI investigation"
                        >
                          <Clock size={13} /> Continue (+180s)
                        </button>
                        <button
                          disabled={busy || running}
                          onClick={() => resumeInvestigation("ai", 180)}
                          title="Retry connection and continue AI review"
                        >
                          <RotateCw size={13} /> {caseFile.error_type === "connection_error" ? "Retry" : "Continue AI"}
                        </button>
                        <button
                          disabled={busy || running}
                          onClick={() => resumeInvestigation("offline")}
                          title="Finish remaining review offline"
                        >
                          <ShieldCheck size={13} /> Finish offline
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <InvestigationInsights
                    leads={caseFile.leads}
                    findings={caseFile.findings}
                    selectedId={selectedFindingId}
                    onSelect={setSelectedFindingId}
                    onEvidence={showEvidence}
                  />
                  <div className="investigation-grid">
                    <section className="panel">
                      <div className="panel-title">
                        <h2>Money trail</h2>
                        <span className="small-label">SOURCE-LINKED</span>
                      </div>
                      <MoneyGraph
                        entries={caseFile.timeline}
                        onEvidence={showEvidence}
                        highlightedEvidence={(caseFile.findings.find(f => f.id === selectedFindingId) ?? caseFile.findings[0])?.evidence || []}
                      />
                    </section>
                    <section className="panel lead-panel">
                      <div className="panel-title">
                        <h2>Lead register</h2>
                        <span className="count">{caseFile.leads.length}</span>
                      </div>
                      {caseFile.leads.length ? (
                        caseFile.leads.map((lead) => (
                          <div className="lead" key={lead.id}>
                            <div>
                              <b>{lead.id}</b>
                              <Badge value={lead.state} />
                            </div>
                            <p>{lead.reason}</p>
                            <small>{lead.hypothesis}</small>
                          </div>
                        ))
                      ) : (
                        <p className="muted padded">
                          No candidate leads under the implemented rules. This
                          does not establish that the dataset is fraud-free.
                        </p>
                      )}
                    </section>
                  </div>
                  <section className="panel timeline-panel">
                    <div className="panel-title">
                      <h2>Investigation timeline</h2>
                      <span className="small-label">
                        DECISIONS & TOOL RESULTS
                      </span>
                    </div>
                    {caseFile.timeline.length === 0 && (
                      <p className="muted padded">
                        Waiting for the first tool result.
                      </p>
                    )}
                    {caseFile.timeline.map((entry, i) => (
                      <details
                        className="timeline-entry"
                        key={i}
                        open={i === caseFile.timeline.length - 1}
                      >
                        <summary>
                          <span className="step">
                            {String(entry.step).padStart(2, "0")}
                          </span>
                          <span>
                            <b>{toolNames[entry.tool] || entry.tool}</b>
                            <small>{entry.lead_id}</small>
                          </span>
                          <ChevronRight size={16} />
                        </summary>
                        <div className="timeline-result">
                          {entry.result.reason && <p>{entry.result.reason}</p>}
                          {entry.result.calculation && (
                            <code>{entry.result.calculation}</code>
                          )}
                          {entry.result.conclusion && (
                            <p>{entry.result.conclusion}</p>
                          )}
                          {entry.result.checks?.map((check: string) => (
                            <p key={check}>{check}</p>
                          ))}
                          <EvidenceLinks refs={entry.result.evidence || []} />
                          <details>
                            <summary>Inspect structured tool result</summary>
                            <pre>{JSON.stringify(entry.result, null, 2)}</pre>
                          </details>
                        </div>
                      </details>
                    ))}
                  </section>
                </>
              )}
            </>
          )}

          {view === "Case file" &&
            (!caseFile ? (
              <Empty
                icon={<FileCheck2 size={32} />}
                title="A case built on evidence."
                detail="Your verified findings and lead dispositions will be collected here."
                action={() => setView("Overview")}
                label="Load records"
              />
            ) : (
              <>
                <div className="case-summary">
                  <div>
                    <div className="eyebrow">{estate ? "DOCUMENTED EXPOSURE" : "EXCESS-SETTLEMENT EXPOSURE"}</div>
                    {Object.entries(caseFile.totals).length ? (
                      Object.entries(caseFile.totals).map(
                        ([currency, value]) => (
                          <h2 key={currency}>{money(value, currency)}</h2>
                        ),
                      )
                    ) : (
                      <h2>No verified exposure</h2>
                    )}
                    <p>
                      {estate ? caseFile.total_definition : "Explicit allocations, counted once. Not demonstrated loss or tax liability."}
                    </p>
                  </div>
                  <div className="export-actions">
                  {estate && <><a className="secondary" href={`/api${base}/export/json?full=true`}>Judge JSON · original identities</a><a className="secondary" href={`/api${base}/export/replay?full=true`}>Offline replay · original records</a></>}
                    <button
                      className="secondary"
                      onClick={downloadJson}
                      disabled={busy}
                    >
                      <ArrowDownToLine size={16} /> JSON
                    </button>
                    <a className="secondary" href={`/api${base}/export/html`}>
                      <ArrowDownToLine size={16} /> Printable HTML
                    </a>
                  </div>
                </div>
                {dataset && <IntegrityPanel key={dataset.session_id} kind={estate ? "estates" : "datasets"} identity={dataset.session_id} running={running} />}
                <section className="panel category-panel"><h3>Separate amount categories</h3>
                  <p>{caseFile.total_definition}</p>
                  {Object.entries(caseFile.totals_by_category || {}).map(([category, values]) => <p key={category}><b>{category.replaceAll("_", " ")}</b>: {Object.entries(values).map(([currency, amount]) => money(amount, currency)).join(" · ")}</p>)}
                  {caseFile.discovery?.truncated && <p>Discovery was truncated. This case does not cover all candidate paths.</p>}
                  <details><summary>Local reviewer export with unmasked source records</summary><a className="secondary" href={`/api${base}/export/html?full=true`}>Full evidence HTML (contains sensitive data)</a></details>
                </section>
                <div className="section-title">
                  <h2>
                    Verified findings <span>{verified}</span>
                  </h2>
                  <span className="small-label">
                    DETERMINISTICALLY VALIDATED
                  </span>
                </div>
                {caseFile.findings.map((finding) => (
                  <article className="panel finding" key={finding.id}>
                    <div className="finding-top">
                      <span className="finding-icon">
                        <ShieldCheck size={22} />
                      </span>
                      <div>
                        <div className="tiny-label">{finding.rule}</div>
                        <h3>{finding.title}</h3>
                        <p>
                          {finding.supplier_name} · {finding.invoice_id}
                        </p>
                      </div>
                      <Badge value={finding.confidence || "substantiated"} />
                    </div>
                    <p>{finding.claim}</p>
                    {finding.rule === "excess-settlement-v1" ? <div className="calculation">
                      <div>
                        <span>Allocated payments</span>
                        <b>
                          {money(
                            finding.calculation?.payments_centavos,
                            finding.currency,
                          )}
                        </b>
                      </div>
                      <span>−</span>
                      <div>
                        <span>Refunds</span>
                        <b>
                          {money(
                            finding.calculation?.refunds_centavos,
                            finding.currency,
                          )}
                        </b>
                      </div>
                      <span>−</span>
                      <div>
                        <span>Recorded obligation</span>
                        <b>
                          {money(
                            finding.calculation?.obligation_centavos,
                            finding.currency,
                          )}
                        </b>
                      </div>
                      <span>=</span>
                      <div className="result">
                        <span>Excess settlement</span>
                        <b>
                          {money(finding.amount_centavos, finding.currency)}
                        </b>
                      </div>
                    </div> : <div className="calculation"><p>{finding.calculation?.calculation || "Calculation unavailable."}</p><b>{money(finding.amount_centavos, finding.currency)}</b></div>}
                    <details>
                      <summary>Alternative explanations checked</summary>
                      <ul>
                        {finding.alternatives.map((value: string) => (
                          <li key={value}>{value}</li>
                        ))}
                      </ul>
                    </details>
                    <div className="tiny-label source-label">
                      SUPPORTING EVIDENCE
                    </div>
                    <EvidenceLinks refs={finding.evidence} />
                  </article>
                ))}
                {!verified && (
                  <p className="muted">
                    No finding met the evidence gate. Review the lead register
                    for unresolved questions.
                  </p>
                )}
                <div className="section-title">
                  <h2>
                    Other lead dispositions{" "}
                    <span>{caseFile.leads.length - verified}</span>
                  </h2>
                  <span className="small-label">{unresolved} UNRESOLVED</span>
                </div>
                <section className="panel disposition-list">
                  {caseFile.leads
                    .filter((lead) => lead.state !== "substantiated")
                    .map((lead) => (
                      <div key={lead.id}>
                        <div>
                          <b>{lead.id}</b>
                          <p>{lead.reason}</p>
                          <EvidenceLinks refs={lead.evidence} />
                        </div>
                        <Badge value={lead.state} />
                      </div>
                    ))}
                  {caseFile.leads.length === verified && (
                    <p className="muted">No other generated leads.</p>
                  )}
                </section>
                <details className="coverage-notes" open>
                  <summary>Scope and limitations</summary>
                  {caseFile.limitations.map((value) => (
                    <p key={value}>{value}</p>
                  ))}
                </details>
              </>
            ))}

          {view === "Source records" &&
            (!dataset ? (
              <Empty
                icon={<Database size={32} />}
                title="The original record matters."
                detail="Upload the documented CSV bundle to inspect records and their provenance."
                action={() => setView("Overview")}
                label="Upload records"
              />
            ) : (
              <section className="panel records-panel">
                <div className="records-header">
                  <label>
                    Record type{" "}
                    <select
                      value={table}
                      onChange={(e) => {
                        setTable(e.target.value);
                        setOffset(0);
                      }}
                    >
                      {Object.entries(dataset.coverage).map(([name, count]) => (
                        <option value={name} key={name}>
                          {name} ({count})
                        </option>
                      ))}
                    </select>
                  </label>
                  <span className="small-label">
                    {records.total} RECORDS · AMOUNTS IN CENTAVOS
                  </span>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        {Object.keys(records.rows[0] || {})
                          .filter((key) => key !== "evidence_id")
                          .map((key) => (
                            <th key={key}>{key.replaceAll("_", " ")}</th>
                          ))}
                        <th>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.rows.map((row: Json) => (
                        <tr key={row.id}>
                          {Object.entries(row)
                            .filter(([key]) => key !== "evidence_id")
                            .map(([key, value]) => (
                              <td key={key}>{String(value)}</td>
                            ))}
                          <td>
                            <button
                              className="source-button"
                              onClick={() => showEvidence(row.evidence_id)}
                            >
                              <Fingerprint size={15} /> Inspect
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!records.rows.length && (
                    <p className="padded muted">
                      No records supplied in this table.
                    </p>
                  )}
                </div>
                <div className="pagination">
                  <span>
                    {records.total ? offset + 1 : 0}–
                    {Math.min(offset + 100, records.total)} of {records.total}
                  </span>
                  <button
                    className="secondary"
                    disabled={!offset}
                    onClick={() => setOffset(Math.max(0, offset - 100))}
                  >
                    Previous
                  </button>
                  <button
                    className="secondary"
                    disabled={offset + 100 >= records.total}
                    onClick={() => setOffset(offset + 100)}
                  >
                    Next
                  </button>
                </div>
              </section>
            ))}

          {view === "Ask the auditor" &&
            (!caseFile ? (
              <Empty
                icon={<CircleHelp size={32} />}
                title="Start with a case."
                detail="Run an investigation to ask about findings, calculations, and investigative decisions."
                action={() => setView("Overview")}
                label="Go to overview"
              />
            ) : (
              <div className="ask-layout">
                <section className="panel chat-panel">
                  <div className="chat-intro">
                    <span className="finding-icon">
                      <Fingerprint size={25} />
                    </span>
                    <h2>What would you like to verify?</h2>
                    <p>
                      Chat with the AI using this case’s findings, calculations,
                      evidence trails and investigation decisions.
                    </p>
                    <label className="answer-mode">Answer mode <select value={answerMode} onChange={e => setAnswerMode(e.target.value)} disabled={busy}>
                      <option value="ai">AI auditor</option>
                      <option value="offline">Offline case extraction</option>
                    </select></label>
                    {!estate && <AuditorVoice key={dataset?.session_id} base={base} synthetic={Boolean(dataset?.synthetic)}
                      onAnswer={(question, response) => setAnswers(previous => [...previous, { question, ...response }])} />}
                    <div className="suggestions">
                      {[
                        "How was the total calculated?",
                        "Why were leads dismissed?",
                        "Which suppliers have findings?",
                      ].map((text) => (
                        <button
                          disabled={busy}
                          key={text}
                          onClick={() => ask(text)}
                        >
                          {text}
                          <ArrowRight size={13} />
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="chat-messages" aria-live="polite">
                    {answers.map((item, i) => (
                      <div className="exchange" key={i}>
                        <div className="question">{item.question}</div>
                        <div className="answer">
                          <span className="tiny-label">
                            {item.mode === "ai" ? "AUDITOR · AI" : "AUDITOR · OFFLINE EXTRACTION"}
                          </span>
                          <AuditorMarkdown>{item.answer}</AuditorMarkdown>
                          <EvidenceLinks refs={item.evidence} />
                          <small>
                            Case status: {item.case_status.replaceAll("_", " ")}
                          </small>
                        </div>
                      </div>
                    ))}
                  </div>
                  {busy && <p role="status">The auditor is reviewing the case…</p>}
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      ask();
                    }}
                  >
                    <label className="sr-only" htmlFor="question">
                      Ask about this case
                    </label>
                    <input
                      id="question"
                      value={question}
                      maxLength={1000}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="Ask about an amount, finding, or decision…"
                    />
                    <button
                      aria-label="Send question"
                      disabled={busy || !question.trim()}
                    >
                      <Send size={18} />
                    </button>
                  </form>
                </section>
                <aside className="ask-note">
                  <ShieldCheck size={25} />
                  <h3>A defensible answer has a source.</h3>
                  <p>
                    The AI receives masked case context and remembers your last
                    six exchanges. Citations are checked against this dataset;
                    generated explanations do not create or change findings.
                  </p>
                  <p>Keep questions focused on the case; do not include new personal or confidential information. Uploaded data requires a model with private routing.</p>
                  <p>Inspect the linked records to review each answer.</p>
                </aside>
              </div>
            ))}
          {view === "Saved analyses" && (
            <>
              {!archive.enabled ? (
                <section className="panel empty-state">
                  <History size={32} />
                  <h2>Saving is off.</h2>
                  <p>
                    Set TIGER_DATABASE_URL in the server .env and restart the API.
                    Completed investigations are then saved as masked case files.
                  </p>
                </section>
              ) : (
                <>
                  {archive.last_error && (
                    <div className="warning-banner">
                      The last analysis was not saved: {archive.last_error}
                    </div>
                  )}
                  <section className="panel records-panel">
                    <div className="records-header">
                      <span className="small-label">
                        {archive.items.length} SAVED · MASKED VIEWS ONLY
                      </span>
                      <button className="secondary" disabled={busy} onClick={refreshArchive}>
                        <RotateCw size={14} /> Refresh
                      </button>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Saved</th><th>Type</th><th>Status</th><th>Mode</th>
                            <th>Findings</th><th>Totals</th><th>Dataset SHA-256</th><th />
                          </tr>
                        </thead>
                        <tbody>
                          {archive.items.map((item: Json) => (
                            <tr key={item.id}>
                              <td>{new Date(item.created_at).toLocaleString()}</td>
                              <td>{item.kind === "official" ? "Judge estate" : "CSV records"}{item.synthetic ? " · demo" : ""}</td>
                              <td><Badge value={item.status} /></td>
                              <td>{item.mode}</td>
                              <td>{item.findings_count} / {item.leads_count} leads</td>
                              <td>
                                {item.kind === "official"
                                  ? (item.totals.schemes || []).join(", ").replaceAll("_", " ") || "—"
                                  : Object.entries(item.totals).map(([currency, value]) => money(value as number, currency)).join(" · ") || "—"}
                              </td>
                              <td><code>{item.dataset_sha256.slice(0, 12)}…</code></td>
                              <td>
                                <button className="source-button" disabled={busy} onClick={() => openSaved(item.id)}>Open</button>
                                <button className="source-button" disabled={busy} onClick={() => deleteSaved(item.id)} aria-label="Delete saved analysis"><X size={14} /></button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {!archive.items.length && (
                        <p className="padded muted">
                          No saved analyses yet. Completed investigations appear here.
                        </p>
                      )}
                    </div>
                  </section>
                  {savedCase && (
                    <section className="panel">
                      <div className="panel-title">
                        <h2>{savedCase.kind === "official" ? "Judge estate case" : "CSV case"} · {new Date(savedCase.created_at).toLocaleString()}</h2>
                        <button className="secondary" onClick={() => saveJson(savedCase.masked_case, `saved-case-${savedCase.id}.json`)}>
                          <ArrowDownToLine size={14} /> Masked JSON
                        </button>
                      </div>
                      <p className="mode-note">
                        Read-only masked view. Aliases do not resolve to source records. Load the original dataset again to inspect evidence or ask questions.
                      </p>
                      {savedCase.masked_case.findings.map((finding: Json, i: number) => (
                        <article className="panel finding" key={finding.id || finding.finding_id || i}>
                          <div className="tiny-label">{finding.rule || finding.scheme_type}</div>
                          <h3>{finding.title || String(finding.scheme_type).replaceAll("_", " ")}</h3>
                          <p>{finding.claim || finding.summary || (finding.entities || []).join(", ")}</p>
                          <b>{finding.amount_centavos !== undefined ? money(finding.amount_centavos, finding.currency) : `MXN ${finding.peso_amount}`}</b>
                        </article>
                      ))}
                      {!savedCase.masked_case.findings.length && <p className="muted">No finding met the evidence gate in this run.</p>}
                      <details>
                        <summary>Inspect the full masked case</summary>
                        <pre>{JSON.stringify(savedCase.masked_case, null, 2)}</pre>
                      </details>
                    </section>
                  )}
                </>
              )}
            </>
          )}
          <footer>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <img
                src={traceBlockCompact}
                alt=""
                style={{ width: "16px", height: "16px", borderRadius: "3px" }}
              />
              TRACEBLOCK
            </span>
            <span>Prove the discrepancy. Preserve the uncertainty.</span>
            <span>v0.1 / local prototype</span>
          </footer>
        </main>
      </div>
      <input
        ref={fileInput}
        className="sr-only"
        aria-label="Upload company ZIP"
        type="file"
        accept=".zip"
        disabled={busy || running}
        onChange={(e) => {
          upload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {evidence && (
        <div className="modal-backdrop" onClick={() => setEvidence(null)}>
          <section
            className="evidence-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="evidence-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <span className="eyebrow">SOURCE RECORD · MASKED BY DEFAULT</span>
                <h2 id="evidence-title">{evidence.id}</h2>
              </div>
              <button
                ref={closeEvidence}
                aria-label="Close evidence"
                onClick={() => setEvidence(null)}
              >
                <X size={22} />
              </button>
            </header>
            <button className="secondary reveal-button" onClick={() => showEvidence(evidenceRef, true)}>Reveal original values locally</button>
            <div className="provenance">
              <span>
                <b>File</b>
                {evidence.file}
              </span>
              <span>
                <b>Source location</b>
                {evidence.csv_record}
              </span>
              <span>
                <b>Ingestion</b>
                {evidence.ingestion_version}
              </span>
            </div>
            <div className="hash">
              <Fingerprint size={16} />
              <span>
                SHA-256
                <br />
                {evidence.sha256}
              </span>
            </div>
            <h3>Original values</h3>
            <dl>
              {Object.entries(evidence.original).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
            <h3>Normalized record · money in centavos</h3>
            <pre>{JSON.stringify(evidence.normalized, null, 2)}</pre>
          </section>
        </div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="metric">
      <div>
        {label}
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
function PanelHeading({
  number,
  title,
  subtitle,
}: {
  number: string;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="panel-heading">
      <span>{number}</span>
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}
function Empty({
  icon,
  title,
  detail,
  action,
  label,
}: {
  icon: React.ReactNode;
  title: string;
  detail: string;
  action: () => void;
  label: string;
}) {
  return (
    <section className="panel empty-state">
      {icon}
      <h2>{title}</h2>
      <p>{detail}</p>
      <button className="primary" onClick={action}>
        {label}
        <ArrowRight size={15} />
      </button>
    </section>
  );
}
