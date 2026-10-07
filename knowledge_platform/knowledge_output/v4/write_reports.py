from __future__ import annotations
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'v3'
M=ROOT/'machine'
FILES=('sources.jsonl','organizations.jsonl','competences.jsonl','contacts.jsonl',
 'routing_rules.jsonl','qa_pairs_ru.jsonl','qa_pairs_ky.jsonl','rag_chunks.jsonl','aliases.jsonl')
def rows(v,name):
 p=v/'machine'/f'{name}.jsonl';return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines() if x.strip()]
def version(v):
 p=v/'runtime_export'
 return hashlib.sha256(''.join(hashlib.sha256((p/n).read_bytes()).hexdigest() for n in FILES).encode()).hexdigest()[:16]
build=json.loads((ROOT/'build_metrics.json').read_text(encoding='utf8'))
validation=json.loads((ROOT/'validation.json').read_text(encoding='utf8'))
compat=json.loads((ROOT/'bot_compatibility.json').read_text(encoding='utf8'))
v3=version(BASE);v4=version(ROOT)
source_rows=rows(ROOT,'sources')
new_sources=[s for s in source_rows if s['source_id'].startswith('NEW-') and int(s['source_id'].split('-')[1])>=258]

def categories(contacts):
 c=Counter()
 for x in contacts:
  if x.get('status') in ('CONFLICT','AMBIGUOUS'):c[x['status']]+=1
  elif x.get('visibility')=='PUBLIC':c['PUBLIC']+=1
  else:c['INTERNAL_ONLY']+=1
 return c
old=categories(rows(BASE,'contacts'));new=categories(rows(ROOT,'contacts'))
metrics=[('sources','sources'),('organizations','organizations'),('contacts total','contacts'),
 ('PUBLIC','PUBLIC'),('INTERNAL_ONLY','INTERNAL_ONLY'),('CONFLICT','CONFLICT'),('AMBIGUOUS','AMBIGUOUS'),
 ('staff','staff_roles'),('territories','territories'),('competences','competences'),('services','services'),
 ('procedures','procedures'),('routing rules','routing_rules'),('RAG chunks','rag_chunks'),
 ('real query examples','real_query_examples'),('escalation rules','escalation_rules'),
 ('district profiles','district_profiles'),('conflicts records','conflicts')]
lines=['# Knowledge promotion v4','',f'V3 runtime version: `{v3}`. V4 runtime version: `{v4}`.','',
 'V3 machine and runtime files were left unchanged. Eight incoming DOCX files have unique SHA-256 hashes; exact duplicates: **0**. '
 'Three are filled variants of a shared information-request form. Their filled responses are ingested as source facts; blank prompts are not treated as facts.','',
 '| Dataset | V3 | V4 | Delta |','|---|---:|---:|---:|']
for label,name in metrics:
 if name in ('PUBLIC','INTERNAL_ONLY','CONFLICT','AMBIGUOUS'):a,b=old[name],new[name]
 else:a,b=build['v3'].get(name,0),build['v4'].get(name,0)
 lines.append(f'| {label} | {a} | {b} | {b-a:+d} |')
lines.extend(['','Runtime export: **'+str(validation['public_contacts'])+'** audited PUBLIC contacts, **'+str(validation['runtime_counts']['routing_rules'])+
 '** advisory routing rules, **'+str(validation['runtime_counts']['rag_chunks'])+'** RAG chunks. '
 'One legacy PUBLIC contact with no locator is suppressed.','',
 '## New files and source relations','',
 '| Source | File | SHA-256 | Relation | Promoted facts |','|---|---|---|---|---|'])
for s in new_sources:
 sid=s['source_id'];relation=s.get('source_relation','NEW_SOURCE')
 if s.get('relation_to'):relation+=f' `{s["relation_to"]}`'
 counts=build['by_source'].get(sid,{})
 facts=', '.join(f'{k}: {v}' for k,v in counts.items()) or 'Existing contact provenance only'
 lines.append(f'| {sid} | {s["file_name"]} | `{s["sha256"]}` | {relation} | {facts} |')
lines.extend(['','## Source findings','',
 '- `NEW-258`, `NEW-259`: Toktogul district and city contacts, village coverage, municipal service routing, district profile and escalation.',
 '- `NEW-260`: Tash-Komur city contacts, office hours, appeal submission procedure, utility routes. The contradictory phone is preserved as a conflict.',
 '- `NEW-261`: a filled Mayluu-Suu mayor contact confirms and adds provenance to an existing phone; blank form fields were ignored.',
 '- `NEW-262`: health institution addresses, competences, services and internal staff roles. Named staff mobiles were not published.',
 '- `NEW-263`, `NEW-264`: Ala-Buka administration and four ayyl-area contacts, village memberships, explicit municipal routing, escalation and staff roles.',
 '- `NEW-265`: Suzak district administration, institution registry, service zones and road/electricity routing. Phone/fax and road-zone conflicts remain unresolved.',
 '',f'Validation: **{validation["result"]}** ({validation["error_count"]} errors); source-value rechecks: **{validation["new_source_value_checks"]}**. '
 f'Bot staged parser: **{compat["result"]}**, {compat["public_contacts_approved"]} contacts approved. '
 'The unchanged bot passed 71 offline unit tests covering knowledge, turn resolution, golden dialogues and CRM. '
 'Current bot remains on its previous working version; embedding index has not been rebuilt.',''])
(ROOT/'PROMOTION_V4_REPORT.md').write_text('\n'.join(lines),encoding='utf8')

review=['# V4 review required','',
 'These records remain in machine data. Conflict and ambiguous contacts are excluded from the public export.','',
 '## Conflicting facts','',
 '- `NEW-260`: Tash-Komur mayor phone is `03745 50030` in paragraph 0 and `0745 50030` in table 0 row 4. Neither is published.',
 '- `NEW-265` versus the earlier Suzak source: `037 48 50075` is labelled phone in paragraph 25 and fax in the older record. Both attributions are suppressed.',
 '- `NEW-265`: Kök-Art road service zone appears under DEP-31 and DEP-22 (paragraphs 84, 86). Neither is selected automatically.',
 '', '## Ambiguous or incomplete','']
review.extend('- '+x for x in build['review'])
review.extend(['- `NEW-264` named enterprise managers and specialists have private staff numbers. The Ынтымак number is also explicitly labelled a general/official contact in table 3 row 1, so that institutional contact remains public.',
 '- `NEW-262` named medical employees have private staff roles; institution addresses and services remain public.',
 '- `NEW-259` has a sentence about a Suzak akim inside a Toktogul section. It was not attached to the Toktogul administration.',
 '- `NEW-260` appeal procedure is PARTIAL; no response deadline is stated.',
 '- Several new health and district organizations have no documented working hours. No hours were invented.',
 '- `SRC-135` old contact lacks a source locator; it remains in machine data but is suppressed from v4 public runtime.',
 '- Eleven offline queries have no exact scoped route or contain a conflict; see `OFFLINE_QUERY_COVERAGE.md`.',''])
(ROOT/'V4_REVIEW_REQUIRED.md').write_text('\n'.join(review),encoding='utf8')

bot_manifest=json.loads((Path('C:/Users/user/PycharmProjects/AI-presentation/tg_bot-')/'knowledge/data/knowledge_manifest.json').read_text(encoding='utf8'))
index_manifest=json.loads((Path('C:/Users/user/PycharmProjects/AI-presentation/tg_bot-')/'knowledge/index/index_manifest.json').read_text(encoding='utf8'))
bot_report=['# Local bot update readiness','',
 f'Current bot data/index: `{bot_manifest["knowledge_version"]}` / `{index_manifest["knowledge_version"]}`, '
 f'{bot_manifest["rag_chunks_count"]} chunks, model `{index_manifest["model"]}`.',
 f'V4 staged data: `{v4}`, {validation["runtime_counts"]["rag_chunks"]} chunks. '
 f'Embedding operation estimate: {validation["runtime_counts"]["rag_chunks"]} texts in '
 f'{(validation["runtime_counts"]["rag_chunks"]+63)//64} batches using `{index_manifest["model"]}`.',
 '', 'The local production bot was not synced because this task does not authorize paid embeddings. '
 'A sync without a matching index would remove semantic retrieval until rebuilding. '
 'The v4 data and contact audit were synced only to `v4/staging_bot` and passed parser checks.',
 '', 'The server archive requiring `knowledge/index/*` is not deployable yet. '
 'Build the embedding index and complete bot acceptance before packaging it.', '']
(ROOT/'BOT_UPDATE_READINESS.md').write_text('\n'.join(bot_report),encoding='utf8')
print('reports written',v3,v4)
