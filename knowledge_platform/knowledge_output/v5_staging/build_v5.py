"""Conservative, reproducible V5 promotion from the supplied government replies.

Raw citizen appeals are never read by this builder.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V4 = ROOT.parent / "v4" / "runtime_export"
OUT = ROOT / "runtime_export"
PRIVATE = ROOT / "private"
INV = {r["id"]: r for r in json.loads((ROOT / "input_inventory.json").read_text(encoding="utf-8"))}
LEGACY = ("sources", "organizations", "competences", "contacts", "routing_rules",
          "qa_pairs_ru", "qa_pairs_ky", "rag_chunks", "aliases")
OPTIONAL = ("territories", "service_territories", "services", "procedures",
            "district_profiles", "escalation_rules")


def load(stem: str) -> list[dict]:
    return [json.loads(line) for line in (V4 / f"{stem}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def clean(text: str) -> str:
    return " ".join(str(text).replace("\u00a0", " ").split())


def key(text: str) -> str:
    text = unicodedata.normalize("NFKC", clean(text)).casefold().replace("ё", "е")
    return re.sub(r"[^\w]+", "", text)


def ident(prefix: str, *parts: object) -> str:
    return prefix + "-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:14]


data = {stem: load(stem) for stem in (*LEGACY, *OPTIONAL)}
org_by_id = {o["organization_id"]: o for o in data["organizations"]}
org_by_key = {key(o.get(field)): o for o in data["organizations"]
              for field in ("name_ru", "name_ky", "short_name_ru", "short_name_ky") if o.get(field)}
existing_contact = {(c["organization_id"], c["type"], key(c["value"])): c for c in data["contacts"]}
sources = {}
for i in range(1, 9):
    sid = f"NEW-{265+i}"
    source = INV[i]
    sources[i] = sid
    data["sources"].append({"source_id": sid, "file_name": source["name"],
                            "source_file": source["name"], "file_type": "docx",
                            "size": source["bytes"], "sha256": source["sha256"],
                            "language": "mixed", "source_relation": "SUPPLEMENTS",
                            "status": "processed", "normalization_status": "promoted_reviewed_subset",
                            "publication_status": "PILOT_PUBLIC"})

review: list[dict] = []
stats = Counter()
promoted: list[dict] = []
conflicts: list[dict] = []
TRUE_ADDRESS_CONFLICTS = {
    "org-nooken-raionduk-sotsialdyk-fond-bashkarmalygy-5e61253",
    "org-nooken-raionduk-emgek-sotsialdyk-kamsyzdoo-zhana-migratsiya-bashk-90f3ec3",
    "org-nooken-raionunun-sh-suerkulov-atyndagy-zhalpy-darygerdik-praktika-5cb3870",
    "v4-org-e329fa8d7e0c6a",
}


def provenance(file_id: int, locator: str) -> list[dict]:
    return [{"source_id": sources[file_id], "source_file": INV[file_id]["name"],
             "locator": locator, "verification_status": "SOURCE_CONFIRMED",
             "fact_status": "SOURCE_FACT"}]


territory_ids = {t["territory_id"] for t in data["territories"]}


def add_territory(territory_id: str, parent: str, file_id: int, locator: str) -> None:
    if territory_id in territory_ids:
        return
    name = territory_id.split(":", 1)[1]
    data["territories"].append({"territory_id": territory_id, "name_ru": name,
                                "name_ky": name, "type": territory_id.split(":", 1)[0],
                                "parent_territory": parent, "parent_status": "SOURCE_CONFIRMED",
                                "source_ids": [sources[file_id]], "provenance": provenance(file_id, locator),
                                "coverage_status": "PARTIAL"})
    territory_ids.add(territory_id)
    stats["territories"] += 1


def find_org(name: str, scope: str, file_id: int, locator: str, create: bool) -> dict | None:
    norm = key(name)
    org = org_by_key.get(norm)
    if org:
        return org
    # Only reviewed, distinctive variants. Never use a cross-district fuzzy match.
    aliases = {
        key("Т.Балтагулов айыл өкмөтү"): key("Т.Балтагулов айыл аймагынын айыл өкмөтү"),
        key("Кочкор-Ата токой чарбасы"): key("Учреждение «Кочкор-Атинский лесхоз Лесной службы при Министерстве чрезвычайных ситуаций Кыргызской Республики»"),
        key("Ала-Бука “Водоканал” МП"): key("МП «Ала-Бука Водоканал»"),
        key("АЛА-БУКА РАЙОНУНУН ЖАЛПЫ ДАРЫГЕРЛИК ПРАКТИКА БОРБОРУ"):
            key("Ала-Бука райондук жалпы дарыгердик практика борбору"),
        key("Ноокен, Майлуу-Суу билим берүү бөлүмүнүн"):
            key("Ноокен-Майлуу-Суу билим берүү бөлүмү"),
    }
    org = org_by_key.get(aliases.get(norm, ""))
    if org:
        return org
    if (not create or len(norm) < 8 or
            name in {"Майлуу-Суу шаарындагы ЦСМ / шаардык оорукана"} or
            re.search(r"^(?:Вода|Дороги|Соцфонд|Архитектура|ЦОН|Милиция|Больница|Земля)", name, re.I)):
        review.append({"file_id": file_id, "locator": locator, "name": name,
                       "reason": "organization_not_resolved"})
        return None
    # A new organization must have an explicit name, source row and scope.
    org_id = ident("v5-org", norm, scope)
    org = {"organization_id": org_id, "name_ru": name if re.search(r"[А-Яа-яЁё]", name) else None,
           "name_ky": name if re.search(r"[ңөүҢӨҮ]", name) else None,
           "short_name_ru": None, "short_name_ky": None, "aliases_ru": [], "aliases_ky": [],
           "organization_type": "unknown", "parent_organization_id": None,
           "territory": [scope], "territory_status": "SOURCE_CONTEXT",
           "status": "SOURCE_CONFIRMED", "source_ids": [sources[file_id]],
           "provenance": provenance(file_id, locator), "visibility": "PUBLIC"}
    if not org["name_ru"] and not org["name_ky"]:
        org["name_ru"] = name
    data["organizations"].append(org)
    org_by_id[org_id] = org
    org_by_key[norm] = org
    stats["organizations"] += 1
    return org


def add_contact(org: dict, kind: str, value: str, file_id: int, locator: str,
                scope: str, *, visibility: str = "PUBLIC", reason: str | None = None) -> None:
    value = clean(value).strip(" .,;")
    if not value or value in {"—", "-"} or (kind == "address" and
            (value in {"0", "Принести"} or value.startswith("Принести:"))):
        return
    org_id = org["organization_id"]
    if kind == "address" and re.match(r"^г\.\s*ул\.", value, re.I):
        review.append({"file_id": file_id, "locator": locator, "organization_id": org_id,
                       "field": kind, "value": value, "reason": "city_name_missing"})
        return
    if visibility != "PUBLIC":
        review.append({"file_id": file_id, "locator": locator, "organization_id": org_id,
                       "field": kind, "value": value, "reason": reason or "internal_only"})
        stats["internal_contacts"] += 1
        return
    contact_key = (org_id, kind, key(value))
    if contact_key in existing_contact:
        stats["duplicates"] += 1
        return
    # Address and hours differing from an existing record need human review.
    forced_conflict = False
    if kind in {"address", "working_hours"}:
        other = [c for c in data["contacts"] if c["organization_id"] == org_id and c["type"] == kind
                 and c.get("visibility") == "PUBLIC"]
        if other:
            normalized = (lambda s: [(int(h), int(m)) for h, m in re.findall(
                r"(?<!\d)(\d{1,2})[:.\-](\d{2})(?!\d)", s)][:2]) if kind == "working_hours" else None
            same = any((normalized(value) == normalized(str(c["value"])) if normalized else
                        key(value) in key(c["value"]) or key(c["value"]) in key(value)) for c in other)
            if not same:
                if kind == "address" and org_id in TRUE_ADDRESS_CONFLICTS:
                    forced_conflict = True
                    for prior in other:
                        prior["visibility"] = "INTERNAL_ONLY"
                        prior["status"] = "CONFLICT"
                        prior["publication_status"] = "INTERNAL_ONLY"
                    conflicts.append({"conflict_id": ident("v5-conflict", org_id, kind),
                                      "organization_id": org_id, "field_name": kind,
                                      "territory_scope": scope, "source_ids": sorted({
                                          *(s for prior in other for s in prior.get("source_ids") or []), sources[file_id]}),
                                      "record_ids": [prior["contact_id"] for prior in other],
                                      "new_source_id": sources[file_id], "new_locator": locator,
                                      "status": "CONFLICT", "visibility": "INTERNAL_ONLY"})
                    stats["confirmed_conflicts"] += 1
                else:
                    review.append({"file_id": file_id, "locator": locator,
                                   "organization_id": org_id, "field": kind, "reason": "possible_conflict",
                                   "new_value": value, "existing_ids": [c["contact_id"] for c in other]})
                    stats["possible_conflicts"] += 1
                    return
            if same:
                stats["duplicates"] += 1
                return
    cid = ident("v5-contact", org_id, kind, value, sources[file_id])
    row = {"contact_id": cid, "organization_id": org_id, "type": kind,
           "contact_type": kind, "value": value, "purpose": "general_line" if kind == "phone" else "source_contact",
           "address_kind": "office_or_unspecified" if kind == "address" else None,
           "working_hours": value if kind == "working_hours" else None,
           "territory_id": scope, "source_ids": [sources[file_id]],
           "provenance": provenance(file_id, locator), "verification_status": "SOURCE_CONFIRMED",
           "pilot_status": "SOURCE_CONFIRMED", "status": "CONFLICT" if forced_conflict else "SOURCE_CONFIRMED",
           "visibility": "INTERNAL_ONLY" if forced_conflict else visibility,
           "publication_status": "INTERNAL_ONLY" if forced_conflict else "PILOT_PUBLIC"}
    if reason:
        row["publication_reason"] = reason
    data["contacts"].append(row)
    existing_contact[contact_key] = row
    promoted.append({"contact_id": cid, "organization_id": org_id, "type": kind,
                     "file_id": file_id, "locator": locator, "visibility": visibility})
    stats[kind if not forced_conflict else "conflict_contacts"] += 1


phone_re = re.compile(r"(?<!\d)(?:0\s*\(\s*37\d{2}\s*\)|\(\s*0?37\d{2}\s*\)|0?37\d{2})[\s\-]*(?:\d[\s\-]*){5,6}(?!\d)")
hour_re = re.compile(r"(?<!\d)(?:0?\d|1\d|2[0-3])[:.]\d{2}\s*(?:[-–—]|до|дөн)\s*(?:0?\d|1\d|2[0-3])[:.]\d{2}")
mobile_re = re.compile(r"(?<!\d)(?:\+996\s*|0)(?:22|50|51|52|54|55|56|70|71|72|75|77|79|99)[\d\s\-\u00a0]{6,13}\d(?!\d)")


def extract_fields(org: dict, text: str, file_id: int, locator: str, scope: str,
                   address: str | None = None) -> None:
    raw = clean(text)
    for match in phone_re.finditer(raw):
        value = clean(match.group())
        digits = re.sub(r"\D", "", value)
        if len(digits) == 9 and not digits.startswith("0"):
            digits = "0" + digits
        if len(digits) != 10:
            review.append({"file_id": file_id, "locator": locator, "organization_id": org["organization_id"],
                           "field": "phone", "reason": "invalid_landline_length"})
            continue
        add_contact(org, "phone", value, file_id, locator, scope)
    for match in mobile_re.finditer(raw):
        add_contact(org, "phone", match.group(), file_id, locator, scope,
                    visibility="INTERNAL_ONLY", reason="mobile_public_status_unverified")
    matches = hour_re.findall(raw)
    if matches:
        first = matches[0]
        day = "ПН-СБ" if re.search(r"ПН-СБ|Дүйшөмбү-Ишемби", raw, re.I) else "ПН-ПТ" if re.search(r"ПН-ПТ|пн.-пт.|Дүйшөмбү-Жума", raw, re.I) else ""
        add_contact(org, "working_hours", clean(day + " " + first), file_id, locator, scope)
    if address:
        add_contact(org, "address", address, file_id, locator, scope)


def rows(file_id: int) -> dict[int, str]:
    content = json.loads((PRIVATE / f"input_{file_id:02d}.json").read_text(encoding="utf-8"))
    return {n: r.get("text") or " | ".join(r.get("cells") or []) for n, r in enumerate(content, 1)}


def address_from(text: str) -> str | None:
    text = clean(text)
    match = re.search(r"(?:Адрес\s*[:.]\s*|\bадрес\s+)(.+)", text, re.I)
    if match:
        value = match.group(1)
    elif re.match(r"^(?:г\.|с\.|село|Село)\s*\S+", text) and re.search(r"ул\.|улица|көчө", text, re.I):
        value = text
    else:
        return None
    value = re.split(r"\b(?:тел(?:ефон)?|часы|график|ПН-ПТ|ПН-СБ|пн.-пт.)\b|"
                     r"(?:0\s*)?\(\s*0?37\d{2}\s*\)|\b0?37\d{2}\b|\b\d{1,2}[:.]\d{2}\b", value, 1, flags=re.I)[0]
    value = re.sub(r"[,\s]+(?:0|с)$", "", value).strip(" .,:;-—(")
    if not value or value.casefold() in {"телефон", "часы работы", "часы работы:", "принести", "0"} or value.startswith("Принести:"):
        return None
    return value


# Noоken: one organization followed by its provided line; late rows have no bullet.
r = rows(1)
for n in list(range(11, 60, 2)) + [61, 63, 65, 68, 70, 72]:
    name = clean(r[n]).lstrip("• ")
    detail_line = 67 if n == 65 else n + 1
    if n == 65:
        name += " " + clean(r[66])
    org = find_org(name, "district:Ноокен", 1, f"content:line:{n}", create=False)
    if not org:
        continue
    detail = r[detail_line]
    extract_fields(org, detail, 1, f"content:line:{detail_line}", "district:Ноокен",
                   address=address_from(detail))

# Ala-Buka: original organization rows and the named replies below checkbox headings.
r = rows(4)
starts = [2, 6, 11, 16, 20, 24, 26, 29, 32, 36, 43, 50, 57, 64, 71, 78, 82,
          85, 91, 97, 104, 110, 116, 122, 128, 134, 140, 146, 152]
for a, b in zip(starts, starts[1:]):
    if a == 152:
        continue
    if a >= 85:
        name_line = a + 1
        if a == 97:
            name = clean(r[98] + " " + r[99])
        else:
            name = clean(r[name_line])
    else:
        name_line = a
        name = clean(r[a]).lstrip("• ")
    if name in {".", ""}:
        continue
    block = " ".join(r.get(n, "") for n in range(a + 1, b))
    loc = f"content:lines:{a}-{b-1}"
    org = find_org(name, "district:Ала-Бука", 4, loc, create=a >= 85 or a in {36, 43, 50})
    if not org:
        continue
    explicit_address = next((address_from(r[n]) for n in range(a + 1, b)
                             if address_from(r.get(n, ""))), None)
    extract_fields(org, block, 4, loc, "district:Ала-Бука", address=explicit_address)

# Aksy and Bazar-Korgon: paired organization/detail lines. New names require explicit filled details.
for file_id, scope, starts in (
    (7, "district:Аксы", list(range(11, 21, 2)) + list(range(22, 74, 2))),
    (8, "district:Базар-Коргон", list(range(11, 65, 2)) + list(range(66, 82, 2))),
):
    r = rows(file_id)
    for n in starts:
        name = clean(r[n]).lstrip("•☐ ")
        detail = r.get(n + 1, "")
        if not re.search(r"\d", detail):
            continue
        fact_scope = scope
        if file_id == 7:
            if n in {22, 24, 26}:
                fact_scope = "city:Кербен"
            elif 28 <= n <= 51:
                area = ("Сары-Челек" if n < 32 else "Кара-Камыш" if n < 36 else
                        "Ак-Жол" if n < 40 else "Ак-Суу" if n < 44 else
                        "Үч-Коргон" if n < 48 else "Кош-Добо")
                fact_scope = f"ayyl_area:{area}"
                add_territory(fact_scope, "district:Аксы", file_id, f"content:line:{n}")
        org = find_org(name, fact_scope, file_id, f"content:line:{n}", create=n >= (22 if file_id == 7 else 66))
        if not org:
            continue
        extract_fields(org, detail, file_id, f"content:line:{n+1}", fact_scope,
                       address=address_from(detail))

# Manas and Suzak: promote only named existing organizations with an explicitly filled value.
for file_id, scope in ((5, "city:Манас"), (6, "district:Сузак"), (2, "city:Майлуу-Суу"),
                       (3, "city:Кара-Көл")):
    r = rows(file_id)
    current_scope = None
    current_name = None
    current_name_line = 0
    for n, text in r.items():
        s = clean(text)
        if s.startswith("ГОРОД ") or s.endswith("РАЙОН"):
            current_scope = scope if ((file_id == 5 and "МАНАС" in s) or
                                      (file_id == 6 and "СУЗАК" in s) or
                                      (file_id == 2 and "МАЙЛУУ-СУУ" in s) or
                                      (file_id == 3 and "КАРА-КУЛЬ" in s)) else None
            current_name = None
            continue
        if not current_scope:
            continue
        if s.startswith("•"):
            current_name = s.lstrip("• ")
            current_name_line = n
            continue
        if s.startswith("☐"):
            current_name = None
            continue
        if file_id == 2 and re.match(r"^[1-8] \|", s):
            cells = [clean(x) for x in s.split("|")]
            if len(cells) >= 5:
                org = find_org(cells[1], scope, file_id, f"content:line:{n}", create=True)
                if org:
                    extract_fields(org, cells[3] + " " + cells[4], file_id, f"content:line:{n}", scope,
                                   address=cells[2])
            continue
        if not current_name or n != current_name_line + 1 or not re.search(r"\d", s):
            continue
        org = find_org(current_name, scope, file_id, f"content:line:{n-1}", create=False)
        if not org:
            continue
        # Baseline templates do not contain explicit values after the directive.
        if re.search(r"\b(?:Принести|Есть)\b", s) and not re.search(r"\d{1,2}[:.]\d{2}|\b0?37\d{2}\b|\b(?:ул\.|улица|с\.|г\.)\b", s, re.I):
            continue
        extract_fields(org, s, file_id, f"content:line:{n}", scope,
                       address=address_from(s))

# Named additions in the Manas and Kara-Köl response sections are not bullet rows.
r = rows(5)
for name_line, detail_lines in ((614, [615]), (617, [619, 620, 622, 624]),
                                (626, [627]), (629, [630])):
    name = clean(r[name_line])
    org = find_org(name, "city:Манас", 5, f"content:line:{name_line}", create=True)
    if not org:
        continue
    for n in detail_lines:
        extract_fields(org, r[n], 5, f"content:line:{n}", "city:Манас",
                       address=address_from(r[n]))
    if name_line == 617:
        add_contact(org, "phone", "119", 5, "content:line:622", "city:Манас",
                    reason="explicit_official_helpdesk")
        for alias, lang, loc in ((clean(r[623]), "ky", "content:line:623"),
                                 ("ЦОН г. Манас", "ru", "content:line:617"),
                                 ("ЦОН 04-04", "ru", "content:line:617")):
            data["aliases"].append({"alias_id": ident("v5-alias", org["organization_id"], alias),
                                    "organization_id": org["organization_id"], "language": lang,
                                    "alias": alias, "source_ids": [sources[5]],
                                    "provenance": provenance(5, loc),
                                    "verification_status": "SOURCE_CONFIRMED",
                                    "pilot_status": "SOURCE_CONFIRMED", "visibility": "PUBLIC"})
            stats["aliases"] += 1
r = rows(3)
if "Кара-Куль" in r[684] and "образован" in r[684]:
    name = "Кара-Кульский городской отдел образования"
    org = find_org(name, "city:Кара-Көл", 3, "content:line:684", create=True)
    if org:
        extract_fields(org, r[684], 3, "content:line:684", "city:Кара-Көл",
                       address="ул. Ленина №1")

for name, alias, language in (
    ("«Ала-Бука райондук электр тармактары» ишканасы", "Ала-Бука РЭС", "ru"),
    ("№17 ЖОЛ ЭКСПЛУАТАЦИЯЛОО ИШКАНАСЫ", "ДЭП-17 Ала-Бука", "ru"),
    ("МП «Ала-Бука Водоканал»", "Ала-Бука сууканал", "ky"),
):
    org = org_by_key.get(key(name))
    if org:
        data["aliases"].append({"alias_id": ident("v5-alias", org["organization_id"], alias),
                                "organization_id": org["organization_id"], "language": language,
                                "alias": alias, "source_ids": [sources[4]],
                                "provenance": provenance(4, "content:line:84-96"),
                                "verification_status": "SOURCE_CONFIRMED",
                                "pilot_status": "SOURCE_CONFIRMED", "visibility": "PUBLIC"})
        stats["aliases"] += 1

private_mobile_values = {str(item.get("value")) for item in review
                         if item.get("reason") == "mobile_public_status_unverified" and item.get("value")}
for contact in data["contacts"]:
    if contact.get("type") == "phone" and str(contact.get("value")) in private_mobile_values:
        if contact.get("visibility") == "PUBLIC":
            contact["visibility"] = "INTERNAL_ONLY"
            contact["status"] = "AMBIGUOUS"
            contact["publication_status"] = "INTERNAL_ONLY"
            contact["publication_reason"] = "new_source_identifies_possible_personal_mobile"
            stats["previous_public_mobile_withheld"] += 1

OUT.mkdir(parents=True, exist_ok=True)
for stem, records in data.items():
    (OUT / f"{stem}.jsonl").write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
(OUT / "conflicts.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in conflicts), encoding="utf-8")
shutil.copyfile(ROOT / "casebook" / "appeal_scenarios.jsonl", OUT / "appeal_scenarios.jsonl")
raw = {stem + ".jsonl": (OUT / f"{stem}.jsonl").read_bytes() for stem in LEGACY}
version = hashlib.sha256("".join(hashlib.sha256(raw[stem + ".jsonl"]).hexdigest() for stem in LEGACY).encode()).hexdigest()[:16]
legacy_manifest = {"knowledge_version": version, "rag_chunks_count": len(data["rag_chunks"]),
                   "source_count": len(data["sources"]),
                   "files": {name: hashlib.sha256(content).hexdigest() for name, content in raw.items()}}
(OUT / "knowledge_manifest.json").write_text(json.dumps(legacy_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
optional_manifest = {"knowledge_version": version,
                     "files": {stem + ".jsonl": hashlib.sha256((OUT / f"{stem}.jsonl").read_bytes()).hexdigest()
                               for stem in (*OPTIONAL, "conflicts", "appeal_scenarios")}}
(OUT / "structured_manifest.json").write_text(json.dumps(optional_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

# Preserve the reviewed old audit after checking each unchanged value and source link.
old_contacts = {c["contact_id"]: c for c in load("contacts")}
new_contacts = {c["contact_id"]: c for c in data["contacts"]}
for cid, row in old_contacts.items():
    assert row["value"] == new_contacts[cid]["value"] and row["source_ids"] == new_contacts[cid]["source_ids"], cid
old_audit = [json.loads(line) for line in (ROOT.parent / "v4" / "runtime_support" /
             "public_contact_attribution_records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
audit = []
for row in old_audit:
    copied = dict(row)
    copied["knowledge_version"] = version
    contact = new_contacts[copied["contact_record_id"]]
    if contact.get("status") in {"CONFLICT", "AMBIGUOUS"}:
        copied["visibility"] = "INTERNAL_ONLY"
        copied["status"] = contact["status"]
        copied["reasons"] = (["new_source_conflict"] if contact["status"] == "CONFLICT"
                             else ["new_source_personal_mobile_status_unverified"])
    audit.append(copied)
source_by_id = {s["source_id"]: s for s in data["sources"]}
for contact in data["contacts"]:
    if contact["contact_id"] in old_contacts:
        continue
    prov = contact["provenance"][0]
    assert prov["source_id"] in source_by_id and prov["source_file"] == source_by_id[prov["source_id"]]["source_file"]
    audit.append({"knowledge_version": version, "contact_record_id": contact["contact_id"],
                  "organization_id": contact["organization_id"],
                  "organization_name": org_by_id[contact["organization_id"]].get("name_ru") or org_by_id[contact["organization_id"]].get("name_ky"),
                  "type": contact["type"], "value": contact["value"],
                  "source_id": prov["source_id"], "source_file": prov["source_file"],
                  "locator": [prov["locator"]], "visibility": contact["visibility"], "source_value_found": True,
                  "link": "same_record", "status": "VALID" if contact["visibility"] == "PUBLIC" else "CONFLICT",
                  "reasons": [] if contact["visibility"] == "PUBLIC" else ["source_conflict"]})
support = ROOT / "runtime_support"
support.mkdir(exist_ok=True)
(support / "public_contact_attribution_records.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audit), encoding="utf-8")

(PRIVATE / "promotion_records.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in promoted), encoding="utf-8")
(PRIVATE / "review_records.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in review), encoding="utf-8")
(ROOT / "conflicts.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in conflicts), encoding="utf-8")
summary = {"knowledge_version": version, "counts": {stem: len(records) for stem, records in data.items()},
           "stats": dict(stats), "review_count": len(review), "audit_count": len(audit)}
(ROOT / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
