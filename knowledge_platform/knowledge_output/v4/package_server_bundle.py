"""Package the staged V4 bot data only after its embedding index is ready."""
from __future__ import annotations
import json
import tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STAGE=ROOT/'staging_bot'
data=STAGE/'knowledge/data'
index=STAGE/'knowledge/index'
manifest=json.loads((data/'knowledge_manifest.json').read_text(encoding='utf8'))
index_manifest_path=index/'index_manifest.json'
if not index_manifest_path.exists():raise SystemExit('INDEX_REBUILD_REQUIRED: no index manifest')
index_manifest=json.loads(index_manifest_path.read_text(encoding='utf8'))
if index_manifest.get('knowledge_version')!=manifest['knowledge_version']:
    raise SystemExit('INDEX_REBUILD_REQUIRED: index version mismatch')
if index_manifest.get('count')!=manifest['rag_chunks_count'] or not (index/'embeddings.npy').exists():
    raise SystemExit('INDEX_REBUILD_REQUIRED: missing vectors or count mismatch')
audit=[json.loads(x) for x in (STAGE/'docs/public_contact_attribution_records.jsonl').read_text(encoding='utf8').splitlines() if x.strip()]
contacts=[json.loads(x) for x in (data/'contacts.jsonl').read_text(encoding='utf8').splitlines() if x.strip()]
if len(audit)!=len(contacts) or any(x.get('knowledge_version')!=manifest['knowledge_version'] or x.get('status')!='VALID' for x in audit):
    raise SystemExit('CONTACT_AUDIT_STALE')
archive=ROOT/'knowledge-v4-demo.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for relative in ('knowledge/data','knowledge/index','docs/public_contact_attribution_records.jsonl',
                     'docs/public_contact_attribution_audit.md'):
        path=STAGE/relative
        if not path.exists():raise SystemExit(f'Missing release file: {relative}')
        tar.add(path,arcname=relative)
print(archive)
