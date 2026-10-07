"""Hard validation gates for pilot knowledge v2."""
import collections
import hashlib
import json
import re
from pathlib import Path

V2=Path(__file__).resolve().parent
OUT=V2.parent
M=V2/'machine'
def load(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
data={p.stem:load(p) for p in M.glob('*.jsonl')}
errors=[]
def check(ok,message):
    if not ok:errors.append(message)
base=json.loads((V2/'baseline_hashes.json').read_text(encoding='utf-8'))
for rel,sha in base.items():check(hashlib.sha256((OUT/rel).read_bytes()).hexdigest()==sha,'baseline changed: '+rel)

sources={x['source_id'] for x in data['sources']}
organizations={x['organization_id'] for x in data['organizations']}
territories={x['territory_id'] for x in data['territories']}
check(len(sources)==len(data['sources']),'duplicate source ID')
check(len(organizations)==len(data['organizations']),'duplicate organization ID')
for kind,idkey in [('contacts','contact_id'),('competences','competence_id'),('routing_rules','routing_rule_id'),
                   ('services','service_id'),('procedures','procedure_id'),('rag_chunks','chunk_id'),
                   ('qa_pairs_ru','qa_id'),('qa_pairs_ky','qa_id')]:
    rows=data[kind]
    check(len({x[idkey] for x in rows})==len(rows),'duplicate ID in '+kind)
    for x in rows:
        check(bool(x.get('source_ids') or x.get('document_id')),'missing source '+kind+' '+x[idkey])
        for sid in x.get('source_ids',([x['document_id']] if x.get('document_id') else [])):
            check(sid in sources,'unknown source '+kind+' '+x[idkey]+' '+sid)
        oid=x.get('organization_id') or x.get('target_organization_id')
        if oid:check(oid in organizations,'unknown org '+kind+' '+x[idkey])
        for oid in x.get('organization_ids',[]):check(oid in organizations,'unknown org '+kind+' '+x[idkey])
        tid=x.get('territory_id')
        if tid:check(tid in territories,'unknown territory '+kind+' '+x[idkey]+' '+tid)

for c in data['contacts']:
    check(bool(c.get('provenance')),'contact without provenance '+c['contact_id'])
    check(c.get('visibility') in ('PUBLIC','INTERNAL_ONLY'),'bad contact visibility '+c['contact_id'])
    check(c.get('status') in ('SOURCE_CONFIRMED','CONFLICT','AMBIGUOUS'),'bad contact status '+c['contact_id'])
    if c['visibility']=='PUBLIC':check(c['status']=='SOURCE_CONFIRMED','public contact not confirmed '+c['contact_id'])
    if c['status']=='CONFLICT':check(c['visibility']=='INTERNAL_ONLY','conflict exposed '+c['contact_id'])
for p in data['procedures']:
    check(bool(p.get('steps')),'procedure without steps '+p['procedure_id'])
    check(p['completeness'] in ('FULL','PARTIAL'),'bad procedure completeness '+p['procedure_id'])
for r in data['routing_rules']:
    check(bool(r['source_ids']),'route without source '+r['routing_rule_id'])
    check(r.get('production_status')!='AUTO_ASSIGN','automatic assignment slipped in '+r['routing_rule_id'])
for c in data['contacts']:
    if 'SRC-205' in c['source_ids'] and c['type']=='phone' and re.search(r'(?<!\d)(?:\+996\s*)?0[2579]\d',c['value']):
        check(c['visibility']!='PUBLIC','SRC-205 mobile public '+c['contact_id'])
public_values={c['value'] for c in data['contacts'] if c['visibility']=='INTERNAL_ONLY' and c['type']=='phone' and len(re.sub(r'\D','',c['value']))>=9}
for ch in data['rag_chunks']:
    if ch.get('visibility')!='PUBLIC':continue
    for value in public_values:
        check(value not in ch['text'],'private number in public RAG chunk '+ch['chunk_id'])
check(len(data['conflicts'])>=6,'conflicts missing')
review=load(V2/'review/recoverable_dispositions.jsonl')
check(len(review)==194 and len({x['fact_id'] for x in review})==194,'recoverable review incomplete')
check(len(data['sources'])==247,'new source registry incomplete')
check(len([s for s in data['sources'] if s['source_id'].startswith('NEW-')])==17,'new sources incomplete')
for s in data['sources']:
    if s['source_id'].startswith('NEW-') and not s.get('duplicate_of'):
        path=V2/s['v2_copy'];check(path.is_file(),'new source copy missing '+s['source_id'])
        if path.is_file():check(hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256'],'new source hash mismatch '+s['source_id'])
check(len(data['public_contacts'])==sum(c['visibility']=='PUBLIC' and c['status']=='SOURCE_CONFIRMED' for c in data['contacts']),'public contact export mismatch')
check(len(data['hours'])==sum(c['type'] in ('working_hours','reception_hours') for c in data['contacts']),'hours export mismatch')
runtime=V2/'runtime_export'
runtime_files=('sources','organizations','competences','contacts','routing_rules',
               'qa_pairs_ru','qa_pairs_ky','rag_chunks','aliases')
if runtime.is_dir():
    public={name:load(runtime/(name+'.jsonl')) for name in runtime_files}
    check(len(public['contacts'])==len(data['public_contacts']),'runtime contact count mismatch')
    for c in public['contacts']:
        check(c.get('visibility')=='PUBLIC' and c.get('status')=='SOURCE_CONFIRMED',
              'nonpublic runtime contact '+c['contact_id'])
        if c['type']=='working_hours':
            check(c.get('working_hours')==c['value'],'runtime hours parser incompatibility '+c['contact_id'])
    for r in public['routing_rules']:
        check(r.get('pilot_status')=='SOURCE_CONFIRMED_SUGGESTION' and r.get('production_status')!='AUTO_ASSIGN',
              'unsafe runtime route '+r['routing_rule_id'])
else:
    errors.append('runtime_export missing')
report={'result':'PASS' if not errors else 'FAIL','errors':errors,
        'counts':{k:len(v) for k,v in data.items()},
        'contacts_by_type':dict(collections.Counter(c['type'] for c in data['contacts'])),
        'public_contacts_by_type':dict(collections.Counter(c['type'] for c in data['public_contacts'])),
        'original_files_unchanged':len(base)}
(V2/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
if errors:raise SystemExit(1)
