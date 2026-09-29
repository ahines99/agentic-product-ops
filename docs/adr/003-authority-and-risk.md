# ADR-003: Fail-closed authority and conservative lexical risk

Status: accepted, 2026-09-28.

Context: source text can claim approval, resolve its own questions, downgrade risk, or propose arbitrary teams. The suggested question model contains `resolved_by`, but a string is not an authenticated clarification receipt. Confidence and boolean fields cannot establish authority.

Decision: server-side policy remains code-owned. Unknown prompts produce maximum-risk clarification holds. Recognized authored fixtures have a conservative minimum tier 1; sensitive terms raise the floor to tier 2 and destructive/credential/compliance terms to tier 3. Scan source, requirements, criteria, proposed work, assumptions, questions, and repository excerpts. This heuristic may over-escalate and cannot understand every risky paraphrase; it is not complete semantic classification. High-risk publication validation requires a configured security approver; consumer tiers default to 0/1.

Blocking questions, needs-human-decision flags, unresolved criterion decisions, and inferred behavioral requirements stop readiness. M0 rejects claimed human clarification until an authenticated receipt service exists. Lifecycle commands requiring authenticated human or durable provider evidence remain unavailable. The simulator uses explicitly labeled actor/clock inputs and cannot produce live evidence.

Consequences: the original ambiguous revenue example cannot pass by guessed defaults or confidence. Complete example decisions are written directly into an authored source fixture. General extraction, independent review, authenticated clarification, and robust risk review remain required before live publication.
