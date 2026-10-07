# Validation

Последний прогон `python knowledge_output/v2/validate_v2.py`: **PASS**, ошибок 0. Разобраны все JSONL полного v2; проверены уникальность ключей, разрешение `organization_id`, `source_id` и `territory_id`, provenance контактов, источники часов/процедур/маршрутов, допустимые статусы и видимость. Отдельно проверено отсутствие публичных личных мобильных SRC-205 и приватных телефонных значений в публичных RAG chunks. Все 13 новых уникальных DOCX сверены по SHA-256; 29 исходных файлов корпуса совпадают с сохранёнными хешами. `validation.json` содержит машинный результат.

`runtime_export/` проверен исходным `knowledge.runtime.sync_knowledge` в временном каталоге без записи в бота: загрузились 247 источников, 308 публичных контактов, 53 структурированных графика и 348 chunks. Индекс в этой проверке не создавался.

Повторить локальную проверку из рабочей папки:

```powershell
python knowledge_output/v2/extract_v2.py
python knowledge_output/v2/build_v2.py
python knowledge_output/v2/prepare_runtime_export.py
python knowledge_output/v2/validate_v2.py
python knowledge_output/v2/offline_queries.py
```

Первый шаг регенерирует внутренние текстовые блоки источников. Файл `.source_blocks.jsonl` содержит сырой текст документов и не является публичным артефактом.
