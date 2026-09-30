# ADR-021: Publication recovery, one Linear write gate and derived lifecycle state

Status: accepted, 2026-09-30. Exercised with mock Linear transport and recorded roles only.

## Context

An independent review of version 0.5.2 found that the approval and dispatch gates were sound
but that several paths ended in a hold with no governed way forward:

- An uncertain write could not be reconciled once its approval expired (at most 60 minutes),
  because reconciliation ran behind the same check as a new write.
- A failure during read-only preflight left a write intent that every later attempt refused.
- An expired approval of an unchanged revision could not be replaced.
- A new revision derives new ticket identities, so publishing it after an earlier revision
  had written tickets would have duplicated them in Linear.
- Mutations were checked in `create()` and in webhook management, but the shared `_query`
  helper would send any document. "Read-only" adapters were a labelling convention.
- Publication and handoff never advanced the lifecycle. The states after `APPROVED` existed
  only in the diagram.
- An edited Linear issue conflicted permanently with its enrolled specification.
- The operator grant expired after 30 days with no renewal command, and revocation had no
  command surface.

## Decisions

**Reconciliation is separate from dispatch.** `NativePublisher.reconcile` observes recorded
intents with exact-ID reads and records what it finds. It needs an active operator but no
unexpired approval, because it cannot send a write. It only looks at intents that acquired
dispatch authority. Absence, mismatch or a failed lookup leaves the operation `UNKNOWN`. The
pilot command visits every revision with a recorded plan, so a write left uncertain by an
earlier revision stays reachable after a later revision exists.

**An intent without dispatch authority may be dispatched.** Dispatch authority is committed in
the transaction immediately before the mutation is sent. If it is missing, no write left the
process, so the intent is dispatched under the authority validated for the current attempt.
Acquiring authority is exclusive: under the specification lock, a caller that finds the record
already present stops with `UNKNOWN` and sends nothing. An independent review found that the
first version of this change relied on the immutable put conflicting, which it does not when
two publishers produce byte-identical records in the same clock tick; a regression test now
interleaves two publishers deterministically.

**An expired approval can be renewed for the same exact revision.** A renewal is a new
authenticated human approval of the same content digest and plan digest. It is accepted only
after the earlier approval's expiry. A rejection, or an approval still inside its window, stays
final for that revision, and renewal is refused once every operation already succeeded, since
it would authorize nothing. Renewals are stored as a sequence beside the first decision and are
audited as `approval_renewed`. They are not signalled to the revision's workflow, which has
already completed; durable records carry the authority.

**A new revision holds when an earlier one has publication writes.** The publisher refuses
before any provider call. `allow_revision_republication` is an explicit operator assembly
setting for deployments where the downstream consumer supersedes by revision and duplicate
Linear tickets are acceptable. It defaults to off and is never read from source text. It lives
on the publisher and the pilot profile, not on `ServerPolicy`, because the server policy is
hashed into durable analysis bindings and must not change shape.

**One wire gate for mutations.** `_query` refuses any document containing a mutation unless
the caller declares `write=True`, the adapter has writes enabled, and its declared scopes
include a write-capable one. It also refuses a declared write that is not a mutation. The
webhook manager now declares an `admin` scope; every other pilot adapter is read-only at the
wire regardless of what the API key could do.

**Post-decision state is derived, not stored.** `publication_state` computes `APPROVED`,
`EXPIRED`, `REJECTED`, `LINEAR_PUBLISHING`, `RECONCILIATION_REQUIRED`, `PUBLISHED`,
`HANDOFF_READY` and `CANCELLED` from the same immutable records that authorize each dispatch.
It cannot drift from them and no caller can set it. The Temporal workflow still owns the
states up to the human decision. Handoff export now refuses a publication that is incomplete
or whose writes were dispatched under more than one approval. The pilot exports under the
approval named in the dispatch records, so a later renewal cannot detach a finished handoff.

**Source supersession is an explicit approver command.** `POST /v1/intakes/linear` accepts
`supersedes`. In one transaction it cancels the named specification and enrolls the edited
issue as a new specification at tier 3. It requires the approver role, the same issue, a real
edit, and no publication writes on the stale specification. The monitor never supersedes on
its own; an edited issue is still held until an operator decides.

**Grant renewal and revocation are local operator commands.** `grant-renew` issues the next
grant revision with the same subject, roles and scope for at most 30 days. Approvals bound to
the previous grant become stale. `revoke` is monotonic and has no inverse.

**Each pilot profile routes its own work.** A newly initialized profile gets its own Temporal
`worker_queue`, and its worker only dispatches outbox rows for its own workspace. Otherwise a
second profile's worker could start the first profile's workflows under the wrong server
policy. Existing profiles keep the shared legacy queue so in-flight workflows are not orphaned.

**The lexical risk floor gained terms.** Purge, wipe, erase and truncate (at a word start, so
"swipe" does not match), password, key and force-push wording now floors at tier 3; backup, billing, invoice, personal data, encryption
and privilege wording at tier 2. The word "author" no longer matches the `auth` rule. It is
still a conservative floor and not a classifier (ADR-003).

## Consequences and limits

- A write that was dispatched and cannot be observed stays `UNKNOWN` indefinitely. There is
  still no operator command that declares it absent and permits a resend. That is deliberate:
  absence has never proved a safe retry.
- A publication whose writes span a renewed approval is `PUBLISHED` but cannot be handed off,
  because the public v2 envelope carries exactly one approval. Changing that is a contract
  change for the consumer and was not made here.
- Stored specifications whose text matches a newly added risk term now fail the floor check
  until a human reassesses them. This fails closed.
- A superseded specification with publication writes must be handled by a person. Nothing
  here closes or edits existing Linear tickets.
- Renewing the operator grant makes every approval bound to the earlier grant stale, including
  for handoff of work already published under it. Hand off before renewing.
- The derived state reports `CANCELLED` for a cancelled specification even if one of its writes
  is still unobserved; `reconcile` still reaches that write.
- A crash after dispatch authority is committed but before the request leaves the process is
  indistinguishable from a lost response. It reads as `RECONCILIATION_REQUIRED` indefinitely.
- Existing pilot profiles share one worker queue until the operator gives each its own.
- Nothing in this ADR was exercised against live Linear. The running pilot was not restarted
  and keeps the earlier code until the operator merges and restarts it.
- The general intake floor of tier 2 for model proposals is unchanged, so only the constrained
  documentation lane (ADR-017) can reach handoff. Widening that is a risk-policy decision for
  the owner.
