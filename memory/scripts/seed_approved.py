#!/usr/bin/env python3
"""RW-1: re-ingest ONLY approved batches into a running Memory service.

Usage: python scripts/seed_approved.py [--base http://localhost:8092] [--dry-run]
Approved: seed/batch-003.jsonl, seed/verification-test-fixtures.jsonl.
Permanent exclusions are refused client-side too (server enforces them as well).
"""
import argparse, json, sys, urllib.request
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "seed"
FILES = ["batch-003.jsonl", "verification-test-fixtures.jsonl"]
EXCLUDE = ("ha-e9572b47", "ha-6a3868004d8868d9b08acd9e", "batch-002")

def load(p):
    for line in p.read_text().splitlines():
        if line.strip():
            yield json.loads(line)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8092")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    total, bad = 0, 0
    for f in FILES:
        by_proj = {}
        for r in load(SEED / f):
            blob = json.dumps(r)
            if any(x in blob for x in EXCLUDE):
                print(f"REFUSED excluded record in {f}: {r.get('chunk_id')}"); bad += 1; continue
            md = {k: v for k, v in r.items() if k not in ("text", "chunk_id", "record_id", "project_id")}
            md["seed_source"] = f
            by_proj.setdefault(r["project_id"], []).append({
                "id": r["chunk_id"], "record_id": r.get("record_id"), "text": r["text"],
                "project_id": r["project_id"], "highlight_score": float(r.get("highlight_score", 0.5)),
                "source_type": r.get("source_type", "documentation"),
                "redaction_flag": bool(r.get("redaction_flag", False)), "metadata": md})
        for proj, recs in by_proj.items():
            total += len(recs)
            if a.dry_run:
                print(f"[dry-run] {f} project={proj} n={len(recs)}"); continue
            req = urllib.request.Request(f"{a.base}/memory/ingest", method="POST",
                data=json.dumps({"project_id": proj, "records": recs}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                out = json.loads(resp.read())
            print(f"{f} project={proj} -> {json.dumps(out)[:300]}")
            if out.get("blocked_quarantine"): bad += 1
    print(f"seed done: {total} records submitted, {bad} refused/blocked")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
