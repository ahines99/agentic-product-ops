# PER-7 controlled live integration record

Observed 2026-09-30 UTC. This record supersedes the earlier v0.5.2 integration boundary;
it does not claim MVP completion or general autonomous software execution.

## Real workflow and evidence

1. A genuine Linear-origin PER-7 event reached the durable Product Ops intake.
2. Product Ops analyzed the request and retained four model-call receipts, including the
   separately reviewed constrained documentation preview. Earlier failures were preserved.
3. Alex Hines explicitly approved revision 3, specification digest
   `2fae2dbaf44396f8875ef2b0789beb8788742886ced8289b5500181c8867f6fe`,
   plan digest `77fc782d14dc7e8f59e8c7e88b8fe02135c57696a14c9aecef3ea6286cbba562`,
   and the exact constrained policy at base `d9604888843e2b0ba60cc49565339a910e3ec393`.
   Approval ID: `75fce2c5-9c2f-4fac-a4c7-2a250dd834ea`. The original one-hour validity
   ends at `2026-09-30T03:22:15.300888Z`; completion does not renew execution authority.
4. Product Ops created [PER-8](https://linear.app/personal-portfolio-project/issue/PER-8/add-docspilot-successmd-pilot-success-marker-and-submit-for-human),
   provider ID `e05663f7-3be9-4590-9efa-435684a01fc5`. Linear reformatted Markdown.
   The publisher held UNKNOWN, then reconciled this exact ID read-only using the tested
   [syntax comparison](adr/018-linear-markdown-readback.md). It did not repeat issue creation.
5. Product Ops signed its v2 handoff. The actual Delivery API authenticated and verified it,
   reread PER-8, and transactionally created its own inbox, run and start outbox.
   Workflow ID: `f109d0c5-ee2b-43e3-8cea-159aacbe3dc6`.
6. Delivery's constrained dispatcher revalidated approval, capability, current operator,
   configuration, cancellation, ticket and base. It created Git objects and an atomic review
   reference without executing target-repository code or invoking a builder model.
7. Delivery persisted a content-addressed OPEN/UNMERGED local change request and projected
   HUMAN_REVIEW. There is one run, one inbox and one start outbox. Repeat producer delivery
   and completed execution returned the same receipt/result.

## Exact delivered change

- Branch: `delivery/doc-2fae2dbaf44396f8875ef2b0789beb8788742886ced8289b5500181c8867f6fe`.
- Commit: `b44c681ffa1df5fe0094520219a283416e35239b`.
- Parent: `d9604888843e2b0ba60cc49565339a910e3ec393`.
- Diff: only `A docs/pilot-success.md`, UTF-8 with LF and final newline, 98 bytes.
- File SHA-256: `26fc9bf3cefc5e743f0e8d71c17d617608b48e48bad692f78811d86b511a1b2d`.
- Change-request artifact SHA-256:
  `842ac4d16207fe1ec5ab4b62504ba4e6debe60a05e2b4e2dbb22c929bceb286c`.
- Target main remained clean at the approved parent. No GitHub push, PR or merge occurred.

```markdown
# Pilot success

This file confirms that the approved Linear request reached Agentic Delivery OS.
```

Private receipts, approval, signed envelope and provider read-back are retained under the
operator's `.local` profiles. Delivery's `product-ops-per7/verification.json` records exact
byte/diff assertions, workflow result and change-request reference. No credentials or private
envelopes are committed to either repository.

## Architecture and security delivered

- Authenticated prompt/repository intake endpoint and CLI; source tickets are optional.
- Public stateless verifier and strict inert-document capability, vendored with schema/license
  into Delivery; no shared persistence or imports of Product Ops internals.
- Exact specification/plan approval, semantic capability binding, current roles, expiry,
  source freshness, risk/ambiguity gates and deterministic external-write authorization.
- Signed public handoff, pinned trust/scope, idempotent admission, current-ticket rechecks,
  transactional outbox and immutable review evidence.
- Isolated Git index/hooks/environment, no target checkout or code, exact new-file and pinned
  base checks, atomic ref transaction, deterministic retry commit, human-only merge.

## Spend and limitations

Product Ops reserved $1.489624 across four observed calls (50,958 input / 6,953 output tokens),
within its $2 allocation. Delivery made zero model calls under its $3 allocation. The combined
$5 PER-7 cap was preserved. Reservations are conservative estimates, not verified billing.
Paid execution is disabled; this authorization does not fund future prompts.

The live PER-7 run began from a Linear issue. The separate authenticated prompt API is now
running on loopback port 18013 with paid execution/publication disabled. A live acceptance
request (`a48b232b-1dd7-49cb-861d-8803ed621dfd`) was recorded as held; repeating its command
returned the same intake ID and an unauthenticated request was denied with HTTP 401.
This process is not yet enrolled in the Windows login supervisor; future requests have no
new inference allowance. The older supervised monitor remains unchanged.
Product Ops can propose multiple items; actual Delivery admission currently rejects multi-item
DAGs and replacement revisions. The exercised execution lane permits this exact inert addition;
general software still has its existing separate plan/review controls. There is no UI, hosted
PR for this change, automatic merge, independent semantic evaluation result or production SLA.
Cross-system supersession/cancellation propagation and per-prompt enrollment/budget automation
remain in the [dependency-ordered backlog](prompt-to-delivery.md#dependency-ordered-continuation).

## Reproduce local checks and inspect the result

Product Ops local verification passed: 314 tests, five explicitly skipped disposable-service
tests, Ruff/format, mypy (91 source files), schema consistency, 50-document local-link checks,
219-file secret scan, unchanged fixture regeneration, two byte-identical wheel/sdist builds,
clean-wheel offline execution outside the checkout, and no known dependency vulnerabilities.
These are local results; hosted Actions have not run for this branch. The build check first
detected worktree logs leaking into source archives; an explicit source-file allowlist and
archive exclusion assertion fixed the cause before the passing rerun.

Delivery's 40 focused contract/security/storage/Git tests, lint, format, mypy (125 sources),
package build and clean-wheel public-contract smoke passed. The complete Delivery Linux collection also passed: **3,013 passed, 91 explicitly skipped**
across all 3,104 cases in eight disjoint processes. The slow Windows full run was stopped after
that complete result; it is not reported as passing. Delivery
`docs/per7-validation-record.md` retains the detailed platform boundary. The pinned Gitleaks image found
no secrets in the exported repository inventory after allowing only two exact deterministic
operation digests in named synthetic fixtures; default detectors remain enabled.

From the Product Ops integration worktree:

```powershell
python -m uv sync --locked --python 3.12
$env:VIRTUAL_ENV = Join-Path (Get-Location) '.venv'
$env:PATH = (Join-Path $env:VIRTUAL_ENV 'Scripts') + ';' + $env:PATH
.\.venv\Scripts\python.exe scripts/verify.py
.\.venv\Scripts\python.exe -m agentic_product_ops.cli demo --output out/review-demo
.\.venv\Scripts\python.exe -m agentic_product_ops.pilot.cli prompt --help
```

From the Delivery integration worktree:

```powershell
python -m uv sync --locked --extra dev --python 3.12
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
python -m uv build
```

From the original target Product Ops checkout, inspect without switching branches or merging:

```powershell
git show --stat b44c681ffa1df5fe0094520219a283416e35239b
git diff d9604888843e2b0ba60cc49565339a910e3ec393 b44c681ffa1df5fe0094520219a283416e35239b -- docs/pilot-success.md
git status --short
```

For future prompt intake, against the separate running prompt API with inference disabled:

```powershell
.\.venv\Scripts\python.exe -m agentic_product_ops.pilot.cli --directory '..\pilot\prompt' prompt --repo agentic-product-ops --text 'Describe the requested change'
```

This records held intake only. Fresh budget and exact proposal approval remain necessary before
new paid analysis/publication/execution. Do not replay the expired PER-7 approval to authorize work.

If the separate prompt process has stopped, start it from the integration worktree:

```powershell
.\.venv\Scripts\python.exe -m agentic_product_ops.pilot.cli --directory '..\pilot\prompt' serve
```
