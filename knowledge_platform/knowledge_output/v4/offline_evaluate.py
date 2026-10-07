from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
routes=[json.loads(x) for x in (ROOT/'runtime_export/routing_rules.jsonl').read_text(encoding='utf8').splitlines()]
orgs={x['organization_id']:x for x in map(json.loads,(ROOT/'runtime_export/organizations.jsonl').read_text(encoding='utf8').splitlines())}
cases=[
 ('Кто чинит дороги в Кетмен-Добо?','ROAD','ayyl_area:Кетмен-Добо'),
 ('Кто чинит дороги в Айры-Там?','ROAD','ayyl_area:Айры-Там'),
 ('Кто чинит дороги в Көк-Арт?','ROAD','ayyl_area:Көк-Арт'),
 ('Не горит фонарь в Уч-Терек','STREET_LIGHT','ayyl_area:Уч-Терек'),
 ('Нет уличного света в Ынтымак','STREET_LIGHT','ayyl_area:Ынтымак'),
 ('Мусор в Токтогуле','WASTE','city:Токтогул'),
 ('Таштанды Айры-Там','WASTE','ayyl_area:Айры-Там'),
 ('Нет воды в Токтогуле','WATER','city:Токтогул'),
 ('Вода в Ала-Бука','WATER','ayyl_area:Ала-Бука'),
 ('Канализация в Токтогуле','SEWER','city:Токтогул'),
 ('Открытый люк в Айры-Там','MANHOLE','ayyl_area:Айры-Там'),
 ('Электричество в Сузаке','ELECTRICITY','ayyl_area:Сузак'),
 ('Земельный вопрос в Уч-Терек','LAND','ayyl_area:Уч-Терек'),
 ('Сломан светофор в Токтогуле','TRAFFIC_LIGHT','city:Токтогул'),
 ('Нет дорожного знака в Токтогуле','TRAFFIC_SIGN','city:Токтогул'),
 ('Школа в Токтогуле','EDUCATION','district:Токтогул'),
 ('Детский сад в Токтогуле','KINDERGARTEN','district:Токтогул'),
 ('Медицинская помощь в Кара-Көл','HEALTH','city:Кара-Көл'),
 ('Социальная поддержка в Токтогуле','SOCIAL_SUPPORT','district:Токтогул'),
 ('Жилье в Сузаке','HOUSING','district:Сузак'),
 ('Нарушение порядка в Токтогуле','PUBLIC_ORDER','district:Токтогул'),
 ('Бродячие животные в Ала-Бука','STRAY_ANIMALS','district:Ала-Бука'),
 ('Нет воды в Кара-Көл','WATER','city:Кара-Көл'),
]
results=[];wrong_entity=wrong_territory=0
for text,topic,territory in cases:
    found=[r for r in routes if r.get('canonical_topic',r.get('topic'))==topic
           and (r.get('territory_scope') or r.get('territory_id'))==territory]
    targets=sorted({r.get('target_organization_id') for r in found if r.get('target_organization_id')})
    sources=sorted({s for r in found for s in r.get('source_ids',[])})
    wrong_entity+=sum(t not in orgs for t in targets)
    wrong_territory+=sum((r.get('territory_scope') or r.get('territory_id'))!=territory for r in found)
    results.append({'question':text,'topic':topic,'territory':territory,
      'result':'FOUND' if found else 'MISSING_OR_CONFLICT','organization_ids':targets,
      'source_ids':sources,'routing_rule_ids':[r['routing_rule_id'] for r in found],
      'operator_confirmation_required':any(r.get('operator_confirmation_required') for r in found)})
cross_topic={}
for topic in ('ROAD','WASTE','WATER','STREET_LIGHT'):
    grouped={r['territory'] : tuple(r['organization_ids']) for r in results if r['topic']==topic and r['organization_ids']}
    cross_topic[topic]=len(set(grouped.values()))
status='PASS' if not wrong_entity and not wrong_territory else 'FAIL'
(ROOT/'offline_query_coverage.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results),encoding='utf8')
(ROOT/'OFFLINE_QUERY_COVERAGE.md').write_text(
    '# Offline query coverage v4\n\n'
    f'Result: **{status}**; queries: **{len(results)}**; exact scoped routes: **{sum(r["result"]=="FOUND" for r in results)}**; '
    f'missing or conflict: **{sum(r["result"]!="FOUND" for r in results)}**. '
    f'Wrong entity: **{wrong_entity}**; wrong territory: **{wrong_territory}**.\n\n'
    'Lookup requires the exact territory scope; no rule is spread to the whole region. '
    'MISSING_OR_CONFLICT is a safe abstention, not a claimed answer. Routes remain advisory.\n\n'
    '| Question | Territory | Result | Targets | Sources |\n|---|---|---|---|---|\n'
    +''.join(f'| {r["question"]} | {r["territory"]} | {r["result"]} | {", ".join(r["organization_ids"])} | {", ".join(r["source_ids"])} |\n' for r in results),
    encoding='utf8')
print(json.dumps({'result':status,'queries':len(results),'found':sum(r['result']=='FOUND' for r in results),'missing_or_conflict':sum(r['result']!='FOUND' for r in results),'wrong_entity':wrong_entity,'wrong_territory':wrong_territory},ensure_ascii=False))
