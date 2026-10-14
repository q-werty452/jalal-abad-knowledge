"""Reuse V4 vectors only when V5 RAG bytes and row count are identical."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOT = Path(r"C:\Users\user\PycharmProjects\AI-presentation\tg_bot-")
V4 = ROOT.parent / "v4" / "runtime_export"
V5 = ROOT / "runtime_export"
STAGED = ROOT / "staged_bot_index"
DATA = ROOT / "staged_bot_data"
INDEX = BOT / "knowledge" / "index"

old_chunks = (V4 / "rag_chunks.jsonl").read_bytes()
new_chunks = (V5 / "rag_chunks.jsonl").read_bytes()
if old_chunks != new_chunks:
    raise ValueError("RAG chunks changed; new embeddings are required")
old_manifest = json.loads((INDEX / "index_manifest.json").read_text(encoding="utf-8"))
v4_manifest = json.loads((V4 / "knowledge_manifest.json").read_text(encoding="utf-8"))
v5_manifest = json.loads((V5 / "knowledge_manifest.json").read_text(encoding="utf-8"))
if old_manifest["knowledge_version"] != v4_manifest["knowledge_version"] or old_manifest["count"] != 667:
    raise ValueError("Current index is not the verified V4 index")
chunks = json.loads((INDEX / "chunks.json").read_text(encoding="utf-8"))
if len(chunks) != old_manifest["count"]:
    raise ValueError("Current index chunks mismatch")
export_chunks = [json.loads(line) for line in old_chunks.decode("utf-8").splitlines() if line.strip()]
if chunks != export_chunks:
    raise ValueError("Current indexed chunks do not match V4 export")
STAGED.mkdir(parents=True, exist_ok=True)
shutil.copyfile(INDEX / "embeddings.npy", STAGED / "embeddings.npy")
shutil.copyfile(INDEX / "chunks.json", STAGED / "chunks.json")
new_index_manifest = dict(old_manifest)
new_index_manifest["knowledge_version"] = v5_manifest["knowledge_version"]
new_index_manifest["reused_from_version"] = v4_manifest["knowledge_version"]
new_index_manifest["rag_sha256"] = hashlib.sha256(new_chunks).hexdigest()
(STAGED / "index_manifest.json").write_text(json.dumps(new_index_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
shutil.copyfile(ROOT / "runtime_support" / "public_contact_attribution_records.jsonl",
                DATA / "public_contact_attribution_records.jsonl")
print(json.dumps({"version": v5_manifest["knowledge_version"], "chunks": len(chunks),
                  "model": old_manifest["model"], "vectors_reused": True}, ensure_ascii=False))
