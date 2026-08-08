# Phase 07 Discussion Log

## Area: Internal ID Strategy
- **Options presented:** Deterministic hash, Random UUID4, Let the Database handle it
- **User selection:** Deterministic hash (e.g., UUID5 of source + external_id)
- **Notes:** Easier for idempotency and MERGE queries without prior lookup

## Area: Cypher Query Generation
- **Options presented:** Separate Repository Layer, Methods on Models
- **User selection:** Separate Repository Layer (e.g., `TopologyRepository.upsert(model)`)
- **Notes:** Keeps database logic out of domain models

## Area: Handling missing external fields
- **Options presented:** Strict validation (drop entity), Default placeholders (e.g., "unknown")
- **User selection:** Default placeholders (e.g., "unknown")
- **Notes:** Allows partial data to be persisted for debugging and visibility
