# RAG preparation

Подготовлено **193** самодостаточных фрагментов в `machine/rag_chunks.jsonl` для будущей индексации BGE-M3 + pgvector. Embeddings не создавались.

## Schema and provenance

Каждый chunk содержит `chunk_id`, `document_id`, `organization_ids`, `topic`, `language`, `title`, `text`, `source_file`, страницу или лист/строку при наличии, дату документа, `verification_status`, `publication_status` и provenance. Повторы одинакового текста свернуты.

## Indexing gate

Технический RAG-индекс может использовать этот файл только во внутреннем контуре с показом source_id и проверкой ответа человеком. Перед citizen-visible выдачей требуется подтвердить право публикации, актуальность документов, географию пилота, RU/KY переводы и конфликтные сведения.

## Exclusions

Телефонные справочники сотрудников, персональные обращения и непроверенные сканы не превращены в публичные chunks. Содержимое `.extracted.jsonl` — только рабочий материал и не должно индексироваться или публиковаться.

## Future retrieval

Рекомендуемые фильтры: language, topic, organization_ids, source authority, publication_status, date validity. Answer generation should cite `document_id` and avoid treating proposed routing as an official assignment.
