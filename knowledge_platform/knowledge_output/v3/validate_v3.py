"""Check integrity and publication safety of the complete v3 snapshot."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

V3 = Path(__file__).resolve().parent
V2 = V3.parent / 'v2'
M = V3 / 'machine'
EXPORT = V3 / 'runtime_export'
errors = []

def check(ok, message):
    if not ok:errors.append(message)

def read(path):
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():continue
        try:record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f'{path}:{number}: invalid JSON: {exc}')
            continue
        check(isinstance(record, dict), f'{path}:{number}: JSONL row not object')
        if isinstance(record, dict):rows.append(record)
    return rows

data = {p.stem: read(p) for p in M.glob('*.jsonl')}
public = {p.stem: read(p) for p in EXPORT.glob('*.jsonl')}
base_hashes = json.loads((V3 / 'v2_baseline_hashes.json').read_text(encoding='utf-8'))
for name, digest in base_hashes.items():
    check(hashlib.sha256((V2 / 'machine' / name).read_bytes()).hexdigest() == digest,
          f'v2 modified: {name}')

source_ids = {x['source_id'] for x in data['sources']}
org_ids = {x['organization_id'] for x in data['organizations']}
territory_ids = {x['territory_id'] for x in data['territories']}
check(len(source_ids) == len(data['sources']), 'duplicate source ID')
check(len(org_ids) == len(data['organizations']), 'duplicate organization ID')
check(len(territory_ids) == len(data['territories']), 'duplicate territory ID')
unique_keys = {'contacts':'contact_id','competences':'competence_id','services':'service_id',
               'procedures':'procedure_id','routing_rules':'routing_rule_id','rag_chunks':'chunk_id',
               'qa_pairs_ru':'qa_id','qa_pairs_ky':'qa_id','aliases':'alias_id',
               'conflicts':'conflict_id','staff_roles':'staff_role_id',
               'real_query_examples':'example_id','escalation_rules':'escalation_rule_id',
               'service_territories':'relation_id','topic_aliases':'topic_alias_id',
               'appeal_categories':'category_id'}
for name, key in unique_keys.items():
    rows = data[name]
    check(len({r.get(key) for r in rows}) == len(rows), f'duplicate {key} in {name}')
    for row in rows:
        label = f'{name}:{row.get(key)}'
        ids = row.get('source_ids') or ([row['document_id']] if row.get('document_id') else [])
        check(bool(ids), f'{label}: missing source')
        for sid in ids:check(sid in source_ids, f'{label}: unknown source {sid}')
        for provenance in row.get('provenance', []):
            check(provenance.get('source_id') in source_ids, f'{label}: bad provenance source')
            if str(row.get(key,'')).startswith('v3-'):
                check(bool(provenance.get('locator')), f'{label}: missing locator')
        for oid in ([row.get('organization_id'),row.get('target_organization_id'),
                     row.get('primary_candidate_id')] + row.get('organization_ids', []) +
                    row.get('responsible_organization_ids', [])):
            if oid:check(oid in org_ids, f'{label}: unknown org {oid}')
        for tid in [row.get('territory_id'), *row.get('territory_scope', [])]:
            if tid:check(tid in territory_ids, f'{label}: unknown territory {tid}')

for row in data['contacts']:
    label = row['contact_id']
    check(bool(row.get('provenance')), f'contact without provenance {label}')
    check(row.get('visibility') in ('PUBLIC','INTERNAL_ONLY'), f'bad visibility {label}')
    check(row.get('status') in ('SOURCE_CONFIRMED','CONFLICT','AMBIGUOUS'), f'bad status {label}')
    if row.get('visibility') == 'PUBLIC':
        check(row.get('status') == 'SOURCE_CONFIRMED', f'public nonconfirmed contact {label}')
    if row.get('status') in ('CONFLICT','AMBIGUOUS'):
        check(row.get('visibility') == 'INTERNAL_ONLY', f'unsafe conflict contact {label}')
for row in data['staff_roles']:
    check(row['visibility'] == 'INTERNAL_ONLY', f'public staff role {row["staff_role_id"]}')
for row in data['procedures']:
    check(bool(row.get('steps')), f'empty procedure {row["procedure_id"]}')
    check(row.get('completeness') in ('FULL','PARTIAL'), f'bad procedure completeness {row["procedure_id"]}')
for row in data['routing_rules']:
    check(row.get('production_status') != 'AUTO_ASSIGN', f'automatic route {row["routing_rule_id"]}')
    if row['routing_rule_id'].startswith('v3-'):
        check(bool(row.get('territory_scope')), f'new route without territory {row["routing_rule_id"]}')
        check(row.get('production_status') == 'SUGGESTION_ONLY', f'new route not suggestion {row["routing_rule_id"]}')
for row in data['service_territories']:
    check(row['territory_id'] in territory_ids, f'unknown service zone {row["relation_id"]}')
    if next(t for t in data['territories'] if t['territory_id'] == row['territory_id']).get('parent_status') == 'CONFLICT':
        check(row['status'] == 'CONFLICT', f'zone parent conflict exposed {row["relation_id"]}')
for row in data['rag_chunks']:
    if row['chunk_id'].startswith('v3-'):
        check(bool(row.get('locator')), f'new RAG chunk without locator {row["chunk_id"]}')
        if row['topic'] == 'routing':check(bool(row.get('territory_scope')), f'routing chunk without territory {row["chunk_id"]}')

new_sources = [x for x in data['sources'] if x['source_id'].startswith('NEW-') and int(x['source_id'][4:]) >= 248]
check(len(new_sources) == 10, 'October batch not fully registered')
check(sum(x.get('duplicate_of') == 'SRC-183' for x in new_sources) == 2, 'Noorken duplicate mapping wrong')
check(sum(not x.get('duplicate_of') for x in new_sources) == 8, 'unique source count wrong')
for row in new_sources:
    path = V3 / row['v3_copy']
    check(path.is_file(), f'new source copy missing {row["source_id"]}')
    if path.is_file():check(hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'],
                            f'new source copy mismatch {row["source_id"]}')

required_export = ('sources','organizations','competences','contacts','routing_rules',
                   'qa_pairs_ru','qa_pairs_ky','rag_chunks','aliases')
check(set(public) == set(required_export), 'runtime export file set wrong')
if set(public) == set(required_export):
    check(len(public['contacts']) == sum(c['visibility'] == 'PUBLIC' and c['status'] == 'SOURCE_CONFIRMED'
                                         for c in data['contacts']), 'runtime contacts count wrong')
    for row in public['contacts']:
        check(row['visibility'] == 'PUBLIC' and row['status'] == 'SOURCE_CONFIRMED',
              f'nonpublic contact in runtime {row["contact_id"]}')
        if row['type'] in ('working_hours','reception_hours'):
            check(row.get('working_hours') == row['value'], f'hours parser mismatch {row["contact_id"]}')
    for row in public['routing_rules']:
        if row['routing_rule_id'].startswith('v3-'):
            check(row.get('route_type') == 'SINGLE' and row.get('target_organization_id') and row.get('territory_scope'),
                  f'unsafe new runtime route {row["routing_rule_id"]}')
    private_numbers = {''.join(re.findall(r'\d', c['value'])) for c in data['contacts']
                       if c['type'] == 'phone' and c['visibility'] == 'INTERNAL_ONLY'}
    for row in public['contacts']:
        if row['type'] == 'phone':
            check(''.join(re.findall(r'\d', row['value'])) not in private_numbers,
                  f'public personal phone {row["contact_id"]}')
    for name in ('qa_pairs_ru','qa_pairs_ky','rag_chunks'):
        for row in public[name]:
            text = row.get('text') or row.get('answer') or ''
            for candidate in re.findall(r'\+?\d[\d\s()\-]{7,}\d', text):
                check(''.join(re.findall(r'\d', candidate)) not in private_numbers,
                      f'private number in public {name}:{row.get("chunk_id") or row.get("qa_id")}')
    mombekov = 'org-mombekov-aiyl-okmotu-d36a51d'
    check(not any(c['organization_id'] == mombekov for c in public['contacts']),
          'Mombekov contact exposed despite Нет')
    shamal = 'org-shamalduu-sai-shaardyk-meriya-9de9534'
    check(not any(c['organization_id'] == shamal and c['type'] == 'address' for c in public['contacts']),
          'conflicting Shamalduu address exposed')

report = {'result': 'PASS' if not errors else 'FAIL', 'errors': errors,
          'full_counts': {name: len(rows) for name, rows in data.items()},
          'runtime_counts': {name: len(rows) for name, rows in public.items()},
          'new_sources': Counter(x['status'] for x in new_sources)}
(V3 / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
if errors:raise SystemExit(1)
