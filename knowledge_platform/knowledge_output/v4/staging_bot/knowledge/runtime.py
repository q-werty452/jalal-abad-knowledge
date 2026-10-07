from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)
FILES = ("sources.jsonl", "organizations.jsonl", "competences.jsonl", "contacts.jsonl",
         "routing_rules.jsonl", "qa_pairs_ru.jsonl", "qa_pairs_ky.jsonl",
         "rag_chunks.jsonl", "aliases.jsonl")
DEFAULT_DATA = Path(__file__).parent / "data"
DEFAULT_INDEX = Path(__file__).parent / "index"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"{path.name}:{number}: invalid JSON") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path.name}:{number}: expected an object")
        rows.append(item)
    return rows


def sync_knowledge(source: Path, destination: Path = DEFAULT_DATA) -> dict:
    """Validate and copy only runtime JSONL files; never touch the corpus."""
    source = source.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    contents: dict[str, bytes] = {}
    for name in FILES:
        path = source / name
        if not path.is_file():
            raise FileNotFoundError(f"Required knowledge file is missing: {path}")
        raw = path.read_bytes()
        rows = _read_jsonl(path)
        unique_field = "chunk_id" if name == "rag_chunks.jsonl" else "source_id" if name == "sources.jsonl" else None
        if unique_field:
            ids = [row.get(unique_field) for row in rows]
            if any(not value for value in ids) or len(ids) != len(set(ids)):
                raise ValueError(f"{name}: {unique_field} values must be present and unique")
        contents[name] = raw
    for name, raw in contents.items():
        (destination / name).write_bytes(raw)
    manifest = {
        "knowledge_version": hashlib.sha256("".join(hashlib.sha256(contents[n]).hexdigest() for n in FILES).encode()).hexdigest()[:16],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rag_chunks_count": len(_read_jsonl(source / "rag_chunks.jsonl")),
        "source_count": len(_read_jsonl(source / "sources.jsonl")),
        "files": {name: hashlib.sha256(contents[name]).hexdigest() for name in FILES},
    }
    (destination / "knowledge_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def build_index(data_dir: Path = DEFAULT_DATA, index_dir: Path = DEFAULT_INDEX,
                *, client=None, model: str | None = None) -> int:
    chunks = _read_jsonl(data_dir / "rag_chunks.jsonl")
    if not chunks:
        raise ValueError("rag_chunks.jsonl is empty")
    if client is None:
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is required to build embeddings")
        client = OpenAI(api_key=key, timeout=float(os.getenv("REQUEST_TIMEOUT", "90")))
    model = model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), 64):
        batch = chunks[start:start + 64]
        texts = [_chunk_text(row) for row in batch]
        response = client.embeddings.create(model=model, input=texts)
        vectors.extend([item.embedding for item in sorted(response.data, key=lambda x: x.index)])
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "embeddings.npy", np.asarray(vectors, dtype=np.float32))
    (index_dir / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    (index_dir / "index_manifest.json").write_text(json.dumps({"model": model, "count": len(chunks), "knowledge_version": _manifest_version(data_dir)}, indent=2), encoding="utf-8")
    return len(chunks)


def _manifest_version(data_dir: Path) -> str:
    path = data_dir / "knowledge_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")).get("knowledge_version", "unknown") if path.exists() else "unknown"


def validate_manifest(data_dir: Path = DEFAULT_DATA) -> dict:
    manifest = json.loads((data_dir / "knowledge_manifest.json").read_text(encoding="utf-8"))
    for name in FILES:
        digest = hashlib.sha256((data_dir / name).read_bytes()).hexdigest()
        if digest != manifest.get("files", {}).get(name):
            raise ValueError(f"Knowledge checksum mismatch: {name}")
    if len(_read_jsonl(data_dir / "rag_chunks.jsonl")) != manifest.get("rag_chunks_count"):
        raise ValueError("Knowledge chunk count mismatch")
    return manifest


def _chunk_text(item: dict) -> str:
    return str(item.get("text") or item.get("chunk_text") or item.get("content") or "")


def _looks_like_exact_contact(text: str) -> bool:
    return bool(re.search(
        r"@|https?://|(?:телефон|тел\.|phone|email|e-mail|адрес|дарек|график|часы работы|working_hours)\s*:|"
        r"\+?996[\d\s()\-]{6,}\d|\b0[\d\s()\-]{8,}\d|"
        r"\b(?:ул\.|улица|көчө|көчөсү)\s+\S+|\b\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2}",
        text, re.IGNORECASE))


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower().replace("ё", "е")
    return " ".join(re.findall(r"[\w-]+", value, flags=re.UNICODE))


def _public_contacts(rows: list[dict], approved_ids: set[str]) -> list[dict]:
    """Only contacts with a reviewed source-to-organization link may be shown."""
    return [row for row in rows if row.get("visibility") == "PUBLIC"
            and row.get("status") not in {"INTERNAL_ONLY", "CONFLICT", "AMBIGUOUS"}
            and str(row.get("contact_id")) in approved_ids]


@dataclass
class Retrieval:
    mode: str
    answer: str = ""
    chunks: list[dict] | None = None
    score: float = 0.0


class KnowledgeBase:
    def __init__(self, data_dir: Path = DEFAULT_DATA, index_dir: Path = DEFAULT_INDEX,
                 *, min_score: float = 0.32, candidate_k: int = 10, top_k: int = 5):
        self.data_dir, self.index_dir = Path(data_dir), Path(index_dir)
        self.min_score, self.candidate_k, self.top_k = min_score, candidate_k, top_k
        self.files: dict[str, list[dict]] = {}
        self.territories = None
        self.approved_contact_ids: set[str] = set()
        self.chunks: list[dict] = []
        self.vectors = np.empty((0, 0), dtype=np.float32)
        self.load()

    def load(self) -> None:
        if not (self.data_dir / "knowledge_manifest.json").exists():
            return
        self.files = {name.removesuffix(".jsonl"): _read_jsonl(self.data_dir / name) for name in FILES}
        from territory import TerritoryIndex
        self.territories = TerritoryIndex(self.files)
        self.approved_contact_ids = self._load_approved_contacts()
        chunks_path, vector_path = self.index_dir / "chunks.json", self.index_dir / "embeddings.npy"
        if chunks_path.exists() and vector_path.exists():
            index_manifest = self.index_dir / "index_manifest.json"
            if index_manifest.exists():
                metadata = json.loads(index_manifest.read_text(encoding="utf-8"))
                if metadata.get("knowledge_version") != _manifest_version(self.data_dir):
                    logger.warning("Knowledge snapshot changed; rebuild embeddings")
                    return
            self.chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
            self.vectors = np.load(vector_path, allow_pickle=False)
            if len(self.chunks) != len(self.vectors):
                logger.warning("Knowledge index row mismatch; retrieval disabled")
                self.chunks, self.vectors = [], np.empty((0, 0), dtype=np.float32)

    def _load_approved_contacts(self) -> set[str]:
        organizations = {str(o.get("organization_id")): o for o in self.files.get("organizations", [])}
        sources = {str(s.get("source_id")): s for s in self.files.get("sources", [])}
        contacts = self.files.get("contacts", [])
        if self.data_dir.resolve() == DEFAULT_DATA.resolve():
            audit_file = Path(__file__).parents[1] / "docs" / "public_contact_attribution_records.jsonl"
            if not audit_file.exists():
                logger.error("Contact attribution audit missing; suppressing exact contacts")
                return set()
            version = _manifest_version(self.data_dir)
            reviewed = {str(r.get("contact_record_id")): r for r in _read_jsonl(audit_file)}
            if len(reviewed) != len(contacts) or any(r.get("knowledge_version") != version for r in reviewed.values()):
                logger.error("Contact attribution audit stale; suppressing exact contacts")
                return set()
            approved = set()
            for contact in contacts:
                record = reviewed.get(str(contact.get("contact_id"))) or {}
                source_id = record.get("source_id")
                source = sources.get(str(source_id))
                if (record.get("status") != "VALID"
                        or record.get("link") not in {"same_record", "adjacent_section", "reviewed_letterhead"}
                        or contact.get("visibility") != "PUBLIC"
                        or record.get("organization_id") != contact.get("organization_id")
                        or str(contact.get("organization_id")) not in organizations
                        or record.get("type") != contact.get("type")
                        or record.get("value") != contact.get("value")
                        or source_id not in (contact.get("source_ids") or [])
                        or not source or record.get("source_file") != source.get("source_file")
                        or not any(p.get("source_id") == source_id
                                   and p.get("source_file") == record.get("source_file")
                                   and p.get("locator") in (record.get("locator") or [])
                                   for p in contact.get("provenance") or [])):
                    continue
                approved.add(str(contact["contact_id"]))
            return approved
        # Synthetic snapshots in tests still need proof of the same source row.
        approved = set()
        for contact in contacts:
            organization = organizations.get(str(contact.get("organization_id")))
            if not organization or contact.get("visibility") != "PUBLIC":
                continue
            for provenance in contact.get("provenance") or []:
                source_id, locator = provenance.get("source_id"), provenance.get("locator")
                if (source_id in sources and locator and source_id in (contact.get("source_ids") or [])
                        and provenance.get("source_file") == sources[source_id].get("source_file")
                        and any(p.get("source_id") == source_id and p.get("locator") == locator
                                for p in organization.get("provenance") or [])):
                    approved.add(str(contact["contact_id"]))
        return approved

    def public_contacts(self, organization_id: str) -> list[dict]:
        return _public_contacts([c for c in self.files.get("contacts", [])
                                 if str(c.get("organization_id")) == organization_id],
                                self.approved_contact_ids)

    def exact_match(self, question: str) -> Retrieval | None:
        query = _norm(question)
        if not query:
            return None
        for key in ("qa_pairs_ru", "qa_pairs_ky"):
            for row in self.files.get(key, []):
                if (_norm(str(row.get("question") or "")) == query and row.get("answer")
                        and not _looks_like_exact_contact(str(row["answer"]))):
                    return Retrieval("faq", str(row["answer"]), chunks=[row], score=1.0)
        aliases: dict[str, list[str]] = {}
        for row in self.files.get("aliases", []):
            alias = row.get("alias") or row.get("name")
            target = row.get("entity_id") or row.get("organization_id") or row.get("contact_id") or row.get("competence_id")
            if alias and target:
                aliases.setdefault(str(target), []).append(str(alias))
        matches = []
        for row in self.files.get("organizations", []):
            org_id = str(row.get("organization_id") or "")
            names = [str(row[k]) for k in ("name_ru", "name_ky", "short_name_ru", "short_name_ky") if row.get(k)]
            names += [str(x) for field in ("aliases_ru", "aliases_ky") for x in (row.get(field) or [])]
            names += aliases.get(org_id, [])
            if any(len(_norm(name)) >= 4 and _norm(name) in query for name in names):
                matches.append(row)
        # Generic "мэрия" names multiple entities: never pick the first row.
        if not matches and ("мэри" in query or "мери" in query):
            for row in self.files.get("organizations", []):
                name = _norm(str(row.get("name_ru") or row.get("name_ky") or ""))
                if name.startswith(("мэрия ", "мерия ")) or name.endswith((" мэрия", " мэриясы")):
                    city_words = [x for x in name.split() if x not in {"мэрия", "мерия", "города", "шаарынын", "шаардик", "шаардык"}]
                    if any(word in query.split() for word in city_words if len(word) > 3):
                        matches.append(row)
        if len(matches) == 1:
            row = matches[0]
            org_id = str(row["organization_id"])
            contacts = self.public_contacts(org_id)
            name = str(row.get("name_ru") or row.get("name_ky") or "")
            if any(word in query for word in ("прием", "запис", "кабыл", "жазыл")):
                return Retrieval("safe_no_answer",
                    "В доступной базе знаний нет подтверждённой информации о порядке записи на приём.",
                    chunks=[row], score=1.0)
            if any(word in query for word in ("телефон", "связ", "контакт", "адрес", "дарек", "байланыш")):
                if contacts:
                    from response_composer import FactLock, compose_response
                    selected = contacts[:3]
                    facts = ({"kind": "organization", "value": name},) + tuple(
                        {"kind": c.get("type"), "value": c.get("value")} for c in selected)
                    answer = compose_response(FactLock(language="ru", intent="CONTACT",
                        outcome="FULL", facts=facts))
                    return Retrieval("structured", answer, chunks=[row, *selected], score=1.0)
                return Retrieval("safe_no_answer", "В доступной базе знаний нет подтверждённого контакта этой организации.", chunks=[row], score=1.0)
            return Retrieval("structured", name, chunks=[row], score=1.0)
        if any(word in query for word in ("прием", "приём", "запис", "кабыл", "жазыл")) and any(
                word in query for word in ("област", "облус", "главе области", "руководител")):
            return Retrieval("safe_no_answer",
                "В доступной базе знаний нет подтверждённой информации о порядке записи на приём.")
        if not matches and ("районн" in query or "райондук" in query) and "администрац" in query:
            return Retrieval("safe_no_answer", "Уточните, пожалуйста, какой районной администрации касается вопрос.")
        if not matches and ("мэри" in query or "мери" in query):
            return Retrieval("safe_no_answer", "Уточните, пожалуйста, о мэрии какого города идёт речь.")
        return None

    def resolve_organizations(self, question: str, topic: str | None = None,
                              citizen_context: dict | None = None,
                              previous_id: str | None = None) -> list[dict]:
        """Find named entities first, then topic candidates; never merge scopes."""
        from intent import evidence_forms, turn_type
        query = _norm(question)
        scope = (citizen_context or {}).get("_territory_scope")
        names: dict[str, list[str]] = {}
        competence_text = {str(c.get("organization_id")): _norm(" ".join(str(c.get(k) or "") for k in
                            ("description_ru", "description_ky", "topic")))
                           for c in self.files.get("competences", [])}
        for alias in self.files.get("aliases", []):
            if alias.get("organization_id") and alias.get("alias"):
                names.setdefault(str(alias["organization_id"]), []).append(str(alias["alias"]))
        scored = []
        for row in self.files.get("organizations", []):
            org_id = str(row.get("organization_id") or "")
            variants = [row.get(k) for k in ("name_ru", "name_ky", "short_name_ru", "short_name_ky")]
            variants += (row.get("aliases_ru") or []) + (row.get("aliases_ky") or []) + names.get(org_id, [])
            variants = [_norm(str(v)) for v in variants if v and len(_norm(str(v))) >= 4]
            explicit = max((len(v) for v in variants if v in query), default=0)
            name = _norm(str(row.get("name_ru") or row.get("name_ky") or ""))
            topic_forms = evidence_forms(topic)
            topic_hit = bool(topic_forms and any(form in name for form in topic_forms))
            topic_hit = topic_hit or bool(topic_forms and any(form in competence_text.get(org_id, "") for form in topic_forms))
            if "водоканал" in query and "водоканал" in name:
                explicit = max(explicit, 20)
            if "мэри" in query and name.startswith("мэрия ") and any(w in query for w in name.split() if w in {"манас", "жалал-абад"}):
                explicit = max(explicit, 20)
            if topic == "water" and "водоканал" in name:
                topic_hit = True
            if topic == "tax" and "салык" in name:
                topic_hit = True
            if not explicit and not topic_hit:
                continue
            if not explicit and topic_hit and scope and self.territories and not self.territories.organization_allowed(org_id, scope):
                continue
            locality = _norm(" ".join(str((citizen_context or {}).get(k) or "") for k in
                                     ("raw_locality", "district_name", "district", "settlement")))
            locality_parts = {w for w in locality.split() if len(w) >= 5 and w not in {"району", "район", "шаары", "город"}}
            local_hit = bool(locality_parts.intersection(name.split()))
            score = int(explicit > 0) * 10 + min(explicit, 100) / 100 + int(local_hit) * 3 + int(topic_hit)
            logger.debug("entity_query=%s candidate=%s match_type=%s match_score=%.2f",
                         re.sub(r"\d", "*", query[:100]), org_id,
                         "name_or_alias" if explicit else "topic", score)
            scored.append((score, row))
        if not scored and previous_id and turn_type(question) == "FOLLOWUP":
            return [r for r in self.files.get("organizations", []) if str(r.get("organization_id")) == previous_id]
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored and scored[0][0] >= 10:
            return [r for score, r in scored if score >= 10][:10]
        if scored and any(score >= 4 for score, _ in scored):
            return [r for score, r in scored if score >= 4][:10]
        return [r for _, r in scored][:15]

    def organization_card(self, organization_id: str, language: str = "ru") -> Retrieval | None:
        org = next((row for row in self.files.get("organizations", [])
                    if str(row.get("organization_id")) == organization_id), None)
        if not org:
            return None
        ky = language == "ky"
        name = org.get("name_ky" if ky else "name_ru") or org.get("name_ru") or org.get("name_ky")
        if not name:
            return None
        contacts = self.public_contacts(organization_id)
        competences = [c for c in self.files.get("competences", []) if str(c.get("organization_id")) == organization_id]
        lines = [str(name)]
        territory = org.get("territory")
        if territory:
            places = territory if isinstance(territory, list) else [territory]
            display = []
            for place in places:
                kind, separator, value = str(place).partition(":")
                display.append(value if separator and kind in {"region", "district", "city", "ayyl_area", "village"} else str(place))
            lines.append(("Аймак: " if ky else "Территория: ") + ", ".join(display))
        for c in competences[:2]:
            description = c.get("description_ky" if ky else "description_ru") or c.get("description_ru") or c.get("description_ky")
            if description:
                lines.append(("Ишмердик: " if ky else "Чем занимается: ") + str(description))
        labels = {"phone": ("Телефон", "Телефон"), "address": ("Дарек", "Адрес"),
                  "email": ("Email", "Email"), "website": ("Сайт", "Сайт"),
                  "fax": ("Факс", "Факс")}
        for kind, pair in labels.items():
            values = [str(c.get("value")) for c in contacts if c.get("type") == kind and c.get("value")]
            if values:
                lines.append(f"{pair[0 if ky else 1]}: {', '.join(dict.fromkeys(values))}")
        hours = [str(c.get("working_hours") or c.get("value")) for c in contacts
                 if c.get("working_hours") or (c.get("type") == "working_hours" and c.get("value"))]
        if hours:
            lines.append(("Иштөө убактысы: " if ky else "График: ") + ", ".join(dict.fromkeys(hours)))
        lines.append("Кайрылуу каттоого жардам бере алам." if ky else "Могу помочь с вопросом или обращением.")
        return Retrieval("organization_card", "\n".join(lines), chunks=[org, *competences[:2], *contacts], score=1.0)

    def browse(self, question: str, citizen_context: dict | None = None) -> Retrieval:
        from intent import topic_of
        ky = (citizen_context or {}).get("language") == "ky"
        scope = self.territories.explicit(question) if self.territories else None
        if scope:
            return self.browse_inventory(question, "LIST_ORGANIZATIONS_IN_TERRITORY",
                                         {**(citizen_context or {}), "_territory_scope": scope})
        orgs = [row for row in self.files.get("organizations", []) if row.get("name_ru") or row.get("name_ky")]
        topic = topic_of(question)
        if topic:
            ids = {str(c.get("organization_id")) for c in self.files.get("competences", [])
                   if topic in _norm(str(c.get("topic") or ""))}
            orgs = [row for row in orgs if str(row.get("organization_id")) in ids]
        names = [str(row.get("name_ky" if ky else "name_ru") or row.get("name_ru") or row.get("name_ky")) for row in orgs[:6]]
        if not orgs:
            return Retrieval("browse", "Бул аймак боюнча уюмдар табылган жок. Башка районду жазыңыз." if ky else
                             "По этому названию организаций не нашлось. Уточните район или город.")
        heading = (f"Бул суроо боюнча {len(orgs)} уюм табылды." if ky else
                   f"По запросу найдено {len(orgs)} организаций.")
        tail = "Кайсы уюм тууралуу толугураак айтып берейин?" if ky else "О какой организации рассказать подробнее?"
        return Retrieval("browse", heading + "\n" + "\n".join("• " + name for name in names) +
                         ("\n…" if len(orgs) > len(names) else "") + "\n" + tail,
                         chunks=orgs[:6], score=1.0)

    def browse_inventory(self, question: str, kind: str,
                         citizen_context: dict | None = None) -> Retrieval:
        """Structured territory inventory; no embedding or inferred service area."""
        ky = (citizen_context or {}).get("language") == "ky"
        inventory = self.territories
        if not inventory:
            return Retrieval("browse", "Маалымат азырынча жок." if ky else "Данных пока нет.")
        if kind == "LIST_TERRITORIES":
            q = _norm(question)
            category = "city" if any(x in q for x in ("город", "шаар")) else "district"
            scopes = inventory.list_scopes(category)
            label = "шаарлар" if ky and category == "city" else "райондор" if ky else "города" if category == "city" else "районы"
            names = [s.split(":", 1)[1] for s in scopes]
            answer = ((f"Маалымат базасындагы {label}: " if ky else f"В базе представлены {label}: ") +
                      ", ".join(names) + ".")
            return Retrieval("browse", answer)
        scope = (citizen_context or {}).get("_territory_scope") or inventory.explicit(question)
        matching = inventory.matching_scopes(question) if not scope else [scope]
        if not scope and len({_norm(s.split(":", 1)[1]) for s in matching}) == 1 and matching:
            scope = matching[0]
        if not scope:
            return Retrieval("clarify", "Кайсы район же шаар?" if ky else "Уточните район или город.")
        label = scope.split(":", 1)[1]
        if kind == "LIST_ORGANIZATIONS_IN_TERRITORY":
            scopes = matching if len(matching) > 1 else [scope]
            orgs = list({str(o.get("organization_id")): o for s in scopes
                         for o in inventory.organizations_in(s)}.values())
            names = [str(o.get("name_ky" if ky else "name_ru") or o.get("name_ky") or o.get("name_ru"))
                     for o in orgs[:10]]
            answer = ((f"{label} боюнча базадагы уюмдар: " if ky else f"Организации в базе по территории {label}: ") +
                      ("; ".join(names) if names else ("так уюм көрсөтүлгөн эмес" if ky else "не указаны")) + ".")
            return Retrieval("browse", answer, chunks=orgs[:10])
        topics = sorted({str(r.get("topic")) for r in self.files.get("routing_rules", [])
                         if inventory.routing_rule_allowed(r, scope) and r.get("topic")})
        answer = ((f"{label} боюнча темалар: " if ky else f"Темы по территории {label}: ") +
                  ("; ".join(topics[:10]) if topics else ("так темалар көрсөтүлгөн эмес" if ky else
                                                      "подтверждённых территориальных тем нет")) + ".")
        return Retrieval("browse", answer)

    def structured_lookup(self, question: str, intent: str, *, topic: str | None = None,
                          citizen_context: dict | None = None,
                          previous_id: str | None = None) -> Retrieval | None:
        from intent import topic_of
        topic = topic or topic_of(question)
        ky = (citizen_context or {}).get("language") == "ky" or bool(re.search(r"[ңөү]", question.lower()))
        candidates = self.resolve_organizations(question, topic, citizen_context, previous_id)
        if not candidates:
            query = _norm(question)
            if any(x in query for x in ("мэри", "мери", "районная администрац", "райондук администрац")):
                return Retrieval("clarify", "Кайсы район же шаардагы уюм керек?" if ky else
                                 "Уточните, пожалуйста, район или город нужной организации.")
            if intent == "PROCEDURE" and any(w in _norm(question) for w in ("губернатор", "области", "област")):
                return Retrieval("partial", "Жеке кабыл алууга жазылуунун так тартиби азырынча тастыктала элек. Кайсы маселе боюнча кайрылгыңыз келет? Кайрылууну даярдоого жардам берем." if ky else
                                 "Точный порядок записи на приём пока не подтверждён. По какому вопросу Вы хотите обратиться? Помогу подготовить обращение.")
            return None
        if len(candidates) > 1:
            return Retrieval("clarify", "Кайсы район же шаардагы уюм керек?" if ky else
                             "Уточните, пожалуйста, район или город нужной организации.", chunks=candidates[:5])
        org = candidates[0]
        org_id = str(org["organization_id"])
        name = str(org.get("name_ky") if ky and org.get("name_ky") else org.get("name_ru") or org.get("name_ky") or "")
        contacts = self.public_contacts(org_id)
        if intent in {"CONTACT", "ADDRESS", "WORKING_HOURS", "EMAIL", "WEBSITE", "FAX", "PROCEDURE"}:
            needed = {"CONTACT": {"phone"}, "ADDRESS": {"address"}, "WORKING_HOURS": set(),
                      "EMAIL": {"email"}, "WEBSITE": {"website"}, "FAX": {"fax"}, "PROCEDURE": set()}[intent]
            selected = ([c for c in contacts if c.get("working_hours") or (c.get("type") == "working_hours" and c.get("value"))] if intent == "WORKING_HOURS" else
                        [c for c in contacts if c.get("type") in needed] if needed else contacts)
            values = ([str(c.get("working_hours") or c.get("value")) for c in selected if c.get("working_hours") or c.get("value")] if intent == "WORKING_HOURS" else
                      [str(c.get("value")) for c in selected if c.get("value")])
            if intent == "PROCEDURE":
                prefix = "Катталуу тартиби тууралуу тастыкталган маалымат жок." if ky else "Подтверждённого порядка записи в базе нет."
                if values:
                    labeled = [f"{c.get('type', 'контакт')}: {c.get('value')}" for c in selected[:3] if c.get("value")]
                    return Retrieval("partial", f"{prefix} {name}: {'; '.join(labeled)}", chunks=[org, *selected[:3]], score=1.0)
                return Retrieval("partial", f"{prefix} {name}. Суроону кызматкерге өткөрүп бере алам." if ky else
                                 f"{prefix} {name}. Могу предложить передать вопрос сотруднику.", chunks=[org], score=1.0)
            if values:
                from response_composer import FactLock, compose_response
                facts = ({"kind": "organization", "value": name},) + tuple(
                    {"kind": "working_hours" if intent == "WORKING_HOURS" else c.get("type"),
                     "value": c.get("working_hours") or c.get("value")}
                    for c in selected[:3] if c.get("working_hours") or c.get("value"))
                answer = compose_response(FactLock(language="ky" if ky else "ru", intent=intent,
                    outcome="FULL", facts=facts, topic=topic))
                return Retrieval("structured", answer, chunks=[org, *selected[:3]], score=1.0)
            from response_composer import FactLock, compose_response
            missing_field = {"CONTACT": "phone", "ADDRESS": "address", "WORKING_HOURS": "working_hours",
                             "EMAIL": "email", "WEBSITE": "website", "FAX": "fax"}[intent]
            competence = next((c for c in self.files.get("competences", [])
                               if str(c.get("organization_id")) == org_id), None)
            description = ((competence.get("description_ky" if ky else "description_ru") or
                            competence.get("description_ru") or competence.get("description_ky"))
                           if competence else None)
            facts = ({"kind": "organization", "value": name},)
            if description:
                facts += ({"kind": "competence", "value": description},)
            answer = compose_response(FactLock(language="ky" if ky else "ru", intent=intent,
                outcome="PARTIAL", facts=facts, topic=topic, missing=(missing_field,),
                allowed_actions=("report_issue",)))
            return Retrieval("partial", answer, chunks=[org] + ([competence] if competence else []), score=1.0)
        competences = [c for c in self.files.get("competences", []) if str(c.get("organization_id")) == org_id]
        if intent in {"COMPETENCE", "INCIDENT"} and competences:
            description = competences[0].get("description_ky" if ky else "description_ru") or competences[0].get("description_ky") or competences[0].get("description_ru")
            if description:
                if ky and not competences[0].get("description_ky"):
                    return Retrieval("structured", f"Маалымат базасында орусча мындай деп көрсөтүлгөн: {name}: {description}",
                                     chunks=[org, competences[0]], score=1.0)
                return Retrieval("structured", f"{name}: {description}", chunks=[org, competences[0]], score=1.0)
        return Retrieval("structured", name, chunks=[org], score=1.0)

    @staticmethod
    def _format_row(row: dict) -> str:
        preferred = ("name_ru", "name_ky", "name", "title", "short_name_ru", "short_name_ky", "short_name", "value", "phone", "address", "work_hours", "description_ru", "description_ky", "description", "comment")
        parts = [str(row[k]).strip() for k in preferred if row.get(k)]
        return ". ".join(parts) if parts else json.dumps(row, ensure_ascii=False)

    def retrieve(self, question: str, *, embed_query=None, citizen_context: dict | None = None,
                 topic: str | None = None, organization_id: str | None = None,
                 skip_exact: bool = False) -> Retrieval:
        exact = None if skip_exact else self.exact_match(question)
        if exact:
            return exact
        if not len(self.vectors) or embed_query is None:
            return Retrieval("safe_no_answer")
        from intent import forms_for, evidence_forms, topic_of
        topic = topic or topic_of(question)
        expanded = question + (" " + " ".join(forms_for(topic)[:6]) if topic else "")
        vector = np.asarray(embed_query(expanded), dtype=np.float32)
        matrix_norms = np.linalg.norm(self.vectors, axis=1)
        qnorm = np.linalg.norm(vector)
        similarities = self.vectors @ vector / (matrix_norms * qnorm + 1e-12)
        scores = similarities.copy()
        profile = citizen_context or {}
        scope = profile.get("_territory_scope")
        query = _norm(question)
        language = profile.get("language") or ("ky" if re.search(r"[ңөү]", query) else "ru")
        locality = _norm(" ".join(str(profile.get(k) or "") for k in ("district", "settlement", "raw_locality")))
        locality_tokens = {x for x in locality.split() if len(x) >= 4 and
                           x not in {"район", "району", "город", "шаар", "шаары", "область", "облусу", "село", "айыл"}}
        query_tokens = {x for x in query.split() if len(x) >= 4}
        debug = []
        synonyms = evidence_forms(topic)
        for i, chunk in enumerate(self.chunks):
            bonuses = {"language_bonus": 0.0, "topic_bonus": 0.0,
                       "lexical_bonus": 0.0, "territory_bonus": 0.0,
                       "alias_bonus": 0.0, "organization_bonus": 0.0,
                       "bilingual_bonus": 0.0}
            if chunk.get("language") == language:
                bonuses["language_bonus"] = .015
            metadata = _norm(" ".join(str(chunk.get(k) or "") for k in ("title", "topic", "territory", "text")))
            overlap = query_tokens.intersection(metadata.split())
            bonuses["lexical_bonus"] = min(len(overlap) * .025, .1)
            if topic and any(form in metadata for form in synonyms):
                bonuses["topic_bonus"] = .09 if chunk.get("organization_ids") else .025
            if topic and any(form in metadata for form in synonyms if re.search(r"[ңөү]", form)):
                bonuses["bilingual_bonus"] = .025
            if locality_tokens.intersection(metadata.split()):
                bonuses["territory_bonus"] = .055
            if organization_id and organization_id in (chunk.get("organization_ids") or []):
                bonuses["organization_bonus"] = .12
            if organization_id:
                aliases = [a.get("alias", "") for a in self.files.get("aliases", []) if a.get("organization_id") == organization_id]
                if any(_norm(a) in metadata for a in aliases if len(_norm(a)) >= 4):
                    bonuses["alias_bonus"] = .04
            scores[i] += sum(bonuses.values())
            debug.append(bonuses)
        eligible = []
        routing_evidence: dict[int, dict] = {}
        local_topics = {"manhole", "roads", "water", "water.pipeline", "street_lighting",
                        "waste", "traffic_light", "fallen_tree", "bus_stop", "transformer"}
        for i, chunk in enumerate(self.chunks):
            tags = chunk.get("tags") or []
            if "contact" in tags or _looks_like_exact_contact(_chunk_text(chunk)):
                continue
            if organization_id and chunk.get("organization_ids") and organization_id not in chunk["organization_ids"]:
                continue
            if "routing" in tags:
                rule = self.territories.routing_rule_for_chunk(chunk) if self.territories else None
                if not rule or not self.territories.routing_rule_allowed(rule, scope):
                    continue
                routing_evidence[i] = rule
            elif scope and topic in local_topics and chunk.get("organization_ids") and self.territories:
                known = [self.territories.organizations.get(str(org)) for org in chunk["organization_ids"]]
                if any(org and org.get("territory") for org in known) and not any(
                        self.territories.organization_allowed(str(org), scope) for org in chunk["organization_ids"]):
                    continue
            metadata = _norm(" ".join(str(chunk.get(k) or "") for k in ("title", "topic", "text")))
            if topic and synonyms and not any(form in metadata for form in synonyms):
                if not organization_id or organization_id not in (chunk.get("organization_ids") or []):
                    continue
            if float(similarities[i]) < self.min_score:
                continue
            if topic and not (float(similarities[i]) >= .62 or debug[i]["topic_bonus"] >= .09
                              or debug[i]["organization_bonus"] > 0):
                continue
            eligible.append(i)
        indices = sorted(eligible, key=lambda i: float(scores[i]), reverse=True)[:self.candidate_k]
        selected = [(int(i), float(scores[i])) for i in indices[:self.top_k]]
        if not selected:
            return Retrieval("safe_no_answer", score=float(scores.max()) if len(scores) else 0.0)
        ranked = []
        for i, score in selected:
            row = {**self.chunks[i], "_score": score,
                   "_vector_score": float(similarities[i]), **debug[i]}
            if i in routing_evidence:
                rule = routing_evidence[i]
                row.update({"routing_rule_id": rule.get("routing_rule_id"),
                            "topic": rule.get("topic"),
                            "territory": rule.get("territory") or [],
                            "territory_id": rule.get("territory_id"),
                            "organization_id": rule.get("target_organization_id"),
                            "source_ids": rule.get("source_ids") or [],
                            "source_id": (rule.get("source_ids") or [None])[0]})
            ranked.append(row)
        return Retrieval("rag", chunks=ranked, score=selected[0][1])
