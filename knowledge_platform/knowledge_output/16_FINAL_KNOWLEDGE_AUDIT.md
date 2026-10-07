# Final knowledge audit

## Summary

| Metric | Count |
|---|---:|
| sources | 230 |
| processed | 184 |
| duplicates | 34 |
| blocked | 12 |
| official_with_explicit_requisites | 4 |
| official_candidates | 98 |
| organizations | 94 |
| competences | 83 |
| contacts | 72 |
| routing_verified | 18 |
| routing_proposed | 28 |
| qa_ru | 6 |
| qa_ky | 27 |
| rag_chunks | 193 |
| conflicts | 3 |
| knowledge_gaps | 10 |
| processed_sources_with_canonical_records | 108 |

## Validation pass

- JSONL parse and required fields: PASS.
- Physical file and ZIP-entry coverage: 230 logical files; PASS.
- Post-build source integrity: SHA-256 of all 230 logical source files matches the initial inventory; originals were not changed.
- SHA-256 exact duplicates: recorded with `duplicate_of`; similar titles are kept distinct.
- Organization/source references and contact provenance: checked against source registry.
- Routing with no source, premature production status, RAG phone/email patterns, RU/KY flags and duplicate chunk text: checked.
- Text extraction is distinct from factual verification. Unrepresented processed files are retained in the source registry and can be reopened on demand.

## Verified

18 routing facts directly appear in SRC-109, SRC-135, SRC-142 or SRC-165. 83 competence entries and 72 contact entries are tied to source locators. `verified` means source-backed, not approved for automatic use.

## Needs confirmation

Every routing record has `production_status=NEEDS_CONFIRMATION`. Every contact, FAQ and RAG chunk has `publication_status=NEEDS_REVIEW`. Source validity, pilot territory, backend category mappings and legal version status need approval.

## Conflicts

3 conflicts or source inconsistencies are detailed in 13_CONFLICTS.md. The two plant-protection addresses are left unresolved; the Manas finance-office address is geographically inconsistent; one tax-office address has a spelling variant.

## Outdated candidates

No contact is designated current solely by an undated list. Documents with older dates remain legal/reference candidates until their current editions are confirmed.

## Missing data

10 dataset-level gaps are detailed in 14_KNOWLEDGE_GAPS.md. 12 sources need OCR/conversion. Most organizations lack verified bilingual names, parent links and service zones.

## Ready for RAG

193 deduplicated, source-backed chunks are structurally ready for internal retrieval, with language/topic/organization and publication metadata. Embeddings were not created. Citizen-facing use waits for publication and currency review.

## Not ready for production routing

The 28 proposed rules and even 18 directly documented institution-level rules require the approved pilot routing matrix, exceptions, territorial boundaries and current Django categories.

## Source coverage after normalization

108 of 184 text-extracted sources contribute at least one canonical entity, route, QA or RAG chunk. The remaining extracted sources are indexed for source-on-demand review; many are questionnaires, cover letters or personal-data files. IDs: SRC-001, SRC-003, SRC-006, SRC-014, SRC-026, SRC-028, SRC-029, SRC-030, SRC-032, SRC-038, SRC-058, SRC-097, SRC-111, SRC-115, SRC-116, SRC-117, SRC-118, SRC-119, SRC-120, SRC-121, SRC-125, SRC-126, SRC-127, SRC-128, SRC-129, SRC-130, SRC-131, SRC-132, SRC-136, SRC-137, SRC-138, SRC-139, SRC-140, SRC-141, SRC-143, SRC-146, SRC-149, SRC-150, SRC-151, SRC-152, SRC-153, SRC-154, SRC-157, SRC-160, SRC-161, SRC-162, SRC-163, SRC-166, SRC-168, SRC-169, SRC-182, SRC-184, SRC-188, SRC-190, SRC-196, SRC-197, SRC-198, SRC-199, SRC-200, SRC-201, SRC-202, SRC-204, SRC-205, SRC-206, SRC-208, SRC-209, SRC-210, SRC-211, SRC-212, SRC-213, SRC-215, SRC-219, SRC-220, SRC-221, SRC-227, SRC-228.

## Recommended next actions

1. Request an approved organization/routing/contact register, pilot geography and Django category export from the mayor’s office and system owner.
2. Resolve the three conflicts and 12 blocked files with original issuers.
3. Obtain legal-version review and citizen-publication clearance before opening the RAG corpus to users.

## Validation errors

None.

## Validation warnings

None.
