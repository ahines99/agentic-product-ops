# ADR 019: Explicit source-package boundary

Status: accepted and locally verified.

While verifying the integration worktree, two source distributions differed because a growing
`out/per7-verification.log` was included by the build backend. VCS-ignore discovery in this
worktree was insufficient as a package security boundary. The wheel was unaffected.

The source distribution now explicitly includes source, tests, public docs/examples/evaluations,
scripts, migrations and named root configuration files. Local operator state, credentials,
virtual environments, logs and caches are not package inputs. The reproducibility gate rejects
excluded paths in source archives and still requires two byte-identical wheel/sdist builds.
Secret scanning remains a separate check; an allowlisted example file is not permission to
embed a credential. The repaired build and clean-wheel smoke passed before release claims.
