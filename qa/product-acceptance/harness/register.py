"""Write the defect register from one acceptance run."""

from __future__ import annotations

from pathlib import Path


def write_register(path: Path, summary: dict, findings: list[dict]) -> Path:
    order = {"blocker": 0, "major": 1, "minor": 2, "observation": 3}
    ranked = sorted(findings, key=lambda item: (order.get(item.get("severity", "major"), 9), item.get("id", "")))
    lines = [
        "# ATLAS independent product acceptance",
        "",
        "This register does not approve the product. A passing unit or browser regression is not acceptance.",
        "",
        f"Evidence directory: `{summary.get('evidence')}`.",
        f"Isolated API port: {summary.get('api_port')}. Isolated web port: {summary.get('web_port')}.",
        f"Database: `{summary.get('database')}`.",
        f"Shared API before/after: {summary.get('shared_before')} / {summary.get('shared_after')}.",
        f"Checks that held: {len(summary.get('passed') or [])}. Defects: {len(ranked)}.",
        "",
        "The acceptance process forced sandbox billing, cleared the n8n dispatch URL, refused live email, live campaigns, and live WhatsApp, and pointed SMTP at a closed local port. It did not open checkout, send a message, or create a charge. Assistant prompts stay in `qa/product-acceptance/sealed/` and are not copied into this register.",
        "",
        "Re-run with `qa/product-acceptance/run.ps1` after the implementation sessions finish. The same sealed bank scores the improved assistant.",
        "",
    ]
    if not ranked:
        lines.extend([
            "## Defects",
            "",
            "This run recorded no product defects. That is not approval until the register is reviewed against the improved build.",
            "",
        ])
    else:
        lines.extend(["## Defects", ""])
        for item in ranked:
            lines.extend([
                f"### {item.get('id')} — {item.get('severity')} — {item.get('title')}",
                "",
                f"- Module: {item.get('module')}",
                f"- Workstream: {item.get('workstream')}",
                "- Reproduction:",
            ])
            for step in item.get("steps") or []:
                lines.append(f"  - {step}")
            lines.extend([
                f"- Expected: {item.get('expected')}",
                f"- Actual: {item.get('actual')}",
                f"- Evidence: {item.get('evidence') or summary.get('evidence')}",
                f"- Acceptance: {item.get('acceptance')}",
                "",
            ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
