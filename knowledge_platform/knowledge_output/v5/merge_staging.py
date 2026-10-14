"""
merge_staging.py — добавить в наш v5 то, что нашла параллельная сборка
v5_staging (Windows-копия, тот же набор из 8 ответов администрации).

Запуск после build_v5.py:  python3 merge_staging.py <путь к v5_staging>

Что делает (идемпотентно — повторный запуск ничего не дублирует):
  * контакты, которых у нас нет (сверка по цифрам телефона / тексту адреса
    в пределах организации), — добавляет; организации и территории, которых
    у нас нет, — тоже;
  * мобильные, которые staging пометил «публичность не подтверждена»
    (private/review_records.jsonl), у нас скрывает (INTERNAL_ONLY) —
    личные номера сотрудников не публикуем;
  * алиасы организаций и карточки источников NEW-266…273 — добавляет;
  * пересчитывает хэши и счётчики в манифестах.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "runtime_export"
TAG = "staging-merge"


def read(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def write(p: Path, rows: list[dict]) -> None:
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def digits(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def akey(v: str) -> str:
    return re.sub(r"[^0-9a-zа-яёөүң]", "", (v or "").lower())


def clean(ctype: str, v: str) -> str | None:
    v = (v or "").strip()
    if ctype == "address":
        v = re.sub(r"[.,;]?\s*тел[.:].*$", "", v, flags=re.I)        # «… №45. Тел: 6-00-34,»
        v = re.sub(r",?\s*с\s*\d{1,2}[:.]\d{2}.*$", "", v)            # «Манас көчөсү №92, с 08:30до»
        v = v.strip(" ,.;")
        return v if len(v) >= 6 else None
    if ctype in ("phone", "fax"):
        d = digits(v)
        return v if (len(d) >= 5 or d in ("112", "119", "101", "102", "103")) else None
    return v or None


def hours_key(v: str) -> tuple:
    """«ПН-ПТ 8:30 – 17:30» и «пн-пт 08:30-17:30» — один и тот же график."""
    return tuple(int(h) * 60 + int(m) for h, m in re.findall(r"(\d{1,2})[:.](\d{2})", v or ""))


def ctype_of(c: dict) -> str:
    return c.get("contact_type") or c.get("type") or ""


def is_dup(c: dict, ours: list[dict]) -> bool:
    t, v = ctype_of(c), c["value"]
    for o in ours:
        if ctype_of(o) != t:
            continue
        if t in ("phone", "fax"):
            a, b = digits(v), digits(o["value"])
            if a and b and (a.endswith(b[-5:]) or b.endswith(a[-5:])):
                return True
        elif t == "address":
            a, b = akey(v), akey(o["value"])
            if a and b and (a in b or b in a):
                return True
        elif t == "working_hours":
            if hours_key(v) == hours_key(o["value"]):
                return True
        elif akey(v) == akey(o["value"]):
            return True
    return False


def main(stage: Path) -> None:
    S = stage / "runtime_export"
    files = {n: read(OUT / f"{n}.jsonl") for n in ("organizations", "contacts", "territories", "aliases", "sources")}
    st = {n: read(S / f"{n}.jsonl") for n in files}

    orgs = {o["organization_id"]: o for o in files["organizations"]}
    s_orgs = {o["organization_id"]: o for o in st["organizations"]}
    by_name: dict[str, str] = {}
    for o in files["organizations"]:
        for n in (o.get("name_ru"), o.get("name_ky")):
            if n:
                by_name.setdefault(akey(n), o["organization_id"])

    def resolve(oid: str) -> str | None:
        if oid in orgs:
            return oid
        so = s_orgs.get(oid)
        if not so:
            return None
        for n in (so.get("name_ru"), so.get("name_ky")):
            if n and akey(n) in by_name:
                return by_name[akey(n)]
        orgs[oid] = dict(so, merged_from=TAG)          # новая организация из staging
        files["organizations"].append(orgs[oid])
        return oid

    # 1. Личные мобильные, которые staging не счёл публичными, — скрыть.
    hidden_phones = {digits(r.get("value") or r.get("new_value"))[-9:] for r in read(stage / "private" / "review_records.jsonl")
                     if r.get("reason") == "mobile_public_status_unverified"
                     and digits(r.get("value") or r.get("new_value"))}
    # То, что мы сами придержали при разборе (held_back.jsonl), staging не возвращает.
    held = {digits(r["value"])[-9:] if r.get("kind") == "phone" else akey(r["value"])
            for r in read(HERE / "held_back.jsonl") if r.get("value")}
    hidden = 0
    for c in files["contacts"]:
        if ctype_of(c) == "phone" and c.get("visibility") == "PUBLIC" and digits(c["value"])[-9:] in hidden_phones:
            c.update(visibility="INTERNAL_ONLY", publication_status="WITHHELD_PRIVATE_MOBILE")
            hidden += 1

    # 2. Недостающие контакты.
    per_org: dict[str, list[dict]] = {}
    for c in files["contacts"]:
        per_org.setdefault(c["organization_id"], []).append(c)
    have_ids = {c["contact_id"] for c in files["contacts"]}
    added = 0
    for c in st["contacts"]:
        if c.get("visibility") != "PUBLIC" or c["contact_id"] in have_ids:
            continue
        t = ctype_of(c)
        v = clean(t, c["value"])
        if not v or (t == "phone" and digits(v)[-9:] in hidden_phones | held) or akey(v) in held:
            continue
        oid = resolve(c["organization_id"])
        if not oid:
            continue
        c = dict(c, value=v, organization_id=oid, merged_from=TAG)
        if is_dup(c, per_org.get(oid, [])):
            continue
        files["contacts"].append(c)
        per_org.setdefault(oid, []).append(c)
        have_ids.add(c["contact_id"])
        added += 1

    # 3. Территории, алиасы, источники — чего нет.
    def add_missing(name: str, key: str, need_org: bool = False) -> int:
        have = {r[key] for r in files[name]}
        n = 0
        for r in st[name]:
            if r[key] in have:
                continue
            if need_org:
                oid = resolve(r["organization_id"])
                if not oid:
                    continue
                r = dict(r, organization_id=oid)
            files[name].append(dict(r, merged_from=TAG))
            have.add(r[key])
            n += 1
        return n

    n_terr = add_missing("territories", "territory_id")
    n_alias = add_missing("aliases", "alias_id", need_org=True)
    n_src = add_missing("sources", "source_id")

    for n, rows in files.items():
        write(OUT / f"{n}.jsonl", rows)

    km_p, sm_p = OUT / "knowledge_manifest.json", OUT / "structured_manifest.json"
    km = json.loads(km_p.read_text(encoding="utf-8"))
    for f in list(km.get("files", {})):
        km["files"][f] = hashlib.sha256((OUT / f).read_bytes()).hexdigest()
    km.update(organizations_count=len(files["organizations"]), contacts_count=len(files["contacts"]),
              source_count=len(files["sources"]), merged_staging="619cf2a505e5b5fb")
    km["knowledge_version"] = hashlib.sha256("".join(sorted(km["files"].values())).encode()).hexdigest()[:16]
    km_p.write_text(json.dumps(km, ensure_ascii=False, indent=2), encoding="utf-8")
    if sm_p.exists():
        sm = json.loads(sm_p.read_text(encoding="utf-8"))
        sm["knowledge_version"] = km["knowledge_version"]
        sm_p.write_text(json.dumps(sm, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"скрыто мобильных: {hidden}; добавлено контактов: {added}; территорий: {n_terr}; "
          f"алиасов: {n_alias}; источников: {n_src}; организаций всего: {len(files['organizations'])}; "
          f"версия {km['knowledge_version']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
