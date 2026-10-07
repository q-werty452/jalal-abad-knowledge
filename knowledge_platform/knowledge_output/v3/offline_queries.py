"""Deterministic, offline coverage examples across topics and territories."""
import json
from pathlib import Path

V3 = Path(__file__).resolve().parent
M = V3 / 'machine'
PUB = V3 / 'runtime_export'

def read(directory, name):
    return [json.loads(line) for line in (directory / f'{name}.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]

routes = read(M, 'routing_rules')
contacts = read(PUB, 'contacts')
all_contacts = read(M, 'contacts')
orgs = {x['organization_id']: x for x in read(M, 'organizations')}
categories = read(M, 'appeal_categories')
cases = [
    ('Жол бузулду, Ноокен району', 'ROAD', 'district:Ноокен', None),
    ('Көчө жарыгы күйбөйт, Ноокен району', 'STREET_LIGHT', 'district:Ноокен', None),
    ('Таштанды чыгарылган жок, Ноокен району', 'WASTE', 'district:Ноокен', None),
    ('Суу түтүгү жарылды, Ноокен району', 'WATER_PIPE_BREAK', 'district:Ноокен', None),
    ('Суу жок, Ноокен району', 'NO_WATER', 'district:Ноокен', None),
    ('Канализация маселеси, Ноокен району', 'SEWER', 'district:Ноокен', None),
    ('Ачык люк, Ноокен району', 'MANHOLE', 'district:Ноокен', None),
    ('Электр жарыгы өчтү, Ноокен району', 'ELECTRICITY', 'district:Ноокен', None),
    ('Жер участогу, Ноокен району', 'LAND', 'district:Ноокен', None),
    ('Светофор бузулду, Ноокен району', 'TRAFFIC_SIGN_LIGHT', 'district:Ноокен', None),
    ('Баланы мектепке берүү, Ноокен району', 'EDUCATION', 'district:Ноокен', None),
    ('Дарыгер керек, Ноокен району', 'HEALTH', 'district:Ноокен', None),
    ('Социалдык жардам, Ноокен району', 'SOCIAL_SUPPORT', 'district:Ноокен', None),
    ('Үйүм жок, Ноокен району', 'HOUSING', 'district:Ноокен', None),
    ('Момбековдо суу жок', 'NO_WATER', 'ayyl_area:Момбеков', None),
    ('Бүргөндү-Достукта таштанды', 'WASTE', 'ayyl_area:Бүргөндү-Достук', None),
    ('Каныш-Кыя айылындагы суу авариясы', 'WATER_SERVICE', 'ayyl_area:Каныш-Кыя', None),
    ('Терек-Сай айылындагы суу авариясы', 'WATER_SERVICE', 'ayyl_area:Терек-Сай', None),
    ('Каныш-Кыядагы жол маселеси', 'ROAD', 'ayyl_area:Каныш-Кыя', None),
    ('Кочкор-Ата мэриясынын телефону', 'CONTACT', 'city:Кочкор-Ата', 'org-kochkor-ata-shaarynyn-meriyasy-2cc10ef'),
    ('Шамалдуу-Сай мэриясынын дареги', 'ADDRESS', 'city:Шамалдуу-Сай', 'org-shamalduu-sai-shaardyk-meriya-9de9534'),
    ('Момбеков айыл өкмөтүнүн телефону', 'CONTACT', 'ayyl_area:Момбеков', 'org-mombekov-aiyl-okmotu-d36a51d'),
]

results = []
for question, topic, territory, direct_org in cases:
    matched = [r for r in routes if r.get('canonical_topic') == topic
               and territory in r.get('territory_scope', [])
               and r.get('routing_rule_id', '').startswith('v3-')]
    if topic in ('NO_WATER', 'WATER_PIPE_BREAK') and not matched:
        matched = [r for r in routes if r.get('canonical_topic') == 'WATER_SERVICE'
                   and territory in r.get('territory_scope', [])
                   and r.get('routing_rule_id', '').startswith('v3-')]
    safe_routes = [r for r in matched if r.get('visibility') == 'PUBLIC']
    source_ids = sorted({sid for r in matched for sid in r['source_ids']})
    chosen = direct_org or next((r.get('target_organization_id') for r in safe_routes
                                 if r.get('route_type') == 'SINGLE' and r.get('target_organization_id')), None)
    published_contacts = [c for c in contacts if c['organization_id'] == chosen] if chosen else []
    if direct_org:
        wanted = 'phone' if topic == 'CONTACT' else 'address'
        published_contacts = [c for c in published_contacts if c['type'] == wanted]
        source_ids = sorted(set(source_ids) | {sid for c in all_contacts if c['organization_id'] == direct_org
                                             and c['type'] == wanted for sid in c['source_ids']})
    else:
        source_ids = sorted(set(source_ids) | {sid for c in published_contacts for sid in c['source_ids']})
    if safe_routes:
        route_status = 'SOURCE_CONFIRMED_SUGGESTION' if any(r['route_type'] == 'SINGLE' for r in safe_routes) else 'NEEDS_OPERATOR'
    elif matched:route_status = 'INTERNAL_ONLY'
    else:route_status = 'NO_SAFE_ROUTE'
    if direct_org and published_contacts:route_status = 'STRUCTURED_CONTACT'
    category_found = any(c.get('territory_id') == territory and
                         (c.get('canonical_topic') == topic or topic == 'HOUSING' and 'турак' in c.get('original_wording','').lower())
                         for c in categories)
    if category_found and not source_ids:
        source_ids = sorted({sid for c in categories if c.get('territory_id') == territory
                             and (c.get('canonical_topic') == topic or topic == 'HOUSING' and 'турак' in c.get('original_wording','').lower())
                             for sid in c['source_ids']})
    missing = []
    if not safe_routes and not published_contacts:missing.append('публичный маршрут/контакт')
    if any(r['route_type'] != 'SINGLE' for r in safe_routes):missing.append('конкретный исполнитель и точный адрес проблемы')
    if topic in ('CONTACT', 'ADDRESS') and not published_contacts:missing.append('подтверждённое публичное значение')
    if topic in ('NO_WATER','WATER_PIPE_BREAK','MANHOLE','WASTE','ROAD','STREET_LIGHT','ELECTRICITY'):
        missing.append('улица/село для выбора местной службы')
    if topic == 'EDUCATION':missing.append('школа, возраст ребёнка и полный порядок зачисления')
    if topic == 'SOCIAL_SUPPORT':missing.append('вид помощи и полный порядок обращения')
    if topic == 'HOUSING':missing.append('компетентный исполнитель и порядок предоставления жилья')
    answer = ('; '.join(f'{c["type"]}: {c["value"]}' for c in published_contacts[:3]) or
              '; '.join(', '.join(r.get('responsible_candidate_labels', [])) or r.get('notes') or r['topic']
                        for r in safe_routes[:2]) or 'Публичного точного ответа нет; требуется уточнение/оператор')
    results.append({'question': question, 'topic': topic, 'territory_id': territory,
                    'route_status': route_status, 'structured_routes': [r['routing_rule_id'] for r in matched],
                    'public_route_count': len(safe_routes), 'public_contacts': [c['contact_id'] for c in published_contacts],
                    'source_ids': source_ids, 'category_found': category_found,
                    'offline_answer': answer, 'missing_fields': missing})

with (V3 / 'offline_query_coverage.jsonl').open('w', encoding='utf-8') as handle:
    for row in results:handle.write(json.dumps(row, ensure_ascii=False) + '\n')
lines = ['# V3 — офлайн-проверка вопросов', '',
         'Использованы только структурированные JSONL и фильтр публичного runtime. Генерация OpenAI и embeddings не использовались.', '']
for number, row in enumerate(results, 1):
    lines.extend([f'## {number}. {row["question"]}', '',
                  f'- Территория: `{row["territory_id"]}`; тема: `{row["topic"]}`.',
                  f'- Результат: `{row["route_status"]}`; маршрутов: {len(row["structured_routes"])} (публичных {row["public_route_count"]}); публичных контактов: {len(row["public_contacts"])}.',
                  f'- Источники: {", ".join(row["source_ids"]) or "не найдены"}.',
                  f'- Структурный ответ: {row["offline_answer"]}.',
                  f'- Недостаёт: {", ".join(row["missing_fields"]) or "нет"}.', ''])
(V3 / 'OFFLINE_QUERY_COVERAGE.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps({'queries': len(results), 'statuses': {x: sum(r['route_status'] == x for r in results)
                                                   for x in sorted({r['route_status'] for r in results})}}, ensure_ascii=False))
