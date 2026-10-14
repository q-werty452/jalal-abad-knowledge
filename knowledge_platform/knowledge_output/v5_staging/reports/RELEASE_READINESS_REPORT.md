# Готовность V5 к локальному пилоту

Knowledge manifest `619cf2a505e5b5fb`, 667 chunks и столько же переиспользованных embeddings. Индекс совместим, так как байты chunks не изменились. Attribution audit: 803 контактов, 790 разрешены. Четыре структурированных конфликта адреса сохраняются; 66 неустановленных мобильных контактов исключены. V4 каталог сохранён.

Локальная приёмка: 51/51 без платных вызовов; проверка JSONL/ссылок/manifest/index — PASS. Оба канала прошли офлайн-проверку общего orchestrator и нового телефона: `../channel_results.json`. Информационный запрос не создавал CRM ticket. Полный набор V4: 185 тестов, 6 пропущено, один сбой на «Номеричи?» в первом прогоне; причина исправлена. После исправления целевые 42 теста прошли (6 skipped), включая многоходовый сценарий. Полный набор после исправления целиком повторно не запускался.

Новые сценарии обращения работают через общий `AnswerService`. Сетевой end-to-end webhook и реальная запись в CRM требуют отдельной проверки в пилотной среде с тестовым обращением и ручным подтверждением. V5 пока доступна в staging; активный default runtime бота остаётся V4. Production deploy, push и merge не выполнены.

Команды PowerShell для воспроизведения:

```powershell
$py = 'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-\venv\Scripts\python.exe'
$stage = 'C:\Users\user\Desktop\knowledge_platform\knowledge_output\v5_staging'
& $py "$stage\run_acceptance.py"
& $py -m unittest discover -s 'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-\tests' -q
& $py "$stage\prepare_staged_index.py"
& $py "$stage\validate_v5.py"
& $py "$stage\verify_channels.py"
```

Локальная активация после остановки процесса бота и завершения проверок:

```powershell
$bot = 'C:\Users\user\PycharmProjects\AI-presentation\tg_bot-'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $stage "backups\before_v5_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item (Join-Path $bot 'knowledge\data') (Join-Path $backup 'data') -Recurse
Copy-Item (Join-Path $bot 'knowledge\index') (Join-Path $backup 'index') -Recurse
& $py (Join-Path $bot 'scripts\sync_knowledge.py') (Join-Path $stage 'runtime_export') --destination (Join-Path $bot 'knowledge\data')
Copy-Item (Join-Path $stage 'runtime_support\public_contact_attribution_records.jsonl') (Join-Path $bot 'knowledge\data\public_contact_attribution_records.jsonl')
Copy-Item (Join-Path $stage 'staged_bot_index\*') (Join-Path $bot 'knowledge\index') -Force
& $py (Join-Path $stage 'run_acceptance.py')
```

На сервере применять тот же порядок после отдельной проверки конфигурации CRM, Telegram и Meta webhook. Команды запуска/перезапуска конкретного сервиса зависят от серверного менеджера процессов и здесь не предполагаются.
