# ADR-006: Preserve evidence and label same-context evaluation

Status: accepted, 2026-09-28.

Context: the specification requires evaluation from foundation and independent authoring for meaningful quality claims. Initialization has no live model engine, and fixture routing cannot measure extraction quality.

Decision: freeze 15 authored routing cases now, explicitly marking same-initialization-context authorship. Preserve the first report and refuse report overwrites. Do not describe the corpus as independent validation. M1/M6 require separate authorship/evaluation contexts, frozen configs, at least 40 cases for release, retained failures, and human studies only when actually conducted.

Consequences: M0 can report safety/routing outcomes and zero model calls but not precision/recall, semantic ticket quality, repository grounding accuracy, real latency/cost, or human savings. Status distinguishes implemented, locally tested, hosted CI, real infrastructure, live providers, external use, human validation, and production acceptance. Passing tests is never an MVP completion criterion by itself.
