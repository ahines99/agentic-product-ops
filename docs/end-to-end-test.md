# End-to-end run: prompt to reviewed change

From a prompt in the Product Ops console to a review branch in `agentic-delivery-engineer`,
through the [ADR-028](adr/028-pull-handoff-contract-with-delivery-os.md) pull contract and the
documentation lane ([ADR-017](adr/017-constrained-documentation-delivery.md),
[ADR-029](adr/029-documentation-lane-per-request-from-the-console.md)). No code is executed and
every merge stays human. Software requests produce tickets but are not handed off until the
owner turns on PO-7.

## One-time setup (done 2026-10-02)

Delivery OS:

- `main` installed on the service, with `automatic_execution`, `linear_repository_names:
  ["agentic-delivery-engineer"]`, `linear_progress_start` and `product_ops_repository_ids:
  ["repo-a8a12ccb002929f9de78b80e29a3e1bb"]` on the `agentic-delivery-engineer` entry.
- `alex-hines` is a Delivery operator with the `reviewer` role and in `documentation_approvers`.
- `HANDOFF_READER_TOKEN` in the service's `.local/linear.env`.
- Per-request capabilities read from Product Ops (ADR-029).

Product Ops:

- The prompt profile serves `http://127.0.0.1:18013` with publication and paid analysis on, and
  `delivery-ready` bound.

## The run

1. Open the console: `.local\pilot\prompt\Open Product Ops.cmd`.
2. Repository `agentic-delivery-engineer`. Write the request with the path and one fenced block:

   ````text
   Add a documentation page docs/product-ops-pull-handoff.md with exactly this content:

   ```
   # Product Ops pull handoff

   This file confirms that an approved Product Ops request reached Agentic Delivery OS through the pull contract.
   ```
   ````

   The content must be plain Markdown: no `<`, `>`, backticks, square brackets or links.
3. Wait for the proposal (about a minute; the page refreshes itself). Answer any required
   question.
4. **Use the documentation lane.** One paid review runs, then the request moves to the lane.
5. **Approve** the exact tickets. They start with `Repository:` and `Handoff:` and carry
   `delivery-ready`.
6. **Publish.** If the result is uncertain, use Check Linear, never retry.
7. The page shows Delivery's progress. Within one Delivery poll the ticket gets "in progress",
   then "in review", and a local review branch appears in `agentic-delivery-engineer`.
8. **Merge** the review branch.

Nothing may merge into `agentic-delivery-engineer`'s `main` between steps 4 and 7: the lane is
pinned to the commit it read, and Delivery refuses a moved base.

## Pass criteria

- One Linear ticket, created once, with the two contract lines and the label.
- Delivery OS claimed it only after verifying the envelope and the capability; one run, one
  review branch.
- The branch adds exactly the approved file at the pinned base, and nothing else.
- Progress comments appear on the ticket and in the console.

Record the result in [validation](validation.md) with the IDs, digests and spend, including
anything that failed.

A negative check worth running once: edit the published ticket's text in Linear before Delivery
claims it. Delivery should hold it as changed after approval, without claiming it.
