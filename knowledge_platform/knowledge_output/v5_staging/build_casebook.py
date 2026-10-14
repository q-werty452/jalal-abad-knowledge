"""Extract only controlled, anonymous labels from private appeal messages.

The source text, names, numbers, addresses, dates and medical narratives are
never copied into the generated casebook or sent to an external service.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = Path(r"C:\Users\user\Downloads\richtext_converted_to_markdown (1).md")
raw = SOURCE.read_text(encoding="utf-8")
starts = list(re.finditer(r"\\?\[\d{2}\.\d{2},\s*\d{2}:\d{2}\\?\]\s*[^:]{1,80}:", raw))

TOPICS = [
    ("SCHOOL_ENROLLMENT", r"мектепке|школ[ауеы]|зачисл|каттабай|кабыл албай"),
    ("BRIDGE_ROAD_SAFETY", r"көпүр|мост|кооптуу жол|опасн.{0,12}дорог"),
    ("PROPERTY_COMPENSATION", r"компенсац|баалоо|оценк|пересел|бузул.{0,8}үй"),
    ("SOCIAL_SUPPORT", r"жөлөк|пособ|социалдык жардам|материалдык жардам|пенси"),
    ("LAND_HOUSING", r"жер|земл|участ|үй сал|жиль|кварти|турак жай"),
    ("HEALTH_ACCESS", r"оорукана|больниц|дарыгер|врач|дарылан|лечение"),
    ("WATER_UTILITIES", r"ичүүчү суу|таза суу|водопровод|суу түтүк|канализац"),
    ("OFFICIAL_CONDUCT", r"кызматкер.{0,30}текшер|должностн.{0,30}провер|коррупц|пара"),
    ("GENERAL_APPEAL", r"кайрылуу|обращен|арыз|заявлен"),
]
GOALS = {
    "SCHOOL_ENROLLMENT": ("добиться рассмотрения вопроса о зачислении", ["территория школы", "статус заявления"], "отдел образования по подтверждённой территории"),
    "BRIDGE_ROAD_SAFETY": ("сообщить об опасной инфраструктуре", ["точное место", "характер опасности"], "дорожная или муниципальная служба по подтверждённому маршруту"),
    "PROPERTY_COMPENSATION": ("оспорить или уточнить оценку имущества", ["какой документ получен", "какой расчёт оспаривается"], "компетентный орган после проверки документов и территории"),
    "SOCIAL_SUPPORT": ("получить разъяснение о поддержке", ["территория", "вид запрашиваемой помощи"], "социальная защита по территории"),
    "LAND_HOUSING": ("решить земельный или жилищный вопрос", ["территория", "статус земельного или жилищного вопроса"], "земельный орган или местная администрация после уточнения"),
    "HEALTH_ACCESS": ("получить помощь с доступом к медуслуге", ["территория", "какая услуга требуется"], "медицинская организация по территории"),
    "WATER_UTILITIES": ("сообщить о проблеме водоснабжения", ["точный адрес или ориентир", "тип проблемы"], "водная служба по подтверждённой зоне обслуживания"),
    "OFFICIAL_CONDUCT": ("попросить проверить действия должностного лица", ["какое действие оспаривается", "куда уже обращались"], "уполномоченный орган после проверки компетенции"),
    "GENERAL_APPEAL": ("подать обращение", ["территория", "суть просьбы"], "уполномоченный орган после уточнения"),
    "UNCLASSIFIED": ("уточнить цель обращения", ["суть вопроса", "территория"], "не маршрутизировать автоматически"),
}

records = []
for idx, match in enumerate(starts, 1):
    text = raw[match.end():starts[idx].start() if idx < len(starts) else len(raw)]
    labels = [name for name, pattern in TOPICS if re.search(pattern, text, re.I)]
    primary = next((label for label in labels if label != "GENERAL_APPEAL"),
                   "GENERAL_APPEAL" if "GENERAL_APPEAL" in labels else "UNCLASSIFIED")
    goal, clarify, route = GOALS[primary]
    official = bool(re.search(r"жооп катары|расмий жооп|официальн.{0,10}ответ|маалымдайбыз|сообщаем", text, re.I))
    records.append({"case_id": f"appeal-case-{idx:03d}", "private_source_id": "PRIVATE-APPEALS-2026-10-13",
                    "source_locator": f"message:{idx}", "topic": primary, "related_topics": labels,
                    "message_kind": "OFFICIAL_RESPONSE_OR_FORWARD" if official else "CITIZEN_APPEAL_OR_FORWARD",
                    "citizen_goal": goal, "needed_clarifications": clarify, "routing_hint": route,
                    "requires_operator_confirmation": True,
                    "outcome_is_general_rule": False,
                    "privacy_review": "CONTROLLED_LABELS_ONLY"})

out = ROOT / "casebook"
out.mkdir(exist_ok=True)
(out / "appeal_cases_anonymized.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
scenarios = [
    {"scenario_id": "school-enrollment-problem", "topic": "education", "trigger": "enrollment_problem",
     "answer_ru": "Если ребёнка не зачислили, укажите район, школу, класс и что сообщили при обращении. Проверю доступные контакты отдела образования и помогу подготовить обращение. Зачисление не могу обещать.",
     "answer_ky": "Баланы мектепке кабыл алышпаса, районду, мектепти, классты жана сизге эмне деп жооп беришкенин жазыңыз. Билим берүү бөлүмүнүн байланышын текшерип, кайрылуу даярдоого жардам берем. Кабыл алууну убада кыла албайм."},
    {"scenario_id": "property-compensation-review", "topic": "property_compensation", "trigger": "compensation_dispute",
     "answer_ru": "Если вы не согласны с предложенной компенсацией, укажите, какой документ и расчёт вам предоставили и что именно оспариваете. Помогу составить запрос о расчёте или обращение о пересмотре. Результат рассмотрения заранее неизвестен.",
     "answer_ky": "Сунушталган компенсацияга макул болбосоңуз, кайсы документ жана эсеп берилгенин, эмнеге каршы экениңизди жазыңыз. Эсепти сураган же кайра кароону өтүнгөн кайрылууну даярдоого жардам берем. Натыйжаны алдын ала убада кылбайм."},
    {"scenario_id": "social-support-request", "topic": "social_support", "trigger": "support_request",
     "answer_ru": "Уточните район или город и какую помощь вы хотите запросить. Проверю доступные сведения социальной службы и помогу оформить обращение. Выплата зависит от рассмотрения, обещать её нельзя.",
     "answer_ky": "Районуңузду же шаарыңызды жана кандай жардам сурап жатканыңызды жазыңыз. Социалдык кызматтын маалыматтарын текшерип, кайрылуу даярдоого жардам берем. Төлөмдү алдын ала убада кылбайм."},
    {"scenario_id": "unsafe-bridge", "topic": "roads", "trigger": "unsafe_bridge",
     "answer_ru": "Если мост опасен, не подходите к повреждённому месту. Укажите точное местоположение и характер повреждения; помогу подготовить обращение. Службу подберу только по подтверждённому маршруту для этой территории.",
     "answer_ky": "Көпүрө кооптуу болсо, бузулган жерге жакындабаңыз. Так ордун жана бузулууну жазыңыз; кайрылуу даярдоого жардам берем. Кызматты ушул аймак үчүн тастыкталган багыт боюнча гана көрсөтөм."},
]
(out / "appeal_scenarios.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in scenarios), encoding="utf-8")
(ROOT / "private" / "appeal_source_manifest.json").write_text(json.dumps({
    "private_source_id": "PRIVATE-APPEALS-2026-10-13", "path": str(SOURCE),
    "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "message_count": len(records),
    "public_index_allowed": False}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"messages": len(records), "primary_topics": dict(Counter(r["topic"] for r in records)),
                  "official_response_or_forward": sum(r["message_kind"] == "OFFICIAL_RESPONSE_OR_FORWARD" for r in records)},
                 ensure_ascii=False))
