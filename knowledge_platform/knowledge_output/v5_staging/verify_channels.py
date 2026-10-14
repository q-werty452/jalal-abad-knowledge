"""Offline check that both transport channels use the same V5 decision path."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, r"C:\Users\user\PycharmProjects\AI-presentation\tg_bot-")
from application import ConversationOrchestrator
from knowledge.runtime import KnowledgeBase
from knowledge.service import AnswerService
from onboarding import OnboardingService
from storage import Storage
from tests.test_onboarding import FakeCRM


async def main() -> None:
    base = KnowledgeBase(ROOT / "staged_bot_data", ROOT / "staged_bot_index")
    calls = []

    def embed(_query):
        calls.append("embed")
        return None

    results = []
    for channel in ("telegram", "whatsapp"):
        crm = FakeCRM()
        chat_id = 8801 if channel == "telegram" else 996700880001
        crm.rows[channel, chat_id] = {"profile_name": "Demo", "phone": "",
            "raw_locality": "Ала-Бука", "district": "Ала-Бука", "settlement": "",
            "region": "", "language": "ru", "complete": False}
        flow = ConversationOrchestrator(crm, OnboardingService(crm),
            AnswerService(base=base, enabled=True, embed_query=embed))
        session = Storage("openai").get(chat_id)
        answer = await flow.handle(session, channel=channel, chat_id=chat_id,
            text="Номер МП «Ала-Бука Водоканал»", incoming_profile={"chat_id": chat_id},
            tg_user_id=chat_id if channel == "telegram" else None,
            sender_phone=str(chat_id) if channel == "whatsapp" else None)
        assert "03741 50576" in answer.text, (channel, answer.text)
        assert not crm.incoming_messages, "Information question was registered as an appeal"
        results.append({"channel": channel, "answer_mode": answer.answer_mode,
                        "public_contact_found": True, "unexpected_crm_submissions": 0})
    assert not calls, calls
    (ROOT / "channel_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
