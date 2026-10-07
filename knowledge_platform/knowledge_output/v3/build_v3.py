"""Build Knowledge v3 from immutable v2 plus the October customer batch.

No bot/runtime writes, network calls, or semantic generation. All factual
additions carry a source ID and a paragraph/table-row locator.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / 'knowledge_output' / 'v2'
V3 = ROOT / 'knowledge_output' / 'v3'
M = V3 / 'machine'
DOC = V3 / 'source_documents'
REV = V3 / 'review'
for directory in (M, DOC, REV):
    directory.mkdir(parents=True, exist_ok=True)

def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

def write(path, rows):
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

def id_for(prefix, *parts):
    token = '|'.join(str(part) for part in parts)
    return prefix + hashlib.sha256(token.encode('utf-8')).hexdigest()[:14]

def norm(value):
    return re.sub(r'[^0-9a-zа-яёүөң]+', '', str(value).lower())

def digits(value):
    return ''.join(re.findall(r'\d', value))

base_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (V2 / 'machine').glob('*.jsonl')}
(V3 / 'v2_baseline_hashes.json').write_text(json.dumps(base_hashes, indent=2), encoding='utf-8')
data = {p.stem: copy.deepcopy(read(p)) for p in (V2 / 'machine').glob('*.jsonl')}
S = data['sources']; O = data['organizations']; C = data['contacts']
K = data['competences']; R = data['routing_rules']; G = data['rag_chunks']
T = data['territories']; A = data['aliases']; P = data['procedures']
SERV = data['services']; CONFLICT = data['conflicts']
STAFF = []; QUERIES = []; ESC = []; ZONES = []; TOPIC_ALIASES = []
REVIEW = []; CATEGORIES = []; DECISIONS = []
org_by_id = {o['organization_id']: o for o in O}
org_by_name = {norm(name): o for o in O for name in (o.get('name_ru'), o.get('name_ky')) if name}
territory_by_id = {t['territory_id']: t for t in T}
source_by_id = {s['source_id']: s for s in S}
contact_by_key = {(c['organization_id'], c['type'], norm(c['value'])): c for c in C}

batch = [
    ('NEW-248', 'Ноокен РМА (1) (1).docx'),
    ('NEW-249', 'Алиев.docx'),
    ('NEW-250', 'Простой_запрос_недостающих_данных_AIG2C (2).docx'),
    ('NEW-251', 'Бургонду-Достук (2).docx'),
    ('NEW-252', 'Кочко-Ата.docx'),
    ('NEW-253', 'Момбеков.docx'),
    ('NEW-254', 'Садырбаев.docx'),
    ('NEW-255', 'Шамалдуу-Сай.docx'),
    ('NEW-256', 'Ноокен РМА (1).docx'),
    ('NEW-257', 'Простой_запрос_недостающих_данных_AIG2C (1).docx'),
]
known_hash = {s['sha256']: s['source_id'] for s in S}
docs = {}
raw_texts = {}
for sid, filename in batch:
    original = Path.home() / 'Downloads' / filename
    copy_path = DOC / f'{sid}.docx'
    if not original.is_file() and not copy_path.is_file():
        raise FileNotFoundError(original)
    blob = original.read_bytes() if original.is_file() else copy_path.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    duplicate = known_hash.get(sha)
    if copy_path.exists() and hashlib.sha256(copy_path.read_bytes()).hexdigest() != sha:
        raise ValueError(f'customer copy changed: {copy_path}')
    if not copy_path.exists():
        copy_path.write_bytes(blob)
    path = copy_path
    document = Document(path)
    paragraphs = {i: ' '.join(p.text.split()) for i, p in enumerate(document.paragraphs, 1)}
    tables = {ti: {ri: [' '.join(cell.text.split()) for cell in row.cells]
                   for ri, row in enumerate(table.rows, 1)}
              for ti, table in enumerate(document.tables, 1)}
    docs[sid] = {'paragraphs': paragraphs, 'tables': tables}
    raw_texts[sid] = '\n'.join(paragraphs.values()) + '\n' + '\n'.join('|'.join(row) for table in tables.values() for row in table.values())
    record = {'source_id': sid, 'file_name': filename,
              'source_file': str(copy_path.relative_to(ROOT)),
              'original_file': str(original), 'file_type': 'docx', 'size': len(blob),
              'sha256': sha, 'duplicate_of': duplicate, 'status': 'duplicate' if duplicate else 'processed',
              'normalization_status': 'exact_duplicate' if duplicate else 'v3_promoted',
              'near_duplicate_group': None if duplicate else 'october_missing_data_form' if sid != 'NEW-248' else None,
              'verification_status': 'SOURCE_CONFIRMED',
              'v3_copy': str(copy_path.relative_to(V3))}
    date_value = tables.get(5, {}).get(14, ['', ''])[1] if 5 in tables else ''
    record['document_date'] = '2026-10-05' if date_value.strip() == '05.10.2026' else None
    S.append(record); source_by_id[sid] = record
    if duplicate is None:known_hash[sha] = sid

for sid, _ in batch:
    if source_by_id[sid]['duplicate_of']:
        REVIEW.append({'source_id': sid, 'decision': 'EXACT_DUPLICATE',
                       'duplicate_of': source_by_id[sid]['duplicate_of'],
                       'note': 'facts promoted through the existing source ID'})
    else:
        ratios = [(other, difflib.SequenceMatcher(None, raw_texts[sid], raw_texts[other]).ratio())
                  for other, _ in batch if other != sid and not source_by_id[other]['duplicate_of']]
        nearest, score = max(ratios, key=lambda x: x[1]) if ratios else (None, 0)
        REVIEW.append({'source_id': sid, 'decision': 'NEW_UNIQUE',
                       'near_duplicate_of': nearest if score >= .65 else None,
                       'text_similarity': round(score, 3),
                       'note': 'shared request template; filled answers retained independently' if score >= .65 else 'distinct content'})
write(REV / 'source_decisions.jsonl', REVIEW)

def paragraph(sid, number):
    return docs[sid]['paragraphs'].get(number, '')

def cell(sid, table, row, column=1):
    values = docs[sid]['tables'][table][row]
    return values[column] if column < len(values) else ''

def provenance(sid, locator):
    return {'source_id': sid, 'source_file': source_by_id[sid]['source_file'],
            'locator': locator, 'verification_status': 'SOURCE_CONFIRMED',
            'fact_status': 'SOURCE_FACT'}

def attach(record, sid, locator):
    record.setdefault('source_ids', [])
    if sid not in record['source_ids']:record['source_ids'].append(sid)
    record.setdefault('provenance', [])
    if not any(p.get('source_id') == sid and p.get('locator') == locator for p in record['provenance']):
        record['provenance'].append(provenance(sid, locator))

def territory(tid, sid, locator, name_ru=None, name_ky=None, typ=None, parent=None):
    if tid in territory_by_id:
        record = territory_by_id[tid]
        if sid not in record.get('source_ids', []):record.setdefault('source_ids', []).append(sid)
        if parent and record.get('parent_territory') and record['parent_territory'] != parent:
            old_parent = record['parent_territory']
            record['parent_territory'] = None;record['parent_status'] = 'CONFLICT'
            conflict_id = id_for('V3-CONFLICT-ZONE-', tid)
            if not any(x['conflict_id'] == conflict_id for x in CONFLICT):
                CONFLICT.append({'conflict_id': conflict_id, 'entity': tid,
                                 'field': 'service_zone_parent',
                                 'values': [old_parent, parent],
                                 'source_ids': list(record['source_ids']),
                                 'status': 'CONFLICT', 'resolution': 'NO_WINNER',
                                 'visibility': 'INTERNAL_ONLY'})
            for relation in ZONES:
                if relation['territory_id'] == tid:relation['status'] = 'CONFLICT'
            REVIEW.append({'source_id': sid, 'locator': locator,
                           'decision': 'CONFLICT_SERVICE_ZONE', 'value': tid})
        if parent and record.get('parent_territory') is None:
            if record.get('parent_status') != 'CONFLICT':
                record['parent_territory'] = parent; record['parent_status'] = 'SOURCE_CONFIRMED'
        return tid
    record = {'territory_id': tid, 'name_ru': name_ru, 'name_ky': name_ky,
              'type': typ or tid.split(':')[0], 'parent_territory': parent,
              'parent_status': 'SOURCE_CONFIRMED' if parent else 'UNCONFIRMED',
              'source_ids': [sid], 'provenance': [provenance(sid, locator)],
              'coverage_status': 'SOURCE_CONFIRMED'}
    T.append(record); territory_by_id[tid] = record
    return tid

def organization(name, sid, locator, tid, lang='ru', existing=None):
    record = org_by_id.get(existing) if existing else org_by_name.get(norm(name))
    if record is None:
        record = {'organization_id': id_for('v3-org-', name, tid),
                  'name_ru': name if lang == 'ru' else None,
                  'name_ky': name if lang == 'ky' else None,
                  'short_name_ru': None, 'short_name_ky': None,
                  'aliases_ru': [], 'aliases_ky': [], 'organization_type': 'unknown',
                  'parent_organization_id': None, 'territory': [tid] if tid else [],
                  'territory_status': 'SOURCE_CONTEXT' if tid else 'NEEDS_CONFIRMATION',
                  'status': 'active_unknown', 'source_ids': [], 'provenance': [],
                  'verification_status': 'SOURCE_CONFIRMED', 'pilot_status': 'SOURCE_CONFIRMED',
                  'visibility': 'PUBLIC'}
        O.append(record); org_by_id[record['organization_id']] = record
        org_by_name[norm(name)] = record
    attach(record, sid, locator)
    if tid and tid not in record.get('territory', []):
        record.setdefault('territory', []).append(tid)
    return record['organization_id']

def contact(oid, typ, value, sid, locator, tid, visibility='PUBLIC', status='SOURCE_CONFIRMED',
            kind=None, reason=None, equivalent=False):
    value = ' '.join(value.split()).strip(' ;,')
    if not value:return None
    if equivalent and typ == 'working_hours':
        old = next((c for c in C if c['organization_id'] == oid and c['type'] == typ
                    and '8:30' in c['value'] and '17:30' in c['value']), None)
        if old:
            attach(old, sid, locator)
            return old['contact_id']
    key = (oid, typ, norm(value))
    old = contact_by_key.get(key)
    if old:
        attach(old, sid, locator)
        if visibility != 'PUBLIC':
            old['visibility'] = 'INTERNAL_ONLY'
            old['publication_status'] = 'INTERNAL_ONLY'
        if status != 'SOURCE_CONFIRMED':old['status'] = status; old['pilot_status'] = status
        if kind and typ == 'address':
            old.setdefault('address_roles', [])
            if kind not in old['address_roles']:old['address_roles'].append(kind)
        return old['contact_id']
    record = {'contact_id': id_for('v3-contact-', oid, typ, value),
              'organization_id': oid, 'type': typ, 'contact_type': typ, 'value': value,
              'purpose': kind or 'source_contact', 'address_kind': kind if typ == 'address' else None,
              'working_hours': value if typ in ('working_hours', 'reception_hours') else None,
              'territory_id': tid, 'source_ids': [sid], 'provenance': [provenance(sid, locator)],
              'verification_status': 'SOURCE_CONFIRMED', 'status': status, 'pilot_status': status,
              'visibility': visibility,
              'publication_status': 'PILOT_PUBLIC' if status == 'SOURCE_CONFIRMED' and visibility == 'PUBLIC' else status,
              'reason': reason}
    C.append(record); contact_by_key[key] = record
    return record['contact_id']

def competence(oid, text, sid, locator, tid, topic):
    text = ' '.join(text.split())
    if not text:return None
    old = next((x for x in K if x['organization_id'] == oid and norm(x.get('description_ru') or x.get('description_ky') or '') == norm(text)), None)
    if old:
        attach(old, sid, locator);return old['competence_id']
    rec = {'competence_id': id_for('v3-comp-', oid, text), 'organization_id': oid,
           'topic': topic, 'description_ru': text if re.search(r'[ыэъё]', text.lower()) else None,
           'description_ky': text if not re.search(r'[ыэъё]', text.lower()) else None,
           'territory': [tid] if tid else [], 'territory_status': 'SOURCE_CONTEXT',
           'source_ids': [sid], 'provenance': [provenance(sid, locator)],
           'verification_status': 'SOURCE_CONFIRMED', 'pilot_status': 'SOURCE_CONFIRMED',
           'visibility': 'PUBLIC', 'fact_status': 'SOURCE_FACT'}
    K.append(rec);return rec['competence_id']

def procedure(oid, name, steps, sid, locator, tid, required=None, visibility='PUBLIC'):
    rec = {'procedure_id': id_for('v3-proc-', oid, name, sid), 'organization_id': oid,
           'name': name, 'steps': steps, 'required_documents': required or [],
           'territory_id': tid, 'completeness': 'PARTIAL',
           'source_ids': [sid], 'provenance': [provenance(sid, locator)],
           'status': 'SOURCE_CONFIRMED', 'visibility': visibility}
    P.append(rec);return rec['procedure_id']

def zone(oid, tid, sid, locator, wording, confidence='SOURCE_CONFIRMED'):
    if territory_by_id[tid].get('parent_status') == 'CONFLICT':confidence = 'CONFLICT'
    record = {'relation_id': id_for('v3-zone-', oid, tid, sid, wording),
              'organization_id': oid, 'territory_id': tid, 'original_wording': wording,
              'status': confidence, 'source_ids': [sid], 'provenance': [provenance(sid, locator)]}
    if not any(z['organization_id'] == oid and z['territory_id'] == tid for z in ZONES):ZONES.append(record)

def route(topic, original, tid, sid, locator, candidates, route_type='NEEDS_OPERATOR',
          public=True, notes=None, labels=None):
    oid = candidates[0] if route_type == 'SINGLE' and len(candidates) == 1 else None
    record = {'routing_rule_id': id_for('v3-route-', topic, tid, sid, locator),
              'canonical_topic': topic, 'topic': original, 'original_wording': original,
              'territory_id': tid, 'territory_scope': [tid], 'territory': [tid],
              'responsible_organization_ids': candidates,
              'responsible_candidate_labels': labels or [],
              'primary_candidate_id': oid, 'secondary_candidate_ids': candidates[1:] if oid else [],
              'target_organization_id': oid, 'route_type': route_type,
              'needs_operator': route_type != 'SINGLE',
              'trigger_phrases_ru': [], 'trigger_phrases_ky': [original],
              'source_ids': [sid], 'provenance': [provenance(sid, locator)],
              'confidence': 'SOURCE_CONFIRMED_SUGGESTION', 'pilot_status': 'SOURCE_CONFIRMED_SUGGESTION',
              'production_status': 'SUGGESTION_ONLY', 'visibility': 'PUBLIC' if public else 'INTERNAL_ONLY',
              'publication_status': 'PILOT_PUBLIC' if public else 'INTERNAL_ONLY',
              'notes': notes}
    R.append(record);return record['routing_rule_id']

def staff(oid, name, position, phone, role, sid, locator, tid, note=None):
    rec = {'staff_role_id': id_for('v3-staff-', oid, name, phone, role),
           'organization_id': oid, 'person_name': name or None, 'position': position or None,
           'phone': phone or None, 'system_role': role, 'territory_id': tid,
           'source_ids': [sid], 'provenance': [provenance(sid, locator)],
           'status': 'SOURCE_CONFIRMED', 'visibility': 'INTERNAL_ONLY', 'note': note}
    if not any(x['staff_role_id'] == rec['staff_role_id'] for x in STAFF):STAFF.append(rec)
    if phone:
        contact(oid, 'phone', phone, sid, locator, tid, 'INTERNAL_ONLY', reason='staff/system role phone')
    return rec['staff_role_id']

def chunk(oid, kind, text, sid, locator, tid=None, public=True, language='mixed'):
    text = ' '.join(text.split())
    if not text:return
    rec = {'chunk_id': id_for('v3-chunk-', oid or '', kind, sid, locator, text),
           'document_id': sid, 'source_ids': [sid], 'organization_ids': [oid] if oid else [],
           'topic': kind, 'language': language, 'title': org_by_id[oid].get('name_ru') or org_by_id[oid].get('name_ky') if oid else kind,
           'text': text[:700], 'source_file': source_by_id[sid]['source_file'],
           'territory_scope': [tid] if tid else [], 'territory_id': tid,
           'locator': locator, 'provenance': [provenance(sid, locator)],
           'verification_status': 'SOURCE_CONFIRMED', 'pilot_status': 'SOURCE_CONFIRMED',
           'visibility': 'PUBLIC' if public else 'INTERNAL_ONLY',
           'publication_status': 'PILOT_PUBLIC' if public else 'INTERNAL_ONLY',
           'tags': [kind]}
    G.append(rec)

# The two uploaded Noorken files are exact duplicates of the previously indexed
# SRC-183. Its unrepresented tables are promoted using the original source ID.
district = territory('district:Ноокен', 'SRC-183', 'paragraph:91')
nooken = organization('Ноокен райондук мамлекеттик администрациясы', 'SRC-183', 'paragraph:2',
                      district, 'ky', 'org-nooken-raionduk-mamlekettik-administratsiyasy-313800f')
for number in range(5, 28):
    text = paragraph('NEW-248', number)
    if text:
        rid = competence(nooken, text, 'SRC-183', f'paragraph:{number}', district, 'district_administration')
        chunk(nooken, 'competence', text, 'SRC-183', f'paragraph:{number}', district, language='ky')
staff(nooken, 'Ишенбеков Таалайбек Ишенбекович', 'Руководитель', '+996 550 863 399',
      'manager', 'SRC-183', 'paragraph:28', district)
role_map = {'Жетекчи': 'manager', 'Көзөмөлдөөчү': 'controller',
            'Аткаруучу': 'executor', 'кайрылууну кабыл алуучу,': 'appeal_receiver'}
for ri in range(2, 8):
    name, position, phone, raw_role = [cell('NEW-248', 1, ri, col) for col in (1, 2, 3, 4)]
    staff(nooken, name, position, phone, role_map.get(raw_role, 'system_staff'),
          'SRC-183', f'table:1:row:{ri}', district)
staff(nooken, 'Н.Минбаева', 'Адис', '0501 24 05 37', 'dispatcher',
      'SRC-183', 'table:3:row:3', district)

topic_map = {'Жолдун бузулушу, чуңкурлар': 'ROAD', 'Көчөнүн жарыгы күйбөйт': 'STREET_LIGHT',
             'Таштанды убагында чыгарылбайт': 'WASTE', 'Суу түтүгүнүн жарылышы': 'WATER_PIPE_BREAK',
             'Суу жок': 'NO_WATER', 'Канализация маселеси': 'SEWER', 'Ачык люк': 'MANHOLE',
             'Электр энергиясына байланыштуу маселе': 'ELECTRICITY', 'Мыйзамсыз курулуш': 'ILLEGAL_CONSTRUCTION',
             'Жер маселеси': 'LAND', 'Жол белгилери жана светофорлор': 'TRAFFIC_SIGN_LIGHT',
             'Кароосуз калган же жолбун иттер': 'STRAY_ANIMALS',
             'Өз алдынча таштанды төгүүчү жай': 'ILLEGAL_DUMP', 'Коомдук тартип маселеси': 'PUBLIC_ORDER',
             'Саламаттык сактоо маселеси': 'HEALTH', 'Билим берүү маселеси': 'EDUCATION',
             'Социалдык жардам жана жөлөкпул маселеси': 'SOCIAL_SUPPORT',
             'Башка мамлекеттик кызматтар боюнча маселелер': 'OTHER_SERVICE'}
known_target = {
    'Ноокен райондук электр тармактар ишканасы': 'v2-org-f7d3ded389c7',
    'Ноокен райондук билим берүү бөлүмү': 'org-nooken-mailuu-suu-bilim-beruu-bolumu-c0665db',
    'Ноокен райондук эмгек, социалдык камсыздоо жана миграция башкармалыгы':
        'org-nooken-raionduk-emgek-sotsialdyk-kamsyzdoo-zhana-migratsiya-bashk-90f3ec3',
}
for ri in range(2, 20):
    original = cell('NEW-248', 2, ri, 1)
    target_text = cell('NEW-248', 2, ri, 2)
    if not original:continue
    topic = topic_map.get(original, 'OTHER_SERVICE')
    if original == 'Жол белгилери жана светофорлор':
        original_topic_note = 'traffic signs and lights jointly named; no forced split'
    else:original_topic_note = None
    ids = []
    for target, oid in known_target.items():
        if target in target_text:ids.append(oid)
    if '№51' in target_text:ids.append('v2-org-f9c617c081de')
    if 'ветеринардык' in target_text:
        ids.append('org-nooken-raionduk-veterinariya-mal-charbasyn-onukturuu-zhaiyt-zhana-244ed43')
    ids = list(dict.fromkeys(ids))
    generic = any(term in target_text for term in ('Тиешелүү', 'тиешелүү', 'ЖӨБ органы', 'мекемеси'))
    route_type = 'SINGLE' if len(ids) == 1 and not generic and '/' not in target_text else \
                 'MULTI_AGENCY' if len(ids) > 1 or '/' in target_text or ',' in target_text else 'NEEDS_OPERATOR'
    rid = route(topic, original, district, 'SRC-183', f'table:2:row:{ri}', ids,
                route_type, labels=[x.strip() for x in re.split(r'\s*/\s*|,\s*', target_text) if x.strip()],
                notes='Ответственные по документу: ' + target_text +
                ('. ' + original_topic_note if original_topic_note else ''))
    chunk(nooken, 'routing', f'Ноокен району. {original}: {target_text}. Багыттоо сунушу гана.',
          'SRC-183', f'table:2:row:{ri}', district, language='ky')

for number in range(35, 78):
    text = paragraph('NEW-248', number)
    if text.endswith(':') or not text:continue
    CATEGORIES.append({'category_id': id_for('v3-category-', text, district),
                       'original_wording': text, 'canonical_topic': next((topic for wording, topic in topic_map.items() if wording in text), 'OTHER'),
                       'territory_id': district, 'source_ids': ['SRC-183'],
                       'provenance': [provenance('SRC-183', f'paragraph:{number}')],
                       'status': 'SOURCE_CONFIRMED'})

for number, topic in [(81, 'LAND'), (82, 'LAND'), (83, 'ROAD'),
                      (84, 'SOCIAL_SUPPORT'), (85, 'HOUSING')]:
    QUERIES.append({'example_id': id_for('v3-query-', 'SRC-183', number),
                    'text': paragraph('NEW-248', number), 'language': 'ky', 'topic': topic,
                    'territory_id': district, 'source_ids': ['SRC-183'],
                    'locator': f'paragraph:{number}', 'provenance': [provenance('SRC-183', f'paragraph:{number}')],
                    'use': 'EVALUATION_OR_INTENT_ONLY', 'official_answer': None})
for number, kind in [(88, 'SEPARATE_LETTERS'), (89, 'COMMISSION_REVIEW')]:
    ESC.append({'escalation_rule_id': id_for('v3-escalation-', 'SRC-183', number),
                'organization_id': nooken, 'territory_id': district, 'rule_type': kind,
                'description': paragraph('NEW-248', number), 'multi_agency': True,
                'production_status': 'NEEDS_OPERATOR', 'source_ids': ['SRC-183'],
                'provenance': [provenance('SRC-183', f'paragraph:{number}')],
                'visibility': 'PUBLIC'})
    chunk(nooken, 'escalation', paragraph('NEW-248', number), 'SRC-183', f'paragraph:{number}', district, language='ky')
steps = [paragraph('NEW-248', i) for i in range(98, 104)]
procedure(nooken, 'Обработка обращения в Ноокенской РМА', steps,
          'SRC-183', 'paragraph:97-104', district)
chunk(nooken, 'procedure', 'Ноокен РМА: ' + '; '.join(steps), 'SRC-183', 'paragraph:97-104', district, language='ky')
for number in (93, 94, 95):
    chunk(nooken, 'procedure', paragraph('NEW-248', number), 'SRC-183', f'paragraph:{number}', district, language='ky')
for name, tid in [('Д.Садырбаев', 'ayyl_area:Д.Садырбаев'),
                  ('Эргеш Алиев', 'ayyl_area:Эргеш Алиев'),
                  ('Момбеков', 'ayyl_area:Момбеков'),
                  ('Бүргөндү-Достук', 'ayyl_area:Бүргөндү-Достук'),
                  ('Кочкор-Ата', 'city:Кочкор-Ата'), ('Шамалдуу-Сай', 'city:Шамалдуу-Сай')]:
    territory(tid, 'SRC-183', 'paragraph:91', name_ru=name, parent=district)
    zone(nooken, tid, 'SRC-183', 'paragraph:91', name)

# Filled answer tables in the eight new request forms. Template instructions
# in tables 1–3 are never treated as source-confirmed institutional facts.
form_specs = [
    ('NEW-249', 'org-ergesh-aliev-aiyl-okmotu-54d3a80', 'ayyl_area:Эргеш Алиев'),
    ('NEW-250', nooken, district),
    ('NEW-251', 'org-burgondu-dostuk-aiyl-okmotu-79bc4da', 'ayyl_area:Бүргөндү-Достук'),
    ('NEW-252', 'org-kochkor-ata-shaarynyn-meriyasy-2cc10ef', 'city:Кочкор-Ата'),
    ('NEW-253', 'org-mombekov-aiyl-okmotu-d36a51d', 'ayyl_area:Момбеков'),
    ('NEW-254', None, 'ayyl_area:Д.Садырбаев'),
    ('NEW-255', 'org-shamalduu-sai-shaardyk-meriya-9de9534', 'city:Шамалдуу-Сай'),
]
form_org = {}
for sid, existing, tid in form_specs:
    name = cell(sid, 5, 2)
    oid = organization(name, sid, 'table:5:row:2', tid, 'ru', existing)
    form_org[sid] = oid
    raw_permission = cell(sid, 5, 13).strip().lower()
    if raw_permission == 'да':permission = 'PUBLIC'
    elif raw_permission == 'нет':permission = 'INTERNAL_ONLY'
    else:permission = 'AMBIGUOUS'
    DECISIONS.append({'source_id': sid, 'organization_id': oid,
                      'raw_permission': cell(sid, 5, 13), 'decision': permission,
                      'locator': 'table:5:row:13',
                      'reason': 'mixed/partial/template answer requires clarification' if permission == 'AMBIGUOUS' else 'explicit source permission'})
    vis = 'PUBLIC' if permission == 'PUBLIC' else 'INTERNAL_ONLY'
    status = 'SOURCE_CONFIRMED' if permission != 'AMBIGUOUS' else 'AMBIGUOUS'
    # The organization and its territory remain indexed even when the answer
    # sheet explicitly refuses citizen-facing publication of contact details.
    ctext = cell(sid, 5, 4)
    if ctext and 'все вопросы' not in ctext.lower():
        competence(oid, ctext, sid, 'table:5:row:4', tid, 'local_government')
    raw_phones = cell(sid, 5, 5)
    landlines = re.findall(r'(?:0\s*\(37\d{2}\)|\(?0?37\d{2}\)?)[\s-]*(?:\d[\s-]*){5}', raw_phones)
    plain_numbers = re.findall(r'(?<!\d)0\d{9}(?!\d)', raw_phones)
    for number in landlines + plain_numbers:
        number = number.strip()
        if len(digits(number)) >= 9:
            contact(oid, 'phone', number, sid, 'table:5:row:5', tid, vis, status,
                    reason='publication permission: ' + cell(sid, 5, 13))
    if sid == 'NEW-250':
        for number in re.findall(r'(?:0\s*\(37\d{2}\)|\(?0?37\d{2}\)?)[\s-]*(?:\d[\s-]*){5}', cell(sid, 5, 9)):
            contact(oid, 'phone', number, sid, 'table:5:row:9', tid,
                    'INTERNAL_ONLY', 'AMBIGUOUS', kind='reception_phone',
                    reason='partial publication permission in form')
    address = cell(sid, 5, 6)
    if address:
        # Catch the actual documented address collision before reusing v2.
        if sid == 'NEW-255':
            prior = [c for c in C if c['organization_id'] == oid and c['type'] == 'address'
                     and c.get('visibility') == 'PUBLIC']
            if prior:
                for old in prior:
                    old['visibility'] = 'INTERNAL_ONLY'; old['status'] = 'CONFLICT'
                    old['pilot_status'] = 'CONFLICT'; old['publication_status'] = 'CONFLICT'
                status_address = 'CONFLICT'; visibility_address = 'INTERNAL_ONLY'
                CONFLICT.append({'conflict_id': 'V3-CONFLICT-SHAMALDUU-ADDRESS',
                                 'entity': org_by_id[oid].get('name_ky') or name,
                                 'organization_id': oid, 'field': 'reception_address',
                                 'values': [prior[0]['value'], address],
                                 'source_ids': list(dict.fromkeys(prior[0]['source_ids'] + [sid])),
                                 'status': 'CONFLICT', 'resolution': 'NO_WINNER', 'visibility': 'INTERNAL_ONLY'})
            else:status_address, visibility_address = status, vis
        else:status_address, visibility_address = status, vis
        contact(oid, 'address', address, sid, 'table:5:row:6', tid,
                visibility_address, status_address, kind='reception_address',
                reason='publication permission: ' + cell(sid, 5, 13))
    hours = cell(sid, 5, 7)
    if hours:contact(oid, 'working_hours', hours, sid, 'table:5:row:7', tid,
                     vis, status, equivalent=sid in ('NEW-252', 'NEW-253', 'NEW-255'))
    reception = cell(sid, 5, 8)
    if reception:contact(oid, 'reception_hours', reception, sid, 'table:5:row:8', tid, vis, status)
    intake = cell(sid, 5, 9)
    if intake:
        procedure(oid, 'Подача обращения', [intake], sid, 'table:5:row:9', tid,
                  required=[cell(sid, 5, 10)] if cell(sid, 5, 10) else [],
                  visibility='PUBLIC' if permission == 'PUBLIC' else 'INTERNAL_ONLY')
        chunk(oid, 'procedure', f'{name}. Подача обращения: {intake}', sid,
              'table:5:row:9', tid, public=permission == 'PUBLIC', language='ru')
    coverage = cell(sid, 5, 11)
    # Some respondents entered their office street instead of a service zone.
    if coverage and re.search(r'\d', coverage) and ',' not in coverage:
        REVIEW.append({'source_id': sid, 'locator': 'table:5:row:11',
                       'decision': 'OFFICE_ADDRESS_NOT_SERVICE_ZONE', 'value': coverage})
    elif coverage and not ('ул.' in coverage.lower() and ',' not in coverage):
        for piece in re.split(r',\s*', coverage):
            piece = piece.strip(' .')
            if len(piece) < 3 or 'район' in piece.lower() and sid == 'NEW-250':continue
            if piece.startswith('(') or 'без статуса' in piece:
                REVIEW.append({'source_id': sid, 'locator': 'table:5:row:11',
                               'decision': 'AMBIGUOUS_SERVICE_ZONE', 'value': piece})
                continue
            village = re.sub(r'^(?:с\.|айылы\s*)', '', piece, flags=re.I).strip()
            if village in ('Шамалды-Сай', 'Кочкор-Ата граница'):
                REVIEW.append({'source_id': sid, 'locator': 'table:5:row:11',
                               'decision': 'AMBIGUOUS_SERVICE_ZONE', 'value': village})
                continue
            vtid = 'village:' + village
            territory(vtid, sid, 'table:5:row:11', name_ru=village, parent=tid)
            zone(oid, vtid, sid, 'table:5:row:11', piece,
                 'SOURCE_CONFIRMED' if permission == 'PUBLIC' else 'INTERNAL_ONLY')
    # A separate explicit publication refusal also restricts previously public
    # contacts for that same organization until the discrepancy is resolved.
    if permission == 'INTERNAL_ONLY':
        for c in C:
            if c['organization_id'] == oid and c['visibility'] == 'PUBLIC':
                c['visibility'] = 'INTERNAL_ONLY'; c['publication_status'] = 'INTERNAL_ONLY'
        CONFLICT.append({'conflict_id': 'V3-CONFLICT-MOMBEKOV-PUBLICATION',
                         'entity': name, 'organization_id': oid, 'field': 'publication_permission',
                         'values': ['v2 public facts', 'new form: Нет'],
                         'source_ids': list(dict.fromkeys(org_by_id[oid]['source_ids'] + [sid])),
                         'status': 'CONFLICT', 'resolution': 'WITHHOLD_PENDING_CLARIFICATION',
                         'visibility': 'INTERNAL_ONLY'})

# Filled practical sector responses in the Aliyev, Burgondu and Mombekov forms.
for sid in ('NEW-249', 'NEW-251', 'NEW-253'):
    oid = form_org[sid]
    tid = next(t for s, _, t in form_specs if s == sid)
    for ri, topic in [(2, 'WATER_SERVICE'), (3, 'ROAD'), (4, 'STREET_LIGHT'),
                      (5, 'WASTE'), (6, 'SEWER'), (7, 'LAND'), (8, 'EDUCATION'),
                      (9, 'HEALTH'), (10, 'SOCIAL_SUPPORT'), (11, 'TAX')]:
        text = cell(sid, 4, ri)
        if not text:continue
        # Template-only rows contain a question without a filled response.
        template = 'Название оператора' in text or 'Какая служба отвечает' in text or \
                   'Кто обслуживает' in text or 'Оператор вывоза' in text or \
                   'Кто отвечает за открытые' in text or 'Какая организация отвечает' in text
        if template and sid != 'NEW-253' and topic not in ('LAND', 'EDUCATION', 'HEALTH'):
            continue
        if sid == 'NEW-253' and topic == 'SEWER':continue
        if sid == 'NEW-253' and topic == 'TAX':continue
        if sid in ('NEW-249', 'NEW-251') and topic == 'SOCIAL_SUPPORT':continue
        if sid in ('NEW-249', 'NEW-251') and topic == 'EDUCATION' and 'Мектеп гов' in text:
            REVIEW.append({'source_id': sid, 'locator': f'table:4:row:{ri}',
                           'decision': 'AMBIGUOUS', 'value': text})
            continue
        # No specific organisation can be inferred merely from a free-text
        # answer. Preserve the source wording and require an operator.
        rid = route(topic, cell(sid, 4, ri, 0), tid, sid, f'table:4:row:{ri}', [],
                    'NEEDS_OPERATOR', public=False, notes=text)
        if sid == 'NEW-253':
            for number in re.findall(r'(?<!\d)0[2579]\d{8}(?!\d)', text):
                staff(oid, None, f'{cell(sid, 4, ri, 0)}: жооптуу кызматкер', number,
                      'sector_operator', sid, f'table:4:row:{ri}', tid,
                      note='named sector/zone contact; publication explicitly refused')
        elif sid in ('NEW-249', 'NEW-251'):
            for number in re.findall(r'\+996\s*\d[\d\s]{8,}', text):
                staff(oid, None, f'{cell(sid, 4, ri, 0)}: жооптуу кызматкер', number.strip(),
                      'sector_operator', sid, f'table:4:row:{ri}', tid,
                      note='staff mobile; form publication permission ambiguous')
    if sid == 'NEW-253':
        procedure(oid, 'Подача заявки на приём ребёнка в школу',
                  ['Через Түндүк; остальные условия и документы источником не указаны'],
                  sid, 'table:4:row:8', tid, visibility='INTERNAL_ONLY')

# The partly filled Chatkal form has two explicit emergency/reception numbers
# and territory-qualified road/lighting suggestions. Its blank answer table is
# not an organization record.
chatkal_orgs = {}
for name, tid, number, kind in [
    ('Каныш-Кыя айыл өкмөтү', 'ayyl_area:Каныш-Кыя', '(03749)6-03-32', 'emergency_phone'),
    ('Каныш-Кыя айыл өкмөтү', 'ayyl_area:Каныш-Кыя', '(03749) 3-00-13', 'reception_phone'),
    ('Терек-Сай айыл өкмөтү', 'ayyl_area:Терек-Сай', '(3749) 6-01-97', 'emergency_and_reception_phone')]:
    existing = 'v2-org-4658501bbe27' if 'Терек-Сай' in name else None
    oid = organization(name, 'NEW-257', 'table:4:row:2', tid, 'ky', existing)
    chatkal_orgs[tid] = oid
    contact(oid, 'phone', number, 'NEW-257', 'table:4:row:2', tid,
            'PUBLIC', 'SOURCE_CONFIRMED', kind=kind)
    zone(oid, tid, 'NEW-257', 'table:4:row:2', name)
for tid in ('ayyl_area:Каныш-Кыя', 'ayyl_area:Терек-Сай'):
    oid = chatkal_orgs[tid]
    route('WATER_SERVICE', 'Вода / канализация', tid, 'NEW-257', 'table:4:row:2',
          [oid], 'SINGLE', notes='Авариялык жана кабылдама байланыштары ушул аймакка гана тиешелүү',
          labels=[org_by_id[oid].get('name_ru') or org_by_id[oid].get('name_ky')])
    chunk(oid, 'routing',
          f'{tid}: суу/канализация боюнча булакта ушул айыл өкмөтүнүн байланыштары көрсөтүлгөн. Багыттоо сунушу гана.',
          'NEW-257', 'table:4:row:2', tid, language='mixed')
    route('ROAD', 'Дороги', tid, 'NEW-257', 'table:4:row:3', [],
          'MULTI_AGENCY', notes=cell('NEW-257', 4, 3))
    route('STREET_LIGHT', 'Уличное освещение', tid, 'NEW-257', 'table:4:row:4', [],
          'NEEDS_OPERATOR', notes=cell('NEW-257', 4, 4))

# Topic aliases are taxonomy hints, never routing facts by themselves.
for canonical, forms in {
    'WASTE': [('ru', 'мусор'), ('ru', 'вывоз мусора'), ('ky', 'таштанды')],
    'ROAD': [('ru', 'дорога'), ('ru', 'яма на дороге'), ('ky', 'жол')],
    'MANHOLE': [('ru', 'открытый люк'), ('ky', 'ачык люк'), ('mixed', 'люк')],
    'NO_WATER': [('ru', 'нет воды'), ('ky', 'суу жок')],
    'ELECTRICITY': [('ru', 'электричество'), ('ru', 'свет'), ('ky', 'электр энергиясы')],
}.items():
    for lang, alias in forms:
        TOPIC_ALIASES.append({'topic_alias_id': id_for('v3-topic-alias-', canonical, lang, alias),
                              'canonical_topic': canonical, 'language': lang, 'alias': alias,
                              'source_ids': ['SRC-183'], 'provenance': [provenance('SRC-183', 'table:2:row:2-19')],
                              'effect': 'LEXICAL_ONLY'})

# Prevent the old disputed Shamalduu address from appearing in inherited RAG.
shamal = form_org['NEW-255']
mombekov = form_org['NEW-253']
for row in G:
    if shamal in row.get('organization_ids', []) and 'Ленина' in row.get('text', '') and ('28' in row['text'] or '27' in row['text']):
        row['visibility'] = 'INTERNAL_ONLY';row['publication_status'] = 'CONFLICT';row['pilot_status'] = 'CONFLICT'
    if mombekov in row.get('organization_ids', []):
        row['visibility'] = 'INTERNAL_ONLY';row['publication_status'] = 'INTERNAL_ONLY'
for name in ('qa_pairs_ru', 'qa_pairs_ky'):
    for row in data[name]:
        if mombekov in row.get('organization_ids', []):
            row['visibility'] = 'INTERNAL_ONLY';row['publication_status'] = 'INTERNAL_ONLY'

# Public contact chunks are compact and source-labelled. The full corpus keeps
# internal staff numbers outside RAG so the legacy parser cannot expose them.
new_source_ids = {sid for sid, _ in batch if not source_by_id[sid]['duplicate_of']}
for c in C:
    if c['visibility'] != 'PUBLIC' or c.get('status') != 'SOURCE_CONFIRMED':continue
    recent = next((p for p in c.get('provenance', []) if p['source_id'] in new_source_ids), None)
    if not recent:continue
    sid = recent['source_id'];tid = c.get('territory_id')
    name = org_by_id[c['organization_id']].get('name_ru') or org_by_id[c['organization_id']].get('name_ky')
    chunk(c['organization_id'], 'contact', f'{name}. {c["type"]}: {c["value"]}',
          sid, recent.get('locator', 'table:5'), tid)

data['sources'] = S;data['organizations'] = O;data['contacts'] = C
data['competences'] = K;data['routing_rules'] = R;data['rag_chunks'] = G
data['territories'] = T;data['aliases'] = A;data['procedures'] = P
data['services'] = SERV;data['conflicts'] = CONFLICT
data['public_contacts'] = [c for c in C if c['visibility'] == 'PUBLIC' and c.get('status') == 'SOURCE_CONFIRMED']
data['hours'] = [c for c in C if c['type'] in ('working_hours', 'reception_hours')]
data.update({'staff_roles': STAFF, 'real_query_examples': QUERIES,
             'escalation_rules': ESC, 'service_territories': ZONES,
             'topic_aliases': TOPIC_ALIASES, 'appeal_categories': CATEGORIES})
for name, rows in data.items():write(M / f'{name}.jsonl', rows)
write(REV / 'publication_decisions.jsonl', DECISIONS)

metric_names = ('sources', 'organizations', 'contacts', 'staff_roles', 'territories',
                'competences', 'services', 'procedures', 'routing_rules', 'rag_chunks',
                'real_query_examples', 'escalation_rules', 'service_territories', 'conflicts')
before = {key: len(read(V2 / 'machine' / f'{key}.jsonl')) if (V2 / 'machine' / f'{key}.jsonl').exists() else 0
          for key in metric_names}
after = {key: len(data[key]) for key in metric_names}
before['public_contacts'] = len(read(V2 / 'machine' / 'public_contacts.jsonl'))
after['public_contacts'] = len(data['public_contacts'])
before['internal_contacts'] = before['contacts'] - before['public_contacts']
after['internal_contacts'] = after['contacts'] - after['public_contacts']
metrics = {'before': before, 'after': after,
           'contacts_by_status': dict(Counter(c.get('status', 'SOURCE_CONFIRMED') for c in C)),
           'contacts_by_visibility': dict(Counter(c.get('visibility') for c in C)),
           'source_decisions': dict(Counter(r['decision'] for r in REVIEW)),
           'new_facts_by_source': {sid: dict(Counter(name for name in
                ('organizations', 'contacts', 'competences', 'procedures', 'routing_rules',
                 'rag_chunks', 'staff_roles', 'real_query_examples', 'service_territories')
                for row in data[name] if sid in row.get('source_ids', []) and
                (str(row.get({'organizations':'organization_id','contacts':'contact_id','competences':'competence_id',
                              'procedures':'procedure_id','routing_rules':'routing_rule_id','rag_chunks':'chunk_id',
                              'staff_roles':'staff_role_id','real_query_examples':'example_id',
                              'service_territories':'relation_id'}[name], '')).startswith('v3-')
                 or name in ('staff_roles', 'real_query_examples', 'service_territories'))))
                for sid in ['SRC-183'] + [sid for sid, _ in batch]}}
(V3 / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(metrics, ensure_ascii=False))
