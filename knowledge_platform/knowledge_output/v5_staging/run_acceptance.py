"""Fifty-plus practical offline questions through production AnswerService."""
from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, r"C:\Users\user\PycharmProjects\AI-presentation\tg_bot-")
from knowledge.runtime import KnowledgeBase
from knowledge.service import AnswerService

STATIC = [
    ("Телефон Ноокен райондук мамлекеттик администрациясы", "(03734) 5 00 12"),
    ("Ноокен райондук мамлекеттик администрациясынын графиги кандай?", "08:30-17:30"),
    ("Ноокен райондук электр тармактарынын телефон номери кандай?", "(03734) 5 00 16"),
    ("Номер МП «Ала-Бука Водоканал»", "03741 50576"),
    ("Адрес МП «Ала-Бука Водоканал»", "Балтагулова"),
    ("Когда работает МП «Ала-Бука Водоканал»?", "8:30"),
    ("Телефон Ала-Бука РЭС", "03741 5-08-79"),
    ("Номер ДЭП-17 Ала-Бука", "03741 5-04-76"),
    ("Телефон Мэрии города Кербен", "03742 50207"),
    ("Адрес Мэрии города Кербен", "Ныязалы-47"),
    ("Когда работает Майлуу-Суу шаарынын шаарсууканал мекемеси?", "17:30"),
    ("Телефон Майлуу-Суу шаарынын шаарсууканал мекемеси", "5-00-53"),
    ("Номер Центра обслуживания населения № 04-04 (ЦОН г. Манас)", "119"),
    ("Адрес Центра обслуживания населения № 04-04 (ЦОН г. Манас)", "Барпы Алыкулова"),
    ("Телефон Манас шаардык ички иштер бөлүмү", "03722 5-28-31"),
    ("Адрес Ноокен райондук Социалдык фонд башкармалыгы", "расходятся"),
    ("Адрес Ноокен райондук Эмгек, социалдык камсыздоо жана миграция башкармалыгы", "расходятся"),
    ("Мне предлагают компенсацию за дом, но я не согласен с суммой", "расчёт"),
    ("Моего ребёнка не зарегистрировали в школу, срок прошёл", "зачислили"),
    ("У нас опасный мост, дети ходят через него", "Не подходите"),
    ("Мне нужна помощь с пособием", "Уточните район"),
]


async def main() -> None:
    base = KnowledgeBase(ROOT / "staged_bot_data", ROOT / "staged_bot_index")
    calls = Counter()

    def embed(_question):
        calls["embed"] += 1
        return [0.0] * base.vectors.shape[1]

    async def generate(_question, _chunks):
        calls["generate"] += 1
        return "Уточните вопрос."

    service = AnswerService(base=base, enabled=True, embed_query=embed, generator=generate)
    matrix = [{"question": q, "expected": expected, "kind": "citizen"} for q, expected in STATIC]
    pool = [c for c in base.files["contacts"] if c["contact_id"].startswith("v5-")
            and c["visibility"] == "PUBLIC" and c["type"] in {"phone", "address", "working_hours"}
            and c["organization_id"].startswith("v5-org-")]
    selected_orgs = set()
    per_source = Counter()
    for contact in pool:
        org_id = contact["organization_id"]
        sid = contact["source_ids"][0]
        if org_id in selected_orgs or per_source[sid] >= 10:
            continue
        org = base.organizations_by_id[org_id]
        name = org.get("name_ru") or org.get("name_ky")
        query = ("Телефон " if contact["type"] == "phone" else
                 "Адрес " if contact["type"] == "address" else "Когда работает ") + name
        matrix.append({"question": query, "expected": contact["value"],
                       "kind": "new_public_fact", "contact_id": contact["contact_id"]})
        selected_orgs.add(org_id)
        per_source[sid] += 1
        if len(matrix) >= 51:
            break
    if len(matrix) < 50:
        raise AssertionError(f"Only {len(matrix)} cases built")
    private = [r.get("value") for r in map(json.loads, (ROOT / "private" / "review_records.jsonl").open(encoding="utf-8"))
               if r.get("reason") == "mobile_public_status_unverified" and r.get("value")]
    rows = []
    failures = []
    for idx, item in enumerate(matrix, 1):
        question = item["question"]
        scope = base.territories.explicit(question)
        answer, mode, evidence = await service.answer(question, preferred="openai", system="", history=[],
            max_tokens=500, detailed=False, citizen_context={"_territory_scope": scope})
        ok = item["expected"].casefold() in answer.casefold()
        leaked = any(value in answer for value in private)
        if not ok or leaked:
            failures.append({"case": idx, "reason": "PRIVATE_LEAK" if leaked else "FALSE_NO_DATA_OR_WRONG_ENTITY"})
        rows.append({"case": idx, "question": question, "mode": mode, "expected_found": ok,
                     "privacy_ok": not leaked, "source_ids": sorted({str(s) for r in evidence.chunks or []
                                                                   for s in r.get("source_ids") or []})})
    result = {"count": len(rows), "passed": len(rows) - len(failures), "failures": failures,
              "provider_calls": dict(calls), "rows": rows}
    (ROOT / "acceptance_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("count", "passed", "failures", "provider_calls")}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
