# ADR-029: Documentation lane per request, chosen in the console

Status: accepted, 2026-10-02. Amends ADR-017 and ADR-027.

## Context

The documentation lane (ADR-017) was a profile setting. Using it meant terminal commands to bind
a capability, a service restart, a paid preview and a promotion, then copying the capability into
Delivery OS's config. The owner asked for the whole cycle to run from a prompt in the console.

## Decisions

1. **The lane is chosen per request.** Each revision is governed by the policy it records. A
   promoted documentation candidate records `doc-add-v1-<digest>`; Product Ops stores the
   capability under that version and rebuilds the lane policy from it. Every other revision keeps
   the profile's policy, so existing plans and approvals are unchanged.
2. **The capability comes from the request, not the model.** A documentation request names one
   `docs/` path and one fenced block. The path and the block's text are taken verbatim; the base
   is the selected local repository's `main`, read from Git's files without running Git. The
   capability must still match the analysed specification exactly (one work item, same
   repository, path and content in the source). A capability bound by hand (`doc-lane`) takes
   precedence.
3. **One console action is the security decision.** "Use the documentation lane" runs the paid
   preview and promotes the candidate, under the security approver's grant, for the exact
   revision shown. A blocking review finding stops it. The browser may take this action only
   when the profile enables publication. Other risk changes stay out of the browser (ADR-027).
4. **Approval and publication are unchanged.** The person still approves the exact plan and
   publishes it. Lane tickets carry `delivery-ready`, `Repository:` and `Handoff:`.
5. **Delivery OS reads the capability per handoff.** `GET /handoffs/{digest}/documentation-capability`
   returns it to the same read-only credential. Its digest is the signed approval's policy
   version, so Delivery OS can check it without trusting the response, and needs no
   per-request config.

## Consequences

- From a prompt, the owner's actions are: choose the lane, approve, publish, and merge the
  review branch Delivery OS creates.
- Lane approvals start no governance workflow; durable records carry their authority, as in
  ADR-017's profile mode, which remains available.
- Requests without a fenced block are not offered the lane.
