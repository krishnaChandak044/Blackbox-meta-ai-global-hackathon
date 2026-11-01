"""Readable, escaped PDF report from the same immutable export manifest."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def render_pdf(manifest: dict[str, Any], output_path: Path) -> None:
    """Render a self-contained summary PDF. No remote assets are loaded."""
    case = manifest["case"]
    media_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(item.get("original_filename", "")), item.get("byte_length", ""),
            html.escape(item.get("sha256", "")), html.escape(item.get("integrity", "unknown")))
        for item in manifest.get("media", [])) or "<tr><td colspan='4'>No source media</td></tr>"
    classes = manifest.get("provenance_classes", {})
    limitations = "".join(f"<li>{html.escape(str(item))}</li>" for item in manifest.get("limitations", []))
    claims = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str((item.get("claim") or {}).get("raw_text", ""))),
            html.escape(str((item.get("finding") or {}).get("verdict", "unreviewed"))),
            html.escape(str((item.get("finding") or {}).get("explanation", ""))))
        for item in manifest.get("claims", [])) or "<tr><td colspan='3'>No claim checks recorded</td></tr>"
    runs = "".join("<li>{} v{} · status {} · interval {}</li>".format(
        html.escape(row.get("model_name", "model")),
        html.escape(row.get("model_version", "")), html.escape(row.get("status", "unknown")),
        html.escape(row.get("interval_type", "unknown"))) for row in manifest.get("dynamics_runs", []))
    evidence_needs = "".join("<li>{}: {} — {}</li>".format(
        html.escape(item.get("id", "")), html.escape(item.get("state", "unknown")),
        html.escape((item.get("snapshot_json") or "")[:500])) for item in manifest.get("evidence_needs", []))
    reviewer_actions = "".join("<li>{} · {} · {} · {}</li>".format(
        html.escape(str(item.get("created_at", ""))), html.escape(item.get("action", "")),
        html.escape(item.get("actor", "")), html.escape(item.get("target_type", "")))
        for item in manifest.get("reviewer_actions", []))
    atlas = manifest.get("atlas", {})
    body = f"""<!doctype html><html><head><meta charset='utf-8'><style>
    @page {{ size: A4; margin: 18mm; @bottom-right {{ content: 'Blackbox review package · ' counter(page); font-size: 8pt; color: #666; }} }}
    body {{ font: 10pt sans-serif; color: #17202a; line-height: 1.4 }} h1,h2 {{ color: #102a43 }}
    .notice {{ border: 1px solid #bd7b00; background: #fff8e6; padding: 10px }}
    table {{ border-collapse: collapse; width: 100%; font-size: 8pt }} td,th {{ border: 1px solid #ccd4dc; padding: 5px; text-align: left; word-break: break-word }}
    </style></head><body>
    <h1>Evidence review package</h1><p>Case: {html.escape(case.get('title') or case['id'])}<br>
    Export: {html.escape(manifest['export_id'])}<br>Created: {html.escape(manifest['generated_at'])}</p>
    <div class='notice'><strong>Review aid, not a legal fault finding or certified forensic conclusion.</strong>
    Simulated paths and generated views are illustrative. Numerical intervals are not validated confidence intervals unless explicitly stated otherwise.</div>
    <h2>Source inventory and integrity</h2><table><thead><tr><th>File</th><th>Bytes</th><th>SHA-256</th><th>Export check</th></tr></thead><tbody>{media_rows}</tbody></table>
    <h2>Analysis record</h2><ul>{runs or '<li>No completed dynamics runs.</li>'}</ul>
    <h2>Claims and checks</h2><table><thead><tr><th>Claim</th><th>Finding</th><th>Explanation</th></tr></thead><tbody>{claims}</tbody></table>
    <h2>Evidence Rescue Radar</h2><ul>{evidence_needs or '<li>No evidence needs recorded.</li>'}</ul>
    <h2>Reviewer action history</h2><ul>{reviewer_actions or '<li>No reviewer actions recorded.</li>'}</ul>
    <h2>Prevention Atlas</h2><p>Included: {str(bool(atlas.get('included'))).lower()}. Contributions: {len(atlas.get('contributions', []))}. Atlas data is excluded unless separately opted in.</p>
    <h2>Provenance classes</h2><ul>{''.join(f'<li><b>{html.escape(k)}</b>: {int(v)} records</li>' for k,v in classes.items())}</ul>
    <h2>Limitations</h2><ul>{limitations or '<li>No additional limitations recorded.</li>'}</ul>
    <p>Machine-readable lineage and detailed model outputs are included in the companion JSON manifest (SHA-256 {html.escape(manifest['manifest_sha256'])}).</p>
    </body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from weasyprint import HTML
        HTML(string=body, base_url=None).write_pdf(str(output_path))
    except OSError:
        # Local development environments may not have WeasyPrint's native
        # Pango/GObject libraries. Keep export available with a valid,
        # text-only PDF; the companion JSON retains the complete Unicode data.
        _render_portable_pdf(manifest, output_path)


def _render_portable_pdf(manifest: dict[str, Any], output_path: Path) -> None:
    case = manifest["case"]
    lines = [
        "BLACKBOX EVIDENCE REVIEW PACKAGE",
        f"Case: {case.get('title') or case['id']}",
        f"Case ID: {case['id']}", f"Export ID: {manifest['export_id']}",
        f"Generated: {manifest['generated_at']}", "",
        "REVIEW AID — NOT A LEGAL FAULT FINDING.",
        "Simulated paths and generated views are illustrative.",
        "The JSON companion preserves complete Unicode source text.", "",
        "SOURCE INVENTORY AND INTEGRITY",
    ]
    for media in manifest.get("media", []):
        lines += [f"{media.get('original_filename')} | {media.get('byte_length')} bytes",
                  f"SHA-256: {media.get('sha256')} | {media.get('integrity')}"]
    lines += ["", "DYNAMICS RUNS"]
    for run in manifest.get("dynamics_runs", []):
        lines.append(f"{run.get('id')} | {run.get('model_name')} v{run.get('model_version')} | {run.get('status')} | {run.get('interval_type')}")
    lines += ["", "CLAIM CHECKS"]
    for item in manifest.get("claims", []):
        claim, finding = item["claim"], item.get("finding") or {}
        lines += [f"{finding.get('verdict', 'unreviewed')}: {claim.get('raw_text', '')}",
                  str(finding.get("explanation", ""))]
    lines += ["", "LIMITATIONS"] + [str(x) for x in manifest.get("limitations", [])]
    lines += ["", f"JSON manifest SHA-256: {manifest['manifest_sha256']}"]
    pages: list[list[str]] = []
    page: list[str] = []
    for line in lines:
        wrapped = [line[i:i + 92] for i in range(0, max(len(line), 1), 92)]
        for chunk in wrapped:
            page.append(chunk)
            if len(page) >= 48:
                pages.append(page)
                page = []
    if page or not pages:
        pages.append(page)
    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append((f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] /Count {len(pages)} >>").encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for index, page_lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        stream_lines = ["BT", "/F1 9 Tf", "48 790 Td", "13 TL"]
        for line in page_lines:
            safe = line.encode("cp1252", errors="replace").decode("cp1252")
            escaped = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines += [f"({escaped}) Tj", "T*"]
        stream_lines += ["ET"]
        stream = "\n".join(stream_lines).encode("cp1252", errors="replace")
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>").encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    output_path.write_bytes(output)
