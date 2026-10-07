"""Build a conservative knowledge corpus from indexed, extracted local sources."""
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
sources = [json.loads(s) for s in (OUT / "machine/sources.jsonl").read_text(encoding="utf-8").splitlines()]
extracted = [json.loads(s) for s in (OUT / ".extracted.jsonl").read_text(encoding="utf-8").splitlines()]
S = {s["source_id"]: s for s in sources}
E = {e["source_id"]: e for e in extracted}

# Only dates and issuers visible in the supplied text are asserted here.
known_metadata = {
    "SRC-088": ("2017-05-04", None, "official_law"),
    "SRC-074": ("2025-10-23", "Кыргыз Республикасынын Өзгөчө кырдаалдар министрлиги", "official_order_attachment"),
    "SRC-090": ("2026-07-17", "Кыргыз Республикасынын Финансы министрлиги", "official_order_attachment"),
    "SRC-103": ("2022-08-09", "ОАО «Национальная электрическая сеть Кыргызстана»", "official_organization_provision"),
}
known_numbers = {"SRC-088": "73", "SRC-074": "731", "SRC-090": "402/л", "SRC-103": "Протокол 10"}
for s in sources:
    sid = s["source_id"]
    s["publication_status"] = "NEEDS_REVIEW"
    if sid in known_metadata:
        s["document_date"], s["issuer"], s["authority_level"] = known_metadata[sid]
        s["document_number"] = known_numbers[sid]
    elif sid == "SRC-001": s["authority_level"] = "project_specification"
    elif sid == "SRC-006": s["authority_level"] = "secondary_project_audit"
    elif sid in ("SRC-109", "SRC-225"): s["authority_level"] = "institutional_compilation_unapproved"
    elif s["file_type"] == "docx" and (s["container_archive"] in ("Документы_Word.zip", "Документы_Word_2_часть1.zip")):
        s["authority_level"] = "official_candidate"

def write_jsonl(name, rows):
    with (OUT / "machine" / name).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def norm(v):
    v = re.sub(r"\s+", " ", v or "").strip(" ._\u00a0")
    return v.replace("« ", "«").replace(" »", "»")

trans = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщьыъэюяөүң",
    ["a","b","v","g","d","e","e","zh","z","i","i","k","l","m","n","o","p","r","s","t","u","f","kh","ts","ch","sh","shch","","y","","e","yu","ya","o","u","n"]
))
def slug(v):
    v = norm(v).lower()
    base = "".join(trans.get(c, c) for c in v)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:65].strip("-") or "entity"
    return base + "-" + hashlib.sha1(v.encode()).hexdigest()[:7]

def prov(sid, locator, lang=None):
    s = S[sid]
    p = {"source_id": sid, "source_file": s["source_file"], "source_type": s["file_type"], "source_language": lang or s["language"], "document_date": s["document_date"], "issuer": s["issuer"], "extracted_at": "2026-09-25", "fact_status": "SOURCE_FACT", "verification_status": "verified"}
    if locator.startswith("sheet:"):
        _, sheet, _, row = locator.split(":", 3)
        p.update({"sheet": sheet, "row": int(row), "page": None})
    elif locator.startswith("page:"):
        p.update({"page": int(locator.split(":")[1]), "sheet": None, "locator": locator})
    else:
        p.update({"page": None, "sheet": None, "locator": locator})
    return p

orgs = []
org_by_name = {}
comps = []
contacts = []
aliases = []
conflicts = []
routes = []
qa_ky = []
qa_ru = []
chunks = []
gaps = []

def add_org(name, lang, sid, locator, org_type="unknown", address=None, duty=None, issue=None, duty_locator=None, address_locator=None):
    name = norm(name)
    if len(name) < 6 or "_____" in name or "мекеменин" == name.lower():
        return None
    key = (lang, name.casefold())
    org = org_by_name.get(key)
    if org is None:
        oid = "org-" + slug(name)
        org = {"organization_id": oid, "name_ru": name if lang == "ru" else None, "name_ky": name if lang == "ky" else None,
               "short_name_ru": None, "short_name_ky": None, "aliases_ru": [], "aliases_ky": [], "translation_status": "missing",
               "organization_type": org_type, "parent_organization_id": None, "territory": [], "territory_status": "NEEDS_CONFIRMATION",
               "status": "unknown", "source_ids": [sid], "fact_status": "SOURCE_FACT", "verification_status": "verified", "provenance": [prov(sid, locator, lang)]}
        orgs.append(org); org_by_name[key] = org
    else:
        if sid not in org["source_ids"]: org["source_ids"].append(sid)
        if not any(p["source_id"] == sid and p.get("locator") == locator for p in org["provenance"]): org["provenance"].append(prov(sid, locator, lang))
    if address and norm(address):
        val = norm(address)
        if len(val) >= 7 and "___" not in val:
            existing = [c for c in contacts if c["organization_id"] == org["organization_id"] and c["type"] == "address"]
            if all(c["value"].casefold() != val.casefold() for c in existing):
                contacts.append({"contact_id": "contact-" + slug(name + val), "organization_id": org["organization_id"], "type": "address", "value": val,
                                 "purpose": "office_address", "language": lang, "working_hours": None, "source_ids": [sid], "provenance": [prov(sid, address_locator or locator, lang)],
                                 "fact_status": "SOURCE_FACT", "verification_status": "verified", "publication_status": "NEEDS_REVIEW"})
                if existing:
                    conflicts.append({"conflict_id": f"CONFLICT-{len(conflicts)+1:03d}", "entity": name, "field": "address", "source_a": existing[0]["provenance"][0], "value_a": existing[0]["value"], "source_b": prov(sid, locator, lang), "value_b": val, "preferred_value": "UNKNOWN", "action": "Запросить подтверждение адреса и статуса подразделений у мэрии/ведомства."})
    if duty and norm(duty) and len(norm(duty)) >= 12:
        desc = norm(duty)
        if not any(c["organization_id"] == org["organization_id"] and c.get("description_ky" if lang == "ky" else "description_ru") == desc for c in comps):
            comps.append({"competence_id": "comp-" + slug(name + desc[:80]), "organization_id": org["organization_id"], "topic": "unknown", "description_ru": desc if lang == "ru" else None,
                          "description_ky": desc if lang == "ky" else None, "include_examples": [norm(issue)] if issue and len(norm(issue))<350 else [],
                          "exclude_examples": [], "territory": [], "territory_status": "NEEDS_CONFIRMATION", "legal_basis_source_ids": [],
                          "source_ids": [sid], "provenance": [prov(sid, duty_locator or locator, lang)], "fact_status": "SOURCE_FACT", "verification_status": "verified", "routing_verification_status": "needs_confirmation",
                          "required_citizen_information": []})
    return org

# Batch 1: the dedicated institution/duty tables. Table positions are explicit in their headers.
for sid, lang, start in [("SRC-225", "ky", 2), ("SRC-112", "ky", 2)]:
    for block in E[sid]["blocks"]:
        if not block["locator"].startswith("table:1:row:"): continue
        row = int(block["locator"].split(":")[-1])
        if row < start: continue
        cells = [norm(x) for x in block["text"].split(" | ")]
        if len(cells) < 5: continue
        name, address, duty, issue = cells[1:5]
        if not name or not duty: continue
        add_org(name, lang, sid, block["locator"], address=address, duty=duty, issue=issue)

# Batch 2: dedicated one-institution forms and structured supplemental sources.
b = E["SRC-002"]["blocks"][-1]
c = [norm(x) for x in b["text"].split(" | ")]
if len(c) >= 7: add_org(c[0], "ky", "SRC-002", b["locator"], duty=c[1], address=c[5])

for sid in [f"SRC-{i:03d}" for i in range(171,196)]:
    if sid not in E or E[sid]["status"] != "processed": continue
    blocks = E[sid]["blocks"]
    matches = [(i,b) for i,b in enumerate(blocks[:25]) if "Мекеменин толук аталышы:" in b["text"]]
    if not matches: continue
    i,b = matches[0]
    name = norm(b["text"].split("Мекеменин толук аталышы:",1)[1])
    if not name and i+1<len(blocks): name=norm(blocks[i+1]["text"])
    if sid == "SRC-176": name = name.split("Кыскартылган аталышы:",1)[0].strip()
    if sid == "SRC-180": name = (name + " " + norm(blocks[i+1]["text"])).replace("=", "")
    duty = None; duty_loc = None
    for bb in blocks[i+1:i+8]:
        if "Ишмердүүлүк тармагы" in bb["text"]:
            duty = norm(bb["text"].split(":",1)[-1]); duty_loc=bb["locator"]; break
    if sid == "SRC-178": duty = "Маданий-агартуу иштери: райондук маданий мекемелеринин ишин уюштуруу жана координациялоо."; duty_loc="page:1:line:5"
    if sid == "SRC-180": duty = "Жаныбарлардын жугуштуу жана жугушсуз ооруларын алдын алуу."; duty_loc="page:1:line:4"
    if sid == "SRC-193": duty = "Документтерди топтоо, эсепке алуу, ишенимдүү сактоо жана аларды коомдун муктаждыгы үчүн пайдалануу."; duty_loc="page:1:line:3"
    if name and not name.startswith("_"):
        add_org(name, "ky", sid, b["locator"], duty=duty, duty_locator=duty_loc)

manual = [
    ("SRC-124", "ru", "Жалал-Абадское региональное управление государственного архитектурно-строительного контроля (ГАСК) Минстроя КР", "page:1:line:1", "Надзор за качеством строительно-монтажных работ; выявление незаконного строительства и нарушений строительных норм; выдача разрешений на проведение строительных работ; участие в приеме объектов в эксплуатацию и контроль безопасности зданий.", "г.Манас ул. Эркиндик, 11"),
    ("SRC-145", "ru", "Мэрия города Кара-Куль", "page:1:line:19", "Орган местного управления городом Кара-Куль.", "г.Кара-Куль, ул. Ленина 1а"),
    ("SRC-159", "ru", "Муниципальное территориальное управление «Достук»", "paragraph:5", "Обеспечение общественного порядка на территории, контроль благоустройства и санитарного состояния, прием обращений граждан, координация решения местных проблем с городскими службами.", "г. Манас, ул Шопокова дом № 40"),
    ("SRC-165", "ru", "Управление городских дорог мэрии города Манас", "paragraph:1", "Строительство дорог; устройство асфальта и тротуара, гравийных дорог, ямочные работы.", "Город Манас, Улица Б.Осмонова 113"),
    ("SRC-167", "ru", "Управление земельных ресурсов мэрии города Манас", "paragraph:1", "Вопросы, связанные с муниципальными земельными участками, в том числе аренда и продление договоров аренды.", None),
    ("SRC-189", "ru", "Ноокенский отдел Государственного центра по регистрации транспортных средств и водительского состава", "page:1:line:5", "Вопросы регистрации транспортных средств и водительского состава, включая замену или утерю государственного номерного знака и водительского удостоверения.", "г.Кочкор-Ата ул.Токтогула"),
    ("SRC-217", "ky", "Жалал-Абад облустук дене тарбия жана спорт башкармалыгы", "paragraph:3", "Дене тарбия жана спорт тармагын уюштуруу жана координациялоо.", "Манас шаары Тоголок-Молдо 80/1"),
    ("SRC-191", "ky", "Чарбалык эсептеги муниципалдык «Суу канал» ишканасы", "paragraph:2", None, "Шамалдуу-Сай шаары Ленин көчөсү №29"),
    ("SRC-134", "ky", "Мамлекеттик камсыздандыруу уюмунун Жалал-Абад филиалы", "page:1:line:2", None, None),
]
duty_locs={"SRC-124":"page:1:line:3","SRC-145":"page:1:line:20","SRC-159":"paragraph:6","SRC-165":"paragraph:1","SRC-167":"paragraph:4","SRC-189":"page:1:line:18","SRC-217":"paragraph:4","SRC-191":"paragraph:3"}
address_locs={"SRC-124":"page:1:line:12","SRC-145":"page:1:line:25","SRC-159":"paragraph:10","SRC-165":"paragraph:1","SRC-189":"page:1:line:11","SRC-191":"paragraph:5","SRC-217":"paragraph:8"}
for sid,lang,name,locator,duty,address in manual:
    add_org(name,lang,sid,locator,duty=duty,address=address,duty_locator=duty_locs.get(sid),address_locator=address_locs.get(sid))

# Batch 3: direct, self-contained institutional answers omitted by the general templates.
supplemental = [
    ("SRC-123","ru","Жалал-Абадское региональное управление Архивной службы","page:1:line:15","Руководство работой районных и городских государственных архивов, централизованный учёт документов, принятых на государственное хранение, и обеспечение их сохранности.","page:1:line:21",None,None),
    ("SRC-142","ky","Жалал-Абад электр тармактар ишканасы","paragraph:6","Электр энергиясын жеткирет, бөлүштүрөт жана сатат.","paragraph:7","Манас шаары, Эрмамат Осмонов көчөсү-30","paragraph:11"),
    ("SRC-147","ru","Жалал-Абадский областной филиал ОАО «Кыргызтелеком»","paragraph:1",None,None,None,None),
    ("SRC-147","ru","Бюро повреждения, техническая поддержка","paragraph:8","Устранение повреждений, подключение Интернета и телефона.","paragraph:8","г. Манас, ул. Осмонова 128а","paragraph:9"),
    ("SRC-158","ky","Манас шаарынын мэриясынын Көрктөндүрүү жана жашылдандыруу чарбасы","page:1:line:4","Көрктөндүрүү жана жашылдандыруу; кооптуу дарактарды бутоо, көчөттөрдү жана гүлдөрдү отургузуу.","page:1:line:6","Зулумбек Жамашев 1 в","page:1:line:10"),
    ("SRC-164","ru","Департамент коммунального хозяйства и благоустройства","paragraph:41","Освещение, устройство тротуаров и лотков, очищение селевых каналов, содержание кладбищ и ритуальные услуги.","paragraph:42",None,None),
    ("SRC-164","ru","Манас Тазалык","paragraph:48","Вывоз мусора, установка контейнеров и контроль за полигоном.","paragraph:48",None,None),
    ("SRC-164","ru","Управление водоканал Манас","paragraph:56","Ремонт уличных труб, устранение прорывов воды и строительство канализации.","paragraph:56",None,None),
    ("SRC-184","ru","НРЭС","paragraph:16","Вопросы электрической энергии.","paragraph:16",None,None),
    ("SRC-203","ky","Манас шаардык Социалдык фонд башкармалыгы","paragraph:1",None,None,"Манас шаары, Пушкин көч №1","paragraph:7"),
    ("SRC-214","ky","Жалал-Абад ОИИБ","paragraph:12","Кылмыштардын алдын алуу, кылмыштын бетин ачуу, коомдук коопсуздукту камсыздоо.","paragraph:12",None,None),
    ("SRC-218","ru","МП «Каныш-Кыя Тазалык»","paragraph:11","Обслуживание систем питьевого водоснабжения и оросительных систем, благоустройство и санитарная очистка территории, сбор и вывоз бытовых отходов.","paragraph:12","Чаткальский район, село Каныш-Кыя","paragraph:17"),
    ("SRC-222","ru","Жалал-Абадское региональное управление Министерства природных ресурсов, экологии и технического надзора КР","paragraph:14","Проведение государственной политики в сферах охраны окружающей среды, экологии, климата, геологии и недропользования.","paragraph:16",None,None),
    ("SRC-226","ky","Архив кызматынын Жалал-Абад региондук башкармалыгы","page:1:line:1","Райондук жана шаардык мамлекеттик архивдеринин ишин башкаруу, көзөмөлдөө; документтердин сакталуусун камсыздоо.","page:1:line:20","Манас шаары, Курорт көчөсү, 14","page:1:line:18"),
]
for sid,lang,name,name_loc,duty,duty_loc,address,address_loc in supplemental:
    add_org(name,lang,sid,name_loc,duty=duty,duty_locator=duty_loc,address=address,address_locator=address_loc)

eco_block=next(b for b in E["SRC-135"]["blocks"] if b["locator"]=="sheet:Лист1:row:4")
eco_cells=[norm(v) for v in eco_block["text"].split(" | ")]
eco_org=add_org(eco_cells[2],"ky","SRC-135",eco_block["locator"],duty=eco_cells[3],address=eco_cells[6])

for sid,lang,name,value,locator in [
    ("SRC-124", "ru", "Жалал-Абадское региональное управление государственного архитектурно-строительного контроля (ГАСК) Минстроя КР", "+996-502-15-60-71", "page:1:line:10"),
    ("SRC-109", "ky", "Мамлекеттик камсыздандыруу уюмунун Жалал-Абад филиалы", "+996 999 890 469", "sheet:Маршрутизация:row:2"),
]:
    o = org_by_name.get((lang,name.casefold()))
    if o:
        contacts.append({"contact_id":"contact-"+slug(name+value),"organization_id":o["organization_id"],"type":"phone","value":value,
                         "purpose":"general_line","language":lang,"working_hours":None,"source_ids":[sid],"provenance":[prov(sid,locator,lang)],
                         "fact_status":"SOURCE_FACT","verification_status":"verified","publication_status":"NEEDS_REVIEW"})

forest_name = "«Кыргыз Республикасынын Өзгөчө кырдаалдар министрлигине караштуу Токой кызматынын Кочкор-Ата токой чарбасы» мекемеси"
add_org(forest_name, "ky", "SRC-176", "paragraph:13", duty="Токойлорду коргоо жана сактоо; токой өрттөрүнүн алдын алуу; токойду калыбына келтирүү жана жаңы токойлорду отургузуу.")

# This source explicitly provides both the Kyrgyz and official-language names.
forest = next((o for o in orgs if "Кочкор-Ата токой чарбасы» мекемеси" in (o["name_ky"] or "")), None)
if forest:
    forest["name_ru"] = "Учреждение «Кочкор-Атинский лесхоз Лесной службы при Министерстве чрезвычайных ситуаций Кыргызской Республики»"
    forest["aliases_ky"] = ["Кочкор-Ата токой чарбасы"]
    forest["translation_status"] = "verified"
    aliases.append({"alias_id": "alias-kokchor-ata-forest-ky", "organization_id": forest["organization_id"], "language": "ky", "alias": "Кочкор-Ата токой чарбасы", "source_ids": ["SRC-176"], "provenance": [prov("SRC-176","paragraph:3","ky")], "verification_status": "verified"})
insurance_org = org_by_name.get(("ky", "Мамлекеттик камсыздандыруу уюмунун Жалал-Абад филиалы".casefold()))
if insurance_org:
    insurance_org["name_ru"] = "Жалал-Абадский филиал Государственной страховой организации"
    insurance_org["translation_status"] = "verified"
    insurance_org["provenance"].append(prov("SRC-134","page:1:line:7","ru"))

# Additional direct department structure. The relation is preserved only where the name itself states it.
for child, parent, sid in [
    ("Управление городских дорог мэрии города Манас", "Мэрия города Манас", "SRC-165"),
    ("Управление земельных ресурсов мэрии города Манас", "Мэрия города Манас", "SRC-167"),
]:
    p = add_org(parent, "ru", sid, "paragraph:1")
    o = org_by_name.get(("ru", child.casefold()))
    if o and p: o["parent_organization_id"] = p["organization_id"]

# Directly supplied institutional routing: Госстрах sheet and Manas road-office problem list.
insurance = org_by_name.get(("ky", "Мамлекеттик камсыздандыруу уюмунун Жалал-Абад филиалы".casefold()))
for block in E["SRC-109"]["blocks"]:
    if not block["locator"].startswith("sheet:Маршрутизация:row:"): continue
    row = int(block["locator"].split(":")[-1])
    if row < 2 or row > 10: continue
    cells = [norm(c) for c in block["text"].split(" | ")]
    if len(cells) < 5: continue
    topic, department, _, onward, note = cells[:5]
    department = re.sub(r"\s+[А-ЯӨҮҢ][а-яөүң]+\s+[А-ЯӨҮҢ]\.?.*$", "", department)
    routes.append({"routing_rule_id": f"route-gosstrakh-{row}", "topic": topic, "trigger_phrases_ru": [], "trigger_phrases_ky": [topic],
                   "target_organization_id": insurance["organization_id"], "target_department_id": None, "target_department_name_ky": department,
                   "territory": [], "required_clarifications": [], "exceptions": [], "onward_direction_ky": onward,
                   "source_ids": ["SRC-109"], "provenance": [prov("SRC-109", block["locator"], "ky")], "verification_status": "verified",
                   "fact_status": "SOURCE_FACT", "production_status": "NEEDS_CONFIRMATION", "publication_status": "NEEDS_REVIEW"})

roads = org_by_name.get(("ru", "Управление городских дорог мэрии города Манас".casefold()))
for i,topic in enumerate(("Устройство асфальта и тротуара","Устройство гравийных дорог","Ямочные работы"),5):
    routes.append({"routing_rule_id": f"route-manas-roads-{i}", "topic": topic, "trigger_phrases_ru": [topic], "trigger_phrases_ky": [],
                   "target_organization_id": roads["organization_id"], "target_department_id": None, "territory": ["Манас"],
                   "required_clarifications": ["точное местоположение"], "exceptions": [], "source_ids": ["SRC-165"],
                   "provenance": [prov("SRC-165", f"paragraph:{i}", "ru")], "verification_status": "verified", "fact_status": "SOURCE_FACT",
                   "production_status": "NEEDS_CONFIRMATION", "publication_status": "NEEDS_REVIEW"})

for row in range(14,19):
    block=next(b for b in E["SRC-135"]["blocks"] if b["locator"]==f"sheet:Лист1:row:{row}")
    cells=[norm(v) for v in block["text"].split(" | ")]
    if len(cells)<5 or cells[3]!="ЭТКК" or cells[4]!="Ооба": continue
    routes.append({"routing_rule_id":f"route-eco-{row}","topic":cells[2],"trigger_phrases_ru":[],"trigger_phrases_ky":[cells[2]],
                   "target_organization_id":eco_org["organization_id"],"target_department_id":None,"territory":[],
                   "required_clarifications":["окуя болгон жер"],"exceptions":[],"source_ids":["SRC-135"],
                   "provenance":[prov("SRC-135",block["locator"],"ky")],"verification_status":"verified","fact_status":"SOURCE_FACT",
                   "production_status":"NEEDS_CONFIRMATION","publication_status":"NEEDS_REVIEW"})

electric=org_by_name.get(("ky","Жалал-Абад электр тармактар ишканасы".casefold()))
routes.append({"routing_rule_id":"route-electric-outage-ret","topic":"Электр энергиясы өчүп калды","trigger_phrases_ru":[],
               "trigger_phrases_ky":["Электр энергиясы өчүп калды"],"target_organization_id":electric["organization_id"],
               "target_department_id":None,"target_department_name_ky":"РЭТ","territory":[],"required_clarifications":["дарек же жайгашкан жер"],
               "exceptions":[],"source_ids":["SRC-142"],"provenance":[prov("SRC-142","paragraph:25","ky")],
               "verification_status":"verified","fact_status":"SOURCE_FACT","production_status":"NEEDS_CONFIRMATION","publication_status":"NEEDS_REVIEW"})

# Institution/issue rows in an unsigned collection are proposals for the platform, never official assignments.
for comp in comps:
    if comp["source_ids"] != ["SRC-225"] or not comp["include_examples"]: continue
    topic = comp["include_examples"][0]
    if len(topic) > 180: continue
    routes.append({"routing_rule_id": "route-proposed-" + comp["competence_id"][5:], "topic": topic,
                   "trigger_phrases_ru": [], "trigger_phrases_ky": [], "target_organization_id": comp["organization_id"], "target_department_id": None,
                   "territory": [], "required_clarifications": ["населённый пункт и точное место", "предмет обращения"], "exceptions": [],
                   "source_ids": ["SRC-225"], "provenance": comp["provenance"], "verification_status": "proposed", "fact_status": "DERIVED",
                   "production_status": "NEEDS_CONFIRMATION", "publication_status": "NEEDS_REVIEW"})

# Controlled FAQ: each answer remains within a direct, short source statement.
for comp in comps:
    if comp["source_ids"] not in (["SRC-225"],["SRC-112"]): continue
    desc = comp["description_ky"]
    if not desc or not 20 <= len(desc) <= 165: continue
    org = next(o for o in orgs if o["organization_id"] == comp["organization_id"])
    if not org["name_ky"]: continue
    sid = comp["source_ids"][0]
    qa_ky.append({"qa_id": "qa-ky-" + comp["competence_id"][5:], "language": "ky", "question": f"{org['name_ky']} эмне иш кылат?",
                  "answer": desc, "organization_ids": [org["organization_id"]], "topic": comp["topic"], "source_ids": [sid],
                  "provenance": comp["provenance"], "fact_status": "SOURCE_FACT", "verification_status": "verified", "publication_status": "NEEDS_REVIEW"})
for sid,name,q,answer,locator in [
    ("SRC-165", "Управление городских дорог мэрии города Манас", "Какие дорожные работы указаны для управления городских дорог Манаса?", "Устройство асфальта и тротуара, гравийных дорог и ямочные работы.", "paragraph:5"),
    ("SRC-167", "Управление земельных ресурсов мэрии города Манас", "По каким вопросам работает управление земельных ресурсов мэрии Манаса?", "По вопросам муниципальных земельных участков, включая аренду и продление договоров аренды.", "paragraph:4"),
    ("SRC-124", "Жалал-Абадское региональное управление государственного архитектурно-строительного контроля (ГАСК) Минстроя КР", "Чем занимается региональное управление архитектурно-строительного контроля?", "Надзором за качеством строительных работ и выявлением нарушений строительных норм.", "page:1:line:3"),
    ("SRC-145", "Мэрия города Кара-Куль", "Какая организация отвечает за местное управление городом Кара-Куль?", "Мэрия города Кара-Куль.", "page:1:line:19"),
]:
    org = org_by_name.get(("ru", name.casefold()))
    qa_ru.append({"qa_id": "qa-ru-" + sid.lower(), "language": "ru", "question": q, "answer": answer,
                  "organization_ids": [org["organization_id"]] if org else [], "topic": "organization_competence", "source_ids": [sid],
                  "provenance": [prov(sid, locator, "ru")], "fact_status": "SOURCE_FACT", "verification_status": "verified", "publication_status": "NEEDS_REVIEW"})
for sid,lang,name,q,answer,locator in [
    ("SRC-164","ru","Манас Тазалык","Чем занимается «Манас Тазалык»?","Вывозом мусора, установкой контейнеров и контролем за полигоном.","paragraph:48"),
    ("SRC-218","ru","МП «Каныш-Кыя Тазалык»","Какие коммунальные услуги указаны для МП «Каныш-Кыя Тазалык»?","Обслуживание водоснабжения и оросительных систем, благоустройство, сбор и вывоз бытовых отходов.","paragraph:12"),
    ("SRC-142","ky","Жалал-Абад электр тармактар ишканасы","Жалал-Абад электр тармактар ишканасы эмне кылат?","Электр энергиясын жеткирет, бөлүштүрөт жана сатат.","paragraph:7"),
    ("SRC-158","ky","Манас шаарынын мэриясынын Көрктөндүрүү жана жашылдандыруу чарбасы","Манас шаарынын көрктөндүрүү жана жашылдандыруу чарбасы эмне кылат?","Көрктөндүрүү жана жашылдандыруу иштерин аткарат.","page:1:line:6"),
]:
    o=org_by_name.get((lang,name.casefold()))
    rec={"qa_id":"qa-"+lang+"-"+sid.lower(),"language":lang,"question":q,"answer":answer,"organization_ids":[o["organization_id"]],
         "topic":"organization_competence","source_ids":[sid],"provenance":[prov(sid,locator,lang)],"fact_status":"SOURCE_FACT","verification_status":"verified","publication_status":"NEEDS_REVIEW"}
    (qa_ru if lang=="ru" else qa_ky).append(rec)

# RAG: one compact source-backed statement per competence, plus selected clean official provisions.
for comp in comps:
    org = next(o for o in orgs if o["organization_id"] == comp["organization_id"])
    lang = "ky" if comp["description_ky"] else "ru"
    name = org["name_ky"] if lang == "ky" else org["name_ru"]
    desc = comp["description_ky"] or comp["description_ru"]
    if not desc or len(desc) > 1200: continue
    sid = comp["source_ids"][0]; p=comp["provenance"][0]
    chunks.append({"chunk_id": "chunk-"+comp["competence_id"], "document_id": sid, "organization_ids": [org["organization_id"]],
                   "topic": comp["topic"], "language": lang, "title": name, "text": name + ". " + desc,
                   "source_file": S[sid]["source_file"], "page": p.get("page"), "sheet": p.get("sheet"), "row": p.get("row"),
                   "document_date": S[sid]["document_date"], "valid_from": None, "valid_to": None, "fact_status": "SOURCE_FACT", "verification_status": "verified",
                   "publication_status": "NEEDS_REVIEW", "tags": ["competence"], "provenance": [p]})

official_sids = [s["source_id"] for s in sources if s["status"] == "processed" and s["file_type"] == "docx" and
                 (s["container_archive"] == "Документы_Word.zip" or s["container_archive"] == "Документы_Word_2_часть1.zip" or s["source_id"] in ("SRC-110","SRC-113","SRC-223","SRC-224","SRC-230"))]
for sid in official_sids:
    blocks = E[sid]["blocks"]
    candidates = []
    for b in blocks:
        t = norm(b["text"])
        if not b["locator"].startswith("paragraph:") or not 130 <= len(t) <= 950: continue
        if re.search(r"(?:\+996|\b0\d{8,}\b|@|парол|логин)", t, re.I): continue
        if "________" in t: continue
        if re.search(r"(милдет|функци|задач|ишинин|осуществля|деятельност|основн)", t, re.I): candidates.append(b)
    for bi,b in enumerate(candidates[:2],1):
        t=norm(b["text"])
        lang="ky" if any(ch in t for ch in "өүңӨҮҢ") else "ru"
        chunks.append({"chunk_id": f"chunk-{sid.lower()}-{bi}", "document_id": sid, "organization_ids": [], "topic": S[sid]["topic"][0],
                       "language": lang, "title": S[sid]["document_title"], "text": t, "source_file": S[sid]["source_file"], "page": None,
                       "sheet": None, "locator": b["locator"], "document_date": S[sid]["document_date"], "valid_from": None, "valid_to": None,
                       "fact_status": "SOURCE_FACT", "verification_status": "verified", "publication_status": "NEEDS_REVIEW", "tags": ["provision"],
                       "provenance": [prov(sid,b["locator"],lang)]})

# Exact RAG text deduplication after normalizing whitespace, retaining first provenance.
dedup=[]; seen={}
for c in chunks:
    key=hashlib.sha256(norm(c["text"]).casefold().encode()).hexdigest()
    if key in seen:
        seen[key]["provenance"].extend(c["provenance"])
        continue
    seen[key]=c; dedup.append(c)
chunks=dedup

# Concise per-source disposition, without copying raw personal or employee data.
usage={s["source_id"]:Counter() for s in sources}
for label,rows in [("organization",orgs),("competence",comps),("contact",contacts),("route",routes),("qa_ru",qa_ru),("qa_ky",qa_ky)]:
    for row in rows:
        for sid in row.get("source_ids",[]):usage[sid][label]+=1
for row in chunks:usage[row["document_id"]]["rag_chunk"]+=1
for s in sources:
    sid=s["source_id"]
    if s["status"]=="duplicate":s["normalization_status"]="duplicate";s["source_summary"]="Exact byte duplicate; see duplicate_of."
    elif s["status"]=="blocked":s["normalization_status"]="blocked";s["source_summary"]=s.get("extraction_error") or "Unreadable."
    elif usage[sid]:
        s["normalization_status"]="canonical_record_created"
        s["source_summary"]="Source-backed records: "+", ".join(f"{k}={v}" for k,v in sorted(usage[sid].items()))+"."
    elif sid in ("SRC-001","SRC-006"):
        s["normalization_status"]="context_reference"
        s["source_summary"]="Project specification or secondary audit summarized in human-readable status/source map."
    elif s["authority_level"]=="official_candidate":
        s["normalization_status"]="legal_catalogue_only"
        s["source_summary"]="Indexed in the legal catalogue; no safe standalone function excerpt selected."
    elif re.search(r"справочник|Масаев|Ирисбеков|Сатаров|Абылкасымова|Торобеков",s["file_name"],re.I):
        s["normalization_status"]="sensitive_internal_excluded"
        s["source_summary"]="Employee directory or individual appeal material excluded from citizen knowledge."
    else:
        s["normalization_status"]="indexed_for_source_on_demand"
        s["source_summary"]="Text indexed; no further canonical fact selected in this pass. Reopen by source_id for topic-specific review."

# Dataset-level issues directly observed in source data.
conflicts.append({"conflict_id": f"CONFLICT-{len(conflicts)+1:03d}", "entity": "Манас шаардык финансы башкармалыгы", "field": "address_territory_consistency",
                  "source_a": prov("SRC-225","table:1:row:15","ky"), "value_a": "Жээналиев №54 с.Казарман",
                  "source_b": prov("SRC-039","paragraph:2","ru"), "value_b": "Манасское городское финансовое управление (наименование)",
                  "preferred_value": "UNKNOWN", "action": "Подтвердить фактический адрес управления и территориальную принадлежность."})

gaps += [
    ("GAP-001", "Утверждённая матрица маршрутизации для пилота", "Без неё предложения нельзя переводить в production rules.", "Мэрия и владельцы ведомств", "XLSX: тема, территория, первичный исполнитель, исключения, дата утверждения"),
    ("GAP-002", "Границы пилота и зоны обслуживания", "Областные и городские учреждения смешаны.", "Мэрия", "Утверждённый перечень территорий и GeoJSON/GPKG"),
    ("GAP-003", "Актуальные публичные контакты и адреса", "В документах смешаны служебные и личные номера; адреса местами расходятся.", "Мэрия и каждое ведомство", "Реестр контактов с public_contact и датой проверки"),
    ("GAP-004", "Утверждённые категории Django и соответствия тем", "Кандидатные темы корпуса не равны действующим кодам.", "Владелец Django backend и мэрия", "Экспорт категорий, версий и маппинга"),
    ("GAP-005", "Актуальные официальные акты и сроки", "Анкеты называют сроки без полного нормативного основания.", "Мэрия и юридические службы", "Реестр актов с номером, датой и действующей редакцией"),
    ("GAP-006", "Утверждённые названия RU/KY", "Для большинства организаций подтверждён только один язык.", "Ведомства", "Двуязычный официальный реестр с aliases"),
    ("GAP-007", "Исключения и межведомственные случаи", "Общая компетенция не определяет ответственного при пересечении функций.", "Мэрия и ведомства", "Таблица исключений и эскалаций"),
    ("GAP-008", "OCR/ручная проверка заблокированных файлов", "Часть сканов и старых форматов не даёт проверяемого текста.", "Владельцы документов", "Поисковые PDF/DOCX или заверенная расшифровка"),
    ("GAP-009", "Публичность и права на публикацию", "Даже сведения из предоставленной таблицы не помечены как разрешённые к публикации.", "Мэрия и ведомства", "Поле publication_status и письменное согласование"),
    ("GAP-010", "Тождественность похожих названий и RU/KY пар", "Близкие названия электрических, архивных, дорожных и экологических структур встречаются в разных источниках; автоматическое объединение может создать ложную организацию.", "Мэрия и соответствующие ведомства", "Реестр стабильных ID, официальных названий RU/KY и подтверждённых aliases"),
]

write_jsonl("organizations.jsonl",orgs)
write_jsonl("sources.jsonl",sources)
write_jsonl("competences.jsonl",comps)
write_jsonl("contacts.jsonl",contacts)
write_jsonl("routing_rules.jsonl",routes)
write_jsonl("qa_pairs_ru.jsonl",qa_ru)
write_jsonl("qa_pairs_ky.jsonl",qa_ky)
write_jsonl("rag_chunks.jsonl",chunks)
write_jsonl("aliases.jsonl",aliases)

bundle={"conflicts":conflicts,"gaps":gaps,"counts":{"sources":len(sources),"processed":sum(s["status"]=="processed" for s in sources),
 "duplicates":sum(s["status"]=="duplicate" for s in sources),"blocked":sum(s["status"]=="blocked" for s in sources),"organizations":len(orgs),
 "competences":len(comps),"contacts":len(contacts),"routing_verified":sum(r["verification_status"]=="verified" for r in routes),
 "routing_proposed":sum(r["verification_status"]=="proposed" for r in routes),"qa_ru":len(qa_ru),"qa_ky":len(qa_ky),"rag_chunks":len(chunks),
 "conflicts":len(conflicts),"gaps":len(gaps)}}
(OUT/".canonical_state.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding="utf-8")
print(bundle["counts"])
