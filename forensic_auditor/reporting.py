import html
import json

from .data import Dataset, pesos
from .privacy import Presentation


def export_case(data: Dataset, case: dict, *, full=False, presentation=None) -> dict:
    result = {**case, "total_definition": case.get("total_definition", "Separate amounts by category and currency; not demonstrated loss."),
              "source_evidence": data.evidence, "privacy_mode": "full local evidence" if full else "masked shareable case"}
    return result if full else (presentation or Presentation(data)).apply(result)


def printable(data: Dataset, case: dict, *, full=False, presentation=None) -> str:
    case = export_case(data, case, full=full, presentation=presentation)
    escape = html.escape
    findings = ""
    for finding in case["findings"]:
        links = " ".join(f'<a href="#{escape(ref, quote=True)}">{escape(ref)}</a>' for ref in finding["evidence"])
        findings += f"<article><h2>{escape(finding['title'])}</h2><p>{escape(finding['supplier_name'])}</p><p>{escape(finding['claim'])}</p><strong>{pesos(finding['amount_centavos'], finding['currency'])}</strong><pre>{escape(finding['calculation']['calculation'])}</pre><p>{links}</p></article>"
    leads = "".join(f"<li><b>{escape(lead['id'])} · {escape(lead['state'])}</b>: {escape(lead['reason'])}</li>" for lead in case["leads"])
    evidence = "".join(f'<article id="{escape(ref, quote=True)}"><h3>{escape(ref)}</h3><pre>{escape(json.dumps(row, indent=2, ensure_ascii=False))}</pre></article>' for ref, row in case["source_evidence"].items())
    timeline = "".join(f"<article><h3>Step {entry['step']}: {escape(entry['tool'])}</h3><pre>{escape(json.dumps(entry, indent=2, ensure_ascii=False))}</pre></article>" for entry in case["timeline"])
    limitations = "".join(f"<li>{escape(value)}</li>" for value in case["limitations"])
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>TraceBlock · Case file</title>
<style>body{{font:15px/1.6 system-ui;max-width:960px;margin:50px auto;padding:0 24px;color:#102a45}}h1{{font-size:36px;color:#0c2a4c}}article{{border-top:1px solid #dce5ec;padding:20px 0;break-inside:avoid}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}a{{color:#238294}}@media print{{body{{margin:0}}}}</style>
<h1>TraceBlock</h1><p>Case {escape(data.identity)}</p><p>{escape(case['mode'])} · {escape(case['status'])} · {escape(case['privacy_mode'])}</p>
<p>{escape(case.get('completion_reason', 'Investigation in progress.'))}</p><h2>Verified findings</h2>{findings or '<p>No verified finding published.</p>'}
<p>{escape(case['total_definition'])}</p><h2>Amounts by category (centavos)</h2><pre>{escape(json.dumps(case.get('totals_by_category', {}), indent=2))}</pre>
<h2>Lead dispositions</h2><ul>{leads}</ul><h2>Investigation audit trail</h2>{timeline}<h2>Limitations</h2><ul>{limitations}</ul><h2>Source evidence</h2>{evidence}</html>"""
