#!/usr/bin/env python3
"""Сборка справочника v5 = v4 + ответы администрации Жалал-Абадской области.

Запуск:  python3 build_v5.py
Читает:  ../v4/runtime_export/*, admin_answers/a1..a8.txt (выгрузки заполненных
         администрацией файлов «Запрос сведений для чат-бота»).
Пишет:   runtime_export/ (копия v4 + organizations/contacts), REPORT_V5.md,
         held_back.jsonl (то, что НЕ опубликовано, с причинами), changes.jsonl.

Принципы (ошибка = житель звонит не туда):
  * публикуем только то, что однозначно прочитано; сомнительное идёт в held_back;
  * дописанный код города помечается verification_status=NEEDS_CONFIRMATION;
  * адрес/часы из ответа приоритетнее v4: старое значение -> SUPERSEDED + INTERNAL_ONLY;
  * один номер у разных организаций/в других организациях v4 не публикуем;
  * мобильные номера из строки «Руководитель:» — личные, не публикуем.
Скрипт детерминирован: повторный запуск даёт тот же результат.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4 = HERE.parent / "v4" / "runtime_export"
OUT = HERE / "runtime_export"
ANS = HERE / "admin_answers"
VERSION_TAG = "v5"
DATE = "2026-10-12"
ISSUER = "Администрация (полпредство) Жалал-Абадской области"

SRC_FILE = {
    "a1": "Запрос сведений для чат-бота (1).docx",
    "a2": "Запрос сведений для чат-бота.docx",
    "a3": "Ноокен Запрос сведений для чат-бота (2).docx",
    "a4": "АЛА-БУКА Запрос сведений для чат-бота.docx",
    "a5": "Запрос сведений для чат-бота (1) (1).docx",
    "a6": "Запрос сведений для чат-бота (1) (2).docx",
    "a7": "Запрос сведений для чат-бота (2).docx",
    "a8": "Запрос сведений для чат-бота (1) (3).docx",
}
SRC_ID = {k: f"ADM-{DATE}-{k}" for k in SRC_FILE}
# территория по умолчанию и код города для файла
FILE_TERR = {"a1": "city:Майлуу-Суу", "a2": "city:Кара-Көл", "a3": "district:Ноокен",
             "a4": "district:Ала-Бука", "a5": "district:Сузак", "a6": "district:Аксы",
             "a7": "district:Базар-Коргон", "a8": "city:Манас"}
FILE_CODE = {"a1": "3744", "a2": "3746", "a3": "3734", "a4": "3741", "a5": "3748",
             "a6": "3742", "a7": "3736", "a8": "3722"}
KNOWN_CODES = {"3722", "3746", "3744", "3745", "3742", "3734", "3748", "3736", "3741",
               "3747", "3738", "3749"}

# ----------------------------------------------------------------------------
# разбор текста
# ----------------------------------------------------------------------------
TIME = r"(\d{1,2})\s*:\s*(\d{2})"
HRS = re.compile(
    r"(?:(?P<days>(?:пн|Дүйшөмбү)[.\s]*[-–—]\s*(?:пт|сб|Жума|Ишемби))[.:\s]*)?(?:с\s*)?"
    + TIME + r"\s*(?:до|[-–—])\s*" + TIME, re.I)
PHONE = re.compile(r"(?<![\w№])\+?[\d(][\d\s()\-–]{3,}\d")
TEMPLATE_OK = re.compile(r"^(Есть: [^.]*\.\s*)?(Принести: [^.\d]*\.?|Всё есть\.)?\s*$")
NOISE = [r"Принести:(?:\s|телефон|адрес|часы работы|,|и)*[.:]?", r"Всё есть\.?",
         r"обеденный перерыв:?", r"[Вв]ыходные дни:?\s*(?:Суббота-Воскресенье|суббота, воскресенье)?\.?",
         r"в пятницу короткий день, работают до \d+:\d+\.?", r"-{3,}",
         r"Дүйшөмбү\s*-\s*Жума саат[^.]*?чейин\.?", r"Дежурная часть: круглосуточно,?",
         r"Тез жардам / Кабыл алуу бөлүмү: Күнү-түнү \(24/7\)", r"круглосуточный пост 24/7"]


def norm(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower().replace("ё", "е")).strip()


def digits(x: str) -> str:
    return re.sub(r"\D", "", x)


def fmt_hours(m) -> str:
    days = m.group("days")
    t = f"{int(m.group(2)):02d}:{m.group(3)}-{int(m.group(4)):02d}:{m.group(5)}"
    if days:
        d = days.lower().replace(".", "").replace(" ", "")
        d = {"дүйшөмбү-жума": "пн-пт", "дүйшөмбү-ишемби": "пн-сб"}.get(d, d)
        t = d + " " + t
    return t


def valid_time(m) -> bool:
    return int(m.group(2)) <= 24 and int(m.group(4)) <= 24 and int(m.group(3)) < 60 and int(m.group(5)) < 60


def find_hours(s: str) -> list[str]:
    return [fmt_hours(m) for m in HRS.finditer(s) if valid_time(m)]


def entries_from_txt(f: str) -> list[list]:
    """[[название, [строки ответа]], ...] — только пункты, где администрация что-то вписала."""
    lines = (ANS / f"{f}.txt").read_text(encoding="utf-8").split("\n")
    cur, out = None, []
    for k, l in enumerate(lines):
        nxt = lines[k + 1].strip() if k + 1 < len(lines) else ""
        if l.startswith("•") or l.startswith("- "):
            cur = [l.lstrip("•- ").strip(), []]
            out.append(cur)
        elif l.startswith("☐") or l.startswith("Нет совсем") or l.startswith("=== TABLES") or l.startswith("ОБЩЕЕ"):
            cur = None
        elif cur and f == "a3" and l.strip() == "бөлүмү":
            cur[0] += " бөлүмү"
        elif cur and f == "a3" and nxt.startswith("Адрес:") and not l.startswith("Адрес") \
                and any(x.startswith("Адрес") for x in cur[1]):
            cur = [l.strip(), []]            # a3: новые службы идут без маркера
            out.append(cur)
        elif cur and l.strip():
            cur[1].append(l.strip())
    return [e for e in out if any(not TEMPLATE_OK.match(x) for x in e[1])]


def parse_body(body: list[str]) -> dict:
    s = " ".join(body).replace("\xa0", " ")
    s = re.sub(r"Есть:[^.]*\.", "", s)
    hrs = find_hours(s)
    s2 = HRS.sub(lambda m: " " if valid_time(m) else m.group(0), s)
    phones = [m.group(0).strip(" -–") for m in PHONE.finditer(s2)]
    rest = PHONE.sub(" ", s2)
    for n in NOISE:
        rest = re.sub(n, " ", rest)
    rest = re.sub(r"\s+", " ", rest)
    rest = re.sub(r"(\s*[,.]\s*)+$", "", rest.strip())
    rest = re.sub(r"^(\s*[,.]\s*)+", "", rest).strip()
    hours = None
    if hrs:
        hours = hrs[0]
        if "обеденный перерыв" in s and len(hrs) > 1:
            hours += "; обед " + hrs[1]
    return {"hours": hours, "phones": phones, "address_raw": rest}


def clean_address(a: str | None) -> str | None:
    if not a:
        return None
    a = re.sub(r"^(Адрес|адрес)[:\s]*", "", a.strip())
    a = re.sub(r"^\S+\s+[ав]/[ао][,.]\s*", "", a)             # «Сузакский а/а, »
    a = re.sub(r"\b(телефон|часы работы)\b[\s,.]*", "", a)
    a = re.sub(r"\bСело\b", "с.", a)
    a = re.sub(r"\s*№\s*$", "", a)
    a = re.sub(r"\s+", " ", a).strip(" ,.;")
    if len(a) < 6 or not re.search(r"(ул|көч|с\.|г\.|село|пр\.|трасса|шаар)", a, re.I):
        return None
    return a


# ----------------------------------------------------------------------------
# ручные записи (формат ответа нерегулярный) и поправки к разбору
# ----------------------------------------------------------------------------
def E(f, org_id, name, address=None, phones=(), hours=None, terr=None, aliases=(), leader=False,
      lang=None, note=None, emergency=()):
    return dict(file=f, org_id=org_id, name=name, address=address, phones=list(phones), hours=hours,
                terr=terr, aliases=list(aliases), leader=leader, lang=lang, note=note,
                emergency=list(emergency), manual=True)


MANUAL: list[dict] = [
    # --- a1: Майлуу-Суу ---------------------------------------------------
    E("a1", "v4-org-704c2681f9caef", "Майлуу-Суу шаарынын жалпы дарыгердик практика борбору мекемеси",
      "Майлуу-Суу шаары, Сыдыкова көчөсү 7", ["(03477) 5-00-55"], "08:00-18:00"),
    E("a1", "org-mamlekttik-salyk-kyzmatynyn-zhalal-abad-oblusunun-mailuu-suu-shaa-9fce0e8",
      "Мамлекттик салык кызматынын Жалал-Абад облусунун Майлуу-Суу шаары боюнча башкы башкармалыгы",
      "Майлуу-Суу шаары, Сыдыкова көчөсү 34", ["(03477) 5-5-91"], "09:00-18:00"),
    E("a1", "v2-org-be9b25261852", "Мэрия города Майлуу-Суу",
      "Майлуу-Суу шаары, Ленин көчөсү 135а, 3-кабат", ["(03744) 5-27-10", "5-14-86"], "08:30-17:30"),
    E("a1", "v2-org-dd2424a0bba8", "Управление муниципальной собственности г. Майлуу-Суу",
      "Майлуу-Суу шаары, Ленин көчөсү 135а, 1-кабат", ["(03744) 5-29-19", "5-14-86"], "08:30-17:30"),
    # --- a2: Кара-Көл -----------------------------------------------------
    E("a2", "v4-org-11eeb143baec78", "Кара-Көл шаардык Б.Рысбеков атындагы ЖДПБ",
      None, ["0 (3746) 5-11-53"], "пн-сб 08:00-17:00; круглосуточный пост 24/7"),
    E("a2", "org-kyrgyz-respublikasynyn-finansy-ministrliginin-kara-kol-shaardyk-f-55bbbc4",
      "Кыргыз Республикасынын Финансы министрлигинин Кара-Көл шаардык финансы башкармалыгы",
      None, ["0 (3746)5-12-63"], "пн-пт 09:00-18:00"),
    E("a2", "v2-org-26d472d565f8", "Муниципальное предприятие «Кара-Кульское теплоснабжение»",
      None, ["0 779 936 445"], None),
    E("a2", "v2-org-77bc3cf31267", "Муниципальное предприятие коммуналные хозяйства города Кара-куль",
      None, ["0 (3746) 5-12-30"], None),
    E("a2", None, "Кара-Кульский городской отдел образования", "ул. Ленина №1",
      ["0 (3746) 5-12-25"], "пн-пт 08:30-17:30", terr="city:Кара-Көл", lang="ru"),
    # --- a4: Ала-Бука ------------------------------------------------------
    E("a4", "v4-org-35caae23e20604", "Т.Балтагулов айыл өкмөтү", "с.Ак-Там, ул. К.Мусабаева №45",
      ["03741 60034"], "пн-пт 08:30-17:30"),
    E("a4", "v4-org-d1e41a44c0f34e", "Айыл окмоту Айры-Тамского айылного аймака",
      "с.Айры-Там, ул. С.Жунусова №37", ["+996554479326"], "пн-пт 08:30-17:30"),
    E("a4", "v2-org-38f43ed4bd3a", "Ала-Бука айыл өкмөтү", "с.Ала-Бука, ул. М.Мамырбекова №52",
      ["03741 50013", "0770 558 830"], "пн-пт 08:30-17:30"),
    E("a4", "v4-org-969006a8774a71", "Ынтымак айыл өкмөтү", "с.Тенги, ул. С.Алымкулов №36",
      ["0555111584"], "пн-пт 08:30-17:30"),
    E("a4", "v4-org-ddbcc8d9016aa3", "Ала-Бука райондук жалпы дарыгердик практика борбору",
      "с.Ала-Бука, ул. М.Мамырбекова №98", ["03741 5-00-60", "+996776904158"],
      "пн-сб 08:30-17:30; приёмное отделение круглосуточно"),
    E("a4", "v2-org-11b1aa139d18", "Ала-Бука сектору — транспорт каттоо борбору", None, ["+996555990086"], None),
    E("a4", "org-kyrgyz-respublikasynyn-finansy-ministrliginin-ala-buka-raionduk-f-8defd61",
      "Кыргыз Республикасынын Финансы министрлигинин Ала-Бука райондук финансы башкармалыгы",
      None, ["03741 5-00-75"], "пн-пт 09:00-18:00"),
    E("a4", "v4-org-9ede4e8e944f1b", "МИ «1-Май Эмгек»", "с.Айры-Там, Ж.Нурматов 23 а",
      ["+996772764606"], "пн-пт 08:30-17:30", leader=True),
    E("a4", "v4-org-03f549e7ffae3c", "МИ «Чанач-Сай»", "с.Ак-Там, ул. К.Мусабаева №45",
      ["+996 556 881 577"], "пн-пт 08:30-17:30", leader=True),
    E("a4", "v4-org-448a6f45c6a41a", "МИ «Ынтымак Тазалык»", "с.Тенги, ул. С.Алымкулов №36",
      ["0554778818"], "пн-пт 08:30-17:30", leader=True),
    E("a4", "v4-org-2489d07ee2396b", "МП «Ала-Бука Водоканал»", "с.Ала-Бука, ул. Т.Балтагулова №52",
      ["03741 50576", "+996755 493 849"], "пн-пт 08:30-17:30", leader=True),
    E("a4", "v4-org-8b969da0560847", "МП «Ала-Бука Тазалык»", "с.Ала-Бука, ул. Ибраимова №126",
      ["+996 220 613 834"], "пн-пт 08:30-17:30", leader=True),
    E("a4", "v4-org-242a411d285612", "МП «Ала-Бука Техсервис»", "с.Ала-Бука, ул. Мамырбекова №52",
      ["+996 556860077"], "пн-пт 08:30-17:30", leader=True),
    E("a4", "org-mamlekttik-salyk-kyzmatynyn-zhalal-abad-oblusunun-ala-buka-raionu-64517d4",
      "Мамлекеттик салык кызматынын Жалал-Абад облусунун Ала-Бука району боюнча башкы башкармалыгы",
      None, ["03741 50163"], "пн-пт 08:30-17:30"),
    E("a4", None, "«Ала-Бука райондук электр тармактары» ишканасы", "с.Ала-Бука, ул. Рыскулова №11",
      ["03741 5-08-79", "+996 0701005400"], "пн-пт 08:00-17:00", leader=True, lang="ky"),
    E("a4", None, "№17 жол эксплуатациялоо ишканасы", "с.Ала-Бука, ул. И.Кулбаева №1",
      ["03741 5-04-76", "+996 0706670875"], "пн-пт 08:00-17:00", leader=True, lang="ky"),
    E("a4", None, "Кыргыз Республикасынын Министрлер Кабинетине караштуу Жер ресурстары, кадастр, геодезия "
      "жана картография боюнча мамлекеттик агенттигинин Ала-Бука филиалы",
      "с.Ала-Бука, ул. М.Мамырбекова №1", ["03741 5-00-66", "+996 553856203"], "пн-пт 08:30-17:30",
      leader=True, lang="ky"),
    E("a4", None, "Ала-Бука райондук шаар куруу жана архитектура башкармалыгы",
      "с.Ала-Бука, ул. Архитекторлор №1", ["03741 5-02-83", "+996 557751322"], "пн-пт 08:30-17:30",
      leader=True, lang="ky"),
    E("a4", None, "Ала-Бука райондук Социалдык фонд башкармалыгы", "с.Ала-Бука, ул. М.Мамырбекова №1",
      ["03741 5-03-95", "+996 556192020"], "пн-пт 08:30-17:30", leader=True, lang="ky"),
    E("a4", None, "Ала-Бука райондук эмгек, социалдык камсыздоо жана миграция башкармалыгы",
      "с.Ала-Бука, ул. М.Мамырбекова №42", ["03741 5-01-07", "+996 779866888"], "пн-пт 08:30-17:30",
      leader=True, lang="ky"),
    E("a4", None, "04-02 Ала-Бука райондук калкты тейлөө бөлүмү", "с.Ала-Бука, ул. М.Мамырбекова №40",
      ["03741 5-08-91", "+996 553583583"], "пн-пт 08:30-17:30", leader=True, lang="ky"),
    E("a4", None, "Ала-Бука райондук билим берүү бөлүмү", "с.Ала-Бука, ул. С.Ибраимова №74",
      ["03741 5-04-12", "+996 555477121"], "пн-пт 08:30-17:30", leader=True, lang="ky"),
    E("a4", None, "Ала-Бука райондук ички иштер бөлүмү", "с.Ала-Бука, ул. М.Мамырбекова №54",
      ["03741 5-00-16"], "пн-пт 08:30-17:30", lang="ky", emergency=["102"]),
    E("a4", None, "Кыргыз Республикасынын Суу ресурстары, айыл чарба жана кайра иштетүү өнөр-жай "
      "министрлигинин Ветеринария, мал чарбасын өнүктүрүү жана тоют кызматынын Ала-Бука райондук башкармалыгы",
      "с.Ала-Бука, ул. С.Ибраимова №85", ["03741 5-01-62", "+996 700150877"], "пн-пт 08:30-17:30",
      leader=True, lang="ky"),
    # --- a5: Сузак (дополнения «нет совсем» к уже существующим организациям) --------
    E("a5", "v4-org-2f50301a45d334", "Сузакское районное управление Социального фонда",
      "с.Сузак, ул. Д.Палвана, 3", ["0374850090", "50044"], "пн-пт 09:00-18:00; обед 12:30-13:30", note="a5:☐ Соцфонд"),
    E("a5", "v4-org-a93b81ab540e08", "Межрегиональный отдел Департамента регистрации населения 04-07 (ЦОН)",
      "с.Сузак, ул. Тиллабаева", ["0374850135"], "пн-пт 09:00-18:00; обед 12:30-13:30", note="a5:☐ ЦОН"),
    # --- a6: Аксы ----------------------------------------------------------
    E("a6", "v4-org-e329fa8d7e0c6a", "А.Кутманов атындагы Жалал-Абад облусунун Аксы районунун ЖДПБ",
      "г.Кербен, ул. Уметалиева №148", ["0 (3742)"], "08:30-17:30"),
    E("a6", "v2-org-1b3fb775fcfd", "Аксы райондук мамлекеттик администрациясы",
      "г.Кербен, ул. Ныязалы-235", [], "09:00-18:00"),
    E("a6", "org-zher-agenttiginin-aksy-filialy-e525528", "Жер агенттигинин Аксы филиалы",
      "г.Кербен, ул. Ныязалы-36", ["0 3742 50085", "0 (3742) 50080"], "08:30-17:30",
      note="a6: «Г\\У Кадастр» (Ныязалы-36, 50080) = тот же филиал: адрес совпал с v4"),
    E("a6", "org-kyrgyz-respublikasynyn-finansy-ministrliginin-aksy-raionduk-finan-575b807",
      "Кыргыз Республикасынын Финансы министрлигинин Аксы райондук финансы башкармалыгы",
      None, ["03742 50021"], "09:00-18:00"),
    E("a6", None, "Мэрия города Кербен", "г.Кербен, ул. Ныязалы-47", ["03742 50207"], None,
      terr="city:Кербен", lang="ru"),
    E("a6", None, "МП «Жашылдандыруу жана көрктөндүрүү»", "г.Кербен, ул. Б.Бейшеналиева б/н", [], "08:30-17:30",
      terr="city:Кербен", lang="ky"),
    E("a6", None, "МП «Кербен сууканал»", "г.Кербен, ул. Уметалиев-130", [], "08:30-17:30",
      terr="city:Кербен", lang="ky", note="в ответе «г. ул. Уметалиев- 130» — название города пропущено, раздел Кербен"),
    E("a6", None, "Айыл окмоту айылного аймака Сары-Челек", "с.Авлетим, ул. Стамкулов-61", [], "08:30-17:30",
      lang="ru", aliases=["Сары-Челек а/о"]),
    E("a6", None, "МП «Сары-Челек»", "с.Авлетим, ул. Стамкулов-61", [], "08:30-17:30", lang="ky"),
    E("a6", None, "Айыл окмоту айылного аймака Кара-Камыш", "с.Кара-Жыгач, ул. Шерипбаев-31", [], "08:30-17:30",
      lang="ru", aliases=["Кара-Камыш а/о"]),
    E("a6", None, "МП «Жашыл-Өрөөн»", "с.Кара-Жыгач, ул. Шерипбаев-31", [], "08:30-17:30", lang="ky"),
    E("a6", None, "Айыл окмоту айылного аймака Ак-Жол", "с.Жаңы-Жол, ул. Мырзабек-Болуш-1", [], "08:30-17:30",
      lang="ru", aliases=["Ак-Жол а/о"]),
    E("a6", None, "МП «Малкалды»", "с.Жаңы-Жол, ул. Мырзабек-Болуш-2", [], "08:30-17:30", lang="ky"),
    E("a6", None, "Айыл окмоту айылного аймака Ак-Суу", "с.Ак-Суу, ул. Добулбеков-3", [], "08:30-17:30",
      lang="ru", aliases=["Ак-Суу а/о"]),
    E("a6", None, "МП «Ак-Суу»", "с.Ак-Суу, ул. Добулбеков-3", [], "08:30-17:30", lang="ky"),
    E("a6", None, "Айыл окмоту айылного аймака Үч-Коргон", "с.Нарын, ул. Мешков-9", [], "08:30-17:30",
      lang="ru", aliases=["Үч-Коргон а/о"]),
    E("a6", None, "МП «Үч-Коргон Ак-Ниет»", "с.Нарын, ул. Мешков-9", [], "08:30-17:30", lang="ky"),
    E("a6", None, "Айыл окмоту айылного аймака Кош-Добо", "с.Атана, ул. Чыныбек болуш-17", [], "08:30-17:30",
      lang="ru", aliases=["Кош-Добо а/о"]),
    E("a6", None, "МП «Тазалык» (Кош-Добо)", "с.Атана, ул. Чыныбек болуш-17", [], "08:30-17:30", lang="ky"),
    E("a6", None, "Аксы РЭС", "г.Кербен, ул. Нарбаева б/н", ["50040"], "08:30-17:30", terr="city:Кербен", lang="ru"),
    E("a6", None, "ДЭП-12", "г.Кербен, ул. Эркиндик №5", ["0 (3742) 5-00-85"], "08:00-17:00",
      terr="city:Кербен", lang="ru"),
    E("a6", None, "Управление по градостроительству и архитектуре (Аксы)", "г.Кербен, ул. Жени-Жок б/н",
      ["0 (3742) 50028"], "08:30-17:30", terr="city:Кербен", lang="ru"),
    E("a6", None, "Аксы райондук Социалдык фонд башкармалыгы", "г.Кербен, ул. Уметалиева №154",
      ["0 (3742) 5-00-12"], "09:00-18:00", terr="city:Кербен", lang="ky"),
    E("a6", None, "Управление труда, социального обеспечения и миграции (Аксы)", "г.Кербен, ул. Уметалиев-147",
      ["0(3742) 5-02-82"], "09:00-18:00", terr="city:Кербен", lang="ru"),
    E("a6", None, "Центр обслуживания населения (Аксы)", "г.Кербен, ул. Уметалиев-122", [], "09:00-18:00",
      terr="city:Кербен", lang="ru"),
    E("a6", None, "Отдел внутренних дел (Аксы)", "г.Кербен, ул. Уметалиев-132", ["0 (3742) 50404"], "09:00-18:00",
      terr="city:Кербен", lang="ru"),
    E("a6", None, "Отдел образования (Аксы)", "г.Кербен, ул. Уметалиев-145", ["0 (3742) 50290"], None,
      terr="city:Кербен", lang="ru"),
    E("a6", None, "УГНС по Аксыйскому району", "г.Кербен, ул. Уметалиева 146", ["0 (3742) 5-04-14"], "09:00-18:00",
      terr="city:Кербен", lang="ru"),
    E("a6", None, "Управление ветеринарии, развития животноводства, пастбищ и кормов (Аксы)",
      "г.Кербен, ул. Уметалиев №79", ["0 (3742) 6-05-38"], "08:30-17:30", terr="city:Кербен", lang="ru"),
    # --- a7: Базар-Коргон — «нет совсем» ----------------------------------------
    E("a7", None, "Базар-Коргон райондук №50 жол тейлөө ишканасы", "г.Базар-Коргон, трасса «Бишкек-Ош 545»",
      ["0704 535 654"], "09:00-18:00", terr="city:Базар-Коргон", lang="ky"),
    E("a7", None, "Кыргыз Республикасынын Министрлер Кабинетине караштуу Жер ресурстары, кадастр, геодезия жана "
      "картография боюнча мамлекеттик агенттигинин Базар-Коргон филиалы", "г.Базар-Коргон, ул. Б.Осмонов №85",
      ["0776 135 977"], "09:00-18:00", terr="city:Базар-Коргон", lang="ky"),
    E("a7", None, "Базар-Коргон райондук социалдык фонд башкармалыгы", "г.Базар-Коргон, ул. Сайдуллаев (номер дома не указан)",
      ["0773 708 085"], "09:00-18:00", terr="city:Базар-Коргон", lang="ky"),
    E("a7", None, "Базар-Коргон райондук эмгек, социалдык камсыздоо жана миграция башкармалыгы",
      "г.Базар-Коргон, ул. К.Култаев №2", ["0775 860 000"], "08:30-17:30", terr="city:Базар-Коргон", lang="ky"),
    E("a7", None, "Калкты жана жарандык абалдын актыларын каттоо департаментинин 04-03 регионалдык бөлүмү",
      "г.Базар-Коргон, ул. О.Курбанов №66", ["0771 453 045"], "08:30-17:30", terr="city:Базар-Коргон", lang="ky"),
    E("a7", None, "Базар-Коргон райондук билим берүү бөлүмү", "г.Базар-Коргон, ул. Б.Осмонов №89",
      ["0557 151 565"], "08:30-17:30", terr="city:Базар-Коргон", lang="ky"),
    E("a7", None, "Базар-Коргон райондук ички иштер бөлүмү (РОВД)", "г.Базар-Коргон, ул. Б.Осмонов №126",
      ["0707 262 527"], "08:30-17:30", terr="city:Базар-Коргон", lang="ky"),
    E("a7", None, "Базар-Коргон райондук ветеринария, мал чарбасын өнүктүрүү, жайыт жана тоют башкармалыгы",
      "г.Базар-Коргон, ул. Б.Осмонов №48", ["0508 120 405"], "08:30-17:30", terr="city:Базар-Коргон", lang="ky"),
    # --- a8: Манас — «нет совсем» ------------------------------------------------
    E("a8", None, "Жалал-Абад регионалдык шаар куруу жана архитектура башкармалыгы (Кыргыз Республикасынын "
      "курулуш, архитектура жана турак жай-коммуналдык чарба министрлигинин шаар куруу жана архитектура "
      "департаментинин)", "г.Манас, ул. Железнодорожная №123", ["(3722) 7-00-68"], None, lang="ky"),
    E("a8", None, "Центр обслуживания населения №04-04 (ЦОН г. Манас)", "г.Манас, ул. Барпы Алыкулова №1",
      ["(3722) 2-49-94"], "пн-пт 09:00-18:00", lang="ru",
      aliases=["«Кызмат» мамлекеттик мекемеси 04-04 калкты тейлөө борбору",
               "Государственное учреждение «Кызмат» при Управлении делами Президента КР"]),
    E("a8", None, "Манас шаардык билим берүү бөлүмү (Кыргыз Республикасынын агартуу министрлиги)",
      "г.Манас, ул. Ю.Абдрахманова №6", [], "08:30-17:30", lang="ky"),
    E("a8", None, "Манас шаардык ички иштер бөлүмү", "г.Манас, Эркиндик көчөсү №2 а", ["03722 5-28-31"], None, lang="ky"),
]

# поправки к автоматическому разбору: (файл, начало названия) -> поля
OVERRIDE = {
    ("a3", "Бүргөндү-Достук"): dict(address="с.Жаны Арык, ул. Турдалиева"),
    ("a3", "Шамалдуу Сай шаардык жалпы"): dict(org_id="v4-org-b95b67cdf62a3d"),
    ("a3", "Ноокен районунун Ш. Суеркулов"): dict(drop=["phone", "address"],
        drop_reason="телефон и адрес в ответе совпадают с районной администрацией (Турдумбетов 37, 5 00 12) — вероятно скопированы"),
    ("a3", "Айыл чарба башкармалыгы"): dict(rename="Айыл чарба башкармалыгы (Ноокен району)"),
    ("a3", "Ноокен райондук суу чарба"): dict(address="с.Масы, ул. К. Султанов (номер дома не указан)"),
    ("a5", "Учреждение “Отдел чрезвычайных ситуаций"): dict(org_id="v4-org-30968056c245b2"),
    ("a5", "Сузак РЭС"): dict(hours="пн-пт 08:00-17:00; обед 12:00-13:00; пт до 15:45", address="с.Сузак"),
    ("a5", "Кок-Арт РЭС"): dict(address="Кок-Артский а/а, ул. К.Маманова, 20"),
    ("a5", "Жалал-Абад облусунун Сузак районунун аймактык ооруканасы"):
        dict(hours="пн-пт 08:30-17:30; приёмное отделение круглосуточно"),
    ("a5", "Отдел внутренних дел Сузакского района"):
        dict(hours="пн-пт 08:30-17:30; дежурная часть круглосуточно"),
    ("a7", "Акман айыл өкмөтү"): dict(address="с.Бешик-Жон, ул. Айтмаматова Масабирова №7"),
    ("a7", "Арстанбап-Ата айыл өкмөтү"): dict(address="с.Ооган-Талаа, ул. Н.Кубаева №16"),
    ("a7", "Ачы электр тармактары"): dict(address="с.Чарбак, ул. Б.Борубаев №203"),
    ("a7", "Базар-Коргон райондук мамлекеттик администрациясы"): dict(address="г.Базар-Коргон, ул. Б.Осмонов №170"),
    ("a7", "МП «Арстанбап-Ата таза суу"): dict(address="с.Ооган-Талаа, ул. Укубаева №26"),
    ("a7", "Муниципальное учреждение футбольный клуб"): dict(address="ул. К.Бегимкулов"),
    ("a7", "Сайдыкум айыл өкмөтү"): dict(address="с.Кызыл-Ай, ул. С.Досова, дом 151Б"),
    ("a7", "“Акман” тазалык"): dict(address="с.Бешик-Жон, ул. Айтмаматова Масабирова №7"),
    ("a8", "Департамент коммунального хозяйства"): dict(address="ул. Эркиндик №56"),
    ("a8", "Манас шаарынын Ч. Айтматов"): dict(address="Эркиндик көчөсү №12"),
    ("a8", "Мэрия города Жалал-Абад"): dict(address="ул. Ю.Абдрахманова №6"),
    ("a8", "Мэрия города Манас"): dict(address="ул. Ю.Абдрахманова №6"),
    ("a8", "Управление водоканал Манас"): dict(address="ул. Стрелковая 1а"),
    ("a8", "Управление городских дорог"): dict(hours="08:30-17:30", phones=[]),
    ("a8", "Управление земельных ресурсов"): dict(address="ул. Ю.Абдрахманова №6"),
    ("a8", "Манас Тазалык"): dict(address="Манас көчөсү №92"),
    ("a8", "«Кыргыз темир жолу»"): dict(address=None),
    ("a8", "“Кыргызтелеком” ААК"): dict(address=None),
}

# организации, у которых один и тот же номер — законно (одна и та же служба / здание)
SAME_ENTITY = [
    {"org-kyrgyz-respublikasynyn-finansy-ministrliginin-bazar-korgon-raiond-d9a3f32", "v2-org-79d4092e592e"},
    {"v2-org-40f9dc13ca74", "org-meriya-goroda-manas-a76baa9"},      # мэрия Жалал-Абад = мэрия Манас
    {"org-mamlekttik-salyk-kyzmatynyn-zhalal-abad-oblusunun-suzak-raionu-bo-abbf5bc", "v4-org-510e970604f0f1"},  # налоговая Сузак (две записи v4)
    {"org-nookenskii-otdel-gosudarstvennogo-tsentra-po-registratsii-transpo-a2da63d", "v2-org-9327932466b8"},    # транспорт каттоо Ноокен (две записи v4)
]
# города по умолчанию, чтобы отличить территорию организации
EMERG_OK = {"102", "103", "101", "112"}


# ----------------------------------------------------------------------------
# загрузка v4
# ----------------------------------------------------------------------------
def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").split("\n") if l.strip()]


def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hid(*parts: str, n: int = 12) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:n]


ORGS = read_jsonl(V4 / "organizations.jsonl")
_pt = set()
for _t in read_jsonl(V4 / "territories.jsonl"):
    for _n in (_t.get("name_ru"), _t.get("name_ky")):
        _pt |= {w[:5] for w in re.findall(r"[^\W\d_]+", (_n or "").lower().replace("ё", "е").replace("ы", "и")) if len(w) > 2}
_pt |= {"масис", "масы", "бешик", "жон", "ооган", "талаа", "таала"}
PLACE_TOK = frozenset(_pt - {"токто"})   # улица Токтогула есть почти везде
CONTACTS = read_jsonl(V4 / "contacts.jsonl")
ORG_BY_ID = {o["organization_id"]: o for o in ORGS}
NAME_TO_ID: dict[str, str] = {}
for _o in ORGS:
    for _n in (_o.get("name_ru"), _o.get("name_ky"), _o.get("short_name_ru"), _o.get("short_name_ky"),
               *(_o.get("aliases_ru") or []), *(_o.get("aliases_ky") or [])):
        if _n:
            NAME_TO_ID.setdefault(norm(_n), _o["organization_id"])
V4_CONTACTS_BY_ORG: dict[str, list[dict]] = defaultdict(list)
for _c in CONTACTS:
    V4_CONTACTS_BY_ORG[_c["organization_id"]].append(_c)


def phone_key(raw: str) -> str | None:
    """Ключ для сравнения номеров: 0XXXXXXXXX (моб.) или 0 + код + 5 цифр."""
    d = digits(raw)
    if d.startswith("996") and len(d) in (12, 13):
        d = d[3:]
        if len(d) == 9:
            d = "0" + d
        elif d.startswith("0") and len(d) == 10:
            pass
    if len(d) == 9 and d[:4] in KNOWN_CODES:
        d = "0" + d
    return d if len(d) >= 9 else None


def city_parts(d: str) -> tuple[str, str] | None:
    if len(d) == 10 and d.startswith("0") and d[1:5] in KNOWN_CODES:
        return d[1:5], d[5:]
    return None


# префиксы (3 первых цифры из 5) известных номеров по городам: из v4 и из полных номеров в ответах
PREFIXES: dict[str, set[str]] = defaultdict(set)


def learn_prefix(raw: str) -> None:
    k = phone_key(raw)
    if k and city_parts(k):
        c, n = city_parts(k)
        PREFIXES[c].add(n[:3])


for _c in CONTACTS:
    if _c["type"] == "phone":
        learn_prefix(_c["value"])

# ----------------------------------------------------------------------------
# сбор записей из ответов
# ----------------------------------------------------------------------------
RAW: list[dict] = []
for f in sorted(SRC_FILE):
    if f in ("a3", "a5", "a7", "a8"):
        for name, body in entries_from_txt(f):
            p = parse_body(body)
            org_id = NAME_TO_ID.get(norm(name))
            ov = {}
            for (ff, pref), val in OVERRIDE.items():
                if ff == f and name.startswith(pref):
                    ov = val
            org_id = ov.get("org_id", org_id)
            name = ov.get("rename", name)
            addr = clean_address(p["address_raw"]) if "address" not in ov else ov["address"]
            hrs = ov.get("hours", p["hours"])
            phones = ov.get("phones", p["phones"])
            drop = ov.get("drop", [])
            RAW.append(dict(file=f, org_id=org_id, name=name, address=addr, phones=phones, hours=hrs,
                            terr=None, aliases=[], leader=False, lang=None, note=None, emergency=[],
                            drop=drop, drop_reason=ov.get("drop_reason"), manual=False))
# a5 «Сузакское предприятие электрических сетей» — ответа нет («данные выше»); a5 ☐-строки — в MANUAL
for m in MANUAL:
    m.setdefault("drop", [])
    m.setdefault("drop_reason", None)
    RAW.append(m)
# одиночные дубли в a5: «ветеринария» Сузак — две разные организации, остаются как есть

for r in RAW:
    for p in r["phones"]:
        learn_prefix(p) if phone_key(p) and city_parts(phone_key(p) or "") else None

# ----------------------------------------------------------------------------
# нормализация телефонов
# ----------------------------------------------------------------------------
HELD: list[dict] = []        # не опубликовано: причина
SUSPICIOUS = re.compile(r"(\d)\1{3,}")


def hold(r: dict, kind: str, value: str, reason: str) -> None:
    HELD.append(dict(file=r["file"], org=r["name"], org_id=r["org_id"], kind=kind, value=value, reason=reason))


def normalize_phones(r: dict) -> list[dict]:
    """-> [{value, verification, purpose}] публикуемые; остальное уходит в HELD."""
    raw_phones = [p for p in r["phones"]]
    keys = [phone_key(p) for p in raw_phones]
    entry_code = next((city_parts(k)[0] for k in keys if k and city_parts(k)), None)
    out = []
    for raw, k in zip(raw_phones, keys):
        d = digits(raw)
        if "phone" in r["drop"]:
            hold(r, "phone", raw, r["drop_reason"] or "исключён вручную")
            continue
        if k is None:
            if d.startswith("0") and d[1:] in KNOWN_CODES:
                hold(r, "phone", raw, "указан только код города, номера нет")
                continue
            if len(d) == 5 or len(d) == 6 or len(d) == 4:
                code = entry_code
                if len(d) == 5 and code:
                    out.append(dict(value=f"0{code} {d[0]}-{d[1:3]}-{d[3:]}", verification="NEEDS_CONFIRMATION",
                                    purpose="office_contact", derived=f"код {code} взят из соседнего номера этой же организации"))
                    continue
                if len(d) == 5:
                    code = FILE_CODE[r["file"]]
                    if d[:3] in PREFIXES[code]:
                        out.append(dict(value=f"0{code} {d[0]}-{d[1:3]}-{d[3:]}", verification="NEEDS_CONFIRMATION",
                                        purpose="office_contact",
                                        derived=f"код {code} по району; номерная ёмкость {d[:3]}xx встречается в справочнике"))
                        continue
                    hold(r, "phone", raw, f"номер без кода города (5 цифр); код {code} по району, но ёмкость {d[:3]}xx "
                                           f"в справочнике не встречается — не подтверждено")
                    continue
                hold(r, "phone", raw, "неполный номер (нет части цифр)")
                continue
            if len(d) == 3 and d in EMERG_OK:
                continue
            hold(r, "phone", raw, "не удалось разобрать номер")
            continue
        parts = city_parts(k)
        if parts:
            out.append(dict(value=f"0{parts[0]} {parts[1][0]}-{parts[1][1:3]}-{parts[1][3:]}",
                            verification="SOURCE_CONFIRMED", purpose="office_contact", derived=None))
            continue
        if len(k) == 10 and k[0] == "0" and k[1] in "2579" and not k.startswith("037"):
            if SUSPICIOUS.search(k[3:]):
                hold(r, "phone", raw, "подозрительный шаблон цифр (4 одинаковые подряд) — похоже на заглушку")
                continue
            if r["leader"]:
                hold(r, "phone", raw, "мобильный в строке «Руководитель:» — вероятно личный номер руководителя")
                continue
            out.append(dict(value=f"{k[:4]} {k[4:7]} {k[7:]}", verification="SOURCE_CONFIRMED",
                            purpose="office_contact", derived=None))
            continue
        if d.startswith("03222") or d.startswith("3222"):
            hold(r, "phone", raw, "код 03222 — это Ош, а не Жалал-Абад/Манас; номер не подтверждён")
            continue
        if d.startswith("03477"):
            hold(r, "phone", raw, "код 03477 не существует (в том же файле мэрия Майлуу-Суу — 03744); "
                                  "возможна опечатка, но не подтверждено")
            continue
        hold(r, "phone", raw, "нестандартный номер")
    for e in r.get("emergency", []):
        out.append(dict(value=e, verification="SOURCE_CONFIRMED", purpose="emergency_phone", derived=None))
    return out


for r in RAW:
    r["pub_phones"] = normalize_phones(r)

# ----------------------------------------------------------------------------
# дубли номеров между организациями
# ----------------------------------------------------------------------------
STOP = {"ш", "р", "н", "обл", "ул", "көчөсү", "кочосу", "г", "с", "шаары", "пр", "дом", "айылы", "шаар", "село", "город", "ку", "көчө"}


def addr_tokens(a: str | None) -> frozenset:
    a = re.sub(r"\d+-кабат", "", (a or "").lower().replace("ё", "е").replace("ы", "и"))
    toks = [t for t in re.findall(r"\d+|[^\W\d_]+", a) if t not in STOP]
    return frozenset(t if t.isdigit() else t[:5] for t in toks)


def addr_same(new: str | None, old: str | None) -> bool:
    """Тот же адрес (с точностью до записи). Новый без номера дома, но с той же улицей — тоже тот же."""
    tn, to = addr_tokens(new), addr_tokens(old)
    if not tn or not to:
        return False
    dn, do = {t for t in tn if t.isdigit()}, {t for t in to if t.isdigit()}
    if dn and do and not (dn <= do or do <= dn):
        return False
    if dn and not do:
        return False
    nn, no = tn - dn - PLACE_TOK, to - do - PLACE_TOK     # сравниваем названия улиц, не населённых пунктов
    return len(nn & no) >= 1


def addr_refines(new: str | None, old: str | None) -> bool:
    """Новый адрес уточняет старый (добавлен номер дома к той же улице)."""
    tn, to = addr_tokens(new), addr_tokens(old)
    do = {t for t in to if t.isdigit()}
    return bool(to) and not do and to <= tn


def addr_key(a: str | None) -> str:
    a = re.sub(r"\d+-кабат", "", a or "")
    a = re.sub(r"\b(ул|көчөсү|г|с|шаары|пр|дом)\b\.?", " ", a.lower())
    return norm(a)


def same_entity(a: dict, b: dict) -> bool:
    ia, ib = a["org_id"], b["org_id"]
    if ia and ia == ib:
        return True
    if ia and ib and any(ia in g and ib in g for g in SAME_ENTITY):
        return True
    return addr_same(a["address"], b["address"])


by_phone: dict[str, list[dict]] = defaultdict(list)
for r in RAW:
    for p in r["pub_phones"]:
        by_phone[digits(p["value"])].append(r)
v4_phone_owner: dict[str, set[str]] = defaultdict(set)
for _c in CONTACTS:
    if _c["type"] == "phone":
        k = phone_key(_c["value"])
        if k:
            v4_phone_owner[k].add(_c["organization_id"])

bad_phone: dict[tuple[int, str], str] = {}
for key, rs in by_phone.items():
    uniq = {id(x): x for x in rs}.values()
    uniq = list(uniq)
    clash = False
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            if not same_entity(uniq[i], uniq[j]):
                clash = True
    if clash:
        for x in uniq:
            bad_phone[(id(x), key)] = "один и тот же номер указан у разных организаций (" + "; ".join(
                sorted({y["name"][:40] for y in uniq if y is not x})) + ")"
    # номер уже числится за ДРУГОЙ организацией в v4
    owners = v4_phone_owner.get(phone_key(key) or "", set())
    for x in uniq:
        foreign = {o for o in owners if o != x["org_id"] and not any(o in g and x["org_id"] in g for g in SAME_ENTITY)
                   and not any(y["org_id"] == o and addr_same(x["address"], y["address"]) for y in RAW)}
        if foreign and (id(x), key) not in bad_phone:
            names = "; ".join((ORG_BY_ID[o].get("name_ru") or ORG_BY_ID[o].get("name_ky") or o)[:50] for o in sorted(foreign))
            bad_phone[(id(x), key)] = "номер в v4 числится за другой организацией: " + names

for r in RAW:
    keep = []
    for p in r["pub_phones"]:
        why = bad_phone.get((id(r), digits(p["value"])))
        if why:
            hold(r, "phone", p["value"], why)
        else:
            keep.append(p)
    r["pub_phones"] = keep

# ----------------------------------------------------------------------------
# сопоставление новых организаций с v4 (защита от дублей)
# ----------------------------------------------------------------------------
import difflib

ALL_NAMES = [(norm(n), o["organization_id"], n) for o in ORGS
             for n in (o.get("name_ru"), o.get("name_ky"), o.get("short_name_ru"), o.get("short_name_ky"),
                       *(o.get("aliases_ru") or []), *(o.get("aliases_ky") or [])) if n]


def best_candidates(name: str, k: int = 2):
    q = norm(name)
    sc = sorted(((difflib.SequenceMatcher(None, q, a).ratio(), oid, n) for a, oid, n in ALL_NAMES), reverse=True)
    out, seen = [], set()
    for ratio, oid, n in sc:
        if oid in seen:
            continue
        seen.add(oid)
        out.append((round(ratio, 2), oid, n))
        if len(out) >= k:
            break
    return out


CAND_NOTES = []
for r in RAW:
    if r["org_id"] is None:
        c = best_candidates(r["name"])
        CAND_NOTES.append((r["file"], r["name"], c))
        if c and c[0][0] >= 0.93:
            print(f"ПРОВЕРИТЬ возможный дубль в v4: {r['name'][:60]} ~ {c[0]}")

# ----------------------------------------------------------------------------
# построение записей
# ----------------------------------------------------------------------------
JUNK = re.compile(r"\bТел\b", re.I)          # в адресе v4 затесался телефон
KY_LETTERS = re.compile(r"[өүң]", re.I)
KY_WORDS = re.compile(r"(башкармалыгы|бөлүмү|айыл өкмөтү|ишканасы|борбору|мекемеси|министрлиги)", re.I)


def guess_lang(name: str) -> str:
    return "ky" if (KY_LETTERS.search(name) or KY_WORDS.search(name)) else "ru"


def prov(r: dict, locator: str) -> list[dict]:
    return [dict(source_id=SRC_ID[r["file"]], source_file=SRC_FILE[r["file"]], source_type="docx",
                 source_language="ru", document_date=DATE, issuer=ISSUER, extracted_at=DATE,
                 verification_status="SOURCE_CONFIRMED", page=None, sheet=None, locator=locator,
                 fact_status="SOURCE_FACT")]


NEW_ORGS: list[dict] = []
NEW_CONTACTS: list[dict] = []
SUPERSEDED: list[dict] = []
DISCREPANCIES: list[dict] = []      # адрес/часы: старое -> новое
EXTRA_PHONES: list[dict] = []       # у организации уже был другой номер
CONFIRMED: Counter = Counter()      # совпало с v4
STATS = Counter()
org_terr_cache: dict[str, str] = {}


def org_terr(r: dict, oid: str) -> str:
    if r.get("terr"):
        return r["terr"]
    o = ORG_BY_ID.get(oid)
    if o:
        for t in (o.get("territory") or []):
            if not str(t).startswith("region:") and t != "city:гак":
                return t
        if o.get("territory_id"):
            return o["territory_id"]
        for c in V4_CONTACTS_BY_ORG.get(oid, []):
            if c.get("territory_id") and not str(c["territory_id"]).startswith("region:"):
                return c["territory_id"]
    return FILE_TERR[r["file"]]


def time_set(s: str) -> tuple:
    """Первые два времени (начало и конец рабочего дня), HH:MM."""
    ts = re.findall(r"(\d{1,2})\s*[:/]\s*(\d{2})", s or "")
    return tuple(f"{int(h):02d}:{m}" for h, m in ts[:2])


def mk_contact(r: dict, oid: str, ctype: str, value: str, terr: str, purpose: str, verification: str,
               locator: str, extra: dict | None = None) -> dict:
    c = dict(contact_id=f"v5-contact-{hid(oid, ctype, value)}", organization_id=oid, type=ctype,
             contact_type=ctype, value=value, purpose=purpose, territory_id=terr,
             source_ids=[SRC_ID[r["file"]]], provenance=prov(r, locator),
             verification_status=verification, pilot_status="SOURCE_CONFIRMED" if verification == "SOURCE_CONFIRMED" else verification,
             status="SOURCE_CONFIRMED" if verification == "SOURCE_CONFIRMED" else verification,
             visibility="PUBLIC", publication_status="PILOT_PUBLIC", fact_status="SOURCE_FACT")
    if ctype in ("working_hours", "reception_hours"):
        c["working_hours"] = value
    else:
        c["working_hours"] = None
    if ctype == "address":
        c["address_kind"] = "office_address"
    if extra:
        c.update(extra)
    return c


used_ids: set[str] = set()
NEW_BY_ORG: dict[str, list[dict]] = defaultdict(list)
contacts_out = [dict(c) for c in CONTACTS]
by_id = {c["contact_id"]: c for c in contacts_out}


def add_contact(c: dict) -> bool:
    if c["contact_id"] in used_ids:
        return False
    for o in NEW_BY_ORG[c["organization_id"]]:       # то же самое уже добавлено из другого пункта ответа
        if o["type"] == c["type"] == "address" and addr_same(c["value"], o["value"]):
            return False
        if o["type"] == c["type"] == "working_hours" and time_set(c["value"]) == time_set(o["value"]) \
                and c["value"].split(";")[0] == o["value"].split(";")[0]:
            return False
    used_ids.add(c["contact_id"])
    NEW_BY_ORG[c["organization_id"]].append(c)
    NEW_CONTACTS.append(c)
    return True


for r in RAW:
    oid = r["org_id"]
    new_org = oid is None
    if new_org:
        lang = r["lang"] or guess_lang(r["name"])
        terr = r.get("terr") or FILE_TERR[r["file"]]
        oid = f"v5-org-{hid(r['file'], r['name'])}"
        r["org_id"] = oid
        rec = dict(organization_id=oid, name_ru=r["name"] if lang == "ru" else None,
                   name_ky=r["name"] if lang == "ky" else None, short_name_ru=None, short_name_ky=None,
                   aliases_ru=list(r["aliases"]) if lang == "ru" else [],
                   aliases_ky=list(r["aliases"]) if lang == "ky" else [],
                   translation_status="missing", organization_type="source_named", parent_organization_id=None,
                   territory=[terr], territory_id=terr, territory_status="SOURCE_CONTEXT", status="SOURCE_CONFIRMED",
                   source_ids=[SRC_ID[r["file"]]], provenance=prov(r, f"answer:{r['name'][:60]}"),
                   verification_status="SOURCE_CONFIRMED", fact_status="SOURCE_FACT",
                   pilot_status="SOURCE_CONFIRMED", visibility="PUBLIC")
        NEW_ORGS.append(rec)
        STATS["new_orgs"] += 1
        STATS[f"new_orgs:{terr}"] += 1
    terr = org_terr(r, oid)
    loc = f"answer:{r['name'][:60]}"
    existing = V4_CONTACTS_BY_ORG.get(oid, [])
    live = [c for c in existing if c.get("visibility", "PUBLIC") == "PUBLIC"]

    # --- адрес -----------------------------------------------------------
    addr = None if "address" in r["drop"] else r["address"]
    if "address" in r["drop"] and r["address"]:
        hold(r, "address", r["address"], r["drop_reason"] or "исключён вручную")
    if addr:
        old = [c for c in live if c["type"] == "address" and c.get("purpose") != "legal_address"]
        if old and any(addr_same(addr, c["value"]) and not JUNK.search(c["value"]) for c in old):
            CONFIRMED["address"] += 1
        else:
            for c in old:
                sup = by_id[c["contact_id"]]
                sup["status"] = "SUPERSEDED"
                sup["visibility"] = "INTERNAL_ONLY"
                sup["superseded_by"] = None
                DISCREPANCIES.append(dict(file=r["file"], org=r["name"], org_id=oid, kind="address",
                                          type="уточнение" if (addr_refines(addr, c["value"]) or JUNK.search(c["value"])) else "изменение",
                                          old=c["value"], new=addr, old_contact_id=c["contact_id"]))
            nc = mk_contact(r, oid, "address", addr, terr, "office_address", "SOURCE_CONFIRMED", loc)
            if add_contact(nc):
                for c in old:
                    by_id[c["contact_id"]]["superseded_by"] = nc["contact_id"]
                STATS["address"] += 1
    # --- часы ------------------------------------------------------------
    hrs = None if "hours" in r["drop"] else r["hours"]
    if hrs:
        old = [c for c in live if c["type"] == "working_hours"]
        if old and any(time_set(hrs) == time_set(c["value"]) for c in old):
            CONFIRMED["hours"] += 1
        else:
            for c in old:
                sup = by_id[c["contact_id"]]
                sup["status"] = "SUPERSEDED"
                sup["visibility"] = "INTERNAL_ONLY"
                DISCREPANCIES.append(dict(file=r["file"], org=r["name"], org_id=oid, kind="working_hours",
                                          type="изменение", old=c["value"], new=hrs, old_contact_id=c["contact_id"]))
            nc = mk_contact(r, oid, "working_hours", hrs, terr, "office_contact", "SOURCE_CONFIRMED", loc)
            if add_contact(nc):
                for c in old:
                    by_id[c["contact_id"]]["superseded_by"] = nc["contact_id"]
                STATS["working_hours"] += 1
    # --- телефоны --------------------------------------------------------
    old_phones = [c for c in live if c["type"] == "phone"]
    old_keys = {phone_key(c["value"]) for c in old_phones}
    for p in r["pub_phones"]:
        k = phone_key(p["value"])
        if k in old_keys:
            CONFIRMED["phone"] += 1
            continue
        tail = [c for c in old_phones if phone_key(c["value"]) is None and len(digits(c["value"])) == 5
                and k and city_parts(k) and digits(c["value"]) == city_parts(k)[1]]
        for c in tail:        # в v4 тот же номер был без кода города — заменяем полным
            sup = by_id[c["contact_id"]]
            sup["status"] = "SUPERSEDED"
            sup["visibility"] = "INTERNAL_ONLY"
            DISCREPANCIES.append(dict(file=r["file"], org=r["name"], org_id=oid, kind="phone", type="уточнение",
                                      old=c["value"], new=p["value"], old_contact_id=c["contact_id"]))
        extra = {"derived_note": p["derived"]} if p["derived"] else None
        nc = mk_contact(r, oid, "phone", p["value"], terr, p["purpose"], p["verification"], loc, extra)
        if add_contact(nc):
            STATS["phone"] += 1
            if p["verification"] == "NEEDS_CONFIRMATION":
                STATS["phone_needs_confirmation"] += 1
            if old_phones and p["purpose"] != "emergency_phone":
                EXTRA_PHONES.append(dict(file=r["file"], org=r["name"], org_id=oid, old=[c["value"] for c in old_phones],
                                         new=p["value"]))

# ----------------------------------------------------------------------------
# запись v5
# ----------------------------------------------------------------------------
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
for p in V4.iterdir():
    shutil.copy2(p, OUT / p.name)

# общие русские названия для новых организаций с кыргызскими/короткими названиями:
# без них поиск «отдел образования Ала-Бука» не находит «Ала-Бука райондук билим берүү бөлүмү»
GENERIC_RU = [   # (шаблон названия, основное русское название, синонимы для поиска)
    (r"билим берүү|отдел образования", "Отдел образования", ["школа", "образование"]),
    (r"ички иштер|внутренних дел|ровд", "Отдел внутренних дел", ["милиция", "ОВД", "полиция"]),
    (r"социалдык фонд|социального фонда", "Социальный фонд", ["соцфонд", "пенсия"]),
    (r"эмгек, социалдык камсыздоо|труда, социального обеспечения", "Управление труда, социального обеспечения и миграции", ["соцзащита", "пособия"]),
    (r"шаар куруу жана архитектура|градостроительству и архитектуре", "Управление градостроительства и архитектуры", ["архитектура"]),
    (r"электр тармактары|\bрэс\b", "Электросети", ["РЭС", "электричество", "свет"]),
    (r"жол эксплуатациялоо|жол тейлөө|\bдэп\b|дорожно-эксплуатационн", "Дорожно-эксплуатационное предприятие", ["дороги", "ремонт дорог"]),
    (r"ветеринария|ветеринарии", "Управление ветеринарии", ["ветеринар", "скот"]),
    (r"угнс|салык", "Налоговая служба", ["налоговая", "УГНС"]),
    (r"жер ресурстары|кадастр", "Земельные ресурсы и кадастр", ["земля", "кадастр"]),
    (r"статистика", "Отдел статистики", ["статистика"]),
    (r"суу чарба", "Управление водного хозяйства", ["вода", "ирригация"]),
    (r"айыл чарба башкармалыгы", "Управление сельского хозяйства", ["сельское хозяйство"]),
    (r"калкты тейлөө|обслуживания населения", "Центр обслуживания населения", ["ЦОН", "паспорта", "справки"]),
    (r"каттоо департаментин", "Регистрация населения и актов гражданского состояния", ["ЗАГС", "паспорта"]),
]
for rec in NEW_ORGS:
    nm = (rec.get("name_ru") or rec.get("name_ky") or "").lower()
    place = rec["territory_id"].split(":", 1)[1]
    mains, syns = [], []
    for pat, main, sy in GENERIC_RU:
        if re.search(pat, nm):
            mains.append(f"{main} {place}")
            syns += [f"{x} {place}" for x in sy]
    if mains:
        rec["aliases_ru"] = list(dict.fromkeys([*rec["aliases_ru"], *mains, *syns]))
        rec["aliases_generated"] = "generic_ru_by_keyword"

write_jsonl(OUT / "organizations.jsonl", ORGS + NEW_ORGS)
write_jsonl(OUT / "contacts.jsonl", contacts_out + NEW_CONTACTS)

k4 = json.loads((V4 / "knowledge_manifest.json").read_text(encoding="utf-8"))
s4 = json.loads((V4 / "structured_manifest.json").read_text(encoding="utf-8"))
files_k = {name: sha256(OUT / name) for name in k4["files"]}
digest = hashlib.sha256(json.dumps(files_k, sort_keys=True).encode()).hexdigest()[:16]
k5 = dict(k4)
k5["knowledge_version"] = digest
k5["files"] = files_k
k5["based_on"] = k4["knowledge_version"]
k5["admin_answers_source_ids"] = sorted(SRC_ID.values())
k5["organizations_count"] = len(ORGS) + len(NEW_ORGS)
k5["contacts_count"] = len(contacts_out) + len(NEW_CONTACTS)
(OUT / "knowledge_manifest.json").write_text(json.dumps(k5, ensure_ascii=False, indent=2), encoding="utf-8")
s5 = dict(s4)
s5["knowledge_version"] = digest
s5["files"] = {name: sha256(OUT / name) for name in s4["files"]}
(OUT / "structured_manifest.json").write_text(json.dumps(s5, ensure_ascii=False, indent=2), encoding="utf-8")

write_jsonl(HERE / "held_back.jsonl", HELD)
write_jsonl(HERE / "changes.jsonl", [dict(change="discrepancy", **d) for d in DISCREPANCIES]
            + [dict(change="extra_phone", **d) for d in EXTRA_PHONES])

# ----------------------------------------------------------------------------
# отчёт
# ----------------------------------------------------------------------------
TERR_NAME = {t["territory_id"]: (t.get("name_ru") or t.get("name_ky") or t["territory_id"])
             for t in read_jsonl(V4 / "territories.jsonl")}


def md_table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in row) + " |")
    return "\n".join(out)


answered = Counter(r["file"] for r in RAW)
n_by_type = Counter(c["type"] for c in NEW_CONTACTS)
orgs_by_terr = Counter(o["territory_id"] for o in NEW_ORGS)
rep = [f"# Отчёт сборки справочника v5 ({DATE})", "",
       f"Основа: v4 `{k4['knowledge_version']}` -> v5 `{digest}`. Источники: ответы администрации a1..a8 "
       f"(`admin_answers/`), id `ADM-{DATE}-aN`.", "",
       "## Итоги", "",
       md_table(["Показатель", "Значение"], [
           ["Ответов обработано (организаций/пунктов)", len(RAW)],
           ["…из них к существующим организациям v4", len(RAW) - len(NEW_ORGS)],
           ["…новых организаций", len(NEW_ORGS)],
           ["Добавлено контактов всего", len(NEW_CONTACTS)],
           *[[f"…тип {t}", n] for t, n in sorted(n_by_type.items())],
           ["…из них телефоны с дописанным кодом (NEEDS_CONFIRMATION)", STATS["phone_needs_confirmation"]],
           ["Совпало с v4 (подтверждено, не дублировали)", f"адрес {CONFIRMED['address']}, часы {CONFIRMED['hours']}, телефон {CONFIRMED['phone']}"],
           ["Расхождения адрес/часы (старое -> SUPERSEDED), из них реальных изменений", f"{len(DISCREPANCIES)}, изменений {sum(1 for d in DISCREPANCIES if d['type'] == 'изменение')}, уточнений {sum(1 for d in DISCREPANCIES if d['type'] == 'уточнение')}"],
           ["Не опубликовано (см. ниже)", len(HELD)],
           ["Организаций в v5", len(ORGS) + len(NEW_ORGS)],
           ["Контактов в v5 (вкл. SUPERSEDED)", len(contacts_out) + len(NEW_CONTACTS)],
       ]), "",
       "## Ответы по файлам", "",
       md_table(["Файл", "Исходное имя", "Пунктов", "Новых организаций"],
                [[k, SRC_FILE[k], answered[k], sum(1 for o in NEW_ORGS if o["source_ids"] == [SRC_ID[k]])]
                 for k in sorted(SRC_FILE)]), "",
       "## Новые организации по территориям", "",
       md_table(["Территория", "Новых организаций"],
                [[TERR_NAME.get(t, t), n] for t, n in sorted(orgs_by_terr.items(), key=lambda x: -x[1])]), "",
       "## Расхождения с v4 (адрес/часы: новое значение администрации приоритетно, старое — SUPERSEDED, INTERNAL_ONLY)", ""]
rep.append(md_table(["Файл", "Организация", "Поле", "Тип", "Было (v4)", "Стало (ответ)"],
                    [[d["file"], d["org"][:70], d["kind"], d["type"], d["old"], d["new"]] for d in DISCREPANCIES]) if DISCREPANCIES
           else "Расхождений нет.")
rep += ["", "## Организации, у которых уже был другой телефон (новый добавлен, старый оставлен)", ""]
rep.append(md_table(["Файл", "Организация", "Был в v4", "Добавлен"],
                    [[d["file"], d["org"][:70], "; ".join(d["old"]), d["new"]] for d in EXTRA_PHONES]) if EXTRA_PHONES
           else "Нет.")
rep += ["", "## Не опубликовано / сомнительное (всё в `held_back.jsonl`)", "",
        md_table(["Файл", "Организация", "Поле", "Значение", "Причина"],
                 [[h["file"], h["org"][:70], h["kind"], h["value"], h["reason"]] for h in HELD]) if HELD else "Нет.", ""]
rep += ["## Дописанные коды города (NEEDS_CONFIRMATION, опубликованы)", "",
        md_table(["Файл", "Организация", "Номер", "Основание"],
                 [[r["file"], r["name"][:70], p["value"], p["derived"]] for r in RAW for p in r["pub_phones"] if p["derived"]]), "",
        "## Проверка на дубли новых организаций с v4 (ближайшие названия)", "",
        md_table(["Файл", "Новая организация", "Ближайшая в v4", "Сходство"],
                 [[f, n[:70], (c[0][2][:70] if c else ""), (c[0][0] if c else "")] for f, n, c in CAND_NOTES]), ""]
(HERE / "REPORT_V5.md").write_text("\n".join(rep), encoding="utf-8")
print(json.dumps(dict(version=digest, new_orgs=len(NEW_ORGS), new_contacts=len(NEW_CONTACTS), types=n_by_type,
                      discrepancies=len(DISCREPANCIES), held=len(HELD)), ensure_ascii=False, default=dict))
