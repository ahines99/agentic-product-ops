# ADR-001: Offline foundation before runtime infrastructure

Status: accepted, 2026-09-28.

Context: the specification describes a complete governed vertical slice and recommends FastAPI/PostgreSQL/Temporal, while M0 explicitly requires typed offline fixtures and no external API calls. The layout also prohibits empty directories for appearance.

Decision: initialize a modular Python package with only executable components and required docs. Implement strict contracts and deterministic gates now; use exact fixture routing and a separate fake publication harness. Keep production state ownership exactly as specified: PostgreSQL records, Temporal history, Linear observed state, independent Delivery OS persistence. Do not add unused runtimes, placeholder Docker/Compose files, migrations, HTTP endpoints, or empty adapter folders.

Consequences: M0 is reproducible without services. This does not substitute a JSON/in-memory production database or complete M1–M5. Infrastructure, authentication, durability, and live adapters require the dependency-ordered backlog and their own acceptance evidence.
