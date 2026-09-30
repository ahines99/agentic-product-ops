# ADR-020: Local prompt console and versioned execution briefs

Status: accepted for the local pilot, 2026-09-30.

The operator requested a local URL for entering a prompt and repository name. This later
instruction authorizes a narrow browser console despite the initialization specification's
original no-UI boundary. It does not authorize a hosted application, new model spending,
new Linear publication, automatic approval or expanded Delivery execution.

The console is an opt-in, same-process static page on the existing loopback API. An authenticated
local CLI starts the API if absent and opens a one-use, 60-second bootstrap URL. The browser
removes its fragment immediately and exchanges it for an HttpOnly, SameSite=Strict session.
Sessions expire after one hour, disappear on restart and recheck current operator authority on
every authenticated request. The operator bearer remains server-side. Exact Host and Origin
checks, a required custom header, fetch-site checks, restrictive CSP and text-only DOM rendering
protect against cross-site writes, DNS rebinding and source-content HTML execution. No CDN or
third-party assets are loaded. This trusts the local OS account and is not remote-hosting security.

The browser can submit/read requests, answer questions and approve/reject exact plans. Its
session cannot publish, mint sessions, change risk, authorize spending or start Delivery. Those
effects remain in the existing governed control plane. The page shows held analysis honestly;
acceptance of a prompt is not completion of analysis. Only the latest request ID, never prompt
text or credentials, is kept in tab session storage for refresh recovery.

Detailed execution briefs are enabled only by trusted `pilot-execution-v1` server policy.
They add repository and snapshot binding, requirement provenance, criterion verification kinds
and evidence, dependencies, assumptions and completion instructions. Structural readiness
requires a snapshot, repository assignment, per-item requirement coverage and non-placeholder
criteria/evidence. It does not prove semantic correctness. The model prompt asks for bounded,
independently verifiable work and forbids invented repository references or commands.

Existing policies retain their exact ticket rendering. In particular, PER-7/PER-8's approved
payload, plan digest and signed public handoff are unchanged. No public handoff schema change
or Delivery persistence coupling is introduced. Multiple detailed ticket proposals are supported;
the installed Delivery adapter still accepts one independent item per handoff. The console
reports this constraint rather than issuing unordered starts.

Consequences: a separate prompt profile must opt into both `local_console_enabled` and
`detailed_tickets`. General budget allocation, policy-isolated worker routing and multi-item
execution remain explicit next milestones. Existing historical allowances cannot fund new prompts.
