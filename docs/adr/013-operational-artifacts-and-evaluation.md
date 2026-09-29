# ADR-013: Protected artifacts and honest evaluation evidence

Status: accepted for 0.4.0, 2026-09-29.

Immutable audit evidence and retention requests conflict if retention silently deletes the only approval or provenance record. Store encryption is therefore explicit AES-256-GCM with injected key IDs and row-identity authenticated data. Only raw role request/response access can expire; specifications, approvals, findings and audit metadata remain attributable. Expiry denies reads but retains ciphertext. Physical purge, deployment key custody and legal retention choices require an operator policy and are not represented as completed deletion. Command/outbox/audit metadata still need database encryption and access control.

Metadata-only manifest and metric exports exclude source text, responses, issue titles, credentials and free-form errors. Role durations and publication dispatch-to-observation durations are distinct. They do not invent human-wait metrics, billed costs or distributed trace coverage. Bounds reject oversized exports instead of truncating evidence.

Development containers are pinned by manifest digest. Backup validation uses a populated, explicitly disposable loopback database, restores into an owned random database, compares logical row fingerprints and exercises restored immutability triggers. It never restores over the source. Docker development and successful recovery are local engineering evidence, not production acceptance.

Semantic metrics require frozen gold cases, explicit adjudication of every prediction and every attempt, and original first attempts for every case. Zero denominators remain null; retries cannot overwrite failures. Signed reviewer attestations bind exact corpus/results, but authenticate an assertion rather than proving correctness or independence. Same-context examples cannot count toward the independent 40+ corpus. The scorer always reports MVP completion as false; product milestone acceptance also needs live integration and human evidence.

Consequences: no default deployment secrets, silent evidence deletion, invented semantic scoring or promotion of mock publication to live evidence. The remaining external gates are recorded in the implementation status and dependency backlog.
