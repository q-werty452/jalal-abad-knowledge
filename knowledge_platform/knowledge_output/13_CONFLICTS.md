# Conflicts

Сохранены обе версии, без молчаливого выбора. Орфографические варианты адреса оставлены как отдельный случай для проверки тождественности.

## CONFLICT-001 — Жалал-Абад өсүмдүктөрдү химиялаштыруу,коргоо жана карантин башкармалыгы

- Поле: address
- Source A: SRC-225 (table:1:row:37) → Сузак айылы,Дакан Палван көчосү 52
- Source B: SRC-225 (table:1:row:38) → Манас шаары С.Качкынбаев көчөсү 11
- Preferred value: UNKNOWN
- Action: Запросить подтверждение адреса и статуса подразделений у мэрии/ведомства.

## CONFLICT-002 — Мамлекттик салык кызматынын Жалал-Абад облусунун Майлуу-Суу шаары боюнча башкы башкармалыгы

- Поле: address
- Source A: SRC-225 (table:1:row:23) → Майлуу-Суу шаары Сыдыков көчөсү 34
- Source B: SRC-225 (table:1:row:52) → Майлуу-Суу шаары Сыдыков кочосу 34
- Preferred value: UNKNOWN
- Action: Запросить подтверждение адреса и статуса подразделений у мэрии/ведомства.

## CONFLICT-003 — Манас шаардык финансы башкармалыгы

- Поле: address_territory_consistency
- Source A: SRC-225 (table:1:row:15) → Жээналиев №54 с.Казарман
- Source B: SRC-039 (paragraph:2) → Манасское городское финансовое управление (наименование)
- Preferred value: UNKNOWN
- Action: Подтвердить фактический адрес управления и территориальную принадлежность.

## Duplicate rows and copies

SRC-225 table rows 20 and 25 repeat the same road office with the same address and function. This is a source-row duplicate, not a separate organization. Exact file duplicates are recorded in inventory and `sources.jsonl`.
