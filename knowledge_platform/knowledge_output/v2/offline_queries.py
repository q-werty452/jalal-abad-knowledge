"""Deterministic structured-data checks; no model calls or semantic search."""
import json
from pathlib import Path

V2=Path(__file__).resolve().parent
M=V2/'machine'
def load(name):return [json.loads(x) for x in (M/(name+'.jsonl')).read_text(encoding='utf-8').splitlines() if x.strip()]
O=load('organizations');C=load('public_contacts');K=load('competences');R=load('routing_rules');P=load('procedures')
def name(o):return o.get('name_ru') or o.get('name_ky') or ''
def find(needle):
    options=[o for o in O if needle.lower() in name(o).lower()]
    if not options:raise ValueError('organization not found: '+needle)
    return options[0]
def facts(oid):
    result=[]
    for c in C:
        if c['organization_id']==oid:
            result.append({'type':c['type'],'value':c['value'],'source_ids':c['source_ids'],
                           'territory_id':c.get('territory_id'),'address_kind':c.get('address_kind')})
    for k in K:
        if k['organization_id']==oid and k.get('visibility')=='PUBLIC':
            result.append({'type':'competence','value':(k.get('description_ru') or k.get('description_ky') or '')[:240],
                           'source_ids':k['source_ids'],'territory_id':(k.get('territory') or [None])[0]})
    for p in P:
        if p['organization_id']==oid:
            result.append({'type':'procedure','value':p['name']+' ('+p['completeness']+')',
                           'source_ids':p['source_ids'],'territory_id':p.get('territory_id')})
    return result
def routes(pattern):
    result=[]
    for r in R:
        if r.get('visibility')!='PUBLIC' or r.get('pilot_status')!='SOURCE_CONFIRMED_SUGGESTION':continue
        if not any(k in r['topic'].lower() for k in pattern):continue
        result.append({'type':'routing_suggestion','value':r['topic'],'target_organization_id':r['target_organization_id'],
                       'target':name(next(o for o in O if o['organization_id']==r['target_organization_id'])),
                       'source_ids':r['source_ids'],'territory_id':r.get('territory_id') or (r.get('territory') or [None])[0],
                       'exclusion':r.get('exclusion',False)})
    return result
water=find('Управление водоканал Манас')
governor=find('Аппарат полномочного представителя Президента КР в Жалал-Абадской области')
cases=[]
def add(question,scenario,found,missing,answer):
    cases.append({'question':question,'scenario':scenario,'structured_facts_found':found,'sources':sorted({sid for x in found for sid in x['source_ids']}),
                  'territories':sorted({x['territory_id'] for x in found if x.get('territory_id')}),
                  'missing_fields':missing,'grounded_answer':answer,'method':'OFFLINE_STRUCTURED_LOOKUP_ONLY'})
wf=facts(water['organization_id'])
add('Как связаться с водоканалом?','Манасский водоканал выбран только как пример; город в вопросе не указан',wf,
    ['населённый пункт','публичный номер Манасского водоканала'],
    'Уточните город. Для Управления водоканал Манас известны функции и территориальные подсказки, но публичного номера в v2 нет. Мобильный ответственного сотрудника скрыт.')
for q,field in [('Номеричи?','phone'),('Какой адрес?','address'),('Когда работает?','working_hours')]:
    ff=[x for x in wf if x['type']==field]
    add(q,'контекст предыдущего вопроса: Управление водоканал Манас',ff,[field] if not ff else [],
        ('Для Манасского водоканала '+{'phone':'публичный номер','address':'адрес','working_hours':'график'}[field]+' в переданных данных не подтверждён.' if not ff else '; '.join(x['value'] for x in ff)))
add('Все что есть дай','контекст: Управление водоканал Манас',wf,
    [x for x in ('phone','address','working_hours') if not any(y['type']==x for y in wf)],
    'Есть название и функции Манасского водоканала; отдельные маршруты по воде и открытому люку относятся к Манасу. Публичных телефона, адреса и часов нет.')
gf=facts(governor['organization_id'])
add('Кантип губернаторго кирсем болот?','приём руководителя областной администрации',gf,
    ['порядок записи на личный приём','часы приёма','перечень документов'],
    'Облустук өкүлдүн аппаратынын байланыштары бар, бирок жеке кабыл алууга жазылуунун тартиби жана сааты булактарда көрсөтүлгөн эмес. Кабылдама аркылуу тактоо керек.')
add('Кантип баламды мектепке берсем болот?','приём ребёнка в школу',[],
    ['муниципалитет и школа','официальный порядок зачисления','документы','сроки'],
    'Кайсы шаар же айыл жана баланын жашы? Берилген булактарда мектепке кабыл алуунун толук тартиби жок.')
for q,pattern,missing,answer in [
 ('Люк урдап кетти',['люк'],['точное место','ответственный за иной район'],
  'Аймакты жана так даректи айтыңыз. Арстанбап-Атада булак муниципалдык суу-тазалык ишканасын, Манаста водоканалды көрсөтөт; Сайдыкумда айыл өкмөтү люктарга жооптуу эмес деп жазылган.'),
 ('Жол бузулду',['жол','дороге'],['точный адрес','тип дороги','ответственный вне указанных территорий'],
  'Аймакты жана жолдун дарегин тактаңыз. Манас, Арстанбап-Ата жана Сайдыкум боюнча гана булакка байланган багыттоо бар.'),
 ('Таштанды чыгарылган жок',['таштанды','мусор'],['точный адрес','обслуживающая зона','контакт для иного района'],
  'Аймакты жана көчөнү тактаңыз. Арстанбап-Атада суу-тазалык ишканасы, Манаста «Манас Тазалык», Сайдыкумда айыл өкмөтү/тазалык кызматы аталган.')]:
    add(q,'территория не указана',routes(pattern),missing,answer)

with (V2/'offline_query_check.jsonl').open('w',encoding='utf-8') as f:
    for x in cases:f.write(json.dumps(x,ensure_ascii=False)+'\n')
lines=['# Offline проверка 10 вопросов','',
       'Ответы сформированы только структурированными JSONL; генерация OpenAI и семантический индекс не использовались. Контекст в вопросах «Номеричи?», «Какой адрес?», «Когда работает?» — Манасский водоканал.','']
for i,x in enumerate(cases,1):
    lines.extend([f'## {i}. {x["question"]}','',f'**Сценарий:** {x["scenario"]}.',
                  f'**Найдено:** {len(x["structured_facts_found"])} структурированных записей; источники: {", ".join(x["sources"]) or "нет"}; территории: {", ".join(x["territories"]) or "не заданы"}.',
                  f'**Недостаёт:** {", ".join(x["missing_fields"]) or "ничего из проверяемых полей"}.',
                  f'**Ответ:** {x["grounded_answer"]}',''])
(V2/'OFFLINE_QUERY_CHECK.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'queries':len(cases),'sources_referenced':sorted({s for x in cases for s in x['sources']})},ensure_ascii=False))
