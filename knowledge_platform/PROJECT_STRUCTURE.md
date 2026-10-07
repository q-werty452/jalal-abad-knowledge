# Карта проекта `knowledge_platform`

Корень проекта: `C:\Users\user\Desktop\knowledge_platform`.

Проект хранит переданные документы, markdown-представление знаний, machine-readable corpus, результаты аудитов и отдельные Knowledge v2/v3. Бот и его runtime-каталог в этом проекте отсутствуют.

## Дерево верхнего уровня

```text
knowledge_platform/
├── 00_START_HERE_AIG2C_KNOWLEDGE.md
├── [переданные DOCX / PDF / XLSX документы]
├── [ZIP-архивы с переданными документами]
├── UNIFIED_KNOWLEDGE_AUDIT_JALAL_ABAD (1).xlsx
├── PROJECT_STRUCTURE.md                 ← эта карта
├── docs/
│   └── superpowers/plans/
│       └── 2026-10-04-knowledge-promotion-v2.md
└── knowledge_output/
    ├── 00–26 markdown-документы знаний и аудита
    ├── build/extract/validate python-скрипты
    ├── machine/                           ← canonical corpus
    ├── audit_machine/                     ← результаты второго аудита
    ├── v2/                                 ← Knowledge Promotion v2
    │   ├── machine/                        ← полный v2
    │   ├── review/                         ← решения аудита/кандидатов
    │   ├── runtime_export/                 ← экспорт v2 для parser бота
    │   └── source_documents/               ← 13 DOCX из предыдущей партии
    └── v3/                                 ← Knowledge v3, текущая новая партия
        ├── machine/                        ← полный v3
        ├── review/                         ← решения по дубликатам и публикации
        ├── runtime_export/                 ← публичный экспорт v3 для parser бота
        └── source_documents/               ← копии 10 DOCX новой партии
```

## Корневые документы и архивы

Корневые DOCX/PDF/XLSX — исходники, переданные для проекта. Имена файлов сохраняют исходное написание; сюда входят документы госорганов, положения и уставы учреждений, таблицы контактных данных и аудиторская книга `UNIFIED_KNOWLEDGE_AUDIT_JALAL_ABAD (1).xlsx`.

ZIP-файлы (`07-09-2026_*.zip`, `Документы_Word*.zip`, `Район шаарлар, обл мекеме ишканалар.zip`, `knowledge_output.zip`) — переданные архивы с исходными документами или ранее собранными материалами. Для точного списка см. инвентарь [00_SOURCE_INVENTORY.md](knowledge_output/00_SOURCE_INVENTORY.md).

`00_START_HERE_AIG2C_KNOWLEDGE.md` — входная инструкция и обзор для работы с базой. `PROJECT_STRUCTURE.md` — карта папок и данных.

## `knowledge_output/`: подготовленная база и аудиты

### Markdown 00–16: первая версия знаний

- `00_SOURCE_INVENTORY.md` — перечень источников.
- `01_SOURCE_OF_TRUTH_MAP.md` — карта авторитетности источников.
- `02_CURRENT_KNOWLEDGE_STATUS.md` — состояние базы.
- `03_ORGANIZATIONS.md` — организации.
- `04_DEPARTMENTS_AND_SUBORDINATION.md` — подразделения и подчинённость.
- `05_COMPETENCES_AND_RESPONSIBILITIES.md` — функции и ответственность.
- `06_SERVICES_AND_CITIZEN_QUESTIONS.md` — услуги и вопросы граждан.
- `07_CONTACTS_AND_ADDRESSES.md` — телефоны, адреса и контакты.
- `08_ROUTING_KNOWLEDGE.md` — маршрутизация вопросов.
- `09_LEGAL_AND_REGULATORY_BASIS.md` — правовая основа.
- `10_FAQ_RU.md`, `11_FAQ_KY.md` — вопросы и ответы на русском и кыргызском.
- `12_TERMS_AND_ALIASES.md` — термины и варианты названий.
- `13_CONFLICTS.md` — выявленные противоречия.
- `14_KNOWLEDGE_GAPS.md` — пробелы.
- `15_RAG_PREPARATION.md` — подготовка текстовых данных для поиска.
- `16_FINAL_KNOWLEDGE_AUDIT.md` — итог первого аудита.

### Markdown 17–26: второй аудит

Покрытие географии, организаций, контактов, процедур и услуг находится в `17–20`. `21_RECOVERABLE_FACTS.md` — восстанавливаемые факты; `22_BLOCKED_SOURCE_PRIORITY.md` — приоритет источников с ограничениями; `23_TERRITORY_GAP_MATRIX.md` — пробелы по территориям; `24_REAL_QUERY_COVERAGE.md` — проверка реальных запросов; `25_KNOWLEDGE_COMPLETENESS_AUDIT.md` — полнота; `26_INFORMATION_REQUEST_TO_GOVERNMENT.md` — сведения, запрошенные у госорганов.

### Скрипты сборки и состояния

- `build_corpus.py`, `extract_sources.py`, `render_knowledge.py`, `validate_corpus.py` — сборка, извлечение, отображение и проверка canonical corpus.
- `build_second_audit.py`, `audit_second_pass.py` — сборка и повторная проверка второго аудита.
- `.canonical_state.json`, `.validation.json`, `.work_state.md` — служебное состояние сборки/проверки.

### `machine/`: старый canonical corpus

Девять JSONL-таблиц:

`sources.jsonl`, `organizations.jsonl`, `competences.jsonl`, `contacts.jsonl`, `routing_rules.jsonl`, `qa_pairs_ru.jsonl`, `qa_pairs_ky.jsonl`, `rag_chunks.jsonl`, `aliases.jsonl`.

Это исходная machine-readable версия, сохранённая при создании v2.

### `audit_machine/`: данные второго аудита

`recoverable_facts.jsonl`, `new_sources.jsonl`, `territories.jsonl`, `contact_coverage.jsonl`, `organization_coverage.jsonl`, `query_coverage.jsonl`, `service_procedures.jsonl`, `territory_gap_matrix.jsonl`, `unrepresented_source_review.jsonl`, `baseline_hashes.json` — структурированные результаты и контрольные хеши аудита. Файлы `_review_extract.jsonl` и `_review_hits.jsonl` — временные извлечения аудита, а не canonical corpus.

## `knowledge_output/v2/`: отдельная версия после promotion

- `machine/` — полный v2: исходники, организации, компетенции, контакты, часы, маршруты, QA, RAG, услуги, процедуры, территории и конфликты. Включает записи с INTERNAL_ONLY/CONFLICT/AMBIGUOUS для сохранения provenance и последующего разбора.
- `review/` — `recoverable_dispositions.jsonl` с решением по каждому из 194 recoverable-кандидатов и `source_contact_scan.jsonl` с результатами сканирования 900 блоков, содержащих сигналы контактов/часов.
- `runtime_export/` — девять legacy-файлов для runtime parser, только с публичными подтверждёнными данными. Для старого parser экспортировать следует именно эту папку, не `machine/`.
- `source_documents/` — копии 13 новых уникальных DOCX (`NEW-235`–`NEW-247`); четыре повторно переданных документа сопоставлены существующим source ID и повторно не копировались.
- `build_v2.py`, `extract_v2.py`, `prepare_runtime_export.py`, `validate_v2.py`, `offline_queries.py` — построение, извлечение, безопасная подготовка runtime-экспорта, проверка и офлайн-вопросы.
- `baseline_hashes.json`, `metrics.json`, `validation.json`, `offline_query_check.jsonl` — хеши исходной базы, метрики и машинные результаты проверок.
- `PROMOTION_REPORT.md`, `VALIDATION.md`, `OFFLINE_QUERY_CHECK.md`, `SYNC_LATER.md` — отчёт promotion, результаты проверки, офлайн-запросы и команды для будущего sync/index.

`.source_blocks.jsonl` — временная рабочая выгрузка распознанного текста документов, используемая `build_v2.py`. Она содержит сырой исходный текст, может содержать личные/служебные сведения и не является частью `runtime_export/`.

## `knowledge_output/v3/`: новая партия районных и местных документов

V3 наследует v2 и добавляет 10 зарегистрированных DOCX, из которых 8 уникальны, а 2 являются точными дубликатами `SRC-183`. В `machine/` появились `staff_roles.jsonl`, `real_query_examples.jsonl`, `escalation_rules.jsonl`, `service_territories.jsonl`, `topic_aliases.jsonl` и `appeal_categories.jsonl`. Публичный девятифайловый экспорт — `v3/runtime_export/`; для дальнейшего sync теперь ориентируйтесь на него.

`PROMOTION_V3_REPORT.md` содержит сравнение v2→v3 и факты по каждому новому источнику. `V3_REVIEW_REQUIRED.md` перечисляет спорные адреса, зоны и ограничения публикации. `OFFLINE_QUERY_COVERAGE.md` показывает 22 офлайн-вопроса; `VALIDATION.md` и `validation.json` — результаты проверки; `SYNC_LATER.md` — команды будущего ручного sync/index. Скрипты сборки и проверки находятся в корне `v3/`.

## `knowledge_output/v4/`: новая партия Токтогул, Сузак, Ала-Бука, Таш-Көмүр и здравоохранение

V4 строится поверх неизменённой V3. В `source_documents/` сохранены восемь новых DOCX; `machine/` содержит полный структурированный корпус, включая внутренние роли сотрудников, территориальные зоны и конфликты. `runtime_export/` содержит только девять файлов, которые читает текущий бот; `runtime_support/` — привязанный к точной версии базы аудит публичных контактов. Папка `release/` содержит data-only пакет без платного embedding index. `staging_bot/` — изолированная локальная проверка parser; рабочий бот ею не заменён.

Отчёты: `PROMOTION_V4_REPORT.md`, `V4_REVIEW_REQUIRED.md`, `VALIDATION.md`, `OFFLINE_QUERY_COVERAGE.md`, `BOT_COMPATIBILITY.md`, `BOT_UPDATE_READINESS.md`, `SERVER_DEPLOY_PLAN.md`. Скрипты сборки, проверки и будущей упаковки сервера находятся в корне `v4/`. Архив `knowledge-v4-demo.tar.gz` должен создаваться только после разрешённой сборки нового embedding index и локальной приёмки.

## Где что искать

| Что нужно | Папка/файл |
|---|---|
| Исходные документы и архивы | Корень проекта |
| Краткий вход в базу | `00_START_HERE_AIG2C_KNOWLEDGE.md` |
| Человекочитаемые знания 00–16 | `knowledge_output/00–16_*.md` |
| Второй аудит 17–26 | `knowledge_output/17–26_*.md` |
| Старые структурированные данные | `knowledge_output/machine/` |
| Результаты второго аудита | `knowledge_output/audit_machine/` |
| Полный актуальный promotion v2 | `knowledge_output/v2/machine/` |
| Только публичный экспорт для текущего parser | `knowledge_output/v2/runtime_export/` |
| Полный текущий Knowledge v3 | `knowledge_output/v3/machine/` |
| Публичный экспорт Knowledge v3 | `knowledge_output/v3/runtime_export/` |
| Полный Knowledge v4 | `knowledge_output/v4/machine/` |
| Публичный экспорт Knowledge v4 | `knowledge_output/v4/runtime_export/` |
| Аудит контактов Knowledge v4 | `knowledge_output/v4/runtime_support/` |
| Пакет данных Knowledge v4 | `knowledge_output/v4/release/` |
| План обновления и отката бота/сервера | `knowledge_output/v4/SERVER_DEPLOY_PLAN.md` |
| Отчёт по новой партии | `knowledge_output/v3/PROMOTION_V3_REPORT.md` |
| Решения по recoverable и сомнительным кандидатам | `knowledge_output/v2/review/` |
| Отчёт «до/после» | `knowledge_output/v2/PROMOTION_REPORT.md` |
| Проверка 10 реальных вопросов | `knowledge_output/v2/OFFLINE_QUERY_CHECK.md` |
| Команды последующего sync/index | `knowledge_output/v2/SYNC_LATER.md` |

## Важное различие

`machine/` каждой версии содержит полный след данных и пригоден для аудита/дальнейшей обработки. `runtime_export/` подготовлен для старой схемы бота и отфильтрован по видимости публикации. Не копируйте полный `v3/machine/contacts.jsonl` в runtime: там сохранены внутренние, конфликтные и неоднозначные сведения.
