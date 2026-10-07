"""Conservative territorial scope from reviewed runtime metadata, never vectors."""
from __future__ import annotations

import re
import unicodedata


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).casefold().replace("ё", "е")
    return " ".join(re.findall(r"\w+", value))


class TerritoryIndex:
    def __init__(self, files: dict[str, list[dict]]):
        self.files = files
        self.scopes = sorted({str(scope) for rows in files.values() for row in rows
                              for scope in (row.get("territory") or []) if ":" in str(scope)})
        self.organizations = {str(o.get("organization_id")): o
                              for o in files.get("organizations", [])}
        # A hierarchy edge is admitted only when the source names both levels
        # in one organization title; co-location in an archive is insufficient.
        self.parents: dict[str, set[str]] = {}
        for org in self.organizations.values():
            title = norm(" ".join(str(org.get(k) or "") for k in ("name_ru", "name_ky")))
            for child in self.scopes:
                if child.split(":", 1)[0] == "region" or not self._in_text(child, title):
                    continue
                for parent in self.scopes:
                    if parent.startswith("region:") and self._in_text(parent, title):
                        self.parents.setdefault(child, set()).add(parent)

    @staticmethod
    def _in_text(scope: str, text: str) -> bool:
        name = norm(scope.split(":", 1)[1])
        tokens = name.split()
        return bool(name and (name in text or all(any(word.startswith(t) for word in text.split())
                                                    for t in tokens if len(t) >= 4)))

    def explicit(self, text: str) -> str | None:
        query = norm(text)
        matches = self.matching_scopes(text)
        if not matches:
            return None
        type_hint = None
        if re.search(r"район|району|районе|райондук", query):
            type_hint = "district"
        elif re.search(r"айыл аймак|айыл окмот|айыл өкмөт", query):
            type_hint = "ayyl_area"
        elif re.search(r"город|шаар|шаары", query):
            type_hint = "city"
        elif re.search(r"област|облус", query):
            type_hint = "region"
        if type_hint:
            typed = [s for s in matches if s.startswith(type_hint + ":")]
            if typed:
                matches = typed
        longest = max(len(norm(s.split(":", 1)[1])) for s in matches)
        matches = [s for s in matches if len(norm(s.split(":", 1)[1])) == longest]
        return matches[0] if len(matches) == 1 else None

    def matching_scopes(self, text: str) -> list[str]:
        query = norm(text)
        matches = [s for s in self.scopes if self._in_text(s, query)]
        return matches

    def effective(self, text: str, profile: dict | None, last_scope: str | None = None) -> tuple[str | None, str | None]:
        explicit = self.explicit(text)
        if explicit:
            return explicit, explicit
        profile = profile or {}
        for key in ("district_name", "district", "settlement", "raw_locality", "region"):
            if profile.get(key):
                scope = self.explicit(str(profile[key]))
                if scope:
                    return None, scope
        return None, last_scope

    def contains(self, parent: str, child: str) -> bool:
        return parent == child or parent in self.parents.get(child, set())

    def routing_rule_allowed(self, rule: dict, scope: str | None) -> bool:
        if not scope or rule.get("visibility") not in {None, "PUBLIC"}:
            return False
        zones = rule.get("service_zones") or rule.get("territory") or []
        return any(self.contains(canonical, scope) for zone in zones
                   if (canonical := self.canonical(str(zone))) is not None)

    def canonical(self, value: str) -> str | None:
        if value in self.scopes:
            return value
        if ":" in value:
            return None
        options = [s for s in self.scopes if norm(s.split(":", 1)[1]) == norm(value)]
        return options[0] if len(options) == 1 else None

    def organization_allowed(self, organization_id: str, scope: str | None) -> bool:
        if not scope:
            return False
        org = self.organizations.get(str(organization_id)) or {}
        zones = org.get("territory") or []
        return any(self.contains(str(zone), scope) for zone in zones)

    def routing_rule_for_chunk(self, chunk: dict) -> dict | None:
        if "routing" not in (chunk.get("tags") or []):
            return None
        title = norm(str(chunk.get("title") or ""))
        org_ids = {str(x) for x in chunk.get("organization_ids") or []}
        source_ids = {str(x) for x in chunk.get("source_ids") or [chunk.get("document_id")] if x}
        matches = [r for r in self.files.get("routing_rules", [])
                   if str(r.get("target_organization_id")) in org_ids
                   and source_ids.intersection(str(x) for x in (r.get("source_ids") or []))
                   and norm(str(r.get("topic") or "")) == title]
        return matches[0] if len(matches) == 1 else None

    def matching_route(self, question: str, scope: str | None) -> dict | None:
        query = norm(question)
        matches = []
        for rule in self.files.get("routing_rules", []):
            if not self.routing_rule_allowed(rule, scope):
                continue
            phrases = [rule.get("topic") or "", *(rule.get("trigger_phrases_ru") or []),
                       *(rule.get("trigger_phrases_ky") or [])]
            if any(norm(p) and norm(p) in query for p in phrases):
                matches.append(rule)
        return matches[0] if len(matches) == 1 else None

    def list_scopes(self, kind: str) -> list[str]:
        return [s for s in self.scopes if s.startswith(kind + ":")]

    def organizations_in(self, scope: str) -> list[dict]:
        return [o for o in self.organizations.values() if scope in (o.get("territory") or [])
                and o.get("visibility") in {None, "PUBLIC"}]
