# Local prompt console

The local entry point is **http://127.0.0.1:18013**. Start a secure session with
`product-ops-pilot --directory <prompt-profile> open`. It starts the configured loopback API
if needed and opens a one-use sign-in link without printing credentials. A plain URL works
while that browser session is active; after one hour or an API restart, launch it again.

On the current operator machine, from the main `agentic-product-ops` directory:

```powershell
& '.\.local\pilot\prompt\Open Product Ops.cmd'
```

The equivalent command, using the isolated implementation checkout, is:

```powershell
& '.\.local\integration-product-ops\.venv\Scripts\python.exe' -m agentic_product_ops.pilot.cli --directory '.\.local\pilot\prompt' open
```

Enter a repository name and the outcome you want. Product Ops records the request, inspects
the repository without executing its code, and uses the configured analysis path when a current
budget is authorized. Missing decisions appear as questions. Review the proposed tickets and
exact publication plan before approving. The page restores the latest request in the same tab
after refresh; use Refresh to check analysis progress.

Each detailed proposal contains objective/context, assigned requirements, concrete acceptance
criteria, criterion-specific verification/evidence, repository ID and snapshot references,
dependencies, risks, assumptions and completion instructions. The server holds proposals lacking
repository binding, per-ticket requirement coverage or meaningful non-placeholder evidence.
Model review and human review still determine whether the details actually meet the request.

The current prompt profile has **paid analysis and publication disabled**. Saving a request is
executable now and explicitly reports that hold. Historical smoke/PER-7 budgets do not authorize
new work. Browser approval records an exact decision; it does not enable publication or Delivery.
An authorized controller must separately enroll and advance approved work.

Multiple tickets can be proposed and published by Product Ops under its existing gates. General
multi-ticket execution is not available: the installed Delivery adapter accepts one independent
ticket per handoff. The separately demonstrated PER-7 documentation lane reached human review;
it does not establish arbitrary software delivery readiness.

The profile is a local process with launch-on-demand, not a production or login-supervised
prompt service. Do not bind the console to a remote interface. Each profile's workers must use
the corresponding server policy. Since version 0.6.0 a newly initialized profile gets its own
`worker_queue`, and each worker only dispatches outbox rows for its own workspace. Profiles
created earlier keep the shared `product-ops-pilot` queue until the operator sets `worker_queue`
while no workflows are in flight; two profiles that also share a workspace name and database
cannot be isolated this way. See [ADR-020](adr/020-local-prompt-console-and-execution-briefs.md).

Validation covers HTTP authentication, session replay/revocation/logout, CSRF/rebinding denial,
readiness holds, legacy rendering compatibility and packaged assets. Browser automation was
unavailable in this environment, so visual and interactive browser validation is not claimed.
The updated model prompt has not been exercised with a new paid call.

Final local verification on Python 3.12.10: 330 tests passed, five explicit disposable-service
tests skipped; lint, formatting, typing (93 source files), docs/schema checks, secret scanning,
byte-identical builds, clean-wheel installation including console assets and dependency audit
passed. JavaScript syntax checking passed. Hosted CI was not run in this pass. A live loopback
HTTP check saved one held request, confirmed identical replay, denied unreviewed approval and
invalidated a signed-out session, with zero model calls and zero Linear writes. Its private
receipt is stored in the prompt profile as `console-verification.json`.
