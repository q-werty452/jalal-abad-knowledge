# Проверка Knowledge v3

Последний прогон `validate_v3.py`: **PASS**, ошибок 0. Результат в `validation.json`.

Проверено: JSONL-синтаксис всех таблиц, уникальность ID, ссылки на источники/организации/территории, provenance и locator новых фактов, видимость контактов, отсутствие личных мобильных в публичном экспорте, обязательная территориальная область новых маршрутов, отсутствие автоматического назначения, конфликт адреса и зон обслуживания, хеши всех 10 DOCX и неизменность всех 15 таблиц v2.

В изолированном временном каталоге исходный `knowledge.runtime.sync_knowledge` бота загрузил девятифайловый `runtime_export/`: 257 источников, 317 публичных контактов, 56 записей с совместимым полем `working_hours`, 49 маршрутов и 412 chunks. Боевой runtime и индекс при этой проверке не изменялись.

Повторная локальная сборка из корня `knowledge_platform`:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' knowledge_output/v3/build_v3.py
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' knowledge_output/v3/prepare_runtime_export.py
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' knowledge_output/v3/validate_v3.py
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' knowledge_output/v3/offline_queries.py
```

`build_v3.py` сохраняет копии всей партии DOCX в `source_documents/`, поэтому после первого запуска эти копии позволяют пересобрать v3 без папки Downloads. Точные дубликаты ссылаются на `SRC-183` из существующего corpus.
