# Ручной sync v3 позднее

Команды ниже **не выполнялись** при сборке Knowledge v3. Текущий parser бота читает девять JSONL-файлов. Для него предназначена только `runtime_export/`; полный `machine/` содержит внутренние телефоны, роли и конфликты.

В PowerShell:

```powershell
Set-Location 'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-'
python scripts\sync_knowledge.py 'C:\Users\user\Desktop\knowledge_platform\knowledge_output\v3\runtime_export'
python scripts\build_knowledge_index.py
```

Вторая команда обращается к настроенному OpenAI API для создания embeddings. После ручного выполнения команд потребуется перезапустить процесс бота. Папки `AI-presentation/tg_bot-/knowledge/data` и `knowledge/index` в этом проходе не менялись.
