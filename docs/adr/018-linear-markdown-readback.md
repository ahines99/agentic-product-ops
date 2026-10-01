# ADR 018: Compare Linear read-back Markdown syntax

Status: Accepted

## Context

The approved PER-7 publication created PER-8, but Linear serialized Markdown
with blank lines after headings, alternate bullet markers, and different escaping.
The original byte comparison correctly held the outcome as UNKNOWN. Reconciliation
must recognize presentation changes without accepting changed requirements.

## Decision

Keep signed payloads, plan digests, approval bindings and executable file contents
byte-exact. Only the provider description read-back comparison uses a bounded,
locked CommonMark parser. Compare token types, nesting, tags, attributes, hidden
paragraphs, code language/content, literal text, inline children and line breaks.
Ignore source coordinates, delimiter spelling and duplicated inline source text.
Reject changed reference definitions, unsupported metadata, NUL and oversized bodies.
Exact ticket identity, title, team, project and labels retain existing comparisons.
The same public comparison module is vendored into Delivery OS for admission and
pre-execution freshness checks. It grants no execution or approval authority.

The existing deterministic issue ID is reconciled read-only. No additional issue
creation is authorized by normalization. Parser version changes require regression
review because their syntax interpretation is part of this security boundary.

## Evidence and limits

Adversarial tests reject changed prose, checkbox state, heading depth, emphasis,
links, code, HTML comments, hidden reference definitions and hard breaks. A local
comparison of the actual PER-8 response with the immutable approved payload passes.
This is CommonMark syntax equivalence, not arbitrary rich-text or HTML equivalence.
Unsupported Linear editor transformations remain held for operator review.

References: [Linear GraphQL](https://linear.app/developers/graphql),
[markdown-it-py parser](https://markdown-it-py.readthedocs.io/en/latest/using.html).

## Addendum, 2026-09-30: entity-decoded text

Publishing PER-16 from the prompt console returned an uncertain result although the issue was
created correctly. Linear had decoded HTML entities in the stored description (`&#x27;` to an
apostrophe, `&lt;short-id&gt;` to `<short-id>`, which then parses as inline HTML). The comparison
now joins text and inline-HTML runs and decodes entities before comparing, so it judges the
characters a reader sees. Links, formatting, list structure and every other token must still
match, and a real wording change still fails. Reconciliation then confirmed PER-16 read-only and
publication completed with PER-17; nothing was created twice.

The renderer's escaping is itself imperfect: it HTML-escapes apostrophes and then escapes the `#`
of the entity, so the sent Markdown spells `&#x27;` literally. Correcting it changes ticket text
and therefore plan digests, so it belongs in a new policy version (backlog R14).
