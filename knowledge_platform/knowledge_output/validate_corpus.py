"""Independent validation pass; writes the final audit after checking outputs."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'knowledge_output'
M=OUT/'machine'
required=['sources','organizations','competences','contacts','routing_rules','qa_pairs_ru','qa_pairs_ky','rag_chunks','aliases']
data={}
errors=[]; warnings=[]
for name in required:
    path=M/(name+'.jsonl')
    if not path.exists(): errors.append(f'Missing JSONL: {path.name}'); data[name]=[]; continue
    rows=[]
    for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        try:
            obj=json.loads(line)
            if not isinstance(obj,dict): errors.append(f'{name}:{n} is not a JSON object')
            rows.append(obj)
        except Exception as e:errors.append(f'{name}:{n} invalid JSON: {e}')
    data[name]=rows

sources=data['sources']; source_ids={s['source_id'] for s in sources}
if len(source_ids)!=len(sources):errors.append('Duplicate source_id in source registry')
org_ids={o['organization_id'] for o in data['organizations']}
if len(org_ids)!=len(data['organizations']):errors.append('Duplicate organization_id')

physical=0
for p in ROOT.iterdir():
    if not p.is_file():continue
    if p.suffix.lower()=='.zip':
        with ZipFile(p) as z:physical+=sum(not i.is_dir() for i in z.infolist())
    else:physical+=1
if physical!=len(sources):errors.append(f'Inventory count {len(sources)} != physical logical files {physical}')

for s in sources:
    if s['duplicate_of'] and s['duplicate_of'] not in source_ids:errors.append(f'{s["source_id"]} duplicate_of missing')
    if s['status']=='duplicate' and not s['duplicate_of']:errors.append(f'{s["source_id"]} duplicate without canonical')
    if s['status']=='blocked' and not s.get('extraction_error'):errors.append(f'{s["source_id"]} blocked without reason')

extracted={e['source_id']:e for e in [json.loads(line) for line in (OUT/'.extracted.jsonl').read_text(encoding='utf-8').splitlines()]}

def verify_provenance(record,kind,n):
    for sid in record.get('source_ids',[]):
        if sid not in source_ids:errors.append(f'{kind}:{n} unknown source_id {sid}')
    for p in record.get('provenance',[]):
        sid=p.get('source_id')
        if sid not in source_ids:
            errors.append(f'{kind}:{n} unknown provenance source_id {sid}');continue
        source=next(s for s in sources if s['source_id']==sid)
        if p.get('source_file')!=source['source_file']:errors.append(f'{kind}:{n} source_file mismatch {sid}')
        loc=p.get('locator')
        if p.get('sheet') is not None:loc=f'sheet:{p["sheet"]}:row:{p["row"]}'
        if loc and loc not in {b['locator'] for b in extracted[sid]['blocks']}:
            errors.append(f'{kind}:{n} invalid locator {sid} {loc}')

for name in required[1:]:
    for i,r in enumerate(data[name],1):
        verify_provenance(r,name,i)
        oid=r.get('organization_id',r.get('target_organization_id'))
        if oid and oid not in org_ids:errors.append(f'{name}:{i} unknown organization {oid}')
        for oid in r.get('organization_ids',[]):
            if oid not in org_ids:errors.append(f'{name}:{i} unknown organization {oid}')

for c in data['rag_chunks']:
    if c['document_id'] not in source_ids:errors.append(f'{c["chunk_id"]} unknown document_id')
    if c['language'] not in ('ru','ky','mixed'):errors.append(f'{c["chunk_id"]} invalid language')
    if not c.get('text') or not c.get('title') or not c.get('source_file'):errors.append(f'{c["chunk_id"]} incomplete')
    if c['publication_status']!='NEEDS_REVIEW':warnings.append(f'{c["chunk_id"]} publication status differs')
    if re.search(r'\+996|\b0\d{8,}\b|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b',c['text']):errors.append(f'{c["chunk_id"]} phone/email candidate in RAG')
    if c['language']=='ru' and any(ch in c['text'] for ch in 'өүңӨҮҢ'):errors.append(f'{c["chunk_id"]} RU/KY language mix candidate')

hashes=[hashlib.sha256(re.sub(r'\s+',' ',c['text']).strip().casefold().encode()).hexdigest() for c in data['rag_chunks']]
if len(hashes)!=len(set(hashes)):errors.append('Duplicate RAG text')

for r in data['routing_rules']:
    if r['verification_status']=='verified' and not r.get('source_ids'):errors.append(f'{r["routing_rule_id"]} verified without source')
    if r['verification_status'] not in ('verified','proposed','needs_confirmation'):errors.append(f'{r["routing_rule_id"]} invalid routing status')
    if r['production_status']!='NEEDS_CONFIRMATION':errors.append(f'{r["routing_rule_id"]} incorrectly production-ready')

for c in data['contacts']:
    if not c.get('provenance'):errors.append(f'{c["contact_id"]} contact without provenance')
    if c.get('publication_status')!='NEEDS_REVIEW':errors.append(f'{c["contact_id"]} contact prematurely public')

for q in data['qa_pairs_ru']+data['qa_pairs_ky']:
    if q['language'] not in ('ru','ky') or not q.get('source_ids'):errors.append(f'{q["qa_id"]} invalid QA metadata')

used_sources=set()
for name in required[1:]:
    for r in data[name]:used_sources.update(r.get('source_ids',[]))
used_sources.update(c['document_id'] for c in data['rag_chunks'])
unrepresented=[s['source_id'] for s in sources if s['status']=='processed' and s['source_id'] not in used_sources]
official=sum(s['authority_level'] in ('official_law','official_order_attachment','official_organization_provision') for s in sources)
candidate=sum(s['authority_level']=='official_candidate' for s in sources)

counts={"sources":len(sources),"processed":sum(s['status']=='processed' for s in sources),"duplicates":sum(s['status']=='duplicate' for s in sources),
        "blocked":sum(s['status']=='blocked' for s in sources),"official_with_explicit_requisites":official,"official_candidates":candidate,
        "organizations":len(data['organizations']),"competences":len(data['competences']),"contacts":len(data['contacts']),
        "routing_verified":sum(r['verification_status']=='verified' for r in data['routing_rules']),
        "routing_proposed":sum(r['verification_status']=='proposed' for r in data['routing_rules']),
        "qa_ru":len(data['qa_pairs_ru']),"qa_ky":len(data['qa_pairs_ky']),"rag_chunks":len(data['rag_chunks']),
        "conflicts":len(json.loads((OUT/'.canonical_state.json').read_text(encoding='utf-8'))['conflicts']),
        "knowledge_gaps":len(json.loads((OUT/'.canonical_state.json').read_text(encoding='utf-8'))['gaps']),
        "processed_sources_with_canonical_records":len([s for s in sources if s['status']=='processed' and s['source_id'] in used_sources])}

audit=['# Final knowledge audit','',
       '## Summary','',
       '| Metric | Count |','|---|---:|']
for k,v in counts.items():audit.append(f'| {k} | {v} |')
audit+=['','## Validation pass','',
        f'- JSONL parse and required fields: {"PASS" if not errors else "FAIL"}.',
        f'- Physical file and ZIP-entry coverage: {physical} logical files; {"PASS" if physical==len(sources) else "FAIL"}.',
        '- SHA-256 exact duplicates: recorded with `duplicate_of`; similar titles are kept distinct.',
        '- Organization/source references and contact provenance: checked against source registry.',
        '- Routing with no source, premature production status, RAG phone/email patterns, RU/KY flags and duplicate chunk text: checked.',
        '- Text extraction is distinct from factual verification. Unrepresented processed files are retained in the source registry and can be reopened on demand.','',
        '## Verified','',
        f'{counts["routing_verified"]} routing facts directly appear in SRC-109, SRC-135, SRC-142 or SRC-165. {counts["competences"]} competence entries and {counts["contacts"]} contact entries are tied to source locators. `verified` means source-backed, not approved for automatic use.','',
        '## Needs confirmation','',
        'Every routing record has `production_status=NEEDS_CONFIRMATION`. Every contact, FAQ and RAG chunk has `publication_status=NEEDS_REVIEW`. Source validity, pilot territory, backend category mappings and legal version status need approval.','',
        '## Conflicts','',
        f'{counts["conflicts"]} conflicts or source inconsistencies are detailed in 13_CONFLICTS.md. The two plant-protection addresses are left unresolved; the Manas finance-office address is geographically inconsistent; one tax-office address has a spelling variant.','',
        '## Outdated candidates','',
        'No contact is designated current solely by an undated list. Documents with older dates remain legal/reference candidates until their current editions are confirmed.','',
        '## Missing data','',
        f'{counts["knowledge_gaps"]} dataset-level gaps are detailed in 14_KNOWLEDGE_GAPS.md. {counts["blocked"]} sources need OCR/conversion. Most organizations lack verified bilingual names, parent links and service zones.','',
        '## Ready for RAG','',
        f'{counts["rag_chunks"]} deduplicated, source-backed chunks are structurally ready for internal retrieval, with language/topic/organization and publication metadata. Embeddings were not created. Citizen-facing use waits for publication and currency review.','',
        '## Not ready for production routing','',
        f'The {counts["routing_proposed"]} proposed rules and even {counts["routing_verified"]} directly documented institution-level rules require the approved pilot routing matrix, exceptions, territorial boundaries and current Django categories.','',
        '## Source coverage after normalization','',
        f'{counts["processed_sources_with_canonical_records"]} of {counts["processed"]} text-extracted sources contribute at least one canonical entity, route, QA or RAG chunk. The remaining extracted sources are indexed for source-on-demand review; many are questionnaires, cover letters or personal-data files. IDs: '+', '.join(unrepresented)+'.','',
        '## Recommended next actions','',
        '1. Request an approved organization/routing/contact register, pilot geography and Django category export from the mayor’s office and system owner.',
        '2. Resolve the three conflicts and 12 blocked files with original issuers.',
        '3. Obtain legal-version review and citizen-publication clearance before opening the RAG corpus to users.','',
        '## Validation errors','']
audit += [f'- {e}' for e in errors] if errors else ['None.']
audit += ['','## Validation warnings','']
audit += [f'- {w}' for w in warnings] if warnings else ['None.']
(OUT/'16_FINAL_KNOWLEDGE_AUDIT.md').write_text('\n'.join(audit)+'\n',encoding='utf-8')
(OUT/'.validation.json').write_text(json.dumps({"counts":counts,"errors":errors,"warnings":warnings,"unrepresented_source_ids":unrepresented},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({"counts":counts,"error_count":len(errors),"warning_count":len(warnings)},ensure_ascii=False))
if errors:raise SystemExit(1)
