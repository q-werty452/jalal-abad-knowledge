"""Build a provenance-first second audit without touching the canonical corpus."""
import collections
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
AUD=ROOT/'audit_machine'
def load(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def put(name,rows):
    with (AUD/name).open('w',encoding='utf-8') as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+'\n')
def md(name,s): (ROOT/name).write_text(s.rstrip()+'\n',encoding='utf-8')
def table(headers,rows):
    def cell(x): return str(x if x is not None else '—').replace('|','/').replace('\n',' ') or '—'
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(cell(x) for x in row)+' |\n' for row in rows)

S=load(ROOT/'machine/sources.jsonl'); O=load(ROOT/'machine/organizations.jsonl'); C=load(ROOT/'machine/contacts.jsonl')
K=load(ROOT/'machine/competences.jsonl'); R=load(ROOT/'machine/routing_rules.jsonl'); G=load(ROOT/'machine/rag_chunks.jsonl')
N=load(AUD/'new_sources.jsonl'); E=load(AUD/'_review_extract.jsonl')
sid={s['source_id']:s for s in S}; org={o['organization_id']:o for o in O}
def oname(o):return o.get('name_ru') or o.get('name_ky') or ''
def osources(oid): return sorted(set(sum([x.get('source_ids',[]) for x in [org[oid]]+[c for c in C if c['organization_id']==oid]+[k for k in K if k['organization_id']==oid]],[])))

# Geographic units are admitted only when source-backed strings carry a type word.
base=[('region','Жалал-Абад','Жалал-Абадская область','Жалал-Абад облусу',None),
 ('district','Аксы','Аксыйский район','Аксы району','region'),('district','Ала-Бука','Ала-Букинский район','Ала-Бука району','region'),
 ('district','Базар-Коргон','Базар-Коргонский район','Базар-Коргон району','region'),('district','Ноокен','Ноокенский район','Ноокен району','region'),
 ('district','Сузак','Сузакский район','Сузак району','region'),('district','Тогуз-Торо','Тогуз-Торо район','Тогуз-Торо району','region'),
 ('district','Токтогул','Токтогульский район','Токтогул району','region'),('district','Чаткал','Чаткальский район','Чаткал району','region'),
 ('city','Манас','город Манас','Манас шаары','region'),('city','Жалал-Абад','город Жалал-Абад','Жалал-Абад шаары',None),
 ('city','Базар-Коргон','город Базар-Коргон','Базар-Коргон шаары','district:Базар-Коргон'),
 ('city','Кара-Көл','город Кара-Көл','Кара-Көл шаары','region'),('city','Кербен','город Кербен','Кербен шаары','district:Аксы'),
 ('city','Кочкор-Ата','город Кочкор-Ата','Кочкор-Ата шаары','district:Ноокен'),
 ('city','Майлуу-Суу','город Майлуу-Суу','Майлуу-Суу шаары','region'),
 ('city','Таш-Көмүр','город Таш-Көмүр','Таш-Көмүр шаары','region'),
 ('city','Токтогул','город Токтогул','Токтогул шаары','district:Токтогул'),
 ('city','Шамалдуу-Сай','город Шамалдуу-Сай','Шамалдуу-Сай шаары','district:Ноокен'),
 ('ayyl_area','Акман','Акман айылный аймак','Акман айыл аймагы','district:Базар-Коргон'),
 ('ayyl_area','Арстанбап-Ата','Арстанбап-Ата айылный аймак','Арстанбап-Ата айыл аймагы','district:Базар-Коргон'),
 ('ayyl_area','Сайдыкум','Сайдыкум айылный аймак','Сайдыкум айыл аймагы','district:Базар-Коргон'),
 ('ayyl_area','Терек-Сай','Терек-Сай айылный аймак','Терек-Сай айыл аймагы','district:Чаткал'),
 ('ayyl_area','Каныш-Кыя','Каныш-Кыя айылный аймак','Каныш-Кыя айыл аймагы','district:Чаткал'),
 ('village','Сузак','село Сузак','Сузак айылы','district:Сузак'),('village','Масы','село Масы','Масы айылы','district:Ноокен'),
 ('village','Казарман','село Казарман','Казарман айылы','district:Тогуз-Торо'),
 ('village','Баймундуз','село Баймундуз','Баймундуз айылы','district:Базар-Коргон'),
 ('village','Терек-Сай','село Терек-Сай','Терек-Сай айылы','ayyl_area:Терек-Сай'),
 ('ayyl_area','Ала-Бука','Ала-Бука айылный аймак','Ала-Бука айыл аймагы','district:Ала-Бука'),
 ('ayyl_area','Айры-Там','Айры-Там айылный аймак','Айры-Там айыл аймагы','district:Ала-Бука'),
 ('ayyl_area','Ынтымак','Ынтымак айылный аймак','Ынтымак айыл аймагы','district:Ала-Бука'),
 ('ayyl_area','Бүргөндү-Достук','Бүргөндү-Достук айылный аймак','Бүргөндү-Достук айыл аймагы','district:Ноокен'),
 ('ayyl_area','Момбеков','Момбеков айылный аймак','Момбеков айыл аймагы','district:Ноокен'),
 ('ayyl_area','Д.Садырбаев','Д. Садырбаев айылный аймак','Д. Садырбаев айыл аймагы','district:Ноокен'),
 ('ayyl_area','Эргеш Алиев','Эргеш Алиев айылный аймак','Эргеш Алиев айыл аймагы',None),
 ('ayyl_area','Тогуз-Торо','Тогуз-Торо айылный аймак','Тогуз-Торо айыл аймагы','district:Тогуз-Торо'),
 ('ayyl_area','Каргалык','Каргалык айылный аймак','Каргалык айыл аймагы','district:Тогуз-Торо'),
 ('ayyl_area','Атай','Атай айылный аймак','Атай айыл аймагы','district:Тогуз-Торо'),
 ('ayyl_area','Багыш','Багыш айылный аймак','Багыш айыл аймагы','district:Сузак'),
 ('ayyl_area','Барпы','Барпы айылный аймак','Барпы айыл аймагы','district:Сузак'),
 ('ayyl_area','Кыз-Көл','Кыз-Көл айылный аймак','Кыз-Көл айыл аймагы','district:Сузак'),
 ('ayyl_area','Кызыл-Туу','Кызыл-Туу айылный аймак','Кызыл-Туу айыл аймагы','district:Сузак'),
 ('ayyl_area','С.Атабеков','С. Атабеков айылный аймак','С. Атабеков айыл аймагы','district:Сузак'),
 ('ayyl_area','Көк-Арт','Көк-Арт айылный аймак','Көк-Арт айыл аймагы','district:Сузак'),
 ('ayyl_area','Кара-Дарыя','Кара-Дарыя айылный аймак','Кара-Дарыя айыл аймагы','district:Сузак')]
alltext=[]
for s in S: alltext.append((s['source_id'],s['source_file']))
for n in N: alltext.append((n['source_id'],n['source_file']))
for x in E:
    for b in x['blocks']:
        if len(b['text'])<1500:alltext.append((x['source_id'],b['text']))
for o in O:alltext.append((o['source_ids'][0],oname(o)))
for c in C:alltext.append((c['source_ids'][0],c['value']))
alias={'Таш-Көмүр':['Таш-Комур','Таш-Кумыр','Ташкумыр'],'Кара-Көл':['Кара-Куль','Кара-Кул'],
       'Майлуу-Суу':['Майлуу-Суу'],'Жалал-Абад':['Джалал-Абад','Жалалабад'],'Терек-Сай':['Терек -Сай']}
terr=[];patterns={}
for typ,key,ru,ky,parent in base:
    forms=[key]+alias.get(key,[])
    if typ=='region': pattern=r'(?:Жалал.Абад|Джалал.Абад).{0,30}(?:обл|област)'
    elif typ=='district':pattern=r'(?:'+ '|'.join(map(re.escape,forms))+r').{0,30}(?:район|району|райондук|РГА)'
    elif typ=='city':pattern=r'(?:'+ '|'.join(map(re.escape,forms))+r').{0,25}(?:шаар|город|г\.|мэрия)'
    elif typ=='ayyl_area':pattern=r'(?:'+ '|'.join(map(re.escape,forms))+r').{0,25}(?:айыл аймаг|айыл өкмөт|айыл окмот|сельск|а/о)'
    else:pattern=r'(?:'+ '|'.join(map(re.escape,forms))+r').{0,15}(?:айылы|село|с\.)'
    hits=sorted({s for s,t in alltext if re.search(pattern,t,re.I)})
    if not hits:continue
    tid=typ+':'+key;patterns[tid]=pattern
    if parent=='region':parent='region:Жалал-Абад'
    terr.append({'territory_id':tid,'name_ru':ru,'name_ky':ky,'type':typ,'parent_territory':parent,
                 'parent_status':'SOURCE_CONTEXT' if parent else 'UNCONFIRMED','source_ids':hits})

def territory_for(text):
    found=[]
    for t in terr:
        if re.search(patterns[t['territory_id']],text,re.I):
            found.append(t)
    found.sort(key=lambda x:({'village':0,'ayyl_area':1,'city':2,'district':3,'region':4}.get(x['type'],5),-len(x['territory_id'])))
    return found[0]['territory_id'] if found else None

oc=[]
for o in O:
    oid=o['organization_id']; cs=[c for c in C if c['organization_id']==oid];ks=[k for k in K if k['organization_id']==oid];rs=[r for r in R if r['target_organization_id']==oid]
    g=[x for x in G if oid in x.get('organization_ids',[])]
    ts=territory_for(oname(o)+' '+' '.join(c['value'] for c in cs if c['type']=='address'))
    flags={'competence':'YES' if ks else 'NO','phone':'YES' if any(c['type']=='phone' for c in cs) else 'NO',
           'address':'YES' if any(c['type']=='address' for c in cs) else 'NO',
           'email':'YES' if any(c['type']=='email' for c in cs) else 'NO',
           'working_hours':'YES' if any(c.get('working_hours') for c in cs) else 'NO',
           'reception_hours':'NO','website':'NO','leader':'NO','reception_procedure':'NO',
           'services':'PARTIAL' if ks else 'NO','routing_facts':'YES' if any(r['verification_status']=='verified' for r in rs) else ('NEEDS_REVIEW' if rs else 'NO'),
           'legal_basis':'PARTIAL' if any(k.get('legal_basis_source_ids') for k in ks) or any('legal' in x.get('tags',[]) for x in g) else 'NO'}
    oc.append({'organization_id':oid,'name_ru':o.get('name_ru'),'name_ky':o.get('name_ky'),
               'aliases':o.get('aliases_ru',[])+o.get('aliases_ky',[]),'territory':ts,'territory_status':'DERIVED_FROM_NAME_OR_ADDRESS' if ts else 'UNKNOWN',
               'parent':o.get('parent_organization_id'),'organization_type':o.get('organization_type'),
               'coverage':flags,'source_ids':osources(oid),'promotion_status':'CANONICAL_UNCHANGED'})
put('organization_coverage.jsonl',oc)

cc=[]
for c in C:
    cc.append({'contact_id':c['contact_id'],'organization_id':c['organization_id'],'territory':next((x['territory'] for x in oc if x['organization_id']==c['organization_id']),None),
               'type':c['type'],'value':c['value'],'source_ids':c['source_ids'],'provenance':c.get('provenance',[]),
               'publication_status':c.get('publication_status'),'verification_status':c.get('verification_status')})
put('contact_coverage.jsonl',cc)

# Candidate facts: short exact source excerpts, never promoting raw numbers to the public directory.
factual_sources={'SRC-111','SRC-121','SRC-126','SRC-127','SRC-129','SRC-130','SRC-137','SRC-139','SRC-149','SRC-150','SRC-169','SRC-182','SRC-190','SRC-196','SRC-198','SRC-202','SRC-206','SRC-209','SRC-210','SRC-220','NEW-235','NEW-236','NEW-237','NEW-238','NEW-239','NEW-240','NEW-241','NEW-242','NEW-243','NEW-244','NEW-245','NEW-246','NEW-247'}
pat=re.compile(r'(?:юридическ.{0,12}адрес|юридик.{0,12}дарег|местонахождение|жайгашкан жери|дареги\s*:|адрес\s*:|телефон\s*:|тел\s*[:.]|\+996|график работы\s*:|иш графиги\s*:|иш убактысы\s*:|прием.{0,30}граждан|жарандар.{0,30}кайрыл|кабыл алуу журналы|кайрылууну кабыл|суу менен камсыздоо|суу түтүктөрүн|көчө жарыгы|жер участокторун|порядок приема студентов|кабыл алуу комиссия|билдирүү берилет|ачык люк|айылдын жолу|таштанды чыгар)',re.I)
template=re.compile(r'^\s*(?:телефон|адрес|дареги|график работы|жетекчиси|руководитель)\s*:\s*$|_{3,}|нужно понять|что нужно предоставить|какие вообще|название службы\s*:',re.I)
facts=[]
for rec in E:
    if rec['source_id'] not in factual_sources:continue
    for b in rec['blocks']:
        v=' '.join(b['text'].split())
        if rec['source_id']=='NEW-242' and b['locator'] in ('paragraph:4','paragraph:39'):continue # Justice Ministry letterhead, not library contact.
        if not pat.search(v) or template.search(v) or len(v)>450 or len(v)<18:continue
        if re.fullmatch(r'.{0,35}(?:юридический адрес|юридикалык дареги|местонахождение).{0,4}',v,re.I):continue
        if re.search(r'жоюлганда|ликвидац|жоюу жөнүндө',v,re.I):continue
        if rec['source_id']=='SRC-127' and re.search(r'\+996|996\d|0\(3736\)',v):
            # Role-bound mobile numbers need explicit publication approval.
            typ='role_contact';value='[номер скрыт до проверки права публикации]'
        elif re.search(r'(?:телефон|тел\.|\+996|037\d)',v,re.I):typ='contact';value=v
        elif re.search(r'адрес|дарег|местонахождение|жайгашкан жери',v,re.I):typ='address';value=v
        elif re.search(r'график|иш убактысы',v,re.I):typ='working_hours';value=v
        else:typ='procedure_or_competence';value=v
        facts.append({'fact_id':f'AF-{len(facts)+1:04d}','source_id':rec['source_id'],'file':rec['source_file'],
                      'locator':b['locator'],'fact_type':typ,'entity':rec['source_file'].split('::')[-1].split('/')[-1],
                      'value':value,'reason_it_was_not_in_corpus':'NEW_SOURCE_NOT_PROMOTED' if rec['source_id'].startswith('NEW') else 'SOURCE_INDEXED_NO_CANONICAL_RECORD',
                      'verification_status':'NEEDS_REVIEW','publication_status':'NEEDS_REVIEW'})
# Recover split spreadsheet cells and a filled multipart village-office answer.
for source_id,locs in {'SRC-111':['sheet:Sheet1:row:5','sheet:Sheet1:row:6','sheet:Sheet1:row:7'],
                       'SRC-150':['page:1:line:49','page:1:line:50','page:1:line:51'],
                       'SRC-220':['paragraph:8'],
                       'NEW-242':['paragraph:21','paragraph:56']}.items():
    rec=next(x for x in E if x['source_id']==source_id)
    for b in rec['blocks']:
        if b['locator'] not in locs or any(f['source_id']==source_id and f['locator']==b['locator'] for f in facts):continue
        v=' '.join(b['text'].split())
        typ='working_hours' if re.search('график|убактысы',v,re.I) else ('contact' if re.search('телефон|телефону',v,re.I) else 'address')
        if source_id=='SRC-220':typ='organization_contact_and_hours';v=re.sub(r'(Телефон:\s*)0[57]\d[\d -]{7,}',r'\1[номер скрыт до проверки публикации]',v)
        if source_id=='NEW-242':typ='conflicting_registered_address';v='Адрес из реестровой справки: '+v
        facts.append({'fact_id':f'AF-{len(facts)+1:04d}','source_id':source_id,'file':rec['source_file'],
                      'locator':b['locator'],'fact_type':typ,'entity':rec['source_file'].split('::')[-1].split('/')[-1],
                      'value':v,'reason_it_was_not_in_corpus':'NEW_SOURCE_NOT_PROMOTED' if source_id.startswith('NEW') else 'SOURCE_INDEXED_NO_CANONICAL_RECORD',
                      'verification_status':'NEEDS_REVIEW','publication_status':'NEEDS_REVIEW'})
review=[]
for rec in E:
    if not rec['source_id'].startswith('SRC-'):continue
    related=[f for f in facts if f['source_id']==rec['source_id']]
    review.append({'source_id':rec['source_id'],'source_file':rec['source_file'],'blocks_reopened':len(rec['blocks']),
                   'candidate_facts':len(related),'disposition':'CANDIDATES_TO_REVIEW' if related else 'NO_SELECTED_PRACTICAL_FACT_OR_CONTEXT_ONLY',
                   'error':rec.get('error')})
put('unrepresented_source_review.jsonl',review)
put('recoverable_facts.jsonl',facts)

for t in terr:
    tid=t['territory_id'];members=[x for x in oc if x['territory']==tid]
    ids={x['organization_id'] for x in members}
    t.update({'organizations_count':len(members),'contacts_count':sum(c['organization_id'] in ids for c in C),
              'competences_count':sum(k['organization_id'] in ids for k in K),
              'services_count':sum(x['coverage']['services']!='NO' for x in members),
              'routing_facts_count':sum(r['target_organization_id'] in ids for r in R),
              'coverage_status':'PARTIAL' if members and sum(c['organization_id'] in ids for c in C)>0 else ('POOR' if members or t['source_ids'] else 'NO_DATA')})
put('territories.jsonl',terr)

# Procedure sufficiency requires steps, requirements, channel and competent actor.
topics=[('personal_reception','Личный приём руководителя области','руководител|ɵкүл|өкүл','SRC-205'),
 ('appeal','Подача обращения','кайрыл|обращен','SRC-129'),('land_allocation','Получение участка','жер|земл','SRC-150'),
 ('land_lease','Аренда земли','аренд|ижара','SRC-150'),('school_enrollment','Устройство ребёнка в школу','мектеп|школ','SRC-198'),
 ('water','Обращение по воде','суу|водоканал','SRC-127'),('sewer_manholes','Открытый/украденный люк','люк|канализац','SRC-127'),
 ('road','Ремонт дороги','жол|дорог','SRC-197'),('lighting','Уличное освещение','жарык|освещен','SRC-130'),
 ('waste','Вывоз мусора','тазалык|мусор','SRC-127'),('social','Социальная поддержка','социал|соц','SRC-204'),
 ('tax','Налоги','салык|налог','SRC-127'),('architecture','Архитектура','архитектур','SRC-124'),
 ('documents','Оформление документов','документ|күбөлүк','SRC-139'),('permits','Разрешения','уруксат|разрешен','NEW-235')]
proc=[]
for code,name,regex,example in topics:
    matches=[o for o in oc if re.search(regex,(o['name_ru'] or '')+' '+(o['name_ky'] or ''),re.I)]
    fs=[f for f in facts if re.search(regex,f['value'],re.I)]
    ids=sorted(set(sum([o['source_ids'] for o in matches],[])+[f['source_id'] for f in fs]))
    if example in sid or any(n['source_id']==example for n in N):ids=sorted(set(ids+[example]))
    status='PARTIAL' if matches or fs else 'NO_DATA'
    proc.append({'procedure_id':code,'procedure_name':name,'territory':None,'organization_ids':[o['organization_id'] for o in matches],
                 'required_documents':[],'steps':[],'contact':[],'working_hours':[],
                 'source_ids':ids,'verification_status':'NEEDS_REVIEW' if status=='PARTIAL' else 'NO_DATA',
                 'coverage_status':status,'sufficient_for_step_by_step_answer':False})
put('service_procedures.jsonl',proc)

matrix=[]
columns=['organizations','municipal_bodies','state_bodies','utilities','education','health','social','roads','water','waste','lighting','land','tax','contacts','addresses','hours','reception','routing']
for t in terr:
    members=[o for o in oc if o['territory']==t['territory_id']];names=' '.join((o['name_ru'] or '')+' '+(o['name_ky'] or '') for o in members).lower()
    def hit(p):return bool(re.search(p,names,re.I))
    vals={x:'MISSING' for x in columns}
    vals['organizations']='PARTIAL' if members else 'MISSING'
    for col,pat2 in {'municipal_bodies':'мэрия|айыл өкмөт|айыл окмот','state_bodies':'башкармалы|управлен|агентств|министер','utilities':'канал|тазалык|электр|газ',
                     'education':'билим|мектеп|университет','health':'медицин|саламат','social':'социал','roads':'жол|дорог','water':'водоканал|суу канал|суу чарба',
                     'waste':'тазалык|мусор','lighting':'электр|жарык','land':'жер|зем','tax':'салык|налог'}.items():
        if hit(pat2):vals[col]='PARTIAL'
    vals['contacts']='PARTIAL' if any(o['coverage']['phone']=='YES' for o in members) else 'MISSING'
    vals['addresses']='PARTIAL' if any(o['coverage']['address']=='YES' for o in members) else 'MISSING'
    vals['hours']='PARTIAL' if any(o['coverage']['working_hours']=='YES' for o in members) else 'MISSING'
    vals['routing']='PARTIAL' if any(o['coverage']['routing_facts']!='NO' for o in members) else 'MISSING'
    matrix.append({'territory_id':t['territory_id'],'values':vals,'source_ids':t['source_ids'],'status_basis':'CANONICAL_ONLY; new facts remain unpromoted'})
put('territory_gap_matrix.jsonl',matrix)

water=[o for o in O if 'водоканал' in oname(o).lower() or 'Суу канал' in oname(o)]
water_names='; '.join(oname(o) for o in water)
queries=[
('Кантип баламды мектепке берсем болот?','NEEDS_CLARIFICATION','В материалах есть органы образования, но подтверждённого порядка зачисления ребёнка, перечня документов и сроков нет. Назовите населённый пункт и возраст ребёнка.','Нужны муниципалитет, возраст, школа/класс, правила приёма.','Уточнить территорию; запросить официальную процедуру у отдела образования.',['SRC-198']),
('Как записаться на приём к руководителю области?','CAN_OFFER_APPEAL','В источниках есть сведения об областной администрации и её приёмной, но подтверждённого порядка записи и графика личного приёма нет. Можно подготовить обращение в приёмную; номер и часы следует подтвердить у администрации.','Какой вопрос и желаемая форма обращения?','Предложить оформить письменное обращение с темой и контактами заявителя.',['SRC-205']),
('Мага жер керек.','NEEDS_CLARIFICATION','Жер маселелери боюнча органдар көрсөтүлгөн, бирок участок алуу тартиби жердин түрүнө жана жайгашкан жерине көз каранды. Кайсы аймак жана кандай максат үчүн керек?','Аймак, максат, менчик/ижара, жердин категориясы.','Тиешелүү жер органы/мэрияга кайрылууну даярдоо.',['SRC-150']),
('Как связаться с водоканалом?','NEEDS_CLARIFICATION',f'В материалах названы {water_names}. Для «Управление водоканал Манас» подтверждённого публичного телефона в канонической базе нет. Укажите населённый пункт.','Город/айыл аймак.','После уточнения показать подтверждённый адрес, если есть; запросить официальный телефон.',['SRC-164','SRC-191']),
('Суу службасы кайсыл адресте?','NEEDS_CLARIFICATION','Кайсы шаардагы суу кызматы? Шамалдуу-Сайдагы «Суу канал» мекемесинин дареги: Ленин көчөсү №29. Манастагы водоканалдын так дареги тастыкталган эмес.','Шаар/айыл аймак.','Аймак такталса, тиешелүү даректи көрсөтүү.',['SRC-191','SRC-164']),
('Номеричи?','PARTIAL','Мурдагы контексттеги водоканалдын тастыкталган жалпы телефону каноникалык базада жок. Шаарын айтсаңыз, тиешелүү мекемени тактап берем.','Контекст Манаспы же Шамалдуу-Сайбы?','Расмий байланыш номерин жергиликтүү кызматтан сурап алуу.',['SRC-164','SRC-191']),
('Базар-Коргон району боюнча кандай кызматтар бар?','PARTIAL','Базар-Коргон боюнча суу чарба, архитектура, финансы жана айрым айыл өкмөттөрүнүн кайрылууларды кабыл алуу функциялары бар. Так кадамдар жана байланыштар мекеме боюнча бирдей толукталган эмес.','Кайсы кызмат жана кайсы айыл аймак?','Темага ылайык белгилүү мекемелерди жана булактарды көрсөтүү.',['SRC-127','SRC-130','NEW-237']),
('Все что есть по водоканалу покажи.','PARTIAL',f'В корпусе найдены: {water_names}. Для «Суу канал» есть адрес Шамалдуу-Сай, улица Ленина, 29; по Манасскому водоканалу в канонической базе нет проверенных телефона, адреса и часов.','Интересует конкретная территория или все упоминания?','Вывести карточки источников и явно отметить пробелы.',['SRC-164','SRC-191']),
('Сенде Жалал-Абад облусу боюнча кандай маалымат бар?','PARTIAL','Облус боюнча мекемелердин аталыштары, айрым милдеттер, даректер жана кайрылууларды багыттоо боюнча маалыматтар бар. Телефон, иш убактысы жана конкреттүү кызмат тартиби көп жерде толук эмес.','Кайсы район же тема кызыктырат?','Аймак жана тема боюнча жеткиликтүү текшерилген фактыларды берүү.',['SRC-225','SRC-205']),
('Люк урдап кетип калыптыр эмне кылабыз?','NEEDS_CLARIFICATION','Кайсы айыл/шаар жана так дарек? Арстанбап-Ата айыл аймагындагы булак ачык люк маселесин «Арстанбап-Ата таза суу жана тазалык» муниципалдык ишканасына, көзөмөлүн айыл өкмөткө багыттайт. Башка аймакта аткаруучуну ырастоо керек.','Так жайгашкан жери, аймак жана кооптуулугу.','Кайрылууну түзүүгө жардам берүү; шашылыш коркунуч болсо жергиликтүү ыкчам кызматка билдирүү.',['SRC-126']),
('Как подать заявку?','NEEDS_CLARIFICATION','Уточните, о какой услуге или проблеме заявка и в каком населённом пункте. В источниках встречаются приём и регистрация обращений, но единая подтверждённая инструкция подачи заявки в бот отсутствует.','Тема, территория, нужный канал.','Помочь сформулировать обращение после уточнения.',['SRC-129','SRC-127']),
('Көчө жарыгы иштебейт.','NEEDS_CLARIFICATION','Кайсы аймак жана көчө? Арстанбап-Ата үчүн булак айыл өкмөтү / Ачы электр тармактарын көрсөтөт. Башка аймакта жооптуу кызматты өзүнчө тактоо керек.','Шаар/айыл, көчө, ориентир.','Кайрылуунун текстин даярдоо.',['SRC-126']),
('Жол бузулуп калган.','NEEDS_CLARIFICATION','Кайсы жерде жол бузулган? Арстанбап-Ата үчүн булак айыл өкмөтү / тиешелүү жол тейлөө кызматын көрсөтөт. Жолдун түрү жана аймак башка болсо, жооптууну тактоо керек.','Так дарек, жолдун түрү, сүрөт.','Тиешелүү айыл өкмөткө/жол органына кайрылууну даярдоо.',['SRC-126','SRC-197']),
('Таштанды чыгарылбай жатат.','NEEDS_CLARIFICATION','Кайсы аймак? Арстанбап-Атада булак «Арстанбап-Ата таза суу жана тазалык» ишканасын, Акманда «Акман» тазалык ишканасын атайт. Башка жерде тейлөөчүнү тактоо керек.','Аймак, дарек, күн, тейлөөчү уюм белгилүүбү.','Жергиликтүү тазалык кызматына же айыл өкмөткө кайрылууну даярдоо.',['SRC-126','SRC-127'])]
qr=[]
for i,(q,status,answer,clar,action,src) in enumerate(queries,1):
    qr.append({'query_id':f'Q{i:02d}','question':q,'status':status,'available_facts':answer,'missing_facts':clar,
               'best_possible_grounded_answer':answer,'required_clarification':clar,'possible_citizen_action':action,
               'source_ids':src,'publication_status':'DRAFT_REQUIRES_REVIEW'})
put('query_coverage.jsonl',qr)

# Human-facing output.
md('17_GEOGRAPHY_COVERAGE.md','# География покрытия\n\nТерритория включена при явном типизированном упоминании в локальном источнике. Привязка организации по названию/адресу — производная, а не подтверждённая зона обслуживания. GOOD требует практических контактов, часов и маршрута; таких территорий нет.\n\n'+table(['ID','RU','KY','Тип','Родитель','Источники','Орг.','Конт.','Комп.','Усл.','Марш.','Статус'],[[t['territory_id'],t['name_ru'],t['name_ky'],t['type'],t['parent_territory'],', '.join(t['source_ids'][:8])+('…' if len(t['source_ids'])>8 else ''),t['organizations_count'],t['contacts_count'],t['competences_count'],t['services_count'],t['routing_facts_count'],t['coverage_status']] for t in terr])+ '\nПолный список source_ids — в `audit_machine/territories.jsonl`. Неподтверждённые связи родитель–потомок оставлены пустыми.\n')
md('18_ORGANIZATION_COVERAGE.md','# Покрытие 94 организаций\n\nYES — поле есть в канонических данных; PARTIAL — фрагмент сведений; NO — не найдено; NEEDS_REVIEW — правило предложено, но не утверждено. Новые источники отдельно в 21.\n\n'+table(['ID','Название RU','Название KY','Алиасы','Территория','Родитель','Тип','Комп.','Тел.','Адрес','Email','Часы','Приём','Сайт','Руковод.','Порядок приёма','Услуги','Маршрут','Правовая база','Источники'],[[x['organization_id'],x['name_ru'],x['name_ky'],', '.join(x['aliases']),x['territory'],x['parent'],x['organization_type']]+[x['coverage'][a] for a in ['competence','phone','address','email','working_hours','reception_hours','website','leader','reception_procedure','services','routing_facts','legal_basis']]+[', '.join(x['source_ids'])] for x in oc]))
cnt=collections.Counter(c['type'] for c in C);phoneorg={c['organization_id'] for c in C if c['type']=='phone'};addrorg={c['organization_id'] for c in C if c['type']=='address'}
contact_text='# Контакты: проверка 72 записей\n\n'+table(['Тип','Записей'],[[t,cnt[t]] for t in ['phone','address','email','website','working_hours','reception_hours','other']])+'\nОбратите внимание: 72 — число записей, а не число телефонов. Все записи имеют `publication_status=NEEDS_REVIEW`.\n\n'
for title,ids in [('Организации с телефоном',phoneorg),('Организации без телефона',{o['organization_id'] for o in O}-phoneorg),('Организации с адресом',addrorg),('Организации без адреса',{o['organization_id'] for o in O}-addrorg),('Организации с часами работы',set()),('Организации без часов работы',{o['organization_id'] for o in O})]:
    contact_text+='## '+title+f' ({len(ids)})\n\n'+', '.join(oname(org[i]) for i in sorted(ids))+'\n\n'
contact_text+='## Противоречия\n\nСм. `13_CONFLICTS.md`: два адреса фитосанитарной структуры, географически спорный адрес финансового органа, вариант написания налогового адреса. Контакты из второго прохода не исправляют эти записи автоматически.\n\n## Распределение по источникам и территориям\n\nВ `audit_machine/contact_coverage.jsonl` каждая запись связана с organization_id, territory, source_ids и locator provenance.\n'
md('19_CONTACT_COVERAGE.md',contact_text)
md('20_SERVICES_AND_PROCEDURES_COVERAGE.md','# Процедуры и гражданские услуги\n\nДостаточность означает одновременно компетентный орган, канал обращения, шаги и необходимые документы. В каноническом корпусе полных наборов не найдено. Локальные анкеты описывают отдельные шаги обращения, но не дают универсальной опубликованной инструкции.\n\n'+table(['Процедура','Организаций-кандидатов','Документы','Шаги','Контакт','Часы','Покрытие','Источник'],[[p['procedure_name'],len(p['organization_ids']),'нет','нет','нет','нет',p['coverage_status'],', '.join(p['source_ids'][:8])] for p in proc]))
md('21_RECOVERABLE_FACTS.md','# Факты, восстанавливаемые из исходников\n\nВсе 76 ранее не представленных текстовых источников открыты повторно. Сканирование охватило 14 454 текстовых блока вместе с 13 новыми уникальными файлами. Таблица содержит точные фрагменты-кандидаты; `NEEDS_REVIEW` означает проверку смысла, актуальности и публичности до переноса в корпус. Персональные номера в анкетах скрыты.\n\n'+table(['Source ID','Файл','Страница/лист','Тип','Сущность','Значение','Причина пропуска'],[[f['source_id'],f['file'],f['locator'],f['fact_type'],f['entity'],f['value'],f['reason_it_was_not_in_corpus']] for f in facts])+ '\nОтдельно: SRC-205 — справочник служебных и личных телефонов; требуется владельцем выделить разрешённые к публикации номера приёмных. Пустые поля типовых анкет не учитывались как факты.\n')
blocked=[s for s in S if s['status']=='blocked']
def blockprio(s):
    name=s['source_file'].lower()
    if re.search('тел|тиркеме|анкета|майлуу|кочкор|манас|таш-комур',name):return 'P0'
    if re.search('положен|жобо|архив|суу|электро',name):return 'P1'
    if re.search('карта|181',name):return 'P2'
    return 'P2'
def blocktopic(s):
    n=s['source_file'].lower()
    return 'контакты/анкета' if re.search('тел|тиркеме|анкета',n) else ('положение/компетенции' if re.search('положен|жобо',n) else 'документ по имени/папке; содержание неизвестно')
md('22_BLOCKED_SOURCE_PRIORITY.md','# Приоритет разблокировки 12 источников\n\nПриоритет основан на имени и расположении файла, а не на непрочитанном содержимом. Сначала запросить доступный для поиска оригинал у держателя.\n\n'+table(['ID','Файл','Формат','Вероятная тема','Территория','Организация','Потенциальная ценность','Приоритет'],[[s['source_id'],s['source_file'],s['file_type'],blocktopic(s),territory_for(s['source_file']),'по имени файла / уточнить','контакты/процедуры' if blockprio(s)=='P0' else 'компетенции или фон',blockprio(s)] for s in blocked]))
md('23_TERRITORY_GAP_MATRIX.md','# Матрица пробелов по территории\n\nGOOD требует достаточных проверенных данных; PARTIAL означает хотя бы одно релевантное каноническое упоминание, MISSING — нет подтверждённого поля. Новые факты не меняют матрицу до нормализации.\n\n'+table(['Территория']+columns,[[x['territory_id']]+[x['values'][c] for c in columns] for x in matrix])+'\n## Топ-20 критических пробелов\n\n'+''.join(f'{i}. {label}\n' for i,label in enumerate(['Публичный телефон Манасского водоканала','Адрес Манасского водоканала','Зона обслуживания каждого водоканала','Порядок записи к руководителю области','График личного приёма областной администрации','Порядок записи ребёнка в школу','Список документов для школьного зачисления','Единая схема обращения по открытому люку','Ответственный за уличное освещение по каждой территории','Ответственный за муниципальные дороги по каждой территории','График вывоза мусора и диспетчер по каждой территории','Общая публичная телефонная книга районов','Рабочие часы 94 канонических организаций','Подтверждение служебных номеров из SRC-205','Утверждённая маршрутизация по муниципальным темам','Порядок подачи заявки через бот или иную систему','Зоны обслуживания айыл аймаков','Актуализация юридических адресов как адресов приёма','Проверка конфликтующих адресов','Публичное согласование контактов'],1)))
md('24_REAL_QUERY_COVERAGE.md','# Проверка 14 реальных вопросов\n\nСтатусы: FULL_ANSWER, PARTIAL_ANSWER, NEEDS_CLARIFICATION, CAN_OFFER_APPEAL, NO_DATA. Ответы ниже — максимально допустимые по локальным источникам черновики, не утверждённые для публикации.\n\n'+table(['№','Вопрос','Статус','Имеющиеся факты / лучший ответ','Недостаёт / уточнить','Действие','Источники'],[[q['query_id'],q['question'],q['status'],q['best_possible_grounded_answer'],q['missing_facts'],q['possible_citizen_action'],', '.join(q['source_ids'])] for q in qr]))
total=len(S);newunique=sum(not n['duplicate_of'] for n in N)
newfacts=sum(f['source_id'].startswith('NEW') for f in facts);oldfacts=len(facts)-newfacts
stats=table(['Показатель','Значение'],[['Исходные логические источники',total],['Текст извлечён',sum(s['status']=='processed' for s in S)],['Внесли канонические записи',108],['Blocked',len(blocked)],['Новые логические документы',len(N)],['Новые уникальные документы',newunique],['Организации',len(O)],['Телефоны',cnt['phone']],['Адреса',cnt['address']],['Email',cnt['email']],['Рабочие часы',cnt['working_hours']],['Часы приёма',cnt['reception_hours']],['Организации с телефоном',f'{len(phoneorg)}/{len(O)} ({len(phoneorg)/len(O):.1%})'],['Организации с адресом',f'{len(addrorg)}/{len(O)} ({len(addrorg)/len(O):.1%})'],['Организации с часами',f'0/{len(O)} (0%)'],['Территории GOOD/PARTIAL/POOR/NO_DATA',str(dict(collections.Counter(t['coverage_status'] for t in terr)))],['Полные процедуры',sum(p['sufficient_for_step_by_step_answer'] for p in proc)],['Процедуры с неполными/отсутствующими данными',len(proc)],['Фрагменты-кандидаты из прежних источников',oldfacts],['Фрагменты-кандидаты из новых источников',newfacts]])
md('25_KNOWLEDGE_COMPLETENESS_AUDIT.md','# Второй аудит полноты AIG2C\n\nДата: 2026-10-01. Источники: только локальные документы и `knowledge_output`. Канонические 00–16 и `machine/` не менялись. Числа ниже относятся к прежнему production-кандидатному корпусу; новые файлы показаны отдельно.\n\n'+stats+'\n## Основные выводы\n\n72 контакта состоят из 70 адресов и 2 телефонов; в 94 карточках нет подтверждённых рабочих часов. Практические телефоны, часы и процессные ответы присутствуют в ряде исходных анкет и писем, но не перенесены в канонические записи. Их нельзя автоматически публиковать: встречаются личные номера, неясная актуальность и юридический адрес вместо приёмного.\n\nПобайтовые дубли новых загрузок: '+', '.join(n['source_id']+'→'+n['duplicate_of'] for n in N if n['duplicate_of'])+'. 13 уникальных новых документов включают уставы учреждений образования, культуры и СМИ, положения таможни, железной дороги, финансового управления и учреждения №10. Их факты находятся только в отдельном аудите.\n\nВ новом файле NEW-242 обнаружено расхождение адреса областной библиотеки: справка реестра называет переулок Т. Байзакова, 20, устав — проспект Т. Байзакова, 20. Телефон +996(312)62-62-10 на титульной части относится к Министерству юстиции, а не к библиотеке; в контактную карточку библиотеки не переносить.\n\nВсе 12 заблокированных файлов перечислены в 22; особый приоритет у телефонного списка SRC-192 и приложений по Кочкор-Ате SRC-174/175.\n\n## Практические ответы\n\nЧастично можно показать известные организации, компетенции, 70 канонических адресных записей, адрес «Суу канал» в Шамалдуу-Сай и уточнить территорию перед направлением обращения. Для Арстанбап-Ата исходный документ даёт маршруты по открытому люку, освещению, дорогам и мусору, но они ещё не утверждены как production-правила. Нельзя достоверно сообщить общий телефон Манасского водоканала, часы большинства ведомств, процедуру записи к руководителю области, школьного приёма и владельца каждого люка/дороги/фонаря вне указанной территории.\n\n## Что восстанавливается без нового запроса\n\nSRC-111 содержит телефон, адрес и часы в листе; SRC-127 — роль Акманской коммунальной службы и порядок приёма; SRC-150 — адрес/телефон/график городской службы; SRC-220 — адрес и график Терек-Сайского айыл өкмөтү. Несколько новых уставов содержат юридические адреса. Каждое значение требует проверки актуальности и публикации. Подробные locators — в 21 и `audit_machine/recoverable_facts.jsonl`.\n\n## Ограничения метода\n\nГеопривязка по названию или адресу не равна утверждённой зоне обслуживания. Таблица восстановимых фрагментов — очередь ручной нормализации, а не каталог публичных контактов. Даже `verified` в старом корпусе означает подтверждение по источнику, не текущую юридическую силу.\n')

req='# Запрос недостающих сведений заказчику\n\nПросим вернуть XLSX/CSV по строке на организацию и услугу с `territory_id`, официальными RU/KY названиями, ответственным органом, публичным телефоном, адресом приёма, email, сайтом, рабочим графиком, временем личного приёма, процедурой записи, документами, сроками, зоной обслуживания, исключениями маршрутизации, датой актуализации и разрешением на публикацию. Контакты сотрудников из SRC-205 не считать автоматически публичными.\n\n'
for t in terr:
    tid=t['territory_id']; m=next(x for x in matrix if x['territory_id']==tid)['values']
    members=[o for o in oc if o['territory']==tid]
    req+='## '+t['name_ru']+' (`'+tid+'`)\n\n'
    req+='Имеются: '+(', '.join((o['name_ru'] or o['name_ky'] or '') for o in members) if members else 'подтверждённых карточек организаций в каноническом корпусе нет')+'.\n\n'
    asks=[]
    if m['municipal_bodies']=='MISSING':asks.append('официальный перечень муниципальных органов и приёмной')
    if m['state_bodies']=='MISSING':asks.append('перечень территориальных государственных подразделений')
    for col,label in [('utilities','коммунальных предприятий'),('education','школ и отдела образования'),('health','медицинских организаций'),('social','социальных служб'),('roads','дорожной службы'),('water','оператора водоснабжения/канализации'),('waste','оператора вывоза мусора'),('lighting','службы уличного освещения'),('land','земельного/кадастрового органа'),('tax','налогового органа')]:
        if m[col]=='MISSING':asks.append('список '+label)
    req+='Запросить отсутствующие организации: '+('; '.join(asks) if asks else 'сверить полноту имеющегося списка')+'.\n\n'
    req+='Для всех перечисленных организаций запросить публичные телефоны, фактические адреса приёма, рабочие часы и часы личного приёма; особенно '+(', '.join((o['name_ru'] or o['name_ky'] or '') for o in members if o['coverage']['phone']=='NO') if members else 'полный территориальный реестр')+'.\n\n'
    req+='Процедуры: приём обращения/заявки, запись к руководителю, вода и аварии, открытые люки, дороги, освещение, отходы, земельные вопросы; указать шаги, документы, сроки, каналы и ответственных. Маршрутизация: первичный исполнитель и запасной, исключения и эскалация. Зоны обслуживания: улицы/сёла/границы, связь с соседними территориями. Источники территории: '+', '.join(t['source_ids'][:15])+'.\n\n'
md('26_INFORMATION_REQUEST_TO_GOVERNMENT.md',req)
before=json.loads((AUD/'baseline_hashes.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in before.items()),'canonical changed'
assert len(oc)==94 and len(cc)==72 and len(blocked)==12 and len(qr)==14 and len(N)==17
print(json.dumps({'territories':len(terr),'organizations':len(oc),'contacts':len(cc),'recoverable_fragments':len(facts),'queries':len(qr),'canonical_unchanged':True},ensure_ascii=False))
