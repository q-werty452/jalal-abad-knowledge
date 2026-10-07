"""Add immutable v4 machine facts to the bot export with a versioned sidecar."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAMES = ("territories", "service_territories", "services", "procedures",
         "district_profiles", "escalation_rules")


def main() -> None:
    export = ROOT / "runtime_export"
    legacy = json.loads((export / "knowledge_manifest.json").read_text(encoding="utf-8"))
    digests = {}
    for stem in NAMES:
        name = stem + ".jsonl"
        raw = (ROOT / "machine" / name).read_bytes()
        for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if line.strip() and not isinstance(json.loads(line), dict):
                raise ValueError(f"{name}:{number}: expected an object")
        (export / name).write_bytes(raw)
        digests[name] = hashlib.sha256(raw).hexdigest()
    manifest = {"knowledge_version": legacy["knowledge_version"], "files": digests}
    (export / "structured_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"knowledge_version": legacy["knowledge_version"], "files": list(digests)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
