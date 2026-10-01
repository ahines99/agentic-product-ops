# End-to-end test: prompt to reviewed change through the pull contract

The first run of the [ADR-028](adr/028-pull-handoff-contract-with-delivery-os.md) pull contract
with both systems live. One request adds one documentation file to `agentic-delivery-engineer`
through the constrained documentation lane ([ADR-017](adr/017-constrained-documentation-delivery.md)).
It is the narrowest real path: no code is executed and every merge stays human. Software tickets
are not handed off until the owner turns on PO-7.

Commands run from this repository against the prompt profile:

```powershell
$pilot = { python -m uv run product-ops-pilot --directory .local\pilot\prompt @args }
```

Steps marked **(you)** are human decisions. Nobody else runs them.

## Preconditions

Delivery OS:

1. PRs #15 (DO-1, DO-2, DO-4), #16 (DO-3 pull intake) and the documentation-lane PR are merged
   and installed on the service. Its checkout of `main` is clean.
2. `config.local.json`, for the `agentic-delivery-engineer` repository entry:
   `automatic_execution: true`, `linear_repository_names: ["agentic-delivery-engineer"]`, and
   `linear_progress_start` set to the current time.
3. Delivery OS accepts Product Ops' repository identity for that entry. Product Ops identifies a
   local repository by a hash of its path; for `D:\Code\Personal\Portfolio Projects\agentic-delivery-engineer`
   it is `repo-a8a12ccb002929f9de78b80e29a3e1bb`. Admission looks the signed work item's
   `repository_id` up among configured repository IDs, so Delivery OS needs a mapping from this
   ID to its own entry. This is open Delivery OS work.
4. `HANDOFF_READER_TOKEN` is set in the Delivery service's environment from
   `.local\pilot\prompt\handoff-reader.env` **(you)**.

Product Ops:

5. The pilot is running (`& $pilot start`) and `http://127.0.0.1:18013/health` answers.
6. The spending cap has room: `& $pilot status`. A request needs about $1.50 (analysis plus the
   documentation preview), within the $2 per-request allowance.

## Steps

1. **Write the file content.** For example `e2e-content.md`:

   ```markdown
   # Product Ops pull handoff

   This file confirms that an approved Product Ops request reached Agentic Delivery OS through the pull contract.
   ```

   The lane accepts plain Markdown only: no `<`, `>`, backticks, square brackets or links, and
   it must end with a newline.

2. **Submit the request** in the console, or:

   ```powershell
   & $pilot prompt --repo agentic-delivery-engineer --input e2e-request.txt
   ```

   The request text must contain the path (`docs/product-ops-pull-handoff.md`) and the exact
   content from step 1. Answer any blocking questions. Expect one ticket at tier 2, held from
   handoff by the general policy.

3. **Bind the lane to this request.** Pin the commit the file will be added to:

   ```powershell
   $base = git -C ..\agentic-delivery-engineer rev-parse main
   & $pilot doc-lane --id SPEC-ID --path docs/product-ops-pull-handoff.md --content-file e2e-content.md --base-sha $base
   ```

   The command refuses a request whose path, content, repository or work items differ. Restart
   the pilot (`stop`, then `start`) so the profile uses the lane's policy.

4. **Give Delivery OS the same capability.** Copy the `documentation_capability` object from
   `.local\pilot\prompt\pilot.json` into Delivery's `product_ops` block, add the printed
   `policy_version` to its `policy_versions`, and set `documentation_approvers: ["alex-hines"]`.
   Restart the Delivery service. Do not merge anything into `agentic-delivery-engineer` from here
   until the test ends; the lane refuses a moved base.

5. **Preview** (one paid review call; approves nothing):

   ```powershell
   & $pilot doc-preview --id SPEC-ID
   ```

   Expect no blocking findings. Note `candidate_digest`.

6. **Promote (you).** The security decision that this exact candidate may use the lane:

   ```powershell
   & $pilot doc-promote --candidate CANDIDATE-DIGEST
   ```

7. **Approve the exact plan (you)** in the console. The ticket preview must start with
   `Repository: agentic-delivery-engineer` and `Handoff: sha256:<digest>`, and carry
   `delivery-ready`.

8. **Publish (you)** in the console. If the result is uncertain, use Check Linear, never retry.

9. **Watch the pickup.** Within one Delivery poll, the ticket gets an "in progress" comment.
   Delivery fetches `GET /handoffs/<digest>`, verifies it, and the lane creates a local review
   branch, followed by an "in review" comment. `& $pilot state --id SPEC-ID` shows the progress.

10. **Review and merge (you)** the review branch in `agentic-delivery-engineer`.

## Pass criteria

- One Linear ticket, created once, with the two contract lines and the label.
- Delivery OS claimed it only after verifying the envelope; one run, one review branch.
- The branch adds exactly the approved file at the pinned base, and nothing else.
- Progress comments appear on the ticket, and Product Ops `state` reports them.
- No step needed a credential in a command line or output.

Record the result in [validation](validation.md) with the IDs, digests and spend, as for
[PER-7](per7-validation-record.md), including anything that failed.

## Afterwards

```powershell
& $pilot doc-lane-clear
```

Then restart the pilot. Keep the lane bound until Delivery OS has finished: Product Ops serves
the handoff under the lane's policy, so clearing it early makes `GET /handoffs/<digest>` fail.
Remove the capability from Delivery's config too.

A negative check worth running once: edit the published ticket's text in Linear before Delivery
claims it. Delivery should hold it as changed after approval, without claiming it.
