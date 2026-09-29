# ADR-014: Explicit local operator and bounded Anthropic pilot

Status: accepted, 2026-09-29. Supersedes deployment choices, not governance gates, in ADR-009/010/011. Product Ops still governs work; Delivery OS retains execution and separate persistence.

## Context

The operator selected a local pilot, Alex as approver/operator, ticket-selected repositories, the existing Linear team, API-key authentication (no OAuth), `claude-opus-5-5`, and a $10 total first smoke-test allowance. The Git remote is supplied; pushing and creating live tickets remain separate decisions.

## Decision

- Assemble the existing modular monolith through `product-ops-pilot`. A private directory holds an explicit profile, random operator bearer token, storage key and signing key. No ambient dotenv execution or credential discovery occurs. The API binds loopback. A current, revocable, 30-day durable grant maps that local credential to Alex; this is a single-user local trust model, not enterprise identity or proof that a particular person typed a command.
- Use a separate loopback `product_ops_pilot` PostgreSQL database, encrypted artifacts and the existing Temporal workflows. Test databases cannot serve as pilot databases. No shared Delivery OS store is introduced. Initialization checks migrations before generating identity files; a partial identity is never overwritten automatically.
- Allow any repository only when both server policy and the durable operator grant opt in. A ticket supplies one absolute local Git working-tree path or one fixed-host GitHub owner/repository and immutable commit SHA. Identity, bounded metadata, source snapshot, exact approval and publication digest remain bound. This removes pre-registration, not path/transport/scope checks. Raw repository bodies never become instructions or executable code.
- The Anthropic adapter supplies no tools, performs token preflight, uses strict structured JSON with original local Pydantic validation, discards thinking blocks and never retries uncertain transport outcomes. Unsupported schema constraints are described to the model and still enforced locally. Provider output has no publication authority.
- Reserve worst-case costs durably before every request under one immutable authorization ID. All runs and restarts share the allowance. Failed/uncertain reservations are retained. Input reservations use $8/MTok and output $20/MTok, conservatively above the documented standard input rate of $4. Report actual token usage and price estimates separately from unverified billing. Changing terms under an existing authorization is rejected. This is an application allowance, not a provider-account billing cap; an operator with database/filesystem control remains trusted.
- Keep generic intake at tier 3. Only an explicit authenticated security operator command can request a risk change. It must preserve the specification contents, satisfy the lexical risk floor, create a new revision and pass a fresh separate reviewer context. Prior approvals cannot authorize that revision. The agent does not impersonate Alex to approve or lower risk. The lexical floor may conservatively prevent lowering even a documentation request when repository metadata contains security terms.
- Assemble native Linear publication with API-key authentication, exact current approval/plan/grant checks and per-write authority. It remains disabled in the local profile until an exact plan is approved and live publication is authorized. API-key possession and read-only identity discovery do not authorize writes. OAuth code remains optional and unused.

## Observed consequences

The live smoke exposed mixed requirement provenance and an invalid reviewer digest. Both failures were held and preserved. A correction to provenance guidance and exact-digest echo instructions produced a reviewed proposal using six paid calls total, including failures. Completed analyst/decomposer calls were reused during the final review correction. No output was repaired into passing the gate, no human approval was fabricated and no ticket was created. See [pilot evidence](../v05-validation-record.md).

The original evaluation specification's ten categories are restored in the semantic contract: bug reports, multi-ticket, research-only and duplicate/rephrased cases replace categories inadvertently substituted in v0.4. Existing two-case templates still validate. Older external corpora using the substituted categories require explicit reclassification and re-freezing; no migration relabels evidence silently.

Sources: [Anthropic model overview](https://platform.claude.com/docs/en/models/overview), [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [token counting](https://platform.claude.com/docs/en/api/http/messages/count_tokens). These document transport/pricing choices, not product quality or billing acceptance.
