"""Read supplied DOCX in document order; retain raw extracts outside Git."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "private"
PRIVATE.mkdir(exist_ok=True)
DOWNLOADS = Path(r"C:\Users\user\Downloads")
NAMES = [
    "Ноокен Запрос сведений для чат-бота (2).docx",
    "Запрос сведений для чат-бота (1) (4).docx",
    "Запрос сведений для чат-бота (2).docx",
    "АЛА-БУКА Запрос сведений для чат-бота.docx",
    "Запрос сведений для чат-бота (1) (3).docx",
    "Запрос сведений для чат-бота (1) (2).docx",
    "Запрос сведений для чат-бота (1) (1).docx",
    "Запрос сведений для чат-бота (1).docx",
]

inventory = []
for idx, name in enumerate(NAMES, 1):
    path = DOWNLOADS / name
    doc = Document(path)
    rows = []
    table_count = 0
    for item in doc.iter_inner_content():
        if isinstance(item, Paragraph):
            value = item.text.strip()
            if value:
                rows.append({"kind": "paragraph", "locator": f"paragraph:{len(rows)+1}", "text": value})
        elif isinstance(item, Table):
            table_count += 1
            for ridx, row in enumerate(item.rows, 1):
                cells = ["\n".join(p.text for p in cell.paragraphs).strip() for cell in row.cells]
                rows.append({"kind": "table_row", "locator": f"table:{table_count}:row:{ridx}", "cells": cells})
    (PRIVATE / f"input_{idx:02d}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    all_text = "\n".join(" ".join(r.get("cells") or []) if r["kind"] == "table_row" else r["text"] for r in rows)
    inventory.append({"id": idx, "name": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "bytes": path.stat().st_size, "paragraphs_and_rows": len(rows), "tables": table_count,
                      "phone_like": len(re.findall(r"(?:\+996|0\d{3}|\(\d{3,5}\))[-\d\s()]{5,}", all_text)),
                      "emails": len(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", all_text)),
                      "text_chars": len(all_text),
                      "preview": [r.get("text") or " | ".join(r.get("cells") or []) for r in rows[:4]]})
md = DOWNLOADS / "richtext_converted_to_markdown (1).md"
inventory.append({"id": 9, "name": md.name, "sha256": hashlib.sha256(md.read_bytes()).hexdigest(),
                  "bytes": md.stat().st_size, "text_chars": len(md.read_text(encoding="utf-8"))})
(ROOT / "input_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(inventory, ensure_ascii=False, indent=2))
