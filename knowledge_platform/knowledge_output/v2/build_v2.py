"""Deterministic pilot promotion. Reads customer files; writes only v2/."""
import collections
import copy
import hashlib
import io
import json
import re
import shutil
from difflib import SequenceMatcher
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'knowledge_output'
V2=OUT/'v2'
M=V2/'machine'
REV=V2/'review'
DOC=V2/'source_documents'
for p in (M,REV,DOC):p.mkdir(parents=True,exist_ok=True)

def load(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def write(path,rows):
    with path.open('w',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
def key(*parts):return hashlib.sha256('|'.join(str(x) for x in parts).encode('utf-8')).hexdigest()[:12]
def norm(s):return re.sub(r'[^a-zа-яёүөң0-9]+','',s.lower()).replace('джалал','жалал')
def sourcefile(source_id):return source_by_id[source_id]['source_file']
def prov(sid,loc):return {'source_id':sid,'source_file':sourcefile(sid),'locator':loc,'verification_status':'SOURCE_CONFIRMED','fact_status':'SOURCE_FACT'}

basehash={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('[0-1][0-9]_*.md')}
basehash.update({str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'machine').glob('*.jsonl')})
(V2/'baseline_hashes.json').write_text(json.dumps(basehash,ensure_ascii=False,indent=2),encoding='utf-8')
data={p.stem:load(p) for p in (OUT/'machine').glob('*.jsonl')}
S=data['sources'];O=data['organizations'];C=data['contacts'];K=data['competences'];R=data['routing_rules'];G=data['rag_chunks']
Qru=data['qa_pairs_ru'];Qky=data['qa_pairs_ky'];A=data['aliases']
T=load(OUT/'audit_machine/territories.jsonl')
F=load(OUT/'audit_machine/recoverable_facts.jsonl')
N=load(OUT/'audit_machine/new_sources.jsonl')
E={r['source_id']:r for r in load(V2/'.source_blocks.jsonl')}
orig_ids={s['source_id'] for s in S}
for n in N:
    source={'source_id':n['source_id'],'file_name':n['source_file'].split('::')[-1].split('/')[-1],
            'source_file':n['source_file'],'file_type':'docx','size':n['size'],'sha256':n['sha256'],
            'container_archive':n['container_archive'],'archive_entry':n['source_file'].split('::',1)[1] if '::' in n['source_file'] else None,
            'duplicate_of':n['duplicate_of'],'status':n['status'],'normalization_status':'v2_promoted' if not n['duplicate_of'] else 'duplicate',
            'source_root':'v2/source_documents' if not n['duplicate_of'] else 'existing_source','verification_status':'SOURCE_CONFIRMED'}
    S.append(source)
    if not n['duplicate_of']:
        src=Path.home()/'Downloads'/('New Folder 1.zip' if n['container_archive'] else n['source_file'])
        if n['container_archive']:
            import zipfile
            with zipfile.ZipFile(src) as z:blob=z.read(n['source_file'].split('::',1)[1])
        else:blob=src.read_bytes()
        target=DOC/(n['source_id']+'.docx')
        target.write_bytes(blob)
        source['v2_copy']=str(target.relative_to(V2))
source_by_id={s['source_id']:s for s in S}

terr_by_id={t['territory_id']:t for t in T}
def territory_from(text):
    text=text or ''
    choices=[]
    for t in T:
        ky=t['name_ky'];ru=t['name_ru'];tid=t['territory_id'];name=tid.split(':',1)[1]
        if name.lower() not in text.lower() and not (ru and ru.lower() in text.lower()) and not (ky and ky.lower() in text.lower()):continue
        if t['type']=='ayyl_area' and re.search(r'айыл аймаг|айыл өкмөт|айыл окмот|а/о',text,re.I):rank=0
        elif t['type']=='village' and re.search(r'айылы|село|с\.',text,re.I):rank=1
        elif t['type']=='city' and re.search(r'шаар|город|г\.|мэрия',text,re.I):rank=2
        elif t['type']=='district' and re.search(r'район|району|райондук',text,re.I):rank=3
        elif t['type']=='region' and re.search(r'обл|област',text,re.I):rank=4
        else:continue
        choices.append((rank,-len(name),tid))
    return sorted(choices)[0][2] if choices else None

org_index={norm(o.get('name_ru') or o.get('name_ky') or ''):o for o in O}
oid_index={o['organization_id']:o for o in O}
def org_name(o):return o.get('name_ru') or o.get('name_ky') or ''
def ensure_org(name,sid,loc,territory=None,lang=None):
    name=' '.join(name.strip(' ;.,').split())
    if not name:return None
    n=norm(name)
    o=org_index.get(n)
    if o is None and name=='Жалал-Абадское региональное управление государственного архитектурно-строительного контроля':
        o=next((x for x in O if 'архитектурно-строительного контроля' in org_name(x).lower()),None)
    if o is None and name=='Управление городских дорог':
        o=next((x for x in O if 'Управление городских дорог мэрии города Манас' in org_name(x)),None)
    if o is None and name=='Майлуу-Суу шаардык мэриясы':
        o=next((x for x in O if org_name(x)=='Мэрия города Майлуу-Суу'),None)
    if o is None and name=='Таш-Көмүр шаардык мэриясы':
        o=next((x for x in O if org_name(x)=='Мэрия города Таш-Кумыр'),None)
    if o is None:
        same=[(SequenceMatcher(None,n,k).ratio(),v) for k,v in org_index.items() if k and (n in k or k in n)]
        if same and max(same,key=lambda z:z[0])[0]>=0.94:o=max(same,key=lambda z:z[0])[1]
    if o is None:
        oid='v2-org-'+key(name,territory or '')
        o={'organization_id':oid,'name_ru':name if lang=='ru' or (lang is None and re.search(r'[ёъыэ]',name.lower())) else None,
           'name_ky':name if lang=='ky' or (lang is None and not re.search(r'[ёъыэ]',name.lower())) else None,
           'short_name_ru':None,'short_name_ky':None,'aliases_ru':[],'aliases_ky':[],
           'organization_type':'unknown','parent_organization_id':None,'territory':[territory] if territory else [],
           'territory_status':'SOURCE_CONTEXT' if territory else 'NEEDS_CONFIRMATION','status':'active_unknown',
           'source_ids':[sid],'provenance':[prov(sid,loc)],'verification_status':'SOURCE_CONFIRMED',
           'pilot_status':'SOURCE_CONFIRMED','visibility':'PUBLIC','fact_status':'SOURCE_FACT'}
        O.append(o);org_index[n]=o;oid_index[oid]=o
    else:
        if sid not in o['source_ids']:o['source_ids'].append(sid)
        o['pilot_status']='SOURCE_CONFIRMED'
        o['visibility']='PUBLIC'
        if territory and not o.get('territory'):o['territory']=[territory];o['territory_status']='SOURCE_CONTEXT'
    return o['organization_id']

contact_idx={}
for c in C:
    c['contact_type']=c['type'];c['visibility']='PUBLIC';c['status']='SOURCE_CONFIRMED'
    c['pilot_status']='SOURCE_CONFIRMED';c['publication_status']='PILOT_PUBLIC'
    if c['type']=='address':c['address_kind']='office_or_unspecified'
    contact_idx[(c['organization_id'],c['type'],norm(c['value']))]=c

def add_contact(oid,typ,value,sid,loc,territory=None,visibility='PUBLIC',status='SOURCE_CONFIRMED',kind=None,reason=None):
    if oid not in oid_index:raise ValueError(('unknown org',oid))
    value=' '.join(value.split()).strip(' ,;.')
    if not value:return None
    ck=(oid,typ,norm(value))
    old=contact_idx.get(ck)
    if old:
        if sid not in old['source_ids']:old['source_ids'].append(sid)
        old.setdefault('provenance',[]).append(prov(sid,loc))
        if old.get('visibility')=='INTERNAL_ONLY' or visibility=='INTERNAL_ONLY':old['visibility']='INTERNAL_ONLY';old['publication_status']='INTERNAL_ONLY'
        if status=='CONFLICT':old['status']='CONFLICT';old['visibility']='INTERNAL_ONLY';old['publication_status']='CONFLICT'
        return old['contact_id']
    cid='v2-contact-'+key(oid,typ,value)
    rec={'contact_id':cid,'organization_id':oid,'type':typ,'contact_type':typ,'value':value,
         'purpose':kind or ('legal_address' if typ=='address' and kind=='legal_address' else 'source_contact'),
         'address_kind':kind if typ=='address' else None,
         'working_hours':value if typ in ('working_hours','reception_hours') else None,
         'territory_id':territory or (oid_index[oid].get('territory') or [None])[0],
         'source_ids':[sid],'provenance':[prov(sid,loc)],'verification_status':'SOURCE_CONFIRMED',
         'pilot_status':status,'status':status,'visibility':visibility,
         'publication_status':'PILOT_PUBLIC' if visibility=='PUBLIC' and status=='SOURCE_CONFIRMED' else status,
         'reason':reason}
    C.append(rec);contact_idx[ck]=rec
    return cid

def add_comp(oid,text,sid,loc,territory=None,typ='competence'):
    text=' '.join(text.split()).strip()
    if not text or len(text)<15:return None
    ck=(oid,norm(text))
    if ck in comp_idx:
        register(sid,loc,comp_idx[ck])
        return comp_idx[ck]
    cid='v2-comp-'+key(oid,text)
    rec={'competence_id':cid,'organization_id':oid,'topic':typ,'description_ru':text if re.search(r'[ёъыэ]',text.lower()) else None,
         'description_ky':text if not re.search(r'[ёъыэ]',text.lower()) else None,'territory':[territory] if territory else [],
         'territory_status':'SOURCE_CONTEXT' if territory else 'NEEDS_CONFIRMATION','source_ids':[sid],
         'provenance':[prov(sid,loc)],'verification_status':'SOURCE_CONFIRMED','pilot_status':'SOURCE_CONFIRMED',
         'visibility':'PUBLIC','fact_status':'SOURCE_FACT'}
    K.append(rec);comp_idx[ck]=cid
    register(sid,loc,cid)
    return cid
comp_idx={(x['organization_id'],norm(x.get('description_ru') or x.get('description_ky') or '')):x['competence_id'] for x in K}
services=[];procedures=[];newroutes=[];conflicts=[];review=[];promotion_map=collections.defaultdict(list)
def register(sid,loc,rid):promotion_map[(sid,loc)].append(rid)
def block(sid,loc):
    return next((b for b in E[sid]['blocks'] if b['locator']==loc),None)
def blocktext(sid,loc):
    b=block(sid,loc)
    if b is None:raise ValueError(('missing locator',sid,loc))
    return b['text']
def digits(v):return re.sub(r'\D','',v)
def mobile(v):
    d=digits(v)
    return (len(d) in (9,10,12) and (d.startswith(('9962','9965','9967','9969','02','05','07','09','2','5','7','9'))))
def add_service(oid,name,description,sid,loc,terr=None):
    rid='v2-service-'+key(oid,name,terr or '')
    if any(x['service_id']==rid for x in services):return rid
    services.append({'service_id':rid,'organization_id':oid,'name':name,'description':description,'territory_id':terr,
                     'source_ids':[sid],'provenance':[prov(sid,loc)],'status':'SOURCE_CONFIRMED','visibility':'PUBLIC'})
    register(sid,loc,rid);return rid
def add_procedure(oid,name,steps,sid,loc,terr=None,complete=False):
    rid='v2-proc-'+key(oid,name,terr or '')
    if any(x['procedure_id']==rid for x in procedures):return rid
    procedures.append({'procedure_id':rid,'organization_id':oid,'name':name,'steps':steps,'required_documents':[],
                       'territory_id':terr,'completeness':'FULL' if complete else 'PARTIAL','source_ids':[sid],
                       'provenance':[prov(sid,loc)],'status':'SOURCE_CONFIRMED','visibility':'PUBLIC'})
    register(sid,loc,rid);return rid
def add_route(oid,topic,sid,loc,terr,target_name=None,exclusion=False):
    rid='v2-route-'+key(oid,topic,terr)
    if any(x['routing_rule_id']==rid for x in newroutes):return rid
    newroutes.append({'routing_rule_id':rid,'topic':topic,'trigger_phrases_ru':[],'trigger_phrases_ky':[topic],
                      'target_organization_id':oid,'target_department_id':None,'target_department_name_ky':target_name,
                      'territory':[terr],'territory_id':terr,'required_clarifications':['точный адрес/населённый пункт'],
                      'exceptions':[],'source_ids':[sid],'provenance':[prov(sid,loc)],
                      'verification_status':'SOURCE_CONFIRMED','pilot_status':'SOURCE_CONFIRMED_SUGGESTION',
                      'production_status':'SUGGESTION_ONLY','visibility':'PUBLIC','exclusion':exclusion})
    register(sid,loc,rid);return rid

# Original canonical records remain source-confirmed; proposed routes remain non-public.
for coll in (O,K,Qru,Qky,G,A):
    for x in coll:
        x['pilot_status']='SOURCE_CONFIRMED';x['visibility']='PUBLIC'
        if 'publication_status' in x:x['publication_status']='PILOT_PUBLIC'
for x in R:
    if x.get('verification_status')=='verified':
        x['pilot_status']='SOURCE_CONFIRMED_SUGGESTION';x['visibility']='PUBLIC';x['production_status']='SUGGESTION_ONLY';x['publication_status']='PILOT_PUBLIC'
    else:x['pilot_status']='AMBIGUOUS';x['visibility']='INTERNAL_ONLY';x['publication_status']='INTERNAL_ONLY'

# Existing source conflicts, plus new-source collisions.
for cid,entity,kind,variants,sources in [
 ('CONFLICT-001','Жалал-Абад өсүмдүктөрдү химиялаштыруу,коргоо жана карантин башкармалыгы','address',
  ['Сузак айылы, Дакан Палван көчөсү 52','Манас шаары, С.Качкынбаев көчөсү 11'],['SRC-225']),
 ('CONFLICT-002','Майлуу-Суу салык башкармалыгы','address_spelling',
  ['Майлуу-Суу шаары Сыдыков көчөсү 34','Майлуу-Суу шаары Сыдыков кочосу 34'],['SRC-225']),
 ('CONFLICT-003','Манас шаардык финансы башкармалыгы','territory_address',
  ['Манас шаардык финансы башкармалыгы','Жээналиев №54 с.Казарман'],['SRC-225','SRC-039']),
 ('V2-CONFLICT-004','Жалал-Абад областтык китепканасы','address',
  ['пер. Т. Байзакова, 20 (реестровая справка)','проспект Т. Байзаков, 20 (устав)'],['NEW-242']),
 ('V2-CONFLICT-005','Жалал-Абад облустук дене тарбия жана спорт башкармалыгы','address_territory',
  ['Жалал-Абад шаары, Т. Молдо 80/1','Манас шаары, Тоголок-Молдо 80/1'],['NEW-243','SRC-217'])]:
    conflicts.append({'conflict_id':cid,'entity':entity,'field':kind,'values':variants,'source_ids':sources,
                      'status':'CONFLICT','resolution':'NO_WINNER','visibility':'INTERNAL_ONLY'})
for c in C:
    if c['type']=='address' and (('өсүмдүктөрдү химиялаштыруу' in org_name(oid_index[c['organization_id']])) or
                                  ('Манас шаардык финансы' in org_name(oid_index[c['organization_id']]))):
        c['status']='CONFLICT';c['pilot_status']='CONFLICT';c['visibility']='INTERNAL_ONLY';c['publication_status']='CONFLICT'

def add_checked(oid,typ,value,sid,loc,**kwargs):
    raw=blocktext(sid,loc)
    compact=norm(value)
    if compact not in norm(raw):
        # Address strings sometimes differ only by punctuation or spacing; require a strong overlap.
        if SequenceMatcher(None,compact,norm(raw)).find_longest_match(0,len(compact),0,len(norm(raw))).size<min(8,len(compact)):
            raise ValueError(('value absent from source',sid,loc,value))
    cid=add_contact(oid,typ,value,sid,loc,**kwargs)
    if cid:register(sid,loc,cid)
    return cid

# All 13 unique new documents are retained as sources. Promote explicit entity-bound facts.
new_specs={
 'NEW-235':('Жалал-Абадская таможня','city:Манас','paragraph:21','Кыргызская Республика, город Манас, пр. Т. Байзакова, 141/4','ru'),
 'NEW-236':('«Кыргыз темир жолу» түштүк бөлүмү филиалы','city:Жалал-Абад','paragraph:15','Кыргыз Республикасы, Жалал-Абад шаары, Токтогул көчөсү,7','ky'),
 'NEW-237':('Кыргыз Республикасынын Финансы министрлигинин Базар-Коргон финансы башкармалыгы','city:Базар-Коргон','paragraph:21','Кыргыз Республикасы, Жалал-Абад облусу, Базар-Коргон району, Базар-Коргон шаары, Б.Осмонов көчөсү, 170','ky'),
 'NEW-238':('ЖАМК №10 түзөтүү мекемеси','village:Баймундуз','paragraph:40','Кыргыз Республикасы, Жалал-Абад облусу, Базар-Коргон району, Баймундуз айылы, Сары-Талаа участкасы','ky'),
 'NEW-239':('«Акыйкат» Жалал-Абад облустук гезитинин редакциясы','city:Жалал-Абад','paragraph:16','Жалал-Абад шаары, Ленин көч., №122','ky'),
 'NEW-240':('«Акыйкат» Жалал-Абад облустук гезитинин редакциясы','city:Жалал-Абад','paragraph:26','Жалал-Абад шаары, Ленин көч. 122','ky'),
 'NEW-241':('Б. Осмонов атындагы Жалал-Абад мамлекеттик университети','city:Жалал-Абад','paragraph:23','Жалал-Абад шаары, Р.Азимов көчөсү, № 49','ky'),
 'NEW-242':('Жалал-Абад областтык китепканасы','city:Жалал-Абад','paragraph:88','Жалал-Абад шаары, Т. Байзаков проспектиси № 20','ky'),
 'NEW-243':('Жалал-Абад облустук дене тарбия жана спорт башкармалыгы','region:Жалал-Абад','paragraph:29','Жалал-Абад шаары, Т. Молдо көчөсү 80/1','ky'),
 'NEW-244':('Жалал-Абад облустук телерадиокомпаниясы','city:Жалал-Абад','paragraph:26','Жалал-Абад шаары, Ленин көчөсү, № 122','ky'),
 'NEW-245':('Жалал-Абадский медицинский колледж','city:Жалал-Абад','paragraph:13','Жалал-Абадская область, г.Жалал-Абад, ул.Курортная, 2','ru'),
 'NEW-246':('Жалал-Абадский международный университет','city:Жалал-Абад','paragraph:25','город Жалал-Абад, улица Курманбека №24','ru'),
 'NEW-247':('Международный университет имени К. Ш. Токтомаматова','city:Жалал-Абад','paragraph:19','г. Жалал-Абад, ул. Тарсус, 1 а','ru')}
new_org_ids={}
for sid,(name,terr,loc,address,lang) in new_specs.items():
    oid=ensure_org(name,sid,loc,terr,lang);new_org_ids[sid]=oid
    status='CONFLICT' if sid in ('NEW-242','NEW-243') else 'SOURCE_CONFIRMED'
    vis='INTERNAL_ONLY' if status=='CONFLICT' else 'PUBLIC'
    add_checked(oid,'address',address,sid,loc,territory=terr,visibility=vis,status=status,kind='legal_address')
for sid,loc in [('NEW-235','paragraph:83'),('NEW-237','paragraph:78'),('NEW-238','paragraph:165')]:
    add_comp(new_org_ids[sid],blocktext(sid,loc),sid,loc,new_specs[sid][1],'citizen_appeals')
for sid,loc in [('NEW-241','paragraph:153'),('NEW-247','paragraph:102')]:
    if block(sid,loc):
        add_procedure(new_org_ids[sid],'Приём документов абитуриентов',[blocktext(sid,loc)],sid,loc,new_specs[sid][1],False)

# The newly supplied charters also state institutional functions and concrete
# services. Keep each statement at its own exact paragraph locator.
for sid,loc,typ in [
 ('NEW-236','paragraph:19','rail_transport'),
 ('NEW-240','paragraph:28','newspaper_publication'),
 ('NEW-241','paragraph:32','education'),
 ('NEW-242','paragraph:111','library'),
 ('NEW-243','paragraph:31','sports_development'),
 ('NEW-244','paragraph:33','public_broadcasting'),
 ('NEW-245','paragraph:24','medical_education'),
 ('NEW-247','paragraph:23','education')]:
    add_comp(new_org_ids[sid],blocktext(sid,loc),sid,loc,new_specs[sid][1],typ)
for sid,loc,name in [
 ('NEW-242','paragraph:133','Доступ к библиотечному фонду'),
 ('NEW-242','paragraph:134','Библиографическое обслуживание'),
 ('NEW-245','paragraph:53','Дополнительные платные образовательные услуги'),
 ('NEW-247','paragraph:124','Платные образовательные услуги')]:
    add_service(new_org_ids[sid],name,blocktext(sid,loc),sid,loc,new_specs[sid][1])
add_procedure(new_org_ids['NEW-245'],'Порядок предоставления дополнительных платных услуг',
              [blocktext('NEW-245','paragraph:55')],'NEW-245','paragraph:55',
              new_specs['NEW-245'][1],False)

LANDLINE=re.compile(r'(?<!\d)(?:\+996\s*)?\(?0?37\d{2}\)?[\s\-]*\(?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d\)?')
MOBILE=re.compile(r'(?<!\d)(?:\+996\s*)?0?[2579]\d{2}[\s\-]?\d{2,3}[\s\-]?\d{2}[\s\-]?\d{2,3}(?!\d)')

# Customer's tabular contact directory: each row carries the organization, address, role and phone.
for b in E['SRC-225']['blocks']:
    if not b['locator'].startswith('table:1:row:'):continue
    parts=[x.strip() for x in b['text'].split('|')]
    if len(parts)<6 or not parts[1] or parts[1] in ('Мекеменин аталышы','Облустук/райондук, шаардык мекемелердин аталышы'):continue
    name,address,competence,questions,responsible=parts[1:6]
    oid=ensure_org(name,'SRC-225',b['locator'],territory_from(address or name),'ky')
    terr=(oid_index[oid].get('territory') or [None])[0]
    if competence and len(competence)>18:add_comp(oid,competence,'SRC-225',b['locator'],terr)
    for number in LANDLINE.findall(responsible):
        add_checked(oid,'phone',number,'SRC-225',b['locator'],territory=terr)
    for number in MOBILE.findall(responsible):
        if any(norm(number)==norm(c['value']) for c in C if c['organization_id']==oid and c['type']=='phone'):continue
        add_checked(oid,'phone',number,'SRC-225',b['locator'],territory=terr,visibility='INTERNAL_ONLY',reason='mobile beside named role/person')

# Insurer's explicit call-routing sheet: general and sector channels are public; named employee mobiles are internal.
insurer=next(o['organization_id'] for o in O if 'страх' in org_name(o).lower() and 'филиал' in org_name(o).lower())
for b in E['SRC-109']['blocks']:
    if not b['locator'].startswith('sheet:Маршрутизация:row:'):continue
    parts=[x.strip() for x in b['text'].split('|')]
    if len(parts)<3 or not parts[2].startswith('+996'):continue
    number=parts[2].split(' аркылуу')[0].strip()
    vis='INTERNAL_ONLY' if re.search(r'Примкулова|директор|орун басар',parts[1],re.I) else 'PUBLIC'
    add_checked(insurer,'phone',number,'SRC-109',b['locator'],visibility=vis,reason='named role mobile' if vis!='PUBLIC' else None)

# Filled service cards for Kara-Köl; every section starts with an explicit institution.
groups=[];current=[]
for b in E['SRC-145']['blocks']:
    if 'Название службы:' in b['text']:
        if current:groups.append(current)
        current=[b]
    elif current:
        if re.search(r'^\s*2\. Какая служба',b['text']):groups.append(current);current=[];break
        current.append(b)
if current:groups.append(current)
for group in groups:
    raw=' '.join(b['text'] for b in group)
    nm=re.search(r'Название службы:\s*(.+?)\s+Чем занимается:',raw,re.I)
    if not nm:continue
    name=' '.join(nm.group(1).split()).strip('● ;')
    terr='city:Кара-Көл';oid=ensure_org(name,'SRC-145',group[0]['locator'],terr,'ru')
    comp=re.search(r'Чем занимается:\s*(.+?)\s+Руководитель:',raw,re.I)
    if comp:add_comp(oid,comp.group(1),'SRC-145',group[0]['locator'],terr)
    for b in group:
        txt=b['text']
        if 'Телефон:' in txt:
            for num in LANDLINE.findall(txt):add_checked(oid,'phone',num,'SRC-145',b['locator'],territory=terr)
            for num in MOBILE.findall(txt):add_checked(oid,'phone',num,'SRC-145',b['locator'],territory=terr,visibility='INTERNAL_ONLY',reason='mobile in service card beside leader/employee')
        if re.search(r'\bАдрес\s*:',txt,re.I):
            m=re.search(r'Адрес\s*:\s*(.+?)(?=График работы:|$)',txt,re.I)
            if m and len(m.group(1).strip())>6:add_checked(oid,'address',m.group(1), 'SRC-145',b['locator'],territory=terr,kind='office_or_unspecified')
        if 'График работы:' in txt:
            m=re.search(r'График работы:\s*([^\n]+)',txt,re.I)
            if m and re.search(r'\d',m.group(1)):add_checked(oid,'working_hours',m.group(1),'SRC-145',b['locator'],territory=terr)

# Nine filled municipal cards on page 2–3 of SRC-130; their leader mobiles are not public.
bk_specs=[
 ('МП «Базар-Коргон Тазалык»','page:2:line:2','page:2:line:3','page:2:line:4','page:2:line:5','убирает мусор и отходы'),
 ('МП «Базар-Коргонсууканал»','page:2:line:7','page:2:line:8','page:2:line:9','page:2:line:10','снабжает жителей питьевой водой'),
 ('МП «Айыл чарба»','page:2:line:12','page:2:line:13','page:2:line:14','page:2:line:15','пастбища и земля'),
 ('МП «Базар-Коргон жылуулук»','page:2:line:17','page:2:line:18','page:2:line:19','page:2:line:20','отопление многоквартирных домов и школы'),
 ('Хозрасчетное МП «Базар-Коргон автобекет»','page:2:line:23','page:2:line:24','page:2:line:25','page:2:line:26','перевозка пассажиров'),
 ('Муниципальное учреждение футбольный клуб «Базар-Коргон сити»','page:2:line:29','page:2:line:31',None,'page:2:line:32','развитие футбола'),
 ('Департамент благоустройства и озеленения при мэрии города Базар-Коргон','page:2:line:35','page:2:line:37','page:2:line:38','page:2:line:39','озеленение и освещение города'),
 ('Департамент капитального строительства при мэрии города Базар-Коргон','page:2:line:42','page:2:line:44','page:3:line:1','page:3:line:2','строительство и развитие инфраструктуры'),
 ('Департамент по управлению муниципальной собственностью города Базар-Коргон','page:3:line:5','page:3:line:7','page:3:line:8','page:3:line:9','муниципальная собственность города')]
for name,nloc,ploc,aloc,hloc,comp in bk_specs:
    terr='city:Базар-Коргон';oid=ensure_org(name,'SRC-130',nloc,terr,'ru')
    add_comp(oid,comp,'SRC-130',nloc,terr)
    if ploc:
        for num in MOBILE.findall(blocktext('SRC-130',ploc)):
            add_checked(oid,'phone',num,'SRC-130',ploc,territory=terr,visibility='INTERNAL_ONLY',reason='leader personal mobile')
    if aloc:
        m=re.search(r'Адрес:\s*([^\n]+)',blocktext('SRC-130',aloc),re.I)
        if m:add_checked(oid,'address',m.group(1),'SRC-130',aloc,territory=terr,kind='office_or_unspecified')
    if hloc:
        m=re.search(r'График работы:\s*([^\n]+)',blocktext('SRC-130',hloc),re.I)
        if m:add_checked(oid,'working_hours',m.group(1),'SRC-130',hloc,territory=terr)

# Clear city and utility cards, with office lines separate from employee mobiles.
manas_water=ensure_org('Управление водоканал Манас','SRC-164','paragraph:56','city:Манас','ru')
add_comp(manas_water,'ремонт уличных труб, прорыв воды, строительство канализаций, отключение чистой воды','SRC-164','paragraph:56','city:Манас')
add_checked(manas_water,'phone','0779973966','SRC-164','paragraph:56',territory='city:Манас',visibility='INTERNAL_ONLY',reason='mobile beside named responsible employee')
manas_taz=ensure_org('Манас Тазалык','SRC-164','paragraph:48','city:Манас','ru')
add_comp(manas_taz,'вывоз мусора, установка контейнеров, контроль за полигоном','SRC-164','paragraph:48','city:Манас')
for row,topic in [(5,'прорыв воды'),(6,'нет воды'),(7,'открытый люк')]:
    add_route(manas_water,topic,'SRC-164',f'table:1:row:{row}','city:Манас')
for row,topic,oid in [(2,'Установить Интернет',None),(3,'Интернет не работает',None)]:
    pass
telecom=ensure_org('Городская телефонная сеть г. Манас — бюро повреждений','SRC-147','paragraph:8','city:Манас','ru')
add_comp(telecom,'Устранение повреждений, подключение Интернет и телефона','SRC-147','paragraph:8','city:Манас')
for num in ('1812','145','0372250808','0372250606'):
    add_checked(telecom,'phone',num,'SRC-147','paragraph:8',territory='city:Манас')
add_checked(telecom,'email','djal_kt@kt.kg','SRC-147','paragraph:8',territory='city:Манас')
add_checked(telecom,'address','г.Манас ул.Осмонова 128а','SRC-147','paragraph:9',territory='city:Манас',kind='office_or_unspecified')
add_checked(telecom,'working_hours','08.00-17.00','SRC-147','paragraph:9',territory='city:Манас')

# The regional letters' own letterheads are distinct from their recipients.
direct=[
 ('SRC-121','Ала-Бука райондук мамлекеттик администрациясы','district:Ала-Бука',[
  ('fax','+996 (0-3741) 5-02-09','page:1:line:9'),('email','ala-buka_rga@mail.ru','page:1:line:10')]),
 ('SRC-149','Майлуу-Суу шаардык Социалдык фонд башкармалыгы','city:Майлуу-Суу',[
  ('address','Майлуу-Суу ш., Ленин көч.,14','page:1:line:10'),('phone','+996 (3744) 5-04-57','page:1:line:11'),
  ('fax','(03744) 5-06-07','page:1:line:12'),('email','mailuu-suu@sf.kg','page:1:line:18')]),
 ('SRC-150','Жер ресурстары агенттигинин Майлуу-Суу филиалы','city:Майлуу-Суу',[
  ('address','Майлуу-Суу шаары, М. Конгантиева көчөсү, 41','page:1:line:49'),
  ('phone','+996(3744)5-01-58','page:1:line:50'),('fax','+996 5-01-67','page:1:line:12'),
  ('email','gosregistr.mailuu-suu@mail.ru','page:1:line:13'),
  ('working_hours','дүйшөмбү–жума, саат 08:30дан 17:00гө чейин','page:1:line:51')]),
 ('SRC-169','Жерде жүрүүчү жана суу транспорту департаментинин Жалал-Абад аймактык башкармалыгы','region:Жалал-Абад',[
  ('address','Манас шаары, Ш.Абдраманов көчөсү, 10','page:1:line:38'),('phone','(3722) 5-10-27','page:1:line:39'),
  ('email','mr.zhtugaavt@mail.ru','page:1:line:39')]),
 ('SRC-190','Ноокен райондук финансы башкармалыгы','district:Ноокен',[
  ('address','Турдумбетов көчөсү 37','page:1:line:7'),('phone','03734 50228','page:2:line:21')]),
 ('SRC-196','Жалал-Абад облустук капиталдык курулуш башкармалыгы','region:Жалал-Абад',[
  ('address','Манас шаары, Эркиндик көчөсү,11','page:1:line:27'),('phone','03722 2 05 06','page:1:line:28'),
  ('email','ja_ukc_djgc_2013@mail.ru','page:1:line:30'),('working_hours','с 9-00 до 18-00','page:2:line:24')]),
 ('SRC-202','Жалал-Абадский областной отдел антимонопольного регулирования','region:Жалал-Абад',[
  ('address','Манас шаары, Ю. Абдурахманов көч., 6','page:1:line:19'),
  ('phone','+996 (3722) 5-06-30','page:1:line:21'),('fax','+996 (3722) 5-06-30','page:1:line:21'),
  ('email','azhalalabad@mail.ru','page:1:line:22')]),
 ('SRC-206','Сузак райондук мамлекеттик администрациясы','district:Сузак',[
  ('address','Сузак айылы, Сатвалды Палван көчөсү, 108','page:1:line:48'),
  ('phone','(03748) 5-00-01','page:1:line:49'),('fax','(03748) 5-00-75','page:1:line:49'),
  ('email','suzak_rma@mail.ru','page:1:line:50'),('email','info@suzak.gov.kg','page:1:line:50')]),
 ('SRC-209','Таш-Көмүр шаардык мэриясы','city:Таш-Көмүр',[
  ('phone','(03745)5-00-01','page:1:line:6'),('phone','5-00-30','page:1:line:6'),
  ('fax','(03745)5-04-10','page:1:line:6'),('email','meriya-tk@bk.ru','page:1:line:7')]),
 ('SRC-210','Тогуз-Торо райондук мамлекеттик администрациясы','district:Тогуз-Торо',[
  ('phone','(03738) 5-01-60','page:1:line:9'),('fax','(03738) 5-00-04','page:1:line:9'),
  ('email','toguz_torouskiyi_gosadm@mail.ru','page:1:line:10'),('email','toguz.torouskiyi.gosadm@gmail.com','page:1:line:11')]),
 ('SRC-221','Жалал-Абадское региональное управление Министерства природных ресурсов, экологии и технического надзора','region:Жалал-Абад',[
  ('address','Манас ш, З.Жамашев көчөсү, 2','page:1:line:36'),('fax','(3722) 4-02-93','page:1:line:37'),
  ('fax','4-02-60','page:1:line:37'),('email','JALALABADRU@gov.kg','page:1:line:38')])]
for sid,name,terr,fields in direct:
    oid=ensure_org(name,sid,fields[0][2],terr,'ky' if re.search(r'башкармалы|мэриясы|департаментинин',name,re.I) else 'ru')
    for typ,value,loc in fields:
        status='AMBIGUOUS' if typ in ('phone','fax') and len(digits(value))<9 else 'SOURCE_CONFIRMED'
        vis='INTERNAL_ONLY' if status!='SOURCE_CONFIRMED' else 'PUBLIC'
        if typ=='address' and (sid,typ,value) in []:pass
        add_checked(oid,typ,value,sid,loc,territory=terr,kind='office_or_unspecified' if typ=='address' else None,visibility=vis,status=status,
                    reason='local number without complete dialing code' if status=='AMBIGUOUS' else None)
    if sid=='SRC-169':add_comp(oid,'контроль сохранности дорог общего пользования, лицензии и разрешения в транспортной сфере','SRC-169','page:1:line:14',terr)
    if sid=='SRC-150':add_comp(oid,'кадастровые работы и государственная регистрация прав на недвижимость','SRC-150','page:1:line:53',terr)

# Small explicit forms: office hours and addresses can be public even when a named mobile cannot.
small_forms=[
 ('SRC-111','КР Президентине караштуу Дин иштери жана этностор аралык мамилелер боюнча улуттук агенттиктин Жалал-Абад облусундагы өкүлү','region:Жалал-Абад','sheet:Sheet1:row:1',[
  ('phone','777227972','sheet:Sheet1:row:5','AMBIGUOUS'),('address','Ж. Абдурахманов № 6','sheet:Sheet1:row:6','SOURCE_CONFIRMED'),
  ('working_hours','09:00 - 18:00','sheet:Sheet1:row:7','SOURCE_CONFIRMED')]),
 ('SRC-139','Жалал-Абад аймактык бөлүмү — транспорт каттоо борбору','city:Манас','page:1:line:16',[
  ('phone','03722 5-09-19','page:1:line:19','SOURCE_CONFIRMED'),('address','Манас шаары, Шопокова 32','page:1:line:20','SOURCE_CONFIRMED')]),
 ('SRC-173','Кочкор-Ата шаарынын мэриясы','city:Кочкор-Ата','paragraph:2',[
  ('address','Кочкор-Ата шаары, Токтогул көчөсү №17','paragraph:6','SOURCE_CONFIRMED'),
  ('working_hours','Дүйшөмбү – Жума. Саат 8:30 дан 17:30га чейин','paragraph:7','SOURCE_CONFIRMED'),
  ('phone','+996 772 289 730','paragraph:5','INTERNAL_ONLY')]),
 ('SRC-177','Момбеков айыл өкмөтү','ayyl_area:Момбеков','paragraph:2',[
  ('address','Момбеков айылы К. Сейтканов көчөсү № 47','paragraph:5','SOURCE_CONFIRMED'),
  ('working_hours','8:30 дан 17:30 га чейин','paragraph:5','SOURCE_CONFIRMED'),
  ('phone','0222385261','paragraph:4','INTERNAL_ONLY')]),
 ('SRC-183','Ноокен райондук мамлекеттик администрациясы','district:Ноокен','paragraph:2',[
  ('address','Масы айылы Турдумбетов көчөсү № 37','paragraph:29','SOURCE_CONFIRMED'),
  ('phone','+996 550 863 399','paragraph:28','INTERNAL_ONLY')]),
 ('SRC-185','Мамлекеттик салык кызматынын Жалал-Абад облусунун Ноокен району боюнча башкармалыгы','district:Ноокен','paragraph:2',[
  ('address','Масы айылы, Токтогул көчөсү 1','paragraph:5','SOURCE_CONFIRMED'),
  ('phone','0776 885 553','paragraph:4','INTERNAL_ONLY')]),
 ('SRC-186','Ноокен райондук Эмгек, социалдык камсыздоо жана миграция башкармалыгы','district:Ноокен','paragraph:2',[
  ('address','Масы айылы Т. Эшенкулов №43','paragraph:5','SOURCE_CONFIRMED'),
  ('working_hours','Дүйшөмбүдөн-Жума күнгө чейин 8:30 дан 17:30 га чейин түшкү тыныгуу 12:00 дөн 13:00 го чейин','paragraph:5','SOURCE_CONFIRMED')]),
 ('SRC-189','Ноокенский отдел Государственного центра по регистрации транспортных средств и водительского состава','district:Ноокен','page:1:line:5',[
  ('working_hours','ПН-ПТ с 08:30 до 17:30','page:1:line:12','SOURCE_CONFIRMED'),
  ('phone','(03734) 5-31-30','page:4:line:17','SOURCE_CONFIRMED')]),
 ('SRC-194','Шамалдуу-Сай шаардык мэрия','city:Шамалдуу-Сай','paragraph:2',[
  ('address','Ленина көчөсү № 28','paragraph:5','SOURCE_CONFIRMED'),
  ('working_hours','08:30- 17:30','paragraph:5','SOURCE_CONFIRMED'),
  ('phone','0770685 454','paragraph:4','INTERNAL_ONLY')]),
 ('SRC-217','Жалал-Абад облустук дене тарбия жана спорт башкармалыгы','region:Жалал-Абад','paragraph:3',[
  ('address','Манас шаары Тоголок-Молдо 80/1','paragraph:8','CONFLICT'),
  ('working_hours','09:00-18:00','paragraph:9','SOURCE_CONFIRMED'),
  ('phone','0509 061 917','paragraph:7','INTERNAL_ONLY')]),
 ('SRC-218','МП «Каныш-Кыя Тазалык»','ayyl_area:Каныш-Кыя','paragraph:11',[
  ('address','Чаткальский район село Каныш-Кыя','paragraph:17','SOURCE_CONFIRMED'),
  ('working_hours','08:30-17:30','paragraph:17','SOURCE_CONFIRMED'),
  ('phone','0774836447','paragraph:16','INTERNAL_ONLY')]),
 ('SRC-220','Айыл окмоту Терек-Сайского айылного аймака','ayyl_area:Терек-Сай','paragraph:8',[
  ('address','с.Терек-Сай, ул. К.Турдалиева, 11','paragraph:8','SOURCE_CONFIRMED'),
  ('working_hours','Понедельник – Пятница 08:30 – 17:30','paragraph:8','SOURCE_CONFIRMED'),
  ('phone','0777 519005','paragraph:8','INTERNAL_ONLY')]),
 ('SRC-222','Жалал-Абадское региональное управление Министерства природных ресурсов, экологии и технического надзора','region:Жалал-Абад','paragraph:14',[
  ('phone','(3722) 4-03-93','paragraph:43','SOURCE_CONFIRMED'),
  ('address','г.Манас, ул. З.Жамашева 2','paragraph:43','SOURCE_CONFIRMED'),
  ('working_hours','09.00 – 18.00','paragraph:43','SOURCE_CONFIRMED')])]
for sid,name,terr,nloc,fields in small_forms:
    oid=ensure_org(name,sid,nloc,terr)
    for typ,value,loc,status in fields:
        vis='PUBLIC' if status=='SOURCE_CONFIRMED' else 'INTERNAL_ONLY'
        add_checked(oid,typ,value,sid,loc,territory=terr,visibility=vis,
                    status=status if status!='INTERNAL_ONLY' else 'SOURCE_CONFIRMED',
                    kind=('legal_address' if sid in ('SRC-173','SRC-177','SRC-183','SRC-185','SRC-186','SRC-194') and typ=='address' else 'office_or_unspecified' if typ=='address' else None),
                    reason='named employee mobile or uncertain public designation' if vis=='INTERNAL_ONLY' else None)

# A fully named 24-hour duty line is public. Other named employee mobiles in the form remain internal.
res=ensure_org('Ноокен райондук электр тармактары','SRC-184','paragraph:16','district:Ноокен','ky')
for loc in ('paragraph:16','paragraph:17','paragraph:18','paragraph:19'):
    txt=blocktext('SRC-184',loc)
    m=re.search(r'Телефон:\s*([^\s]+)',txt)
    if m:
        num=m.group(1)
        vis='PUBLIC' if loc=='paragraph:19' else 'INTERNAL_ONLY'
        add_checked(res,'phone',num,'SRC-184',loc,territory='district:Ноокен',visibility=vis,reason=None if vis=='PUBLIC' else 'named employee mobile')
    if loc=='paragraph:19':
        add_checked(res,'working_hours','Круголосуточно','SRC-184',loc,territory='district:Ноокен')

# SRC-205 mixes office lines and personal mobiles. Only complete office landlines tied to a named body become public.
regional=ensure_org('Аппарат полномочного представителя Президента КР в Жалал-Абадской области','SRC-205','paragraph:6','region:Жалал-Абад','ru')
for b in E['SRC-205']['blocks']:
    if not b['locator'].startswith('table:'):continue
    parts=[p.strip() for p in b['text'].split('|')]
    if not parts:continue
    # Table 1 contains the administration's internal extension numbers and personal cellular numbers.
    if b['locator'].startswith('table:1:row:') and int(b['locator'].split(':')[-1])>=3:
        for num in MOBILE.findall(b['text']):
            add_checked(regional,'phone',num,'SRC-205',b['locator'],territory='region:Жалал-Абад',visibility='INTERNAL_ONLY',reason='SRC-205 personal cellular column')
        continue
    # Explicit city-hall rows with a complete dialable work/fax number.
    if re.search(r'Мэрия города|Мэрия г\.',parts[0],re.I):
        name=parts[0].split(' 715')[0].strip()
        oid=ensure_org(name,'SRC-205',b['locator'],territory_from(name),'ru')
        for num in LANDLINE.findall(parts[0]):
            add_checked(oid,'fax',num,'SRC-205',b['locator'],visibility='PUBLIC')
    # Every unassigned directory number remains in review below rather than being lost.

# Territory-specific route suggestions. No record here authorizes automatic backend assignment.
arst='ayyl_area:Арстанбап-Ата'
arst_office=ensure_org('Арстанбап-Ата айыл өкмөтү','SRC-126','page:1:line:3',arst,'ky')
arst_utility=ensure_org('МП «Арстанбап-Ата таза суу жана тазалык»','SRC-126','page:1:line:60',arst,'ky')
achy=ensure_org('Ачы электр тармактары','SRC-126','page:2:line:6',arst,'ky')
add_service(arst_utility,'Ичүүчү суу менен камсыздоо','ичүүчү суу жана суу түтүктөрү боюнча маселелер','SRC-126','page:5:line:36',arst)
add_service(arst_utility,'Таштанды чыгаруу','таштанды чыгаруу боюнча маселелер','SRC-126','page:5:line:37',arst)
for loc,topic,oid,target in [
 ('page:1:line:60','таштанды чыгарылган жок',arst_utility,None),
 ('page:1:line:65','ичүүчү суу жок',arst_utility,None),
 ('page:2:line:1','суу түтүгү жарылды',arst_utility,None),
 ('page:2:line:4','ачык люк',arst_utility,None),
 ('page:2:line:6','электр жарыгы өчтү',achy,None),
 ('page:2:line:12','көчө жарыгы күйбөй жатат',arst_office,'Ачы электр тармактары менен бирге'),
 ('page:2:line:13','айылдын жолу бузулган',arst_office,'тиешелүү жол тейлөө кызматы менен бирге'),
 ('page:2:line:33','жер тилкесине байланыштуу маселе',arst_office,None)]:
    add_route(oid,topic,'SRC-126',loc,arst,target)

sady='ayyl_area:Сайдыкум'
sady_office=ensure_org('Сайдыкум айыл өкмөтү','SRC-129','paragraph:2',sady,'ky')
for row,topic,target in [(3,'айылдын жолу бузулган','райондук жол тейлөө кызматы'),
                         (4,'таштанды чыгарылган жок','тазалык кызматы'),
                         (5,'суу түтүгү жарылды','суу чарба кызматы'),
                         (6,'үйгө суу келбей жатат','суу менен камсыздоо кызматы')]:
    add_route(sady_office,topic,'SRC-129',f'table:1:row:{row}',sady,target)
add_route(sady_office,'жолдо ачык калган люк','SRC-129','paragraph:90',sady,
          'бул айыл өкмөтүнүн карамагына кирбейт; жооптуу кызмат көрсөтүлгөн эмес',True)
for oid,sid,first,last,name in [
 (sady_office,'SRC-129',110,115,'Сайдыкум айыл өкмөтүнө кайрылуу'),
 (ensure_org('Акман айыл өкмөтү','SRC-127','paragraph:1','ayyl_area:Акман','ky'),'SRC-127',91,97,'Акман айыл өкмөтүнө кайрылуу')]:
    steps=[blocktext(sid,f'paragraph:{i}') for i in range(first,last+1)]
    rid=add_procedure(oid,name,steps,sid,f'paragraph:{first}',(oid_index[oid].get('territory') or [None])[0],True)
    proc=next(x for x in procedures if x['procedure_id']==rid)
    proc['provenance']=[prov(sid,f'paragraph:{i}') for i in range(first,last+1)]
    for i in range(first+1,last+1):register(sid,f'paragraph:{i}',rid)

manas_office=ensure_org('Мэрия города Манас','SRC-164','table:1:row:1','city:Манас','ru')
add_checked(manas_office,'email','manasmeriya@gmail.com','SRC-164','table:1:row:1',territory='city:Манас')
manas_roads=ensure_org('Управление городских дорог','SRC-164','paragraph:24','city:Манас','ru')
manas_jkh=ensure_org('Департамент коммунального хозяйства и благоустройства','SRC-164','paragraph:41','city:Манас','ru')
for row,topic,oid in [(2,'не горит уличный фонарь',manas_jkh),(3,'яма на дороге',manas_roads),
                      (4,'не вывезли мусор',manas_taz),(8,'сломанный светофор',manas_jkh),
                      (10,'бродячие собаки',manas_taz)]:
    add_route(oid,topic,'SRC-164',f'table:1:row:{row}','city:Манас')

# Actual services, distinguished from a full procedural recipe.
vehicle=ensure_org('Жалал-Абад аймактык бөлүмү — транспорт каттоо борбору','SRC-139','page:1:line:16','city:Манас','ky')
for loc,name in [('page:1:line:6','Регистрация и перерегистрация транспортных средств'),
                 ('page:1:line:7','Первичная выдача и замена водительских удостоверений')]:
    add_service(vehicle,name,blocktext('SRC-139',loc),'SRC-139',loc,'city:Манас')
nooken_cad=ensure_org('Жер ресурстары агенттигинин Ноокен филиалы','SRC-182','page:1:line:12','district:Ноокен','ky')
for loc,name in [('page:1:line:17','Государственная регистрация земельных участков'),
                 ('page:1:line:19','Регистрация недвижимости'),
                 ('page:1:line:21','Кадастровая информация'),
                 ('page:1:line:24','Подготовка кадастровых планов'),
                 ('page:1:line:26','Геодезические работы')]:
    add_service(nooken_cad,name,blocktext('SRC-182',loc),'SRC-182',loc,'district:Ноокен')
sport=ensure_org('Жалал-Абад облустук дене тарбия жана спорт башкармалыгы','SRC-217','paragraph:3','region:Жалал-Абад','ky')
add_comp(sport,blocktext('SRC-217','paragraph:4'),'SRC-217','paragraph:4','region:Жалал-Абад')
for loc in ('paragraph:11','paragraph:12','paragraph:13'):
    add_route(sport,blocktext('SRC-217',loc).split('—')[0].strip('• '),'SRC-217',loc,'region:Жалал-Абад',blocktext('SRC-217',loc).split('—')[-1].strip())

# Further filled cards discovered by the full-source pass (not present in the 194-fact audit table).
gask=next(o['organization_id'] for o in O if 'архитектурно-строительного контроля' in org_name(o).lower())
add_checked(gask,'working_hours','Пн–Пт с 09:00 до 18:00 (Обед с 12:30 до 13:30)','SRC-124','page:1:line:13',territory='city:Манас')
office=ensure_org('ЦОВП г. Майлуу-Суу','SRC-152','paragraph:20','city:Майлуу-Суу','ru')
for typ,value in [('phone','+996 (3744) 5-14-56'),('address','г.Майлуу-Суу ул.Сыдыкова 7'),('working_hours','с 7:30 до 17:45')]:
    add_checked(office,typ,value,'SRC-152','paragraph:20',territory='city:Майлуу-Суу',kind='office_or_unspecified' if typ=='address' else None)
for value in ('5-15-75','5-15-74'):
    add_checked(office,'phone',value,'SRC-152','paragraph:20',territory='city:Майлуу-Суу',visibility='INTERNAL_ONLY',status='AMBIGUOUS',reason='local extension without explicit dialing prefix')
property_office=ensure_org('Управление муниципальной собственности г. Майлуу-Суу','SRC-153','page:1:line:23','city:Майлуу-Суу','ru')
add_checked(property_office,'address','г.Майлуу-Суу, ул.Ленина№135а','SRC-153','page:1:line:29',territory='city:Майлуу-Суу',kind='office_or_unspecified')
add_checked(property_office,'working_hours','понедельник–пятнича, с 08:30 до 17:30','SRC-153','page:1:line:30',territory='city:Майлуу-Суу')
add_checked(property_office,'phone','5-29-19','SRC-153','page:1:line:28',territory='city:Майлуу-Суу',visibility='INTERNAL_ONLY',status='AMBIGUOUS',reason='local number without area code')
res_mailuu=ensure_org('Майлуу-Сууйский район электрических сетей','SRC-154','paragraph:10','city:Майлуу-Суу','ru')
add_comp(res_mailuu,'Эксплуатация, обслуживание и ремонт электросетей, устранение аварий, подключение абонентов','SRC-154','paragraph:10','city:Майлуу-Суу')
for typ,value,loc,purpose in [
 ('phone','0-3744-5-22-77','paragraph:10',None),('address','г.Майлуу-Суу ул.Советская Армия 36а','paragraph:10','office_or_unspecified'),
 ('working_hours','Круглосуточно (24/7)','paragraph:10','emergency_dispatch'),
 ('working_hours','Пн.–Чт. с 08:00 до 17:00','paragraph:11','administration'),
 ('working_hours','Пятница с 08:00 до 15:45; (перерыв с 12:00 до 12:45)','paragraph:12','administration')]:
    add_checked(res_mailuu,typ,value,'SRC-154',loc,territory='city:Майлуу-Суу',kind=purpose)
dostuk=ensure_org('Муниципальное территориальное управление «Достук»','SRC-159','paragraph:5','city:Манас','ru')
add_comp(dostuk,blocktext('SRC-159','paragraph:6'),'SRC-159','paragraph:6','city:Манас')
add_checked(dostuk,'address','г. Манас, ул Шопокова дом № 40','SRC-159','paragraph:10',territory='city:Манас',kind='office_or_unspecified')
add_checked(dostuk,'working_hours','Понедельник – Пятница: 08:30 – 17:30 (Перерыв: 12:00 – 13:00)','SRC-159','paragraph:11',territory='city:Манас')
add_checked(dostuk,'phone','+3722 7-19-42','SRC-159','paragraph:9',territory='city:Манас',visibility='INTERNAL_ONLY',status='AMBIGUOUS',reason='country/area code malformed in source')
roads=ensure_org('Управление городских дорог мэрии города Манас','SRC-165','paragraph:2','city:Манас','ru')
add_checked(roads,'phone','03722 5 03 49','SRC-165','paragraph:2',territory='city:Манас')
add_checked(roads,'phone','5 02 04','SRC-165','paragraph:2',territory='city:Манас',visibility='INTERNAL_ONLY',status='AMBIGUOUS',reason='local number without area code')
heating=ensure_org('“Шамалдуу-Сай жылуулук менен камсыздоо” муниципалдык ишканасы','SRC-172','paragraph:2','city:Шамалдуу-Сай','ky')
add_checked(heating,'working_hours','8:30-17:30','SRC-172','paragraph:6',territory='city:Шамалдуу-Сай')
add_checked(heating,'address','Темир-Жол көчөсү №жок','SRC-172','paragraph:5',territory='city:Шамалдуу-Сай',visibility='INTERNAL_ONLY',status='AMBIGUOUS',kind='incomplete_address',reason='house number absent')
forest=ensure_org('Кочкор-Ата токой чарбасы','SRC-176','paragraph:3','city:Кочкор-Ата','ky')
add_checked(forest,'working_hours','башталышы 9-00 аякташы 18-00','SRC-176','paragraph:81',territory='city:Кочкор-Ата')
social=ensure_org('Ноокен райондук Социалдык фонд башкармалыгы','SRC-187','paragraph:2','district:Ноокен','ky')
add_checked(social,'address','Ноокен району Масы айылы И.Турдумбетов көчөсү № 36','SRC-187','paragraph:9',territory='district:Ноокен',kind='legal_address')
add_checked(social,'working_hours','дүйшөмбү-жума күндөрү саат 9:00 дөн 18:00 гө чейин, түштөнүү убактысы саат 12:30-13:30гө чейин','SRC-187','paragraph:10',territory='district:Ноокен')
add_checked(social,'phone','(03734) 5-05-04','SRC-187','paragraph:7',territory='district:Ноокен')
add_checked(social,'phone','0772-141-279','SRC-187','paragraph:7',territory='district:Ноокен',visibility='INTERNAL_ONLY',reason='mobile adjacent to named leader')

kyrgyztelecom=ensure_org('Кыргызтелеком — Жалал-Абад аймактык бөлүмү','SRC-146','page:1:line:6','region:Жалал-Абад','ky')
add_checked(kyrgyztelecom,'website','www.kt.kg','SRC-146','page:1:line:6',territory='region:Жалал-Абад')
add_checked(kyrgyztelecom,'email','djal_kt@kt.kg','SRC-146','page:1:line:6',territory='region:Жалал-Абад')
education=ensure_org('Жалал-Абад областтык билим берүү усулдук борбору','SRC-198','page:1:line:2','region:Жалал-Абад','ky')
add_checked(education,'address','Манас шаары, Абдырахманов көчөсү-6','SRC-198','page:1:line:4',territory='region:Жалал-Абад',kind='office_or_unspecified')
add_checked(education,'email','metod-sentr@bk.ru','SRC-198','page:1:line:6',territory='region:Жалал-Абад')
for typ,value in [('phone','2-50-58'),('fax','2-43-64'),('fax','2-05-79')]:
    add_checked(education,typ,value,'SRC-198','page:1:line:5',territory='region:Жалал-Абад',visibility='INTERNAL_ONLY',status='AMBIGUOUS',reason='local number without explicit area code')
police=ensure_org('Жалал-Абад облустук ички иштер башкармалыгы','SRC-214','paragraph:145','region:Жалал-Абад','ky')
add_checked(police,'phone','+996 997 661 610','SRC-214','paragraph:145',territory='region:Жалал-Абад',
            reason='document explicitly says number belongs to regional police office')
for loc,url in [('paragraph:147','https://www.facebook.com/share/1EUY3gufjw/'),
                ('paragraph:149','https://www.instagram.com/uvdjalalabad?stkn=MWIxMXpmcjI0bWNkNQ==')]:
    add_checked(police,'website',url,'SRC-214',loc,territory='region:Жалал-Абад')

# The library registry and charter differ on the street type; retain both as conflict records.
library=new_org_ids['NEW-242']
for loc,address in [('paragraph:21','Джалал-Абад, пер.Т.Байзакова, 20'),
                    ('paragraph:56','Жалал-Абад, Т.Байзаков Кең Көчөсү, 20')]:
    add_checked(library,'address',address,'NEW-242',loc,territory='city:Жалал-Абад',
                visibility='INTERNAL_ONLY',status='CONFLICT',kind='legal_address')

add_checked(insurer,'address','Жалал-Абад облусу, Манас шаары, Ю. Абдурахманов көчөсү, 6',
            'SRC-134','page:2:line:16',territory='city:Манас',kind='office_or_unspecified')
add_checked(insurer,'working_hours','Дүйшөмбү-жума, 09:00-18:00','SRC-134','page:2:line:18',territory='city:Манас')
add_checked(insurer,'email','djalal-abad@gso.kg','SRC-134','page:1:line:15',territory='city:Манас')
add_checked(insurer,'phone','+996 556 712 000','SRC-134','page:1:line:49',territory='city:Манас',
            visibility='INTERNAL_ONLY',reason='executor mobile stated immediately above')
add_checked(insurer,'phone','+996 999 890 469','SRC-134','page:1:line:51',territory='city:Манас',
            reason='explicitly labelled general contact phone')
add_checked(next(o['organization_id'] for o in O if org_name(o)=='Майлуу-Суу шаардык Социалдык фонд башкармалыгы'),
            'working_hours','саат 9-00 – 18-00, ишемби,жекшемби дем алыш','SRC-149','page:1:line:53',
            territory='city:Майлуу-Суу')

# Explicit institutional mailboxes on signed/letterheaded source documents.
mailboxes=[
 ('SRC-115','Жалал-Абад жол-курулуш башкармалыгы','region:Жалал-Абад','ja.kyrgyzavtojol@mail.ru','page:1:line:22'),
 ('SRC-117','Аксы райондук мамлекеттик администрациясы','district:Аксы','adm16_aksy@mail.ru','page:1:line:7'),
 ('SRC-119','Ала-Бука айыл өкмөтү','ayyl_area:Ала-Бука','msu.alabuka.18@bk.ru','page:1:line:9'),
 ('SRC-120','Айры-Там айыл өкмөтү','ayyl_area:Айры-Там','ayry-tam_ao@mail.ru','page:1:line:41'),
 ('SRC-125','Жалал-Абадское региональное управление государственного архитектурно-строительного контроля','region:Жалал-Абад','jagask@bk.ru','page:1:line:48'),
 ('SRC-131','Базар-Коргон райондук мамлекеттик администрациясы','district:Базар-Коргон','bazarkorgon.rga@mail.ru','page:1:line:20'),
 ('SRC-132','Сузак райондук ветеринария башкармалыгы','district:Сузак','vet.suzak@mail.ru','page:1:line:22'),
 ('SRC-136','Жалал-Абад регионалдык экологиялык жана техникалык көзөмөл кызматы','region:Жалал-Абад','cetnjalalabad@mail.ru','page:1:line:25'),
 ('SRC-140','Жалал-Абад аймактык бөлүмү — транспорт каттоо борбору','region:Жалал-Абад','jalal-abad@unaa.srs.kg','page:1:line:21'),
 ('SRC-151','Майлуу-Суу шаардык мэриясы','city:Майлуу-Суу','meria_ms@mail.ru','page:1:line:9'),
 ('SRC-161','Манас шаарынын Ч. Айтматов муниципалдык аймактык башкармалыгы','city:Манас','chingyzaitmatovmab@gmail.com','page:1:line:10'),
 ('SRC-168','Жалал-Абад облусунун Өзгөчө кырдаалдар башкармалыгы','region:Жалал-Абад','umch_jalal-a@mail.ru','page:1:line:22'),
 ('SRC-182','Жер ресурстары агенттигинин Ноокен филиалы','district:Ноокен','ngosregistr@mail.ru','page:1:line:56'),
 ('SRC-197','№51 жол тейлөө мекемеси','district:Ноокен','dep51nooken@mail.ru','page:1:line:10'),
 ('SRC-213','Токтогул райондук мамлекеттик администрациясы','district:Токтогул','ToktogulGov@mail.ru','page:1:line:42'),
 ('SRC-219','Чаткал райондук мамлекеттик администрациясы','district:Чаткал','chatkal_rga@mail.ru','page:1:line:45')]
for sid,name,terr,email,loc in mailboxes:
    oid=ensure_org(name,sid,loc,terr)
    add_checked(oid,'email',email,sid,loc,territory=terr)

# Public switchboard numbers on institutional letterheads. Executor and named staff
# numbers elsewhere on these pages are deliberately excluded from this list.
letterhead_contacts=[
 ('SRC-115','phone','(03722) 5-03-57','page:1:line:23'),
 ('SRC-117','phone','03742 5-00-17','page:1:line:6'),
 ('SRC-117','fax','03742 5-00-18','page:1:line:6'),
 ('SRC-119','phone','(03741) 5-00-13','page:1:line:9'),
 ('SRC-125','phone','(03722) 2-24-37','page:1:line:63'),
 ('SRC-125','fax','(03722) 2-24-37','page:1:line:63'),
 ('SRC-131','phone','(037-36) 5-00-07','page:1:line:19'),
 ('SRC-131','fax','(037-36) 5-00-07','page:1:line:19'),
 ('SRC-131','phone','5-01-07','page:1:line:19'),
 ('SRC-136','phone','(3722) 4-06-81','page:1:line:24'),
 ('SRC-140','phone','0(3722) 72765','page:1:line:20'),
 ('SRC-140','fax','(3722) 20919','page:1:line:20'),
 ('SRC-151','phone','+996 (3744) 5-14-86','page:1:line:7'),
 ('SRC-151','phone','5-29-11','page:1:line:8'),
 ('SRC-151','fax','5-29-10','page:1:line:8'),
 ('SRC-161','phone','(03722) 2-03-51','page:1:line:11'),
 ('SRC-168','phone','2-19-70','page:1:line:18'),
 ('SRC-168','fax','2-19-70','page:1:line:18'),
 ('SRC-197','phone','(03734) 5-02-73','page:1:line:9'),
 ('SRC-197','fax','(03734) 5-02-73','page:1:line:9'),
 ('SRC-213','phone','+996(3747)5-00-20','page:1:line:40'),
 ('SRC-213','fax','+996(3747)5-00-63','page:1:line:41'),
 ('SRC-219','phone','(3749)6-03-10','page:1:line:44'),
 ('SRC-219','fax','(3749)6-03-10','page:1:line:44')]
letterhead_org={sid:(ensure_org(name,sid,loc,terr),terr) for sid,name,terr,email,loc in mailboxes}
for sid,typ,value,loc in letterhead_contacts:
    oid,terr=letterhead_org[sid]
    add_checked(oid,typ,value,sid,loc,territory=terr)

# Parallel language columns disagree on these dialling codes/values. Preserve both,
# withhold both from public lookup, and record the disagreement explicitly.
for sid,variants,locs in [
 ('SRC-120',['+996 (0-3741)0-00-08','+996 (0-3741) 5-07-09'],['page:1:line:40','page:1:line:58']),
 ('SRC-132',['+ 996 (3748) 50179','+ 996 (3734) 50179'],['page:1:line:21','page:1:line:26'])]:
    oid,terr=letterhead_org[sid]
    typ='fax' if sid=='SRC-120' else 'phone'
    for value,loc in zip(variants,locs):
        add_checked(oid,typ,value,sid,loc,territory=terr,visibility='INTERNAL_ONLY',status='CONFLICT',
                    reason='parallel language letterheads disagree')
    conflicts.append({'conflict_id':'V2-CONFLICT-'+sid,'entity':org_name(oid_index[oid]),'field':typ,
                      'values':variants,'source_ids':[sid],'status':'CONFLICT','resolution':'NO_WINNER',
                      'visibility':'INTERNAL_ONLY'})

# Vehicle-registration branches: seven distinct offices with their own addresses and hours.
vehicle_specs=[
 ('Жалал-Абад аймактык бөлүмү — транспорт каттоо борбору','city:Манас','page:1:line:16','page:1:line:19','page:1:line:20','page:1:line:21'),
 ('Ноокен бөлүмү — транспорт каттоо борбору','city:Кочкор-Ата','page:1:line:22','page:1:line:25','page:1:line:26','page:1:line:27'),
 ('Таш-Көмүр бөлүмү — транспорт каттоо борбору','city:Таш-Көмүр','page:1:line:28',None,'page:1:line:32','page:1:line:33'),
 ('Аксы бөлүмү — транспорт каттоо борбору','city:Кербен','page:1:line:34','page:1:line:37','page:1:line:38','page:1:line:39'),
 ('Базар-Коргон сектору — транспорт каттоо борбору','city:Базар-Коргон','page:1:line:40','page:2:line:2','page:2:line:3','page:2:line:4'),
 ('Токтогул сектору — транспорт каттоо борбору','city:Токтогул','page:2:line:5',None,'page:2:line:9','page:2:line:10'),
 ('Ала-Бука сектору — транспорт каттоо борбору','district:Ала-Бука','page:2:line:11','page:2:line:14','page:2:line:15','page:2:line:16')]
for name,terr,nloc,ploc,aloc,hloc in vehicle_specs:
    oid=ensure_org(name,'SRC-139',nloc,terr,'ky')
    if ploc:
        val=blocktext('SRC-139',ploc).split(':',1)[-1].strip(' ;')
        vis='INTERNAL_ONLY' if mobile(val) else 'PUBLIC'
        add_checked(oid,'phone',val,'SRC-139',ploc,territory=terr,visibility=vis,reason='mobile beside responsible staff' if vis!='PUBLIC' else None)
    val=blocktext('SRC-139',aloc).split(':',1)[-1].strip(' ;')
    add_checked(oid,'address',val,'SRC-139',aloc,territory=terr,kind='office_or_unspecified')
    val=blocktext('SRC-139',hloc).split(':',1)[-1].strip(' ;')
    add_checked(oid,'working_hours',val,'SRC-139',hloc,territory=terr)

prov_admin=ensure_org('Аппарат полномочного представителя Президента КР в Жалал-Абадской области','SRC-137','page:1:line:10','region:Жалал-Абад','ru')
for typ,value,loc in [('address','Манас шаары, Ю. Абдырахманов көч., 6','page:1:line:10'),
                      ('phone','(3722) 5-00-01','page:1:line:11'),('phone','(3722) 2-49-70','page:1:line:11'),
                      ('email','jalalabad.oga@gmail.com','page:1:line:12')]:
    add_checked(prov_admin,typ,value,'SRC-137',loc,territory='region:Жалал-Абад',kind='office_or_unspecified' if typ=='address' else None)

add_checked(nooken_cad,'address','Ноокен району, Масы айылы К.Султанов көч. №86/1','SRC-182','page:1:line:53',
            territory='district:Ноокен',kind='office_or_unspecified')
add_checked(nooken_cad,'phone','0 3734 5-06-48','SRC-182','page:1:line:55',territory='district:Ноокен')
add_checked(nooken_cad,'fax','0 3734 5-00-11','SRC-182','page:1:line:55',territory='district:Ноокен')

for name,nloc,ploc,aloc,hloc,comp in bk_specs:
    oid=ensure_org(name,'SRC-130',nloc,'city:Базар-Коргон','ru')
    if not ploc:continue
    raw=blocktext('SRC-130',ploc)
    for match in re.finditer(r'(?:тел|Телефон)\s*:\s*([+0-9][0-9\s()\-]{7,18})',raw,re.I):
        num=match.group(1).strip(' ,;')
        if len(digits(num))>=9:
            add_checked(oid,'phone',num,'SRC-130',ploc,territory='city:Базар-Коргон',
                        visibility='INTERNAL_ONLY',reason='phone explicitly attached to named leader')

akman='ayyl_area:Акман'
akman_utility=ensure_org('“Акман” тазалык муниципалдык ишканасы','SRC-127','table:1:row:3',akman,'ky')
add_comp(akman_utility,'Суу менен камсыздоо, суу түтүктөрүн тейлөө жана авариялык иштер','SRC-127','table:1:row:3',akman)
add_comp(akman_utility,'Айыл ичин көрктөндүрүү, тазалык, инфраструктуралык иштер','SRC-127','table:1:row:4',akman)
add_checked(akman_utility,'phone','+996228833180','SRC-127','table:1:row:3',territory=akman,
            visibility='INTERNAL_ONLY',reason='mobile in named responsible employee column')
add_route(akman_utility,'суу түтүгү жана авария','SRC-127','table:1:row:3',akman)
add_route(akman_utility,'тазалык жана көрктөндүрүү','SRC-127','table:1:row:4',akman)

mayluu_cad=ensure_org('Жер ресурстары агенттигинин Майлуу-Суу филиалы','SRC-150','page:1:line:47','city:Майлуу-Суу','ky')
for loc,name in [('page:1:line:61','Кадастровая информация по земельным участкам'),
                 ('page:2:line:5','Государственная регистрация прав на недвижимость'),
                 ('page:2:line:11','Уточнение границ земельных участков')]:
    add_service(mayluu_cad,name,blocktext('SRC-150',loc),'SRC-150',loc,'city:Майлуу-Суу')
for sid,loc in [('NEW-245','paragraph:31'),('NEW-246','paragraph:148')]:
    add_procedure(new_org_ids[sid],'Приём абитуриентов',[blocktext(sid,loc)],sid,loc,new_specs[sid][1],False)
univ_procedure=next(x for x in procedures if x['organization_id']==new_org_ids['NEW-241'] and x['name']=='Приём документов абитуриентов')
univ_procedure['steps'].append(blocktext('NEW-241','paragraph:154'))
univ_procedure['provenance'].append(prov('NEW-241','paragraph:154'))
register('NEW-241','paragraph:154',univ_procedure['procedure_id'])
add_comp(new_org_ids['NEW-246'],blocktext('NEW-246','paragraph:585'),'NEW-246','paragraph:585','city:Жалал-Абад','foreign_student_admission')

# Repeated letterheads and parallel RU/KY rows corroborate an existing record, not a new service.
def corroborate(sid,loc,oid,typ,value):
    matches=[c for c in C if c['organization_id']==oid and c['type']==typ and norm(c['value'])==norm(value)]
    if not matches:return
    rec=matches[0]
    rec.setdefault('provenance',[]).append(prov(sid,loc))
    if sid not in rec['source_ids']:rec['source_ids'].append(sid)
    register(sid,loc,rec['contact_id'])
corroborate('NEW-239','paragraph:33',new_org_ids['NEW-239'],'address','Жалал-Абад шаары, Ленин көч., №122')
corroborate('NEW-242','paragraph:120',library,'address','Жалал-Абад шаары, Т. Байзаков проспектиси № 20')
corroborate('SRC-121','page:1:line:22',next(o['organization_id'] for o in O if org_name(o)=='Ала-Бука райондук мамлекеттик администрациясы'),'fax','+996 (0-3741) 5-02-09')
corroborate('SRC-150','page:1:line:11',mayluu_cad,'phone','+996(3744)5-01-58')
corroborate('SRC-150','page:1:line:27',mayluu_cad,'phone','+996(3744)5-01-58')
corroborate('SRC-150','page:1:line:28',mayluu_cad,'fax','+996 5-01-67')
corroborate('SRC-169','page:1:line:57',next(o['organization_id'] for o in O if org_name(o).startswith('Жерде жүрүүчү жана суу транспорту департаментинин Жалал-Абад аймактык')),'phone','(3722) 5-10-27')
corroborate('SRC-182','page:1:line:65',nooken_cad,'email','ngosregistr@mail.ru')
corroborate('SRC-149','page:1:line:35',next(o['organization_id'] for o in O if org_name(o)=='Майлуу-Суу шаардык Социалдык фонд башкармалыгы'),
            'address','Майлуу-Суу ш., Ленин көч.,14')
corroborate('SRC-196','page:2:line:23',next(o['organization_id'] for o in O if org_name(o)=='Жалал-Абад облустук капиталдык курулуш башкармалыгы'),
            'address','Манас шаары, Эркиндик көчөсү,11')
corroborate('SRC-202','page:1:line:25',next(o['organization_id'] for o in O if org_name(o)=='Жалал-Абадский областной отдел антимонопольного регулирования'),'phone','+996 (3722) 5-06-30')
corroborate('SRC-202','page:1:line:29',next(o['organization_id'] for o in O if org_name(o)=='Жалал-Абадский областной отдел антимонопольного регулирования'),'phone','+996 (3722) 5-06-30')
for sid,loc,name,typ,value in [
 ('SRC-206','page:1:line:54','Сузак райондук мамлекеттик администрациясы','phone','(03748) 5-00-01'),
 ('SRC-209','page:1:line:13','Мэрия города Таш-Кумыр','phone','(03745)5-00-01'),
 ('SRC-210','page:1:line:20','Тогуз-Торо райондук мамлекеттик администрациясы','phone','(03738) 5-01-60')]:
    oid=next((o['organization_id'] for o in O if org_name(o)==name),None)
    if oid:corroborate(sid,loc,oid,typ,value)

# Staff/project numbers and e-mails remain structured but withheld.
for sid,loc,oid,typ,value,reason in [
 ('SRC-137','page:2:line:36',prov_admin,'phone','+996 990 727 253','data-collection project contact, not citizen line'),
 ('SRC-150','page:5:line:38',mayluu_cad,'phone','+996551191195','executor mobile in signed letter'),
 ('SRC-196','page:2:line:22',next(o['organization_id'] for o in O if org_name(o)=='Жалал-Абад облустук капиталдык курулуш башкармалыгы'),'phone','0771 3260827','responsible employee mobile'),
 ('SRC-196','page:5:line:5',next(o['organization_id'] for o in O if org_name(o)=='Жалал-Абад облустук капиталдык курулуш башкармалыгы'),'phone','0771 3260827','responsible employee mobile'),
 ('SRC-206','page:5:line:1',next(o['organization_id'] for o in O if org_name(o)=='Сузак райондук мамлекеттик администрациясы'),'phone','+996 502 748 988','named village secretary mobile')]:
    add_checked(oid,typ,value,sid,loc,visibility='INTERNAL_ONLY',reason=reason)
finance=next(o['organization_id'] for o in O if org_name(o)=='Ноокен райондук финансы башкармалыгы')
add_checked(finance,'email','u.mamayusupov@minfin.kg','SRC-190','page:1:line:20',
            territory='district:Ноокен',visibility='INTERNAL_ONLY',reason='named employee mailbox')
add_checked(finance,'fax','50028','SRC-190','page:1:line:7',territory='district:Ноокен',visibility='INTERNAL_ONLY',status='CONFLICT',
            reason='differs from full telephone printed on page 2')
for c in C:
    if c['organization_id']==finance and c['type']=='phone' and norm(c['value'])==norm('03734 50228'):
        c['status']='CONFLICT';c['pilot_status']='CONFLICT';c['visibility']='INTERNAL_ONLY';c['publication_status']='CONFLICT'
conflicts.append({'conflict_id':'V2-CONFLICT-006','entity':'Ноокен райондук финансы башкармалыгы',
                  'field':'phone_or_fax','values':['50028 (page 1, тел./факс)','03734 50228 (page 2, тел.)'],
                  'source_ids':['SRC-190'],'status':'CONFLICT','resolution':'NO_WINNER','visibility':'INTERNAL_ONLY'})
add_checked(next(o['organization_id'] for o in O if org_name(o)=='Майлуу-Суу шаардык Социалдык фонд башкармалыгы'),
            'phone','5-06-07','SRC-149','page:2:line:30',territory='city:Майлуу-Суу',visibility='INTERNAL_ONLY',
            status='AMBIGUOUS',reason='short local executor number')




# Every second-audit candidate receives an explicit decision, including weak headings and masked role phones.
contact_by_id={c['contact_id']:c for c in C}
for f in F:
    sid,loc=f['source_id'],f['locator'];ids=list(dict.fromkeys(promotion_map.get((sid,loc),[])))
    matched_contacts=[contact_by_id[x] for x in ids if x in contact_by_id]
    if any(c['status']=='CONFLICT' for c in matched_contacts) or f['fact_type']=='conflicting_registered_address':decision='CONFLICT';reason='competing source values'
    elif matched_contacts and all(c['visibility']=='INTERNAL_ONLY' for c in matched_contacts):decision='INTERNAL_ONLY';reason='personal/undialable/non-public contact'
    elif ids:decision='SOURCE_CONFIRMED';reason='linked to structured v2 record'
    elif f['fact_type']=='role_contact':decision='INTERNAL_ONLY';reason='personal-role mobile masked in audit'
    elif re.search(r'паспорт|туулган|жашаган жери|ИНН|ПИН|р/с|БИК',f['value'],re.I):decision='INTERNAL_ONLY';reason='personal or internal requisites'
    else:decision='AMBIGUOUS';reason='fragment alone lacks a unique publishable entity/value or is a heading/duplicate'
    possible={o['organization_id'] for o in O if sid in o.get('source_ids',[])}
    organization_id=matched_contacts[0]['organization_id'] if matched_contacts else next(iter(possible)) if len(possible)==1 else None
    terr=(oid_index[organization_id].get('territory') or [None])[0] if organization_id else territory_from(f['value']+' '+f['file'])
    review.append({'fact_id':f['fact_id'],'source_id':sid,'locator':loc,'fact_type':f['fact_type'],
                   'organization_id':organization_id,'territory_id':terr,'decision':decision,'reason':reason,
                   'promoted_record_ids':ids,'value':f['value'] if decision not in ('INTERNAL_ONLY',) else '[REDACTED; see original source by locator]'})
assert len(review)==len(F)==194
write(REV/'recoverable_dispositions.jsonl',review)

# Exhaustive contact-pattern inventory over 197 readable, unique documents.
email_re=re.compile(r'[\w.+-]+@[\w.-]+\.[a-z]{2,}',re.I)
website_re=re.compile(r'(?:https?://|www\.)[^\s|<>\]\)]+',re.I)
phone_hint=re.compile(r'\+?996[\s()\-0-9]{6,}|\(?0?37\d\d\)?[\s\-\d]{4,}|(?:телефон|тел\.|факс|байланыш телефону)\s*[:№-]?\s*[+()0-9]',re.I)
hours_hint=re.compile(r'(?:\d{1,2}[:.\-]\d\d\s*(?:-|–|до|дан|ден|чейин)\s*\d{1,2}[:.\-]\d\d|график работы|иш графиги|иш убактысы)',re.I)
scan=[]
for sid,source in E.items():
    for b in source['blocks']:
        text=b['text'];kinds=[]
        if email_re.search(text):kinds.append('email')
        if website_re.search(text):kinds.append('website')
        if phone_hint.search(text):kinds.append('phone_or_fax')
        if hours_hint.search(text):kinds.append('hours')
        if not kinds:continue
        ids=list(dict.fromkeys(promotion_map.get((sid,b['locator']),[])))
        excerpt=' '.join(text.split())[:250]
        if sid=='SRC-205' or MOBILE.search(excerpt):excerpt='[number redacted; inspect original source and locator]'
        scan.append({'source_id':sid,'locator':b['locator'],'candidate_types':kinds,
                     'promoted_record_ids':ids,'disposition':'STRUCTURED_RECORD' if ids else 'AMBIGUOUS_OR_NOT_A_CONTACT',
                     'source_excerpt':excerpt})
write(REV/'source_contact_scan.jsonl',scan)

# Small semantic blocks. Exact structured lookup is authoritative for contacts/hours.
for o in O:
    oid=o['organization_id'];published=[c for c in C if c['organization_id']==oid and c['visibility']=='PUBLIC' and c['status']=='SOURCE_CONFIRMED']
    if not published:continue
    latest=[c for c in published if c['contact_id'].startswith('v2-')]
    if not latest:continue
    bits=[f"{c['type']}: {c['value']}" for c in latest]
    for offset in range(0,len(bits),5):
        sub=latest[offset:offset+5]
        text=f"{org_name(o)}. "+'; '.join(f"{c['type']}: {c['value']}" for c in sub)
        sid=sub[0]['source_ids'][0]
        G.append({'chunk_id':'v2-chunk-'+key(oid,'contact',offset),'document_id':sid,'organization_ids':[oid],
                  'topic':'pilot_contacts','language':'mixed','title':org_name(o),'text':text[:900],
                  'source_file':sourcefile(sid),'source_ids':sorted({s for c in sub for s in c['source_ids']}),
                  'verification_status':'SOURCE_CONFIRMED','pilot_status':'SOURCE_CONFIRMED',
                  'publication_status':'PILOT_PUBLIC','visibility':'PUBLIC','tags':['contact','structured_primary']})
    phones=[c for c in published if c['type']=='phone']
    if phones:
        src=sorted({s for c in phones for s in c['source_ids']})
        Qru.append({'qa_id':'v2-qa-ru-'+key(oid,'phone'),'language':'ru','question':'Как связаться с '+org_name(o)+'?',
                    'answer':'Телефон: '+', '.join(c['value'] for c in phones),'organization_ids':[oid],
                    'topic':'contact','source_ids':src,'verification_status':'SOURCE_CONFIRMED',
                    'publication_status':'PILOT_PUBLIC','visibility':'PUBLIC','pilot_status':'SOURCE_CONFIRMED'})
for collection,kind,idfield,titlefield in [(services,'service','service_id','name'),(procedures,'procedure','procedure_id','name'),(newroutes,'routing','routing_rule_id','topic')]:
    for rec in collection:
        oid=rec['organization_id'] if kind!='routing' else rec['target_organization_id']
        sid=rec['source_ids'][0]
        body=rec.get('description') or '; '.join(rec.get('steps',[])) or rec.get('target_department_name_ky') or ''
        text=f"{org_name(oid_index[oid])}. {rec[titlefield]}. {body}"
        G.append({'chunk_id':'v2-chunk-'+key(rec[idfield]),'document_id':sid,'organization_ids':[oid],
                  'topic':kind,'language':'mixed','title':rec[titlefield],'text':text[:750],
                  'source_file':sourcefile(sid),'source_ids':rec['source_ids'],
                  'verification_status':'SOURCE_CONFIRMED','pilot_status':'SOURCE_CONFIRMED',
                  'publication_status':'PILOT_PUBLIC','visibility':'PUBLIC','tags':[kind]})
R.extend(newroutes)

for name,rows in [('sources',S),('organizations',O),('competences',K),('contacts',C),('routing_rules',R),
                  ('qa_pairs_ru',Qru),('qa_pairs_ky',Qky),('rag_chunks',G),('aliases',A),
                  ('services',services),('procedures',procedures),('territories',T),('conflicts',conflicts)]:
    write(M/(name+'.jsonl'),rows)
write(M/'public_contacts.jsonl',[c for c in C if c['visibility']=='PUBLIC' and c['status']=='SOURCE_CONFIRMED'])
write(M/'hours.jsonl',[c for c in C if c['type'] in ('working_hours','reception_hours')])

before=collections.Counter(c['type'] for c in data['contacts'] if not c['contact_id'].startswith('v2-'))
after=collections.Counter(c['type'] for c in C)
counts={'before':{'organizations':94,'phones':2,'fax':0,'addresses':70,'emails':0,'websites':0,
                  'working_hours':0,'reception_hours':0,'competences':83,'services':0,'procedures':0,
                  'routing_facts':46,'rag_chunks':193},
        'after':{'organizations':len(O),'phones':after['phone'],'fax':after['fax'],'addresses':after['address'],
                 'emails':after['email'],'websites':after['website'],'working_hours':after['working_hours'],
                 'reception_hours':after['reception_hours'],'competences':len(K),'services':len(services),
                 'procedures':len(procedures),'routing_facts':len(R),'rag_chunks':len(G)},
        'contact_visibility':dict(collections.Counter(c['visibility'] for c in C)),
        'contact_status':dict(collections.Counter(c['status'] for c in C)),
        'recoverable_decisions':dict(collections.Counter(x['decision'] for x in review)),
        'contact_scan_blocks':len(scan)}
(V2/'metrics.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(counts,ensure_ascii=False))
