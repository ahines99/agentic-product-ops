# Roadmap: Product Ops and Delivery OS

Updated 2026-10-01. Product Ops items PO-1 to PO-8 are implemented
([ADR-027](adr/027-ticket-pickup-contract-product-ops-side.md)); PO-7 is built switched off pending
the owner's decision. Delivery OS items DO-1 to DO-5 are merged; DO-6 is in progress. This is the
joint plan for the two systems. Product Ops items (`PO-`) are built
in this repository. Delivery OS items (`DO-`) are built in `agentic-delivery-engineer` and are
listed here so both sides work to the same contract. The detailed engineering backlog stays in
[backlog.md](backlog.md).

## Why this roadmap exists

On 2026-09-30, Product Ops published PER-16 and PER-17 from the prompt console. Delivery OS's own
Linear monitor watches the same team, so it claimed both tickets within minutes, assumed they
belonged to `agentic-delivery-os`, and started runs. Its policy blocked both, so nothing was built.
But the two systems disagree about how work moves between them:

- Product Ops' rule: work is handed off only when its handoff policy allows it (today, approved
  documentation changes only), through a signed envelope.
- Delivery OS's practice: it takes any Backlog or Todo ticket in the shared team that is
  unassigned and does not name a different repository.

The roadmap closes that gap first, then builds toward real features flowing end to end.

## Ticket pickup contract, version 1

Both systems implement exactly this. Phase 1 delivers it.

| Rule | Owner | Detail |
| --- | --- | --- |
| Repository line | Product Ops writes it; Delivery OS requires it | First line of every published description: `Repository: <name>`, where `<name>` is the target repository's local directory name. Delivery OS skips a ticket with no line or with a name it does not own, and maps directory names with `linear_repository_names`. |
| Handoff line | Product Ops writes it on `delivery-ready` tickets; Delivery OS reads it | `Handoff: sha256:<digest>`. Delivery OS fetches `GET {base_url}/handoffs/{digest}` from its configured base URL with a read-only token: `200` envelope, `404` unknown or not yet available, `410` with `Reason: superseded` or `revoked` ([ADR-028](adr/028-pull-handoff-contract-with-delivery-os.md)). |
| Progress | Delivery OS writes it; Product Ops reads it | Comments with hidden `<!-- delivery-progress:<key>:<status> -->` markers; display only on the Product Ops side. |
| Opt-in label | Product Ops applies it; Delivery OS requires it | `delivery-ready`. Applied only when Product Ops' handoff policy allows delivery for that specification. Delivery OS never picks up a ticket without it. |
| Status | Neither system depends on it for pickup | New tickets keep the team's default status. Delivery OS may move a ticket it has claimed. |
| Authority | Delivery OS verifies | A label is a routing signal, not authority. From Phase 2, Delivery OS also verifies the signed approval for the ticket before executing. |
| Removal | Either side | Removing `delivery-ready` before Delivery OS claims a ticket stops pickup; after a claim, cancellation follows DO-6. |

## Phase 1: stop accidental pickup (now)

Goal: no Product Ops ticket reaches Delivery OS unless Product Ops' policy says it may.

| ID | Owner | Work | Depends on | Acceptance criteria |
| --- | --- | --- | --- | --- |
| PO-1 (done) | Product Ops | Add the `Repository:` line to every published description, under a new policy version `pilot-execution-v2`. Include the R14 escaping fix in the same version. | None | New proposals render `Repository: <name>` as the first line; apostrophes are never sent as a literal `&#x27;`; plans approved under `pilot-execution-v1` publish unchanged; read-back comparison passes on a mock round trip. |
| PO-2 (done) | Product Ops | Apply the `delivery-ready` label only when the handoff policy allows delivery. The label must already exist in Linear and is bound in the profile's scope like other labels. | PO-1 | The label appears in the exact publication plan and therefore in the approval; it is absent for every tier-2 or tier-3 specification; tests cover both cases. |
| DO-1 (merged, PR #15) | Delivery OS | Require the `delivery-ready` label in the Linear monitor's eligibility check, configurable per repository. | Contract v1 | An eligible-looking ticket without the label is never assigned or run; with the label, current behaviour is unchanged; a regression test reproduces the PER-16 case and shows no claim. |
| DO-2 (merged, PR #15) | Delivery OS | Make the `Repository:` line mandatory for automatic pickup instead of optional. | Contract v1 | Tickets with no line are skipped; tickets naming another repository are skipped; existing configured repositories still pick up correctly named tickets. |
| PO-3 (done) | Product Ops | Add a "Publish to Linear" button to the console, shown only after the exact plan is approved, with a confirmation step. All publish-time checks still run on the server. | PO-1 | The button is absent before approval and after expiry; the server rechecks approval, grant, scope and budget; an uncertain result shows a reconcile action, not a retry. |

Owner decisions in this phase: the label name, if `delivery-ready` is not wanted, and whether
the button in PO-3 is acceptable. It reverses the earlier rule that the browser cannot publish.

## Phase 2: one governed path

Goal: Delivery OS executes Product Ops work only with verifiable approval, and both sides agree on
its state.

| ID | Owner | Work | Depends on | Acceptance criteria |
| --- | --- | --- | --- | --- |
| PO-4 (done, ADR-028) | Product Ops | Write `Handoff: sha256:<digest>` into each `delivery-ready` ticket, and serve the signed envelope at `GET /handoffs/<digest>` to Delivery OS's separate read-only credential. | PO-2 | Delivery OS can fetch the envelope by the reference; the envelope verifies with the pinned key; an expired or revoked approval returns no envelope. |
| DO-3 (merged, PR #16; documentation lane PR #17) | Delivery OS | Before executing a Product Ops ticket, fetch and verify its signed envelope (issuer, key, audience, expected digest, freshness) and check that the ticket text matches the approved plan. | PO-4, DO-1 | A labelled ticket without a valid envelope is held, not run; a ticket edited after approval is held; the PER-7 path still works. |
| DO-4 (merged, PR #15) | Delivery OS | Report progress back to Linear: claimed, in progress, in review, done or blocked, with the reason when blocked, as comments with hidden markers that Product Ops reads (PO-5). | DO-3 | Each state change appears on the ticket within one poll interval; a policy block like PER-16's is visible on the ticket, not only in Delivery OS storage. |
| PO-5 (done) | Product Ops | Read Delivery OS progress and extend the derived lifecycle beyond `HANDOFF_READY` to `IN_DELIVERY`, `IN_REVIEW`, `DELIVERED` and `DELIVERY_BLOCKED`. | DO-4 | The `state` command and console show delivery progress from durable records; nothing in Product Ops changes on the strength of a Linear status alone. |

## Phase 3: real features flow end to end

Goal: an ordinary multi-ticket feature can go from the browser to reviewed changes.

| ID | Owner | Work | Depends on | Acceptance criteria |
| --- | --- | --- | --- | --- |
| PO-6 (partly met: splitting in range, routing 36% below target) | Product Ops | Calibrate ticket splitting after answers and cross-domain routing (backlog R13). | None | On a fresh set from new domains, answered proposals stay within the expected ticket range and first-pass routing holds above 60%. |
| PO-7 (switch built, off) | Owner, then Product Ops | Decide which code changes may be handed off, then encode it as a handoff policy. | Owner decision | The policy is versioned and tested; tier 3 stays excluded; approved low-risk code changes receive `delivery-ready`. |
| DO-5 (merged, PR #18; multi-item handoffs need PO-7, since the documentation lane takes one item) | Delivery OS | Accept a multi-ticket handoff with dependencies: admit all or none, refuse cycles, start a ticket only after its prerequisites succeed, never start one twice. | DO-3 | Tests cover all-or-none admission, cycles, ordering, retries and restarts; single-ticket handoffs are unchanged. |
| DO-6 (in progress) | Delivery OS | Propagate cancellation and supersession from Product Ops: a cancelled or superseded specification stops pending tickets; already-dispatched effects are reconciled, not replayed. | DO-5, PO-5 | Cancelling in Product Ops stops unstarted Delivery OS work within one poll; in-flight work finishes to a reviewable state or is marked superseded. |
| PO-8 (done) | Product Ops | Per-request inference budget in the console (backlog C02). | Owner decision on limits | Each request reserves its own allowance before analysis; exhaustion holds that request only. |

## Phase 4: evidence and release

| ID | Owner | Work | Acceptance criteria |
| --- | --- | --- | --- |
| X-1 | Owner | Independent, human-graded evaluation of at least 40 cases (the MVP gate) | Cases written and graded by a person other than the builders; results published with failures. |
| X-2 | Both | One real multi-ticket feature from the browser to merged code. The single-ticket documentation run comes first ([runbook](end-to-end-test.md)). | Every gate on both sides exercised and recorded; a human merges. |
| X-3 | Both | Tagged releases with linked validation records | Hosted CI green on both repositories; release notes state limits honestly. |

## Order of work

1. Phase 1 together: PO-1 and PO-2 in this repository, DO-1 and DO-2 in Delivery OS. PO-3 can
   follow independently. Until DO-1 ships, avoid publishing Product Ops tickets for repositories
   Delivery OS is configured for, or remove its automatic execution for the shared team.
2. Phase 2 once Phase 1 is live, starting with PO-4 and DO-3 together.
3. Phase 3 after the owner's decisions in PO-7 and PO-8.
