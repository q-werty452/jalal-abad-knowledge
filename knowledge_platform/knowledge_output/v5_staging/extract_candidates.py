"""Draft source-located government facts without publishing them."""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "private"
V4 = ROOT.parent / "v4" / "runtime_export"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return " ".join(re.findall(r"[\w]+", value))


organizations = [json.loads(line) for line in (V4 / "organizations.jsonl").open(encoding="utf-8")]
names = []
for org in organizations:
    for key in ("name_ru", "name_ky", "short_name_ru", "short_name_ky"):
        if org.get(key):
            names.append((norm(org[key]), org))
    for key in ("aliases_ru", "aliases_ky"):
        for alias in org.get(key) or []:
            names.append((norm(alias), org))

scopes = {1: "district:Ноокен", 4: "district:Ала-Бука", 7: "district:Аксы", 8: "district:Базар-Коргон"}
heading_scopes = {"АКСЫЙСКИЙ": "district:Аксы", "АЛА-БУКИНСКИЙ": "district:Ала-Бука",
                  "БАЗАР-КОРГОНСКИЙ": "district:Базар-Коргон", "НООКЕНСКИЙ": "district:Ноокен",
                  "СУЗАКСКИЙ": "district:Сузак", "ТОГУЗ-ТОРОУСКИЙ": "district:Тогуз-Торо",
                  "ТОКТОГУЛЬСКИЙ": "district:Токтогул", "ЧАТКАЛЬСКИЙ": "district:Чаткал",
                  "ГОРОД МАНАС": "city:Манас", "ГОРОД КАРА-КУЛЬ": "city:Кара-Көл",
                  "ГОРОД МАЙЛУУ-СУУ": "city:Майлуу-Суу", "ГОРОД ТАШ-КУМЫР": "city:Таш-Көмүр"}
hour_re = re.compile(r"(?<!\d)(?:0?\d|1\d|2[0-3])[:.]\d{2}\s*[-–—до]+\s*(?:0?\d|1\d|2[0-3])[:.]\d{2}")
landline_re = re.compile(r"(?:\b0\s*\(\s*37\d{2}\s*\)|\b0?37\d{2})[\s\-]*\d[\d\s\-]{3,8}\d")
mobile_re = re.compile(r"(?:\+996\s*|\b0)(?:22|50|51|52|54|55|56|70|71|72|75|77|79|99)\d[\d\s\-\u00a0]{5,9}\d")


def best(name: str, scope: str) -> tuple[str | None, float, str | None]:
    q = norm(name)
    if not q:
        return None, 0.0, None
    territory = scope.split(":", 1)[1]
    prelim = []
    for candidate, org in names:
        q_tokens, c_tokens = set(q.split()), set(candidate.split())
        overlap = len(q_tokens & c_tokens) / max(1, len(q_tokens | c_tokens))
        if not overlap:
            continue
        prelim.append((overlap, candidate, org))
    prelim.sort(key=lambda x: x[0], reverse=True)
    matches = []
    for overlap, candidate, org in prelim[:20]:
        ratio = difflib.SequenceMatcher(None, q, candidate).ratio()
        score = max(ratio, overlap)
        if any(territory in str(t) for t in org.get("territory") or []):
            score += .07
        matches.append((score, org))
    matches.sort(key=lambda x: x[0], reverse=True)
    if not matches:
        return None, 0.0, None
    return str(matches[0][1]["organization_id"]), round(matches[0][0], 3), str(matches[0][1].get("name_ru") or matches[0][1].get("name_ky"))


records = []
for file_id in (1, 2, 3, 4, 5, 6, 7, 8):
    rows = json.loads((PRIVATE / f"input_{file_id:02d}.json").read_text(encoding="utf-8"))
    scope = scopes.get(file_id)
    org_name = None
    block = []

    def flush() -> None:
        if not org_name or not block or not scope:
            return
        value = " ".join(text for _, text in block)
        landlines = list(dict.fromkeys(m.group().strip(" .,-") for m in landline_re.finditer(value)))
        mobiles = list(dict.fromkeys(m.group().strip(" .,-") for m in mobile_re.finditer(value)))
        hours = list(dict.fromkeys(m.group().strip() for m in hour_re.finditer(value)))
        address_parts = [text for _, text in block if re.search(r"\b(?:адрес|дареги|ул\.|улица|көчө|с\.|село|г\.)", text, re.I)
                         and not ("Принести: телефон, адрес, часы работы." == text.strip())]
        if not (landlines or mobiles or hours or address_parts):
            return
        org_id, score, matched = best(org_name, scope)
        records.append({"file_id": file_id, "scope": scope, "name": org_name,
                        "organization_id_candidate": org_id, "match_score": score,
                        "matched_name": matched, "locator": [f"paragraph_or_row:{number}" for number, _ in block],
                        "landlines": landlines, "mobiles": mobiles, "hours": hours,
                        "address_evidence": address_parts})

    for number, row in enumerate(rows, 1):
        text = row.get("text") or " | ".join(row.get("cells") or [])
        stripped = text.strip()
        for heading, territory_scope in heading_scopes.items():
            if stripped.upper().startswith(heading) and len(stripped) < 90:
                flush()
                scope, org_name, block = territory_scope, None, []
                break
        else:
            if stripped.startswith("•"):
                flush()
                org_name = stripped.lstrip("• ").strip()
                block = []
            elif stripped.startswith("☐"):
                flush()
                org_name = stripped.lstrip("☐ ").strip()
                block = []
            elif org_name:
                block.append((number, stripped))
    flush()

(PRIVATE / "candidates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
summary = {"candidate_blocks": len(records), "by_file": Counter(r["file_id"] for r in records),
           "high_match": sum(r["match_score"] >= .85 for r in records),
           "landline_blocks": sum(bool(r["landlines"]) for r in records),
           "mobile_blocks": sum(bool(r["mobiles"]) for r in records),
           "hours_blocks": sum(bool(r["hours"]) for r in records)}
print(json.dumps(summary, ensure_ascii=False, default=dict))
for row in records:
    if row["landlines"] or row["hours"]:
        print(f"{row['file_id']}: {row['name'][:55]} -> {str(row['matched_name'])[:55]} {row['match_score']:.2f} land={len(row['landlines'])} hours={len(row['hours'])}")
