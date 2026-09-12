import html
import json

from .data import Dataset, pesos


def export_case(data: Dataset, case: dict) -> dict:
    return {**case, "total_definition": "Sum of verified per-invoice excess settlement, using non-overlapping explicit bank allocations. Currencies kept separate. Not demonstrated loss.",
            "source_evidence": data.evidence}


def printable(data: Dataset, case: dict) -> str:
    escape = html.escape
    findings = ""
    for finding in case["findings"]:
        links = " ".join(f'<a href="#{escape(ref, quote=True)}">{escape(ref)}</a>' for ref in finding["evidence"])
        findings += f"<article><h2>{escape(finding['title'])}</h2><p>{escape(finding['supplier_name'])}</p><p>{escape(finding['claim'])}</p><strong>{pesos(finding['amount_centavos'], finding['currency'])}</strong><pre>{escape(finding['calculation']['calculation'])}</pre><p>{links}</p></article>"
    leads = "".join(f"<li><b>{escape(lead['id'])} · {escape(lead['state'])}</b>: {escape(lead['reason'])}</li>" for lead in case["leads"])
    evidence = "".join(f'<article id="{escape(ref, quote=True)}"><h3>{escape(ref)}</h3><pre>{escape(json.dumps(row, indent=2, ensure_ascii=False))}</pre></article>' for ref, row in data.evidence.items())
    limitations = "".join(f"<li>{escape(value)}</li>" for value in case["limitations"])
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Forensic Auditor · Case file</title>
<style>body{{font:15px/1.6 system-ui;max-width:960px;margin:50px auto;padding:0 24px;color:#172d27}}h1{{font-size:36px}}article{{border-top:1px solid #ccd6d0;padding:20px 0;break-inside:avoid}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}a{{color:#176c50}}@media print{{body{{margin:0}}}}</style>
<h1>The Forensic Auditor</h1><p>Case {escape(data.identity)}</p><p>{escape(case['mode'])} · {escape(case['status'])}</p>
<p>{escape(case.get('completion_reason', 'Investigation in progress.'))}</p><h2>Verified findings</h2>{findings or '<p>No verified finding published.</p>'}
<p>Amounts are excess-settlement exposure, not demonstrated loss. Currencies are separate; payment allocations are not reused.</p>
<h2>Lead dispositions</h2><ul>{leads}</ul><h2>Limitations</h2><ul>{limitations}</ul><h2>Original evidence</h2>{evidence}</html>"""
