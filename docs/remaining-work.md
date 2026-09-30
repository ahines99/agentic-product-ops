# Remaining work after the local pilot

**Update for 0.6.0 (2026-09-30, unmerged branch):** the owner-independent engineering is done:
publication recovery after expiry, approval renewal, the republication hold, one Linear write
gate, derived lifecycle state, explicit source supersession (the supersession half of P10),
grant renewal/revocation commands and per-profile worker routing. See
[ADR-021](adr/021-publication-recovery-and-write-gate.md) and the
[v0.6 validation record](v06-validation-record.md). Everything below that is still open needs an
owner decision, live credentials, spending, a push, or a change in the Delivery OS repository:

1. Merge `feature/documentation-handoff` and `feature/finalize-offline-engineering`, then restart
   the pilot services so they run the new code.
2. Authorize a controlled live publication and reconciliation test (item 2 below).
3. Decide the risk policy for general handoff; today only the constrained documentation lane can
   reach tier 1 (item 3).
4. Authorize Delivery OS changes for multi-item admission and cancellation propagation (item 4).
5. Fund and commission the independent semantic study (item 5).
6. Authorize a push and inspect hosted CI (item 6).
7. Set a per-prompt inference budget policy before enabling continuing inference (P10) or the
   budget controller (C02).

The later [PER-7 live integration record](per7-validation-record.md) supersedes historical
claims below about missing human approval, genuine Linear events, live publication and actual
Delivery acceptance. The [current continuation](prompt-to-delivery.md#dependency-ordered-continuation)
tracks the remaining multi-ticket, revision, budget and independent acceptance work.

The [issue-driven workflow](issue-driven-operation.md) replaces manual intake preparation: the user supplies a basic Linear issue and repository name, and the agent owns service setup, commands, evidence and implementation. Version 0.5.2 completes the monitoring infrastructure in [acceptance mode](linear-monitor.md): live webhook registration, synthetic delivery, reconciliation and local restart recovery. A genuine Linear-origin issue event remains unobserved. The next engineering work is governed source supersession and continuing-inference operation (P10), followed by actual Delivery OS integration (P11). User input is reserved for the issue/repository, substantive ambiguity, exact work approval and genuinely new spending or publication authority.

Version 0.5 completes the authorized first Anthropic smoke and local integration engineering described in [evidence](v05-validation-record.md). Existing choices are settled: Alex is operator/approver, execution is local, any ticket-selected repository is allowed under the explicit grant, Linear uses the established team and API key, and the model is `claude-opus-5-5`. The Git remote is configured. These choices do not need to be requested again.

1. **Review the concrete proposal.** Read `.local/pilot/smoke-specification.json`, `smoke-review.json` and `smoke-plan.json`. Six requirements, one work item and one planned native issue are present. Alex decides whether the advisory findings need changes. No assistant command has impersonated his human approval. The source README change was a smoke request, not an instruction to execute that proposed work in Product Ops.
2. **Complete controlled Linear acceptance.** After Alex approves exact current revision/specification/plan digests and explicitly authorizes live tickets, enable the local publication setting, restart the API and publish through the guarded command. Capture actual provider receipts and controlled reconciliation evidence. Read-only discovery alone cannot establish write behavior. Use [exact commands](local-pilot.md); do not bypass the publisher with direct ticket creation.
3. **Validate low-risk handoff eligibility.** General intake remains tier 3. An explicit operator risk reassessment can request a lower tier only above the deterministic floor, followed by fresh review and approval. It is not a demo shortcut. This repository's security-related metadata can keep the smoke at tier 3. An independently justified tier-0/1 case is needed for live handoff acceptance.
4. **Integrate actual Delivery OS.** Authorize the downstream code change and pin the public issuer/key/audience/expected-digest channel. Adapt the public v2 artifact into Delivery OS's own models and store, preserve original bytes and invalidate actual stale execution plans. The reference consumer is implemented; actual downstream integration is still engineering work, not merely a missing credential.
5. **Run independent semantic acceptance.** Use the [authoring/adjudication kit](independent-evaluation-kit.md), freeze at least 40 cases across the original ten categories before inference, and authorize a separate study budget. Preserve all original attempts, failures and annotations. Include actual-model indirect injection, grounding, overlap/duplicate and research-only judgments. The $10 first-smoke run is complete and paid execution is off; it is not a 40-case study authorization.
6. **Run hosted CI after push authorization.** Origin is `https://github.com/ahines99/agentic-product-ops.git`. No push occurred. Once publication is authorized, push the reviewed commit and inspect the configured Python matrix, service and container jobs; local success is not a hosted result.
7. **Accept operations appropriate to the chosen deployment.** The local profile has owner-private keys and encrypted artifacts. Validate operator key backup/recovery and grant renewal for continued local use. Public hosting, enterprise login, production TLS/rate limits/retention/observability and incident objectives are needed only if that deployment scope is chosen; do not invent them as blockers to reading the local proposal.
8. **Make measured completion claims.** Apply [milestone exits](backlog.md) and record independent/live evidence. A human editing-time/usefulness study is needed before claiming human savings. Tag or publish an MVP/portfolio release only after its actual acceptance gates and destination authorization.

No additional key, account selection, repository URL or smoke budget is currently needed. The remaining user decisions concern human approval/live writes, downstream modification scope, an independent study and Git publication. Implementation status remains intentionally short of MVP.
