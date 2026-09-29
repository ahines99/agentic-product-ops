import base64
import hashlib

import httpx
import pytest
from pydantic import SecretStr

from agentic_product_ops.adapters.repository.github import GitHubReader
from agentic_product_ops.adapters.repository.local import SnapshotLimits


@pytest.mark.parametrize(
    "fault",
    [
        "commit",
        "tree",
        "blob",
        "size",
        "path",
        "duplicate",
        "oversize",
        "redirect",
        "rate_limit",
        "timeout",
    ],
)
def test_authenticated_read_identity_and_transport_failures(fault):
    raw = b"def export_report(): pass\n"
    sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.url.host == "api.github.com"
        assert request.headers["Authorization"] == "Bearer mock-credential"
        if fault == "redirect":
            return httpx.Response(302, headers={"Location": "https://other.example/token"})
        if fault == "rate_limit":
            return httpx.Response(429, text="private")
        if fault == "timeout":
            raise httpx.ReadTimeout("private")
        if "/commits/" in request.url.path:
            return httpx.Response(
                200,
                json={"sha": ("f" if fault == "commit" else "a") * 40, "tree": {"sha": "b" * 40}},
            )
        if "/trees/" in request.url.path:
            entry = {
                "path": "../report.py" if fault == "path" else "report.py",
                "mode": "100644",
                "type": "blob",
                "sha": sha,
                "size": 200_000 if fault == "oversize" else len(raw),
            }
            return httpx.Response(
                200,
                json={
                    "sha": ("f" if fault == "tree" else "b") * 40,
                    "truncated": False,
                    "tree": [entry, entry] if fault == "duplicate" else [entry],
                },
            )
        return httpx.Response(
            200,
            json={
                "sha": sha,
                "size": 1 if fault == "size" else len(raw),
                "encoding": "base64",
                "content": base64.b64encode(b"modified" if fault == "blob" else raw).decode(),
            },
        )

    reader = GitHubReader(
        {"repo": "example/reporting"},
        httpx.MockTransport(handler),
        token=SecretStr("mock-credential"),
    )
    try:
        with pytest.raises(ValueError, match="held") as failure:
            reader.inspect("repo", "a" * 40)
        assert "private" not in str(failure.value)
        assert len(requests) <= 3
    finally:
        reader.close()


def test_excluded_tree_entries_are_never_fetched():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": "a" * 40, "tree": {"sha": "b" * 40}})
        assert "/trees/" in request.url.path
        entries = [
            {"path": path, "mode": "100644", "type": "blob", "sha": "c" * 40, "size": 10}
            for path in ("vendor/inject.py", "node_modules/a.py", ".private/key.py", "a/b/c.py")
        ]
        return httpx.Response(200, json={"sha": "b" * 40, "truncated": False, "tree": entries})

    reader = GitHubReader({"repo": "example/reporting"}, httpx.MockTransport(handler))
    try:
        assert reader.inspect("repo", "a" * 40, SnapshotLimits(max_depth=2)).files == ()
        assert len(paths) == 2
    finally:
        reader.close()
    with pytest.raises(ValueError, match="authorization"):
        GitHubReader({"repo": "example/reporting"})
