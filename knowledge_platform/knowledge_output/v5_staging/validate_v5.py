"""Full source and organization integrity check for staged V5 JSONL."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "runtime_export"
files = {p.stem: [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
         for p in DATA.glob("*.jsonl")}
manifest = json.loads((DATA / "knowledge_manifest.json").read_text(encoding="utf-8"))
structured = json.loads((DATA / "structured_manifest.json").read_text(encoding="utf-8"))
for record in (manifest, structured):
    assert record["knowledge_version"] == manifest["knowledge_version"]
    for name, digest in record["files"].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == digest, name

orgs = {r["organization_id"] for r in files["organizations"]}
sources = {r["source_id"] for r in files["sources"]}
territories = {r["territory_id"] for r in files["territories"]}
assert len(orgs) == len(files["organizations"])
assert len(sources) == len(files["sources"])
assert len(territories) == len(files["territories"])
for stem, records in files.items():
    for record in records:
        if record.get("organization_id"):
            assert record["organization_id"] in orgs, (stem, record)
        for source_id in record.get("source_ids") or []:
            assert source_id in sources, (stem, source_id)
        for prov in record.get("provenance") or []:
            assert prov["source_id"] in sources, (stem, prov)
            if str(prov["source_id"]).startswith("NEW-"):
                assert prov.get("locator"), (stem, prov)
        if record.get("territory_id") and stem != "territories":
            assert record["territory_id"] in territories, (stem, record)
for c in files["contacts"]:
    assert c.get("source_ids") and c.get("provenance"), c.get("contact_id")
for stem in ("procedures", "routing_rules"):
    for row in files[stem]:
        assert row.get("source_ids") or row.get("provenance"), (stem, row)
audit = [json.loads(line) for line in (ROOT / "runtime_support" /
        "public_contact_attribution_records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
assert len(audit) == len(files["contacts"])
assert {r["contact_record_id"] for r in audit} == {r["contact_id"] for r in files["contacts"]}
assert all(r["knowledge_version"] == manifest["knowledge_version"] for r in audit)
conflicts = files["conflicts"]
assert len(conflicts) == 4
index = json.loads((ROOT / "staged_bot_index" / "index_manifest.json").read_text(encoding="utf-8"))
assert index["knowledge_version"] == manifest["knowledge_version"]
assert index["count"] == len(files["rag_chunks"])
result = {"version": manifest["knowledge_version"], "jsonl_files": len(files),
          "organizations": len(orgs), "sources": len(sources), "contacts": len(files["contacts"]),
          "public_contacts": sum(x.get("visibility") == "PUBLIC" for x in files["contacts"]),
          "conflicts": len(conflicts), "index_rows": index["count"], "status": "PASS"}
(ROOT / "validation_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
