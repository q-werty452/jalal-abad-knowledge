"""Create a publication-safe snapshot for the existing nine-file bot parser.

Run locally after build_v2.py and validate_v2.py. This never syncs the bot or
calls an embedding API. The complete adjudication remains in v2/machine.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MACHINE = HERE / 'machine'
EXPORT = HERE / 'runtime_export'
EXPORT.mkdir(exist_ok=True)
FILES = ('sources', 'organizations', 'competences', 'contacts', 'routing_rules',
         'qa_pairs_ru', 'qa_pairs_ky', 'rag_chunks', 'aliases')

def read(name):
    return [json.loads(line) for line in (MACHINE / f'{name}.jsonl').read_text(encoding='utf-8').splitlines() if line]

tables = {name: read(name) for name in FILES}
public_contacts = [row for row in tables['contacts']
                   if row.get('visibility', 'PUBLIC') == 'PUBLIC'
                   and row.get('status', 'SOURCE_CONFIRMED') == 'SOURCE_CONFIRMED']
tables['contacts'] = public_contacts
tables['routing_rules'] = [row for row in tables['routing_rules']
                           if row.get('visibility', 'PUBLIC') == 'PUBLIC'
                           and row.get('pilot_status') == 'SOURCE_CONFIRMED_SUGGESTION']
for name in ('organizations', 'competences', 'qa_pairs_ru', 'qa_pairs_ky', 'rag_chunks', 'aliases'):
    tables[name] = [row for row in tables[name] if row.get('visibility', 'PUBLIC') == 'PUBLIC'
                    and row.get('pilot_status', 'SOURCE_CONFIRMED') not in ('CONFLICT', 'AMBIGUOUS')]

# The current parser reads the legacy working_hours field, including for exact
# structured lookup. It does not inspect type=working_hours by itself.
for row in tables['contacts']:
    if row.get('type') in ('working_hours', 'reception_hours'):
        row['working_hours'] = row['value']

internal_phones = {''.join(ch for ch in row['value'] if ch.isdigit()) for row in read('contacts')
                   if row.get('type') == 'phone' and row.get('visibility') != 'PUBLIC'}
public_text = '\n'.join(json.dumps(row, ensure_ascii=False) for name in ('contacts', 'qa_pairs_ru', 'qa_pairs_ky', 'rag_chunks')
                        for row in tables[name])
public_digits = ''.join(ch if ch.isdigit() else ' ' for ch in public_text)
for number in internal_phones:
    if len(number) >= 9 and number in public_digits.replace(' ', ''):
        raise ValueError('Private phone appears in public export')

for name in FILES:
    with (EXPORT / f'{name}.jsonl').open('w', encoding='utf-8') as f:
        for row in tables[name]:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
print(json.dumps({name: len(tables[name]) for name in FILES}, ensure_ascii=False))
