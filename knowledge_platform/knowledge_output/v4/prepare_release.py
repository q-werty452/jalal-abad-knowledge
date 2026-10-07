from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from docx import Document

ROOT=Path(__file__).resolve().parent
M=ROOT/'machine'
EXPORT=ROOT/'runtime_export'
SUPPORT=ROOT/'runtime_support'
RELEASE=ROOT/'release'
BOT=Path('C:/Users/user/PycharmProjects/AI-presentation/tg_bot-')
FILES=('sources.jsonl','organizations.jsonl','competences.jsonl','contacts.jsonl',
       'routing_rules.jsonl','qa_pairs_ru.jsonl','qa_pairs_ky.jsonl','rag_chunks.jsonl','aliases.jsonl')

def read(path):
    return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines() if x.strip()]

def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf8')

def digits(s):return ''.join(re.findall(r'\d',str(s)))
def phone_norm(s):
    n=digits(s)
    return n[3:] if n.startswith('996') else n.lstrip('0')

tables={p.stem:read(p) for p in M.glob('*.jsonl')}
sources={s['source_id']:s for s in tables['sources']}
orgs={o['organization_id']:o for o in tables['organizations']}
territories={t['territory_id'] for t in tables['territories']}
staff_nums={digits(x.get('phone')) for x in tables['staff_roles'] if len(digits(x.get('phone')))>=9}
staff_norm={phone_norm(x.get('phone')) for x in tables['staff_roles'] if len(phone_norm(x.get('phone')))>=9}
internal_nums={digits(x.get('value')) for x in tables['contacts'] if x.get('type')=='phone' and x.get('visibility')!='PUBLIC' and len(digits(x.get('value')))>=9}
suppressed=[]

public_contacts=[]
for c in tables['contacts']:
    if c.get('visibility')!='PUBLIC' or c.get('status','SOURCE_CONFIRMED')!='SOURCE_CONFIRMED':continue
    if not any(p.get('locator') and p.get('source_id') in sources and
               p.get('source_file')==sources[p['source_id']].get('source_file')
               for p in c.get('provenance',[])):
        suppressed.append((c['contact_id'],'missing audited source locator'));continue
    num=digits(c['value']) if c['type']=='phone' else ''
    if len(num)>=9 and num in internal_nums:
        suppressed.append((c['contact_id'],'phone also internal'));continue
    if c['type']=='phone' and phone_norm(c['value']) in staff_norm:
        explicitly_official=any(p.get('source_id')=='NEW-264' and
                                re.search(r'table:\d+:row:[01]$',p.get('locator',''))
                                for p in c.get('provenance',[]))
        if not explicitly_official:
            suppressed.append((c['contact_id'],'staff phone without official/general contact row'));continue
    public_contacts.append(copy.deepcopy(c))

runtime={}
for name in FILES:
    key=name.removesuffix('.jsonl')
    if key=='contacts':runtime[key]=public_contacts
    elif key=='routing_rules':
        runtime[key]=[]
        for row in tables[key]:
            if row.get('visibility')!='PUBLIC':continue
            if row['routing_rule_id'].startswith('v4-'):
                if not row.get('territory_scope') or not row.get('target_organization_id'):continue
                r=copy.deepcopy(row)
                r['original_wording']=r.get('topic','')
                r['trigger_phrases_ru']=[r.get('topic','')]
                r['trigger_phrases_ky']=[r.get('topic','')]
                r['provenance']=[{k:v for k,v in p.items() if k!='original_wording'} for p in r.get('provenance',[])]
                runtime[key].append(r)
            elif row.get('pilot_status')=='SOURCE_CONFIRMED_SUGGESTION' and (
                not row['routing_rule_id'].startswith('v3-') or (row.get('route_type')=='SINGLE' and row.get('target_organization_id') and row.get('territory_scope'))):
                runtime[key].append(copy.deepcopy(row))
    else:
        runtime[key]=[copy.deepcopy(x) for x in tables[key]
                      if x.get('visibility','PUBLIC')=='PUBLIC' and x.get('pilot_status','SOURCE_CONFIRMED') not in ('CONFLICT','AMBIGUOUS')]

# Keep structured references and remove source wording from new public RAG if it contains staff contact details.
safe_chunks=[]
for row in runtime['rag_chunks']:
    r=copy.deepcopy(row)
    if str(r.get('chunk_id','')).startswith('v4-'):
        r['provenance']=[{k:v for k,v in p.items() if k!='original_wording'} for p in r.get('provenance',[])]
        phone_text=digits(r.get('text',''))
        if any(n in phone_text for n in staff_nums|internal_nums if len(n)>=9):
            suppressed.append((r['chunk_id'],'staff phone in RAG text'));continue
    safe_chunks.append(r)
runtime['rag_chunks']=safe_chunks

# Compact metadata is accepted by the current parser.
for c in runtime['contacts']:
    if c['type'] in ('working_hours','reception_hours'):c['working_hours']=c['value']
    c['provenance']=[{k:v for k,v in p.items() if k!='original_wording'} for p in c.get('provenance',[])]

for name in FILES:write(EXPORT/name,runtime[name.removesuffix('.jsonl')])
contents={name:(EXPORT/name).read_bytes() for name in FILES}
version=hashlib.sha256(''.join(hashlib.sha256(contents[n]).hexdigest() for n in FILES).encode()).hexdigest()[:16]
manifest={'knowledge_version':version,'rag_chunks_count':len(runtime['rag_chunks']),
          'source_count':len(runtime['sources']),
          'files':{name:hashlib.sha256(contents[name]).hexdigest() for name in FILES}}
(EXPORT/'knowledge_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')

records=[]
new_source_checks=0
new_source_docs={}
def source_contains(contact,sid,locator):
    global new_source_checks
    if sid not in new_source_docs:
        new_source_docs[sid]=Document(Path('C:/Users/user/Downloads')/sources[sid]['source_file'])
    doc=new_source_docs[sid]
    para=re.search(r'paragraph:(\d+)',locator or '')
    tab=re.search(r'table:(\d+):row:(\d+)',locator or '')
    if para:
        start=int(para.group(1));end=re.search(r'paragraph:\d+-(\d+)',locator or '')
        raw=' '.join(p.text for p in doc.paragraphs[start:int(end.group(1))+1 if end else start+1])
    elif tab:raw=' '.join(c.text for c in doc.tables[int(tab.group(1))].rows[int(tab.group(2))].cells)
    else:return False
    new_source_checks+=1
    if contact['type']=='phone':
        number=digits(contact['value']);text=digits(raw)
        if number.startswith('996'):number=number[3:]
        if text.startswith('996'):text=text[3:]
        return number.lstrip('0') in text.lstrip('0')
    if contact['type']=='reception_hours' and sid=='NEW-259':return '14:00' in raw and '17:00' in raw
    norm=lambda value:re.sub(r'\W','',str(value).lower())
    return norm(contact['value']) in norm(raw)
for c in runtime['contacts']:
    sid=next((x for x in c.get('source_ids',[]) if x in sources),None)
    prov=next((p for p in c.get('provenance',[]) if p.get('source_id')==sid),{})
    loc=[p.get('locator') for p in c.get('provenance',[]) if p.get('source_id')==sid and p.get('locator')]
    source=sources.get(sid,{})
    org=orgs.get(c['organization_id'],{})
    valid=bool(sid and loc and org and source.get('source_file')==prov.get('source_file'))
    org_locs={p.get('locator') for p in org.get('provenance',[]) if p.get('source_id')==sid}
    link='same_record' if set(loc)&org_locs else 'adjacent_section'
    record={'knowledge_version':version,'contact_record_id':c['contact_id'],
     'organization_id':c['organization_id'],'organization_name':org.get('name_ru') or org.get('name_ky'),
     'type':c['type'],'value':c['value'],'source_id':sid,'source_file':source.get('source_file'),
     'locator':loc,'visibility':'PUBLIC','source_value_found':valid,'link':link,
     'status':'VALID' if valid else 'SUPPRESSED','reasons':[] if valid else ['missing_source_or_locator']}
    records.append(record)
write(SUPPORT/'public_contact_attribution_records.jsonl',records)

errors=[]
def check(condition,message):
    if not condition:errors.append(message)
for name,rows in tables.items():
    idfield={'sources':'source_id','organizations':'organization_id','contacts':'contact_id',
     'competences':'competence_id','routing_rules':'routing_rule_id','services':'service_id',
     'procedures':'procedure_id','territories':'territory_id','rag_chunks':'chunk_id',
     'staff_roles':'staff_role_id','real_query_examples':'example_id','escalation_rules':'escalation_rule_id'}.get(name)
    if idfield:
        ids=[r.get(idfield) for r in rows]
        check(all(ids) and len(ids)==len(set(ids)),f'{name}: duplicate/missing {idfield}')
    for i,row in enumerate(rows):
        for sid in row.get('source_ids',[]):check(sid in sources,f'{name}:{i}: unknown source {sid}')
        oid=row.get('organization_id') or row.get('target_organization_id')
        if oid:check(oid in orgs,f'{name}:{i}: unknown organization {oid}')
        for oid_in_list in row.get('organization_ids',[]) or []:
            check(oid_in_list in orgs,f'{name}:{i}: unknown organization {oid_in_list}')
        if name=='routing_rules':
            for secondary in row.get('secondary_organization_ids',[]) or []:
                check(secondary in orgs,f'{name}:{i}: unknown secondary organization {secondary}')
        tid=row.get('territory_id')
        if tid and (name in ('territories','service_territories','district_profiles') or any(str(s).startswith('NEW-26') for s in row.get('source_ids',[]) or [])):
            check(tid in territories,f'{name}:{i}: unknown territory {tid}')
        if name!='sources' and any(s.startswith('NEW-26') or s in ('NEW-258','NEW-259') for s in row.get('source_ids',[])):
            check(bool(row.get('provenance')),f'{name}:{i}: missing provenance')
for r in tables['routing_rules']:
    if str(r['routing_rule_id']).startswith('v4-'):
        check(bool(r.get('territory_scope')),f"route:{r['routing_rule_id']}: missing scope")
        check(bool(r.get('target_organization_id')),f"route:{r['routing_rule_id']}: unknown target")
for c in tables['contacts']:
    check(bool(c.get('source_ids') and c.get('provenance')),f"contact:{c['contact_id']}: no provenance")
for c in runtime['contacts']:
    check(c.get('visibility')=='PUBLIC' and c.get('status','SOURCE_CONFIRMED')=='SOURCE_CONFIRMED',f"public contact unsafe:{c['contact_id']}")
    num=digits(c.get('value')) if c.get('type')=='phone' else ''
    check(not (len(num)>=9 and num in internal_nums),f"public personal/internal phone:{c['contact_id']}")
    if c.get('type')=='phone' and phone_norm(c.get('value')) in staff_norm:
        check(any(p.get('source_id')=='NEW-264' and re.search(r'table:\d+:row:[01]$',p.get('locator',''))
                  for p in c.get('provenance',[])),f"unapproved staff phone in public:{c['contact_id']}")
    for p in c.get('provenance',[]):
        sid=p.get('source_id')
        if sid and sid.startswith('NEW-') and int(sid.split('-')[1])>=258:
            check(source_contains(c,sid,p.get('locator')),f"contact not found in new source:{c['contact_id']}:{sid}")
check(len(records)==len(runtime['contacts']),'audit contact count mismatch')
check(all(r['knowledge_version']==version for r in records),'audit version mismatch')
check(all(r['status']=='VALID' for r in records),'audit suppressed contact')
for name in FILES:check(hashlib.sha256((EXPORT/name).read_bytes()).hexdigest()==manifest['files'][name],f'manifest checksum:{name}')
for r in runtime['rag_chunks']:
    if str(r.get('chunk_id','')).startswith('v4-'):
        check(r.get('source_id') in sources and bool(r.get('locator')),f"chunk provenance:{r['chunk_id']}")
        if 'routing' in r.get('tags',[]):check(bool(r.get('routing_rule_id') and r.get('territory_scope')),f"routing chunk scope:{r['chunk_id']}")
        txt=digits(r.get('text',''))
        check(not any(n in txt for n in internal_nums|staff_nums if len(n)>=9),f"private number in chunk:{r['chunk_id']}")
for r in runtime['routing_rules']:
    if str(r.get('routing_rule_id','')).startswith('v4-'):
        payload=digits(json.dumps(r,ensure_ascii=False))
        check(not any(n in payload for n in internal_nums|staff_nums if len(n)>=9),f"private number in route:{r['routing_rule_id']}")

validation={'result':'PASS' if not errors else 'FAIL','errors':errors,'error_count':len(errors),
 'knowledge_version':version,'public_contacts':len(runtime['contacts']),'audit_valid':sum(r['status']=='VALID' for r in records),
 'suppressed':len(suppressed),'new_source_value_checks':new_source_checks,
 'runtime_counts':{k:len(v) for k,v in runtime.items()}}
(ROOT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf8')
(ROOT/'VALIDATION.md').write_text(f"# Knowledge v4 validation\n\nResult: **{validation['result']}**; errors: **{len(errors)}**.\n\n"+'\n'.join(f'- {e}' for e in errors[:100])+'\n',encoding='utf8')
(SUPPORT/'public_contact_attribution_audit.md').write_text(
 f'# Public contact attribution v4\n\nKnowledge version: `{version}`.\n\n'
 f'PUBLIC checked: {len(records)}; VALID: {validation["audit_valid"]}; SUPPRESSED: {len(suppressed)}.\n\n'
 'Each record links a runtime contact to its source, locator, and organization. '
 'Personal staff numbers and conflict contacts are excluded from the runtime export.\n',encoding='utf8')
if errors:
 print(json.dumps(validation,ensure_ascii=False)[:4000]);raise SystemExit(1)

RELEASE.mkdir(exist_ok=True)
for name in FILES:
 p=RELEASE/'runtime_export'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(EXPORT/name,p)
for name in ('public_contact_attribution_records.jsonl','public_contact_attribution_audit.md'):
 p=RELEASE/'runtime_support'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(SUPPORT/name,p)
shutil.copy2(EXPORT/'knowledge_manifest.json',RELEASE/'knowledge_manifest.json')
for name in ('PROMOTION_V4_REPORT.md','VALIDATION.md','OFFLINE_QUERY_COVERAGE.md'):
 src=ROOT/name
 if src.exists():shutil.copy2(src,RELEASE/name)
print(json.dumps(validation,ensure_ascii=False)[:800])
