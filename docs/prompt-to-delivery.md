# Prompt to approved Linear work

The intended operator input is a prompt and repository name. A source Linear issue is optional.
Product Ops turns that input into one or more proposed tickets with acceptance criteria and
dependencies. The human approves the exact proposal before Product Ops publishes it. Delivery OS
verifies the approved handoff and owns execution. Every merge remains human.

The authenticated entry point is `POST /v1/intakes/prompts`, with an operator bearer token,
an `Idempotency-Key`, and JSON containing `source` and `repository`. Repository names resolve
inside configured roots. Repository contents and prompt text cannot grant permissions.

The equivalent local command, against the configured running pilot API, is:

```powershell
.\.venv\Scripts\python.exe -m agentic_product_ops.pilot.cli prompt --repo agentic-product-ops --text "Describe the change here"
```

Use `--input request.txt` for longer input. Acceptance with inference disabled records a held
intake; it does not spend money or create work tickets. `run-issue` remains an optional intake
method for people who prefer to begin in Linear. An opt-in [local prompt console](local-prompt-console.md)
now supports browser intake, clarification and exact-plan review. Jira is not integrated.

The currently running separate prompt API listens on `127.0.0.1:18013`. From this integration
worktree, select it with `--directory '..\pilot\prompt'` before the `prompt` subcommand.
Authenticated intake/replay and unauthenticated denial were exercised live without model calls
or Linear writes. It is a local process, not yet a login-supervised production service.

Approved, explicitly enrolled work can be advanced by the local controller: guarded publication,
signed v2 export, authenticated loopback Delivery admission, then Delivery's own durable start
queue. The controller retries transport failures through producer receipts and consumer
idempotency. An acknowledgement means admitted, not completed. Configured `delivery_port`,
`delivery_key_file` and `delivery_specification_ids` are operator-owned, never ticket fields.

The first constrained execution path adds one inert documentation file at a pinned Git base,
creates a local review branch, and persists an OPEN/UNMERGED change request for human review.
It uses no model or target-repository code. The generic software execution path retains its
existing controls. See [ADR-017](adr/017-constrained-documentation-delivery.md).

## Current boundary and next work

- PER-7 was received from genuine Linear create/update webhooks and analyzed with four paid calls
  including its constrained preview. Product Ops reserved $1.489624 under its $2 allocation;
  Delivery's $3 allocation is untouched. Provider billing is not independently verified.
- The human approved revision 3 and its exact constrained policy. Product Ops published PER-8;
  Delivery admitted one workflow and created the exact success-marker commit with a persisted
  OPEN/UNMERGED local change request. [The live record](per7-validation-record.md) includes the
  commit, evidence, repeat checks and remaining limitations.
- Local automated tests exercise signed synthetic handoff, Delivery-owned storage, exact Git
  execution and an unmerged local change request. Synthetic receipts are not live publication evidence.
- Actual downstream admission currently accepts one work item only. Multiple-ticket dependency
  scheduling and revision invalidation are not enabled. They must not be simulated with unordered
  independent starts.
- Hosted PR publication still needs the existing Delivery GitHub App integration and explicit
  push/publication authority. The constrained local lane never substitutes a PAT or auto-merges.
- The general prompt service still needs an authorized per-request inference budget. PER-7's
  combined $5 allowance does not authorize arbitrary future requests.

## Dependency-ordered continuation

1. **Complete:** approve and exercise PER-7's exact local change request path. Acceptance: real Linear creation,
   matching signed envelope, one Delivery start, exact one-file commit and persisted human review
   evidence; repeat dispatch produces no duplicate ticket or commit.
2. Add atomic multi-item admission and durable dependency scheduling. Acceptance: all work items
   are admitted together, cycles/missing edges are denied, successors cannot start before their
   required predecessor outcome, and retries/restarts cannot create duplicate execution.
3. Add cross-system supersession and cancellation propagation. Acceptance: changed source,
   changed generated ticket, revoked approval and superseded base invalidate pending execution;
   already-dispatched effects reconcile instead of being replayed blindly.
4. Add a per-prompt budget/enrollment controller. Acceptance: prompt plus repo yields a reviewable
   ticket set without operator shell commands; inference limits are reserved before calls and
   approval never follows from a label or model text.
5. Exercise hosted PR handoff and independent product evaluations. Acceptance: actual pinned
   GitHub App checks, human merge authority, independently authored/adjudicated cases, and
   evidence-backed implementation status. Green unit tests alone do not complete this milestone.
