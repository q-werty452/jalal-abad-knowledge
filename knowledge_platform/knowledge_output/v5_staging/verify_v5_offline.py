"""Exercise the normal AnswerService with staged V5, without paid providers."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, r"C:\Users\user\PycharmProjects\AI-presentation\tg_bot-")
from knowledge.runtime import KnowledgeBase
from knowledge.service import AnswerService

QUESTIONS = [
    "Телефон Ноокен райондук мамлекеттик администрациясы",
    "Ноокен райондук мамлекеттик администрациясынын графиги кандай?",
    "Ноокен райондук электр тармактарынын телефон номери кандай?",
    "Номер МП «Ала-Бука Водоканал»",
    "Адрес МП «Ала-Бука Водоканал»",
    "Когда работает МП «Ала-Бука Водоканал»?",
    "Телефон Ала-Бука РЭС",
    "Номер ДЭП-17 Ала-Бука",
    "Телефон Мэрии города Кербен",
    "Адрес Мэрии города Кербен",
    "Когда работает Майлуу-Суу шаарынын шаарсууканал мекемеси?",
    "Телефон Майлуу-Суу шаарынын шаарсууканал мекемеси",
    "Номер Центра обслуживания населения № 04-04 (ЦОН г. Манас)",
    "Адрес Центра обслуживания населения № 04-04 (ЦОН г. Манас)",
    "Телефон Манас шаардык ички иштер бөлүмү",
    "Адрес Ноокен райондук Социалдык фонд башкармалыгы",
    "Адрес Ноокен райондук Эмгек, социалдык камсыздоо жана миграция башкармалыгы",
    "Мне предлагают компенсацию за дом, но я не согласен с суммой",
    "Моего ребёнка не зарегистрировали в школу, срок прошёл",
    "У нас опасный мост, дети ходят через него",
    "Мне нужна помощь с пособием",
]


async def main() -> None:
    base = KnowledgeBase(ROOT / "staged_bot_data", ROOT / "staged_bot_index")
    calls = {"embed": 0, "generate": 0}

    def embed(_question):
        calls["embed"] += 1
        return [0.0] * base.vectors.shape[1]

    async def generate(_question, _chunks):
        calls["generate"] += 1
        return "Уточните вопрос."

    service = AnswerService(base=base, enabled=True, embed_query=embed, generator=generate)
    results = []
    for question in QUESTIONS:
        scope = base.territories.explicit(question)
        answer, mode, evidence = await service.answer(question, preferred="openai", system="",
            history=[], max_tokens=500, detailed=False,
            citizen_context={"_territory_scope": scope})
        results.append({"question": question, "scope": scope, "mode": mode, "answer": answer,
                        "source_ids": sorted({str(s) for row in evidence.chunks or []
                                              for s in row.get("source_ids") or []})})
    print(json.dumps({"results": results, "calls": calls}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
