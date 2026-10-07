from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BOT=Path('C:/Users/user/PycharmProjects/AI-presentation/tg_bot-')
STAGE=ROOT/'staging_bot'
sys.path.insert(0,str(BOT))
sys.path.insert(0,str(STAGE))
from knowledge.runtime import KnowledgeBase, validate_manifest

kb=KnowledgeBase()
manifest=validate_manifest(STAGE/'knowledge/data')
expected=json.loads((ROOT/'runtime_export/knowledge_manifest.json').read_text(encoding='utf8'))
errors=[]
def check(condition,message):
    if not condition:errors.append(message)

check(manifest['knowledge_version']==expected['knowledge_version'],'manifest version mismatch')
check(len(kb.files['contacts'])==len(kb.approved_contact_ids),'public contact audit failed')
check(len(kb.files['rag_chunks'])==manifest['rag_chunks_count'],'chunk count mismatch')
for question,needle in [
    ('Токтогульская районная государственная администрация телефон','5-00-20'),
    ('Сузакская районная государственная администрация телефон','5-00-01'),
    ('Ала-Бука райондук мамлекеттик администрациясы телефон','ала-бука'),
]:
    result=kb.exact_match(question)
    check(bool(result and result.mode=='structured'),f'no structured result: {question}')
    if result and needle not in result.answer.lower():
        # Organization cards may use the contact list order; check exact source-backed phone separately.
        check(any(needle in c.get('value','').lower() for c in kb.files['contacts'] if c.get('organization_id') in
                  [o['organization_id'] for o in kb.files['organizations'] if any(needle in str(x).lower() for x in
                   [o.get('name_ru'),o.get('name_ky'),o.get('aliases_ru'),o.get('aliases_ky')])]),
              f'contact absent: {question}')
for c in kb.files['contacts']:
    check(c.get('visibility')=='PUBLIC',f'private contact exported: {c.get("contact_id")}')
    check(c.get('status','SOURCE_CONFIRMED')=='SOURCE_CONFIRMED',f'nonconfirmed contact exported: {c.get("contact_id")}')
for value in ('03745 50030','0745 50030','037 48 50075','(03748) 5-00-75','0990 907050','+996772764606'):
    check(not any(c.get('value')==value for c in kb.files['contacts']),f'conflict/staff phone leaked: {value}')
check(len(kb.vectors)==0,'staging unexpectedly contains index vectors')
result={'result':'PASS' if not errors else 'FAIL','errors':errors,'error_count':len(errors),
        'knowledge_version':manifest['knowledge_version'],'public_contacts_approved':len(kb.approved_contact_ids),
        'chunks':len(kb.files['rag_chunks']),'index_ready':False}
(ROOT/'bot_compatibility.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
(ROOT/'BOT_COMPATIBILITY.md').write_text('# Bot compatibility v4\n\n'
    f'Result: **{result["result"]}**; errors: {len(errors)}. '
    f'Staged parser approved {len(kb.approved_contact_ids)} / {len(kb.files["contacts"])} PUBLIC contacts.\n\n'
    'The current bot data and index were not changed. The staged copy has no embedding index; '
    'RAG acceptance and INDEX_READY require a new paid embedding build.\n\n'
    +''.join(f'- {e}\n' for e in errors),encoding='utf8')
print(json.dumps(result,ensure_ascii=False))
if errors:raise SystemExit(1)
