# ADR-002: Strict immutable contracts and APO canonical JSON v1

Status: accepted, 2026-09-28.

Context: approval must survive transport while binding all meaningful specification changes. Mutable nested lists and ambiguous serialization can undermine that binding. The suggested acceptance-criterion schema lacks the provenance classification required by the product example.

Decision: use Pydantic strict/frozen/extra-forbid models with nested tuples. JSON arrays remain interoperable. Add acceptance-criterion provenance. S0 contains exact intake text, additional source statements are exact excerpts, and SHA-256 binds raw UTF-8 source bytes including newline differences. IDs are unique across reference namespaces; dependencies and criterion coverage are validated.

Specification content digest is SHA-256 of its typed JSON representation excluding only its own `content_digest`, serialized with sorted keys, UTF-8, no insignificant whitespace, and no NaN. Arrays preserve order. UUIDs serialize canonically, aware timestamps normalize to UTC, decimals serialize as decimal strings. Decimal scale and Unicode normalization are not collapsed; changes may produce a new digest. This is APO canonical JSON v1, not a claim of RFC 8785 compliance. Public schemas and fixed fixtures are compatibility vectors. Plan, request, and envelope digests use analogous explicit self-field exclusion.

The authoring helper fills a digest then runs full final validation; it grants no authorization. Each authority gate revalidates even Pydantic objects, defending against unchecked `model_copy`/`model_construct`. Cryptographic hashes prove integrity against a trusted expected digest, not source truth, human identity, or authenticity. Signatures remain future work.
