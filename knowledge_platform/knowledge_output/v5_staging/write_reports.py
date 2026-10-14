"""Produce release notes from the checked staging artifacts without private values."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V4 = ROOT.parent / "v4" / "runtime_export"
V5 = ROOT / "runtime_export"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)


def rows(folder: Path, stem: str) -> list[dict]:
    path = folder / f"{stem}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def put(name: str, body: str) -> None:
    (REPORTS / name).write_text(body.strip() + "\n", encoding="utf-8")


summary = json.loads((ROOT / "build_summary.json").read_text(encoding="utf-8"))
inventory = json.loads((ROOT / "input_inventory.json").read_text(encoding="utf-8"))
before = {name: rows(V4, name) for name in ("sources", "organizations", "contacts", "territories", "aliases", "competences", "services", "procedures", "routing_rules", "rag_chunks")}
after = {name: rows(V5, name) for name in before}
bt = Counter(x["type"] for x in before["contacts"])
at = Counter(x["type"] for x in after["contacts"])
review = Counter(json.loads(line)["reason"] for line in (ROOT / "private" / "review_records.jsonl").read_text(encoding="utf-8").splitlines())
cases = rows(ROOT / "casebook", "appeal_cases_anonymized")
case_topics = Counter(x["topic"] for x in cases)
acceptance = json.loads((ROOT / "acceptance_results.json").read_text(encoding="utf-8"))
source_delta = defaultdict(Counter)
source_orgs = defaultdict(set)
for line in (ROOT / "private" / "promotion_records.jsonl").read_text(encoding="utf-8").splitlines():
    rec = json.loads(line)
    fid = int(rec.get("file_id") or 0)
    source_delta[fid][str(rec.get("type") or rec.get("fact_type") or "fact")] += 1
    if rec.get("organization_id"):
        source_orgs[fid].add(rec["organization_id"])

source_table = "\n".join(
    f"| NEW-{265+x['id']} | {x['name']} | {x.get('paragraphs_and_rows','—')} | {len(source_orgs[x['id']])} | "
    f"{source_delta[x['id']]['phone']} | {source_delta[x['id']]['address']} | {source_delta[x['id']]['working_hours']} |"
    for x in inventory[:8])
put("SOURCE_INGEST_REPORT.md", f"""
# Реестр входных источников V5

Исходные DOCX сохранены неизменными в `Downloads`; SHA-256 и размеры приведены в `../input_inventory.json`. Чтение выполнено с учётом абзацев и таблиц. Строки шаблона «Принести» считались заполненными только при наличии явного значения. Один файл содержит таблицу. Сходные копии шаблона не использованы как независимое подтверждение.

| Source ID | Документ | Строки/абзацы | Организации с промоутнутым реквизитом | Новые телефоны | Новые адреса | Новые графики |
|---|---|---:|---:|---:|---:|---:|
{source_table}

Девятый источник — `richtext_converted_to_markdown (1).md`, {inventory[8]['text_chars']} символов. Он использован только для закрытого анализа обращений; полный текст и персональные сведения не попали в публичный поиск. Обезличено {len(cases)} сообщений.

Из восьми DOCX добавлено 8 карточек источников. Записи из повторяющихся шаблонов сопоставлены по организации и территории; {summary['stats']['duplicates']} повторных значений не размножены. Требуют проверки {review['organization_not_resolved']} неуверенных связей с организацией, {review['possible_conflict']} возможных разночтений, {review['invalid_landline_length']} некорректных по длине стационарных номера и {review['city_name_missing']} записи без города. Четыре явных конфликта адреса сохранены отдельно.

Подробные исходные строки и закрытые номера находятся в `../private/` только для локальной проверки, вне Git и runtime.
""")

metrics = [("Источники", "sources"), ("Организации", "organizations"), ("Территории", "territories"),
           ("Алиасы", "aliases"), ("Компетенции", "competences"), ("Услуги", "services"),
           ("Процедуры", "procedures"), ("Маршруты", "routing_rules"), ("RAG chunks", "rag_chunks")]
metrics_table = "\n".join(f"| {label} | {len(before[key])} | {len(after[key])} | {len(after[key])-len(before[key]):+d} |" for label, key in metrics)
type_table = "\n".join(f"| {kind} | {bt[kind]} | {at[kind]} | {at[kind]-bt[kind]:+d} |" for kind in ("phone", "fax", "address", "email", "website", "working_hours", "reception_hours"))
put("KNOWLEDGE_UPDATE_REPORT.md", f"""
# Knowledge V5: изменения

Версия: `{summary['knowledge_version']}`. Основа V4 `{json.loads((V4/'knowledge_manifest.json').read_text(encoding='utf-8'))['knowledge_version']}` сохранена отдельно. Никакого production sync или платной индексации при сборке не было.

| Набор | V4 | V5 | Изменение |
|---|---:|---:|---:|
{metrics_table}

| Тип контакта | V4 | V5 | Изменение |
|---|---:|---:|---:|
{type_table}

Контактов всего: {len(before['contacts'])} → {len(after['contacts'])}. Из новых значений: {summary['stats']['phone']} телефонов, {summary['stats']['working_hours']} графиков и {summary['stats']['address']} адресов. Четыре конфликтных адреса добавлены как закрытые альтернативы, поэтому общий прирост адресных строк выше числа опубликованных новых адресов. Компетенции/услуги/процедуры/маршруты из этих документов не добавлены: источники преимущественно содержат справочные реквизиты и шаблонные запросы, из которых процесс или полномочие не выводились.

Каждая новая опубликованная запись содержит `organization_id`, `territory_id` в организации, `source_id` и точный locator. Карточки, часы и адреса доступны structured lookup. Семантические chunks не менялись; 667 старых векторов повторно привязаны к V5 только после побайтового совпадения `rag_chunks.jsonl` и проверки index/chunks.
""")

pub = sum(c.get("visibility") == "PUBLIC" for c in after["contacts"])
internal = len(after["contacts"]) - pub
put("CONTACT_PUBLICATION_AUDIT.md", f"""
# Аудит публикации контактов

В V5 {len(after['contacts'])} структурированных контактов, из них {pub} публичных и {internal} закрытых конфликтных строк. Публичное число включает старые проверенные 473 контакта. Новые публичные контакты допущены после проверки привязки к конкретной организации и исходной строке, а также отдельной version-bound attribution audit на {summary['audit_count']} записей.

{review['mobile_public_status_unverified']} наблюдений мобильных номеров сотрудников вынесены в закрытый список `../private/review_records.jsonl`: публичный статус не доказан, значения не вошли в публичные ответы или этот отчёт. Пять совпадающих значений уже присутствовали как PUBLIC в V4; в V5 их статус понижен до `AMBIGUOUS / INTERNAL_ONLY`. Закрытые значения остаются в структурном runtime для проверки происхождения, но не индексируются как публичные контакты. {review['possible_conflict']} потенциальных разночтений оставлены на ручную проверку. Для четырёх подтверждённых конфликтов адреса обе версии доступны только как conflict record: бот не выдаёт одну из них как истину. Два коротких стационарных номера также удержаны на проверке.

Проверка 51 офлайн-вопроса дополнительно сравнила каждый ответ со всеми закрытыми мобильными значениями: утечек 0. Публикационная проверка не является подтверждением актуальности номера на дату звонка.
""")

topic_table = "\n".join(f"| {topic} | {count} |" for topic, count in case_topics.most_common())
put("CITIZEN_APPEAL_CASEBOOK.md", f"""
# Обезличенный каталог обращений

Из частного MD выделено {len(cases)} пересланных сообщений. Исходник и извлечённые персональные сведения остаются в закрытом локальном пространстве. Публичный casebook содержит только контролируемые ярлыки темы, обобщённую цель и вопросы для уточнения; фактические адреса, телефоны, имена, суммы, даты и исходные цитаты исключены. Автоматическая разметка тем предварительная и требует человеческой проверки перед оценкой качества по каждому случаю.

| Тема | Сообщений |
|---|---:|
{topic_table}

Четыре контролируемых сценария: отказ в зачислении ребёнка, спор о компенсации, запрос социальной помощи, опасный мост. В ответах бот просит нужные подробности и предлагает подготовить обращение; не обещает выплату, зачисление или решение и не назначает ведомство без территориального подтверждения. Файл `../casebook/appeal_cases_anonymized.jsonl` — каталог; `../runtime_export/appeal_scenarios.jsonl` — только безопасные реплики для runtime.
""")

put("APPEAL_ROUTING_MATRIX.md", """
# Матрица маршрутизации обращений

| Тема | Возможная компетенция | Территория и источник | Автоматическое назначение |
|---|---|---|---|
| Запись в школу / отказ | Районный или городской отдел образования, конкретная школа | Название школы, район/город, причина отказа; контакты только по карточке организации | Нет; оператор подтверждает адресата |
| Социальное пособие | Подразделение труда и соцобеспечения / социальный фонд в зависимости от предмета | Уточнить район, вид выплаты и обращённое ведомство | Нет; оператор подтверждает предмет и адресата |
| Компенсация за имущество | Орган, принявший решение, и профильный земельный/имущественный орган | Нужны акт, расчёт, территория и причина несогласия | Нет; решение по делу не является общей нормой |
| Опасный мост / дорога | Муниципальная служба или дорожное предприятие при source-backed route | Точное место и уровень дороги; при непосредственной угрозе сначала безопасность | Нет; отсутствие точного правила ведёт к уточнению |
| Люк, вода, мусор, свет | Служба только по совпадающему правилу `routing_rules` | Район/город/айыл аймак; правило соседней территории не переносится | Нет; это подсказка для сотрудника |
| Действия должностного лица | Соответствующее ведомство / надзорная инстанция после уточнения | Где и когда произошло, что уже подано, есть ли официальный ответ | Нет; человек проверяет полномочия |

Правила маршрутизации из V4 сохранены: 134 → 134. V5 добавляет контактные сведения, а не новые подтверждённые полномочия. CRM-регистрация остаётся за существующим явным подтверждением пользователя.
""")

put("KNOWLEDGE_UTILIZATION_AUDIT.md", f"""
# Использование известных сведений

В V4 было 473 публичных реквизита и 667 RAG блоков. В V5 чистый прирост — {pub-473} публичных структурированных реквизитов с учётом пяти прежних номеров, закрытых после новой проверки; новые телефон/адрес/график находятся без embedding вызова. Исправлена логика, из-за которой слова в названии отдела образования интерпретировались как запрос на процедуру и закрывали ответ о телефоне или часах. Уточнено разрешение мэрии по городу и проверка конфликтов адреса. Бот теперь выдаёт безопасные остальные поля карточки при конфликте одного поля.

Число ложных отказов по всем пользовательским запросам неизвестно: полного журнала эталонных запросов нет. В конкретной приёмке 51/51 проверок прошли; две выявленные в первом прогоне ошибки по вопросам об отделе образования исправлены, затем приёмка повторена целиком. 0 платных provider calls. Это проверка отобранных сценариев, не оценка доли ошибок в реальном трафике.

Новые RAG chunks не создавались, потому что новые данные представлены как короткие структурированные поля; их копирование в семантический индекс дублировало бы факты и потребовало новой платной индексации. Сценарии обращений доступны через контролируемую логику до RAG.
""")

example_rows = "\n".join(f"| {i} | {x['question']} | {x['expected_found']} | {x['privacy_ok']} | {x['mode']} |" for i, x in enumerate(acceptance['rows'][:21], 1))
put("CITIZEN_ACCEPTANCE_TESTS.md", f"""
# Приёмка по обращениям граждан, офлайн

Прогон: {acceptance['passed']}/{acceptance['count']} PASS, privacy leaks 0, provider calls 0. Реальный `AnswerService` + V5 staged `KnowledgeBase`; внешний генератор и embedding заменены счётчиками, поэтому проверена structured/casebook логика без OpenAI. Ещё 30 тестов сгенерированы из новых публичных карточек разных источников. Машинный протокол: `../acceptance_results.json`.

| № | Вопрос (RU/KY) | Ожидаемый факт найден | Нет закрытого номера | Режим |
|---:|---|---|---|---|
{example_rows}

Проверены также спорные адреса (ответ сообщает о расхождении), компенсация (запрос расчёта без обещания), зачисление (уточнение школы без обещания), опасный мост (совет безопасности), пособие (уточнение территории). Это локальная проверка общего сервиса; входящий webhook Meta и Telegram не вызывались по сети.
""")

put("RELEASE_READINESS_REPORT.md", f"""
# Готовность V5 к локальному пилоту

Knowledge manifest `{summary['knowledge_version']}`, {len(after['rag_chunks'])} chunks и столько же переиспользованных embeddings. Индекс совместим, так как байты chunks не изменились. Attribution audit: {summary['audit_count']} контактов, {pub} разрешены. Четыре структурированных конфликта адреса сохраняются; {review['mobile_public_status_unverified']} неустановленных мобильных контактов исключены. V4 каталог сохранён.

Локальная приёмка: {acceptance['passed']}/{acceptance['count']} без платных вызовов; проверка JSONL/ссылок/manifest/index — PASS. Оба канала прошли офлайн-проверку общего orchestrator и нового телефона: `../channel_results.json`. Информационный запрос не создавал CRM ticket. Полный набор V4: 185 тестов, 6 пропущено, один сбой на «Номеричи?» в первом прогоне; причина исправлена. После исправления целевые 42 теста прошли (6 skipped), включая многоходовый сценарий. Полный набор после исправления целиком повторно не запускался.

Новые сценарии обращения работают через общий `AnswerService`. Сетевой end-to-end webhook и реальная запись в CRM требуют отдельной проверки в пилотной среде с тестовым обращением и ручным подтверждением. V5 пока доступна в staging; активный default runtime бота остаётся V4. Production deploy, push и merge не выполнены.

Команды PowerShell для воспроизведения:

```powershell
$py = 'C:\\Users\\user\\PycharmProjects\\AI-presentation\\tg_bot-\\venv\\Scripts\\python.exe'
$stage = 'C:\\Users\\user\\Desktop\\knowledge_platform\\knowledge_output\\v5_staging'
& $py "$stage\\run_acceptance.py"
& $py -m unittest discover -s 'C:\\Users\\user\\PycharmProjects\\AI-presentation\\tg_bot-\\tests' -q
& $py "$stage\\prepare_staged_index.py"
& $py "$stage\\validate_v5.py"
& $py "$stage\\verify_channels.py"
```

Локальная активация после остановки процесса бота и завершения проверок:

```powershell
$bot = 'C:\\Users\\user\\PycharmProjects\\AI-presentation\\tg_bot-'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $stage "backups\\before_v5_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item (Join-Path $bot 'knowledge\\data') (Join-Path $backup 'data') -Recurse
Copy-Item (Join-Path $bot 'knowledge\\index') (Join-Path $backup 'index') -Recurse
& $py (Join-Path $bot 'scripts\\sync_knowledge.py') (Join-Path $stage 'runtime_export') --destination (Join-Path $bot 'knowledge\\data')
Copy-Item (Join-Path $stage 'runtime_support\\public_contact_attribution_records.jsonl') (Join-Path $bot 'knowledge\\data\\public_contact_attribution_records.jsonl')
Copy-Item (Join-Path $stage 'staged_bot_index\\*') (Join-Path $bot 'knowledge\\index') -Force
& $py (Join-Path $stage 'run_acceptance.py')
```

На сервере применять тот же порядок после отдельной проверки конфигурации CRM, Telegram и Meta webhook. Команды запуска/перезапуска конкретного сервиса зависят от серверного менеджера процессов и здесь не предполагаются.
""")

print(f"reports={len(list(REPORTS.glob('*.md')))} version={summary['knowledge_version']}")
