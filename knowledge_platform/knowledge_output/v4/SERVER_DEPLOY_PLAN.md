# Knowledge v4 deployment and rollback

Status: **prepared, not deployable yet**. The 667 V4 RAG chunks require a new `text-embedding-3-small` index. No paid embedding call has been authorized, so the production bot and demo server remain on their working versions. Do not deploy a data-only V4 bundle.

## Build and local acceptance after explicit embedding authorization

Run in PowerShell. These commands keep the existing bot data, index, and contact audit in a versioned backup before changing them.

```powershell
$bot = 'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-'
$v4 = 'C:\Users\user\Desktop\knowledge_platform\knowledge_output\v4'
$py = Join-Path $bot 'venv\Scripts\python.exe'
$oldVersion = (& $py -c "import json; from pathlib import Path; print(json.loads((Path(r'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-')/'knowledge/data/knowledge_manifest.json').read_text(encoding='utf-8'))['knowledge_version'])").Trim()
$backup = Join-Path $v4 ('local_bot_backup_' + $oldVersion)
New-Item -ItemType Directory -Force -Path (Join-Path $backup 'knowledge'), (Join-Path $backup 'docs') | Out-Null
Copy-Item -LiteralPath (Join-Path $bot 'knowledge\data') -Destination (Join-Path $backup 'knowledge\data') -Recurse
Copy-Item -LiteralPath (Join-Path $bot 'knowledge\index') -Destination (Join-Path $backup 'knowledge\index') -Recurse
Copy-Item -LiteralPath (Join-Path $bot 'docs\public_contact_attribution_records.jsonl') -Destination (Join-Path $backup 'docs\public_contact_attribution_records.jsonl')
& $py (Join-Path $bot 'scripts\build_knowledge_index.py') --data (Join-Path $v4 'staging_bot\knowledge\data') --index (Join-Path $v4 'staging_bot\knowledge\index')
& $py (Join-Path $bot 'scripts\sync_knowledge.py') (Join-Path $v4 'runtime_export')
Copy-Item -LiteralPath (Join-Path $v4 'runtime_support\public_contact_attribution_records.jsonl') -Destination (Join-Path $bot 'docs\public_contact_attribution_records.jsonl')
Copy-Item -LiteralPath (Join-Path $v4 'staging_bot\knowledge\index\embeddings.npy'), (Join-Path $v4 'staging_bot\knowledge\index\chunks.json'), (Join-Path $v4 'staging_bot\knowledge\index\index_manifest.json') -Destination (Join-Path $bot 'knowledge\index')
& $py (Join-Path $bot 'scripts\knowledge_status.py')
& $py -m unittest discover -s (Join-Path $bot 'tests') -q
& $py (Join-Path $v4 'package_server_bundle.py')
```

The `knowledge_status.py` result must be `INDEX_READY` with V4 version `7fa44034af0e6322`, 667 chunks, and the staged contact audit must approve all public contacts. The current V4 version must be rechecked against `runtime_export/knowledge_manifest.json` if any data changes before execution. Package only after acceptance.

## Local rollback

Use the backup path printed or chosen above. Restore all three components together, then run `knowledge_status.py` and the smoke checks.

```powershell
$bot = 'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-'
$backup = 'C:\Users\user\Desktop\knowledge_platform\knowledge_output\v4\local_bot_backup_7602e001cb855a11'
Get-ChildItem -LiteralPath (Join-Path $backup 'knowledge\data') -File | Copy-Item -Destination (Join-Path $bot 'knowledge\data') -Force
Get-ChildItem -LiteralPath (Join-Path $backup 'knowledge\index') -File | Copy-Item -Destination (Join-Path $bot 'knowledge\index') -Force
Copy-Item -LiteralPath (Join-Path $backup 'docs\public_contact_attribution_records.jsonl') -Destination (Join-Path $bot 'docs\public_contact_attribution_records.jsonl') -Force
& (Join-Path $bot 'venv\Scripts\python.exe') (Join-Path $bot 'scripts\knowledge_status.py')
```

## Demo server deployment after local acceptance

Upload the completed `knowledge-v4-demo.tar.gz` to the server. The archive contains only `knowledge/data`, `knowledge/index`, and contact audit files. Telegram and WhatsApp use the same shared KnowledgeBase; no channel-specific copy is needed.

```bash
set -euo pipefail
APP=/srv/ai-presentation/tg_bot-
BUNDLE=/srv/ai-presentation/knowledge-v4-demo.tar.gz
BACKUP=/srv/ai-presentation/knowledge-backup-$(date +%Y%m%d-%H%M%S)
sudo systemctl stop aig2c-telegram
if systemctl is-active --quiet aig2c-whatsapp; then sudo systemctl stop aig2c-whatsapp; fi
mkdir -p "$BACKUP/knowledge" "$BACKUP/docs"
cp -a "$APP/knowledge/data" "$BACKUP/knowledge/data"
cp -a "$APP/knowledge/index" "$BACKUP/knowledge/index"
cp -a "$APP/docs/public_contact_attribution_records.jsonl" "$BACKUP/docs/public_contact_attribution_records.jsonl"
tar -xzf "$BUNDLE" -C "$APP"
"$APP/venv/bin/python" "$APP/scripts/knowledge_status.py"
sudo systemctl restart aig2c-crm
sudo systemctl start aig2c-telegram
if systemctl list-unit-files aig2c-whatsapp.service --no-legend | grep -q aig2c-whatsapp; then sudo systemctl start aig2c-whatsapp; fi
```

`knowledge_status.py` must say `INDEX_READY` with the archive's V4 version. Then send Telegram and WhatsApp smoke questions for a confirmed contact, a suppressed personal contact, and a territory-scoped route. If status or smoke fails, stop both channels and restore:

```bash
set -euo pipefail
APP=/srv/ai-presentation/tg_bot-
BACKUP=/srv/ai-presentation/knowledge-backup-YYYYMMDD-HHMMSS
sudo systemctl stop aig2c-telegram
if systemctl is-active --quiet aig2c-whatsapp; then sudo systemctl stop aig2c-whatsapp; fi
cp -a "$BACKUP/knowledge/data/." "$APP/knowledge/data/"
cp -a "$BACKUP/knowledge/index/." "$APP/knowledge/index/"
cp -a "$BACKUP/docs/public_contact_attribution_records.jsonl" "$APP/docs/public_contact_attribution_records.jsonl"
"$APP/venv/bin/python" "$APP/scripts/knowledge_status.py"
sudo systemctl start aig2c-telegram
if systemctl list-unit-files aig2c-whatsapp.service --no-legend | grep -q aig2c-whatsapp; then sudo systemctl start aig2c-whatsapp; fi
```

No server command has been executed.
