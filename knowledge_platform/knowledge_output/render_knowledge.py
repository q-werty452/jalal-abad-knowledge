"""Render reviewable human knowledge files from machine records."""
import json
from collections import Counter
from pathlib import Path

O=Path(__file__).resolve().parent
def read(name): return [json.loads(s) for s in (O/'machine'/name).read_text(encoding='utf-8').splitlines()]
def save(name,body): (O/name).write_text(body.rstrip()+"\n",encoding='utf-8')
def esc(v): return str(v if v is not None else 'UNKNOWN').replace('|','\\|').replace('\n',' ')
def sid(a): return ', '.join(a.get('source_ids',[])) or 'UNKNOWN'
def label(o): return o['name_ky'] or o['name_ru'] or 'UNKNOWN'
src=read('sources.jsonl'); org=read('organizations.jsonl'); comp=read('competences.jsonl'); ct=read('contacts.jsonl'); rt=read('routing_rules.jsonl'); ru=read('qa_pairs_ru.jsonl'); ky=read('qa_pairs_ky.jsonl'); rag=read('rag_chunks.jsonl'); al=read('aliases.jsonl')
state=json.loads((O/'.canonical_state.json').read_text(encoding='utf-8')); counts=state['counts']
byorg={o['organization_id']:o for o in org}

# Refresh inventory after extraction while retaining the first-artifact source list and stable IDs.
x=['# Source inventory','',f'Записей источников: **{len(src)}**. Текст извлечён из {counts["processed"]}; точных байтовых дублей {counts["duplicates"]}; BLOCKED {counts["blocked"]}. ZIP считается контейнером, каждый внутренний документ имеет собственный ID.','',
   'Статус `processed` означает техническое извлечение текста, а не подтверждение актуальности или права на публикацию. Язык и тема на этапе индексации были предположены по имени и уточняются по тексту.','',
   '| ID | File | Type | Size B | Language guess | Topic | Priority | Duplicate of | Status | Normalization |','|---|---|---|---:|---|---|---|---|---|---|']
for s in src:x.append(f'| {s["source_id"]} | {esc(s["source_file"])} | {s["file_type"]} | {s["size"]} | {s["language_guess"]} | {", ".join(s["topic"])} | {s["priority"]} | {s["duplicate_of"] or "—"} | {s["status"]} | {s.get("normalization_status","UNKNOWN")} |')
x+=['','## ZIP structure and duplicates','', 'The `archive::entry` paths above are the logical ZIP structure. Byte-identical entries are marked `duplicate_of` using SHA-256. Similar titles and different-format versions were kept separate.','',
    '## Excel sheets and row structure','']
for s in src:
    if s['file_type']=='xlsx':
        x.append(f'### {s["source_id"]} {s["file_name"]}')
        for sh in s.get('sheet_structure',[]):
            header=' / '.join(v for row in sh.get('first_nonempty_rows',[])[:1] for v in row['values'] if v)
            x.append(f'- `{sh["sheet"]}`: {sh["rows"] or "UNKNOWN"} rows, {sh["columns"] or "UNKNOWN"} columns. First populated row: {esc(header[:220])}.')
        x.append('')
x+=['## BLOCKED source files','']
for s in src:
    if s['status']=='blocked':x.append(f'- {s["source_id"]} {s["source_file"]}: {s["extraction_error"]}.')
x+=['','## Thematic batches','']
for topic in sorted(set(t for s in src for t in s['topic'])):
    ss=[s['source_id'] for s in src if topic in s['topic'] and s['status']=='processed']
    x.append(f'- {topic}: '+', '.join(ss))
save('00_SOURCE_INVENTORY.md','\n'.join(x))

x=['# Source of truth map','','Приоритет применён к конфликтам как ориентир. Ни один вариант не подставляется молча вместо другого.','',
   '| Домен | Основные источники | Сила источника | Использование |','|---|---|---|---|',
   '| Архитектура AIG2C | SRC-001 | PROJECT_DECISION / PLANNED; текущий код отдельно не проверялся | Граница ответственности AI и Django |',
   '| Список учреждений и функции | SRC-225, SRC-112, SRC-002; формы SRC-123, SRC-135, SRC-142, SRC-147, SRC-158, SRC-164, SRC-171–195, SRC-214, SRC-218, SRC-222, SRC-226 | SOURCE_FACT в предоставленных таблицах; утверждение и актуальность NEEDS_CONFIRMATION | Канонические организации и компетенции, без автоматической публикации |',
   '| Прямые соответствия обращение → ответственный | SRC-109, SRC-135, SRC-142, SRC-165 | Прямое утверждение в ведомственной таблице/анкете; production NEEDS_CONFIRMATION | Проверяемые source-backed routing facts |',
   '| Нормативные положения | SRC-007–108, SRC-110, SRC-113, SRC-201, SRC-223, SRC-224, SRC-230 | Часть документов содержит реквизиты; действующую редакцию надо сверить | Обоснование функций; не автоматические SLA |',
   '| Контакты | SRC-225, SRC-112, SRC-124, SRC-135, SRC-142, SRC-145, SRC-147, SRC-158, SRC-159, SRC-165, SRC-189, SRC-203, SRC-217 | SOURCE_FACT; публичность NEEDS_REVIEW | Адреса и общие линии только для внутренней проверки |',
   '| Предыдущий аудит | SRC-006 | Вторичный проектный анализ | Навигация и кандидаты конфликтов; оригиналы имеют приоритет |',
   '| Категории/статусы/SLA в Django | В этой папке экспорт актуального backend не обнаружен | UNKNOWN | Запросить выгрузку владельца системы |','',
   '## Правило выбора','',
   'Актуальный официальный акт с реквизитами → официальный документ организации → утверждённый ведомственный реестр → письмо/анкета → проектный анализ. При отсутствии доказанной актуальности значение остаётся `NEEDS_CONFIRMATION`.']
save('01_SOURCE_OF_TRUTH_MAP.md','\n'.join(x))

x=['# Current knowledge status','',
   f'Корпус содержит {counts["processed"]} текстово обработанных источников из {counts["sources"]} записей, {counts["duplicates"]} точных дубля и {counts["blocked"]} заблокированных файлов. Сведения пригодны для внутреннего поиска с provenance; публикация и автоматическая маршрутизация требуют утверждения.','',
   '## Статусы утверждений','',
   '- `SOURCE_FACT`: значение прямо присутствует в указанном файле. Это не подтверждает его действительность на сегодня.','- `DERIVED`: связь выведена для подготовки правила и не является официальным назначением.','- `PROJECT_DECISION`: правило проекта из SRC-001.','- `IMPLEMENTED`: в этой задаче код не проверялся; утверждения SRC-001 о реализации остаются проектным сообщением.','- `PLANNED`: Qwen, BGE-M3, pgvector и RAG интеграция описаны как будущие этапы.','- `UNKNOWN`: значение отсутствует.','- `CONFLICT`: расхождение сохранено в 13_CONFLICTS.md.','',
   '## Архитектурный контекст из SRC-001','',
   'Django остаётся владельцем обращений, назначений, статусов, SLA, аудита и официального ответа. AI может предлагать анализ и позже извлекать ответы из RAG, но не выполняет официальное действие сам. Это описание решения проекта; фактический код и текущий справочник категорий здесь не проверялись.','',
   '## Полнота','',f'- Организаций: {len(org)}; компетенций: {len(comp)}; контактов: {len(ct)} (адреса и общие линии).',f'- Внутриведомственных/прямых routing facts: {counts["routing_verified"]}; proposed: {counts["routing_proposed"]}.',
   f'- FAQ RU: {len(ru)}; KY: {len(ky)}; RAG chunks: {len(rag)}.','- RU/KY переводы отсутствуют для большинства организаций; поля оставлены `null`.','- Адреса и FAQ помечены `NEEDS_REVIEW` до разрешения публикации.']
save('02_CURRENT_KNOWLEDGE_STATUS.md','\n'.join(x))

x=['# Organizations','','`name_ru` и `name_ky` разделены. Совпадение по похожему названию не считалось доказательством тождественности. Территория обслуживания не выводилась из почтового адреса.','',
   '| ID | Name RU | Name KY | Type | Parent ID | Territory | Sources | Status |','|---|---|---|---|---|---|---|---|']
for o in org:x.append(f'| {o["organization_id"]} | {esc(o["name_ru"])} | {esc(o["name_ky"])} | {o["organization_type"]} | {o["parent_organization_id"] or "UNKNOWN"} | {", ".join(o["territory"]) or "UNKNOWN"} | {sid(o)} | {o["verification_status"]} |')
x+=['','Официальный статус деятельности, подчинённость и актуальность названия требуют сверки с ведомствами, кроме двух прямо названных связей, перечисленных в 04_DEPARTMENTS_AND_SUBORDINATION.md.']
save('03_ORGANIZATIONS.md','\n'.join(x))

x=['# Departments and subordination','','Подчинённость зафиксирована только при прямом указании связи в названии/тексте источника. Упоминание министерства не превращалось автоматически в полный организационный граф.','',
   '| Child | Parent | Source | Status |','|---|---|---|---|']
for o in org:
    if o['parent_organization_id']:
        p=byorg[o['parent_organization_id']]
        x.append(f'| {esc(label(o))} | {esc(label(p))} | {sid(o)} | SOURCE_FACT |')
x+=['','## Отдельно названные подразделения Госстраха','',
   'SRC-109, лист `Маршрутизация`: чекене сектор, корпоративдик сектор, авариялык комиссарлар, улук бухгалтер, директордун орун басары и директор филиала. Эти названия сохранены в маршрутах как текст подразделений. Отдельные department IDs отсутствуют; юридическая подчинённость и состав пользователей должны быть утверждены.','',
   '## Неустановленные связи','',
   f'Для {sum(not o["parent_organization_id"] for o in org)} записей parent organization не установлен. Для филиалов и региональных подразделений требуется официальный реестр структуры.']
save('04_DEPARTMENTS_AND_SUBORDINATION.md','\n'.join(x))

x=['# Competences and responsibilities','','Каждая запись опирается на конкретную строку/абзац. `routing_verification_status=needs_confirmation` означает, что функция ещё не равна производственному правилу назначения. Отсутствующие исключения, границы зоны и правовое основание обозначены как UNKNOWN.','']
for c in comp:
    o=byorg[c['organization_id']]; d=c['description_ky'] or c['description_ru']
    x += [f'## {c["competence_id"]} — {label(o)}','',f'- Описание ({"KY" if c["description_ky"] else "RU"}): {d}',f'- Обращения из источника: {"; ".join(c["include_examples"]) or "UNKNOWN"}',
          '- Исключения: UNKNOWN; территория обслуживания: UNKNOWN; нормативное основание: UNKNOWN.',f'- Дополнительные данные от гражданина: {", ".join(c["required_citizen_information"]) or "NEEDS_CONFIRMATION"}.',
          f'- Provenance: {sid(c)}; {c["provenance"][0].get("locator") or c["provenance"][0].get("sheet")}; SOURCE_FACT.','']
save('05_COMPETENCES_AND_RESPONSIBILITIES.md','\n'.join(x))

topics=[('water_supply','суу, водо, water'),('sewerage','саркынды, канализац'),('roads','жол, дорог, асфальт'),('street_lighting','жарык, освещен'),('waste','таштанды, мусор'),('public_transport','транспорт, ташуу'),('education','билим, образован'),('healthcare','саламат, медицин'),('social_support','социал, пенси'),('housing','турак, жилищ'),('land','жер, земель'),('construction','курулуш, строитель'),('culture','маданият, театр'),('emergency','өзгөчө кырдаал, чрезвычайн')]
x=['# Services and citizen questions','','Ниже — тематический индекс кандидатов, а не утверждённые коды Django. Примеры обращений в `competences.jsonl` остаются в языке источника.','',
   '| Candidate topic | Evidence in corpus | Category mapping |','|---|---|---|']
for topic,terms in topics:
    hits=[]
    for c in comp:
        text=(c['description_ru'] or c['description_ky'] or '').lower()+' '.join(c['include_examples']).lower()
        if any(t.strip() in text for t in terms.split(',')):hits.append(c['competence_id'])
    x.append(f'| `{topic}` | {", ".join(hits[:8]) or "UNKNOWN"}{" …" if len(hits)>8 else ""} | proposed |')
x+=['','Тема `other` означает необходимость ручного уточнения. Матрица категорий должна сверяться с актуальным Django-справочником.']
save('06_SERVICES_AND_CITIZEN_QUESTIONS.md','\n'.join(x))

x=['# Contacts and addresses','','В машинный реестр включены адреса и две линии, прямо обозначенные как общие. Публичность каждого контакта — `NEEDS_REVIEW`. Персональные мобильные номера и справочник сотрудников не перенесены.','',
   '| ID | Organization | Type | Value | Source and locator | Verification | Publication |','|---|---|---|---|---|---|---|']
for c in ct:
    p=c['provenance'][0];loc=p.get('locator') or f'{p.get("sheet")} row {p.get("row")}'
    x.append(f'| {c["contact_id"]} | {esc(label(byorg[c["organization_id"]]))} | {c["type"]} | {esc(c["value"])} | {sid(c)} {loc} | {c["verification_status"]} | {c["publication_status"]} |')
x+=['','Общие телефоны из SRC-124 и SRC-109 остаются только во внутреннем реестре с `publication_status=NEEDS_REVIEW`; остальные номера сотрудников не перенесены.']
save('07_CONTACTS_AND_ADDRESSES.md','\n'.join(x))

x=['# Routing knowledge','','`verified` здесь значит: соответствие прямо записано в конкретном источнике. Это **не** разрешение на автоматическое назначение в Django. У всех правил `production_status=NEEDS_CONFIRMATION`.','',
   '## Direct source statements','',
   '| Rule | Issue | Target | Department | Source |','|---|---|---|---|---|']
for r in rt:
    if r['verification_status']=='verified':
        x.append(f'| {r["routing_rule_id"]} | {esc(r["topic"])} | {esc(label(byorg[r["target_organization_id"]]))} | {esc(r.get("target_department_name_ky"))} | {sid(r)} |')
x+=['','## Proposed mappings from the unsigned chatbot compilation','',
    'Эти записи показывают организацию рядом с типом обращения в SRC-225. Для назначения нужны границы территории, исключения, актуальный справочник Django и письменное утверждение.','',
    '| Rule | Issue | Candidate target | Source |','|---|---|---|---|']
for r in rt:
    if r['verification_status']=='proposed':x.append(f'| {r["routing_rule_id"]} | {esc(r["topic"])} | {esc(label(byorg[r["target_organization_id"]]))} | {sid(r)} |')
save('08_ROUTING_KNOWLEDGE.md','\n'.join(x))

legal=[s for s in src if s['status']=='processed' and (s['authority_level'] in ('official_law','official_order_attachment','official_organization_provision','official_candidate') or s['source_id'] in ('SRC-113','SRC-201','SRC-223','SRC-224','SRC-230'))]
x=['# Legal and regulatory basis','','Каталог содержит указатели на документы, а не юридическое заключение. Номер/дата/орган приведены лишь там, где они установлены по исходному тексту. Наличие положения в папке не доказывает действующую редакцию.','',
   '| Source | Document title | Number | Date | Issuer | Subject / use | Status |','|---|---|---|---|---|---|---|']
for s in legal:
    excerpts=[c['text'] for c in rag if c['document_id']==s['source_id'] and 'provision' in c['tags']]
    subject=excerpts[0][:180]+'…' if excerpts and len(excerpts[0])>180 else excerpts[0] if excerpts else 'Тема требует ручной правовой разметки.'
    x.append(f'| {s["source_id"]} | {esc(s["document_title"])} | {esc(s["document_number"])} | {esc(s["document_date"])} | {esc(s["issuer"])} | {esc(subject)} | {s["authority_level"]} |')
x+=['','Статьи и пункты, которые должны управлять SLA или маршрутом, не назначались автоматически. Нужен отдельный юридически утверждённый реестр действующих редакций.']
save('09_LEGAL_AND_REGULATORY_BASIS.md','\n'.join(x))

for fn,lang,rows in [('10_FAQ_RU.md','RU',ru),('11_FAQ_KY.md','KY',ky)]:
    x=[f'# FAQ {lang}','','Пары основаны на прямых сведениях источника. Перед показом гражданам требуется проверка публикации и актуальности.','']
    for q in rows:x += [f'## {q["question"]}','','**Ответ:** '+q['answer'],'',f'Источник: {sid(q)}; статус факта: {q["verification_status"]}; публикация: {q["publication_status"]}.','']
    save(fn,'\n'.join(x))

x=['# Terms and aliases','','Переводы официальных названий не конструировались. `translation_status=verified` есть только там, где источник прямо даёт оба языка.','',
   '| Organization | Language | Alias | Source |','|---|---|---|---|']
for a in al:x.append(f'| {esc(label(byorg[a["organization_id"]]))} | {a["language"]} | {esc(a["alias"])} | {sid(a)} |')
x+=['','## Controlled terms','',
    '- `SOURCE_FACT`: прямой текст документа; проверка актуальности отдельна.','- `DERIVED`: безопасный вывод или кандидат связи.','- `PROJECT_DECISION`: принято в описании проекта.','- `PLANNED`: указано как будущая функция.','- `UNKNOWN`: в источниках нет проверяемого значения.','- `CONFLICT`: расходящиеся значения без выбранного победителя.','- `verified` в routing: прямое соответствие в источнике.','- `proposed` в routing: предложенная связь, не утверждена.','- `needs_confirmation`: требуется ведомственное подтверждение.']
save('12_TERMS_AND_ALIASES.md','\n'.join(x))

x=['# Conflicts','','Сохранены обе версии, без молчаливого выбора. Орфографические варианты адреса оставлены как отдельный случай для проверки тождественности.','']
for c in state['conflicts']:
    a=c['source_a'];b=c['source_b']
    x += [f'## {c["conflict_id"]} — {c["entity"]}','','- Поле: '+c['field'],f'- Source A: {a["source_id"]} ({a.get("locator") or a.get("sheet")}) → {c["value_a"]}',
          f'- Source B: {b["source_id"]} ({b.get("locator") or b.get("sheet")}) → {c["value_b"]}',f'- Preferred value: {c["preferred_value"]}',f'- Action: {c["action"]}','']
x+=['## Duplicate rows and copies','','SRC-225 table rows 20 and 25 repeat the same road office with the same address and function. This is a source-row duplicate, not a separate organization. Exact file duplicates are recorded in inventory and `sources.jsonl`.']
save('13_CONFLICTS.md','\n'.join(x))

x=['# Knowledge gaps','','Каждый пункт нужен до публикации либо производственной маршрутизации.','']
for gid,missing,risk,owner,fmt in state['gaps']:
    x += [f'## {gid} — {missing}','','- Зачем нужно / риск: '+risk,'- Запросить у: '+owner,'- Желаемый формат: '+fmt,'']
x+=['## Proposed routing requiring approval','','Следующие правила пока имеют `verification_status=proposed`: '+', '.join(r['routing_rule_id'] for r in rt if r['verification_status']=='proposed')+'.','',
    '## Blocked documents','','Требуют OCR, конвертации или визуального извлечения: '+', '.join(s['source_id'] for s in src if s['status']=='blocked')+'.']
save('14_KNOWLEDGE_GAPS.md','\n'.join(x))

x=['# RAG preparation','',f'Подготовлено **{len(rag)}** самодостаточных фрагментов в `machine/rag_chunks.jsonl` для будущей индексации BGE-M3 + pgvector. Embeddings не создавались.','',
   '## Schema and provenance','','Каждый chunk содержит `chunk_id`, `document_id`, `organization_ids`, `topic`, `language`, `title`, `text`, `source_file`, страницу или лист/строку при наличии, дату документа, `verification_status`, `publication_status` и provenance. Повторы одинакового текста свернуты.','',
   '## Indexing gate','','Технический RAG-индекс может использовать этот файл только во внутреннем контуре с показом source_id и проверкой ответа человеком. Перед citizen-visible выдачей требуется подтвердить право публикации, актуальность документов, географию пилота, RU/KY переводы и конфликтные сведения.','',
   '## Exclusions','','Телефонные справочники сотрудников, персональные обращения и непроверенные сканы не превращены в публичные chunks. Содержимое `.extracted.jsonl` — только рабочий материал и не должно индексироваться или публиковаться.','',
   '## Future retrieval','','Рекомендуемые фильтры: language, topic, organization_ids, source authority, publication_status, date validity. Answer generation should cite `document_id` and avoid treating proposed routing as an official assignment.']
save('15_RAG_PREPARATION.md','\n'.join(x))

print('rendered 00-15')
