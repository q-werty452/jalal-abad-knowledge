# Knowledge promotion v4

V3 runtime version: `3fbb0b741ed1592f`. V4 runtime version: `7fa44034af0e6322`.

V3 machine and runtime files were left unchanged. Eight incoming DOCX files have unique SHA-256 hashes; exact duplicates: **0**. Three are filled variants of a shared information-request form. Their filled responses are ingested as source facts; blank prompts are not treated as facts.

| Dataset | V3 | V4 | Delta |
|---|---:|---:|---:|
| sources | 257 | 265 | +8 |
| organizations | 175 | 339 | +164 |
| contacts total | 491 | 653 | +162 |
| PUBLIC | 317 | 474 | +157 |
| INTERNAL_ONLY | 130 | 130 | +0 |
| CONFLICT | 16 | 20 | +4 |
| AMBIGUOUS | 28 | 29 | +1 |
| staff | 27 | 103 | +76 |
| territories | 82 | 163 | +81 |
| competences | 148 | 270 | +122 |
| services | 16 | 51 | +35 |
| procedures | 16 | 19 | +3 |
| routing rules | 120 | 205 | +85 |
| RAG chunks | 418 | 673 | +255 |
| real query examples | 5 | 5 | +0 |
| escalation rules | 2 | 8 | +6 |
| district profiles | 0 | 3 | +3 |
| conflicts records | 12 | 15 | +3 |

Runtime export: **473** audited PUBLIC contacts, **134** advisory routing rules, **667** RAG chunks. One legacy PUBLIC contact with no locator is suppressed.

## New files and source relations

| Source | File | SHA-256 | Relation | Promoted facts |
|---|---|---|---|---|
| NEW-258 | Мааылмат чат ботко 4-5 пункттар боюнча.docx | `a01a776142be983f1c476469cef702b35d9f830904cb2d166b704653d54a547e` | SUPPLEMENTS `NEW-259` | contacts: 16, territories: 41, organizations: 27, routing_rules: 41, rag_chunks: 41, topic_aliases: 6 |
| NEW-259 | Простой_запрос_недостающих_данных_AIG2C — копия (1).docx | `b3ee1e661c9fa7c94ced2587db4778673d542d9232c1092c4f7675e853c5e9e3` | SUPPLEMENTS `NEW-261` | contacts: 39, district_profiles: 1, escalation_rules: 1, procedures: 1, organizations: 37, competences: 38, rag_chunks: 53, service_territories: 3, routing_rules: 3, territories: 2, appeal_categories: 13 |
| NEW-260 | Условия подачи (1).docx | `0ca6777ab6e2ab575c1ae53d0b9c415abf47a737a6fbf907e168ff4daf979f11` | NEW_SOURCE | contacts: 7, conflicts: 1, competences: 1, rag_chunks: 6, organizations: 5, routing_rules: 4, territories: 5, service_territories: 5, procedures: 1, appeal_flows: 1 |
| NEW-261 | Простой_запрос_недостающих_данных_AIG2C (3).docx | `f61896a312e13a120f092f05ad0ca6c0c9a1cde7276220d3c6cd7de0f6795696` | NEW_SOURCE | Existing contact provenance only |
| NEW-262 | Чат Бот область (1).docx | `19f2130aa21fd7f7bf567f28c8c1aa64c93ed7c7ed6fc3180458f8000eed9449` | NEW_SOURCE | organizations: 34, contacts: 35, competences: 35, rag_chunks: 70, services: 35, staff_roles: 42, territories: 3 |
| NEW-263 | Чат Бот боюнча маалымат Ала-Бука РМА.docx | `9aa8de89b7043787d67b2ff0be4d1329e4bb8dfecc62aa97e6d0ce6ef93e0d85` | NEW_SOURCE | contacts: 4, staff_roles: 1, district_profiles: 1 |
| NEW-264 | Ала-Бука районунун айыл окмоттору БОТ.docx | `21dcf45f29bdc4b5a6dc7b65e2c4ec236bdc22cad262692325a62cc2d0ef0488` | SUPPLEMENTS `NEW-263` | organizations: 9, contacts: 9, territories: 26, routing_rules: 22, rag_chunks: 22, staff_roles: 23, escalation_rules: 4, topic_aliases: 5 |
| NEW-265 | Простой_запрос_недостающих_данных_AIG2C — копия.docx | `11c94f94b87849beb08350a888db94c6a9e7ebf1ed36d6c038253319f38f835b` | SUPPLEMENTS `NEW-261` | contacts: 52, conflicts: 2, staff_roles: 10, district_profiles: 1, escalation_rules: 1, procedures: 1, organizations: 52, competences: 48, rag_chunks: 63, territories: 4, service_territories: 22, routing_rules: 15, appeal_categories: 14 |

## Source findings

- `NEW-258`, `NEW-259`: Toktogul district and city contacts, village coverage, municipal service routing, district profile and escalation.
- `NEW-260`: Tash-Komur city contacts, office hours, appeal submission procedure, utility routes. The contradictory phone is preserved as a conflict.
- `NEW-261`: a filled Mayluu-Suu mayor contact confirms and adds provenance to an existing phone; blank form fields were ignored.
- `NEW-262`: health institution addresses, competences, services and internal staff roles. Named staff mobiles were not published.
- `NEW-263`, `NEW-264`: Ala-Buka administration and four ayyl-area contacts, village memberships, explicit municipal routing, escalation and staff roles.
- `NEW-265`: Suzak district administration, institution registry, service zones and road/electricity routing. Phone/fax and road-zone conflicts remain unresolved.

Validation: **PASS** (0 errors); source-value rechecks: **169**. Bot staged parser: **PASS**, 473 contacts approved. The unchanged bot passed 71 offline unit tests covering knowledge, turn resolution, golden dialogues and CRM. Current bot remains on its previous working version; embedding index has not been rebuilt.
