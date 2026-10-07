# Knowledge Promotion v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Produce a separate pilot knowledge v2 from all customer-supplied local sources, with safe visibility, provenance, structured contacts/procedures/routing, and offline query checks.

**Architecture:** Keep `knowledge_output/machine` immutable. Build `knowledge_output/v2/machine` from validated copies plus source-confirmed additions; retain withheld or disputed candidates in separate structured review tables. Use a deterministic builder and validator; never edit bot or index in this pass.

**Tech Stack:** Python 3, python-docx, openpyxl, pypdf, JSONL, PowerShell.

**Spec:** User's PROMOTION PASS supplied in the current conversation; active workspace override is `C:\Users\user\Desktop\knowledge_platform`.

## Global Constraints

- Local customer documents only; no Internet.
- Do not expose private mobile numbers, citizen personal data, passwords, conflicts, or ambiguous attribution as public facts.
- Source-backed territory-specific routing is a suggestion only; no automatic backend assignment.
- Preserve the old corpus and do not rebuild the OpenAI index or change bot conversation logic.

## Review Focus

- Letterhead numbers from an issuing ministry must not become the subject organization's number.
- Legal addresses must not be labeled reception addresses.
- Personal employee mobiles in SRC-205 must remain internal.
- The conflicting library address must not have a silent winner.
- A routing rule for one айыл аймак must not appear province-wide.

### Task 1: Inventory and source scan

**Files:** Create `knowledge_output/v2/build_v2.py`, `knowledge_output/v2/review/*`.

- [x] Read all original machine JSONL and 00–16 reports, second-audit reports, and new source registry.
- [x] Extract source blocks read-only and identify candidates with locators.
- [x] Verify all 194 recoverable candidates have a disposition.

### Task 2: Promote structured knowledge

**Files:** Create `knowledge_output/v2/machine/*.jsonl`.

- [x] Append 17 new source records, preserving four duplicate mappings.
- [x] Promote unambiguous public contacts, hours, competences, procedures, and territorial routing.
- [x] Preserve internal, conflicting, and ambiguous candidates in structured review files.
- [x] Add compact RAG chunks and offline question checks.

### Task 3: Validate and report

**Files:** Create `knowledge_output/v2/VALIDATION.md`, `PROMOTION_REPORT.md`, `OFFLINE_QUERY_CHECK.md`.

- [x] Parse every JSONL and resolve every source and organization reference.
- [x] Check contacts, hours, procedures, routing, private SRC-205 numbers, and conflicts.
- [x] Compare before/after metrics and original corpus hashes.
- [x] Provide a manual sync/index command; do not execute it.

