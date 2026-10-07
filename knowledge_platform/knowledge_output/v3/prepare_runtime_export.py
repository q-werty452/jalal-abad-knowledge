"""Write only the nine public JSONL files supported by the current bot parser."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

V3 = Path(__file__).resolve().parent
M = V3 / 'machine'
OUT = V3 / 'runtime_export'
OUT.mkdir(exist_ok=True)
NAMES = ('sources', 'organizations', 'competences', 'contacts', 'routing_rules',
         'qa_pairs_ru', 'qa_pairs_ky', 'rag_chunks', 'aliases')

def read(name):
    return [json.loads(line) for line in (M / f'{name}.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]

tables = {name: copy.deepcopy(read(name)) for name in NAMES}
all_contacts = tables['contacts']
tables['contacts'] = [x for x in all_contacts if x.get('visibility', 'PUBLIC') == 'PUBLIC'
                      and x.get('status', 'SOURCE_CONFIRMED') == 'SOURCE_CONFIRMED']
tables['routing_rules'] = [x for x in tables['routing_rules']
                           if x.get('visibility') == 'PUBLIC'
                           and x.get('pilot_status') == 'SOURCE_CONFIRMED_SUGGESTION'
                           and (not x['routing_rule_id'].startswith('v3-')
                                or (x.get('route_type') == 'SINGLE'
                                    and x.get('target_organization_id')
                                    and x.get('territory_scope')))]
for name in ('organizations', 'competences', 'qa_pairs_ru', 'qa_pairs_ky', 'rag_chunks', 'aliases'):
    tables[name] = [x for x in tables[name]
                    if x.get('visibility', 'PUBLIC') == 'PUBLIC'
                    and x.get('pilot_status', 'SOURCE_CONFIRMED') not in ('CONFLICT', 'AMBIGUOUS')]

# Extra metadata does not change the nine-file legacy schema. The parser can
# ignore it; a later structured engine can consume the territory relation.
zones = read('service_territories')
zone_map = {}
for relation in zones:
    if relation['status'] == 'SOURCE_CONFIRMED':
        zone_map.setdefault(relation['organization_id'], []).append(relation['territory_id'])
for org in tables['organizations']:
    org['service_territory_ids'] = sorted(set(zone_map.get(org['organization_id'], [])))
for c in tables['contacts']:
    if c['type'] in ('working_hours', 'reception_hours'):
        c['working_hours'] = c['value']

internal_numbers = {''.join(re.findall(r'\d', c['value']))
                    for c in all_contacts if c['type'] == 'phone' and c.get('visibility') != 'PUBLIC'}
public_numbers = {''.join(re.findall(r'\d', c['value']))
                  for c in tables['contacts'] if c['type'] == 'phone'}
overlap = {x for x in internal_numbers & public_numbers if len(x) >= 9}
if overlap:
    raise ValueError(f'phone both public and internal: {len(overlap)} value(s)')
for name in ('competences', 'qa_pairs_ru', 'qa_pairs_ky', 'rag_chunks', 'routing_rules'):
    for row in tables[name]:
        text = json.dumps(row, ensure_ascii=False)
        normalized = ''.join(re.findall(r'\d', text))
        for number in internal_numbers:
            if len(number) >= 9 and number in normalized:
                raise ValueError(f'private phone in public {name}')

for name in NAMES:
    with (OUT / f'{name}.jsonl').open('w', encoding='utf-8') as handle:
        for row in tables[name]:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
print(json.dumps({name: len(tables[name]) for name in NAMES}, ensure_ascii=False))
