# Ручной sync/index позднее

Команды ниже **не выполнялись** в этом promotion pass. Они используют только безопасный девятифайловый снимок `runtime_export/`. Полный `machine/contacts.jsonl` содержит INTERNAL_ONLY, CONFLICT и AMBIGUOUS и не должен копироваться в текущий parser бота.

В PowerShell:

```powershell
Set-Location 'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-'
python scripts\sync_knowledge.py 'C:\Users\user\Desktop\knowledge_platform\knowledge_output\v2\runtime_export'
python scripts\build_knowledge_index.py
```

Первая команда обновит локальный runtime `knowledge/data` и manifest. Вторая создаст embeddings через настроенный OpenAI API и обновит `knowledge/index`; для неё нужны зависимости бота и его `OPENAI_API_KEY`. После выполнения перезапустите процесс бота, чтобы он перечитал данные. Само применение команд и изменение бота в текущую работу не входят.
