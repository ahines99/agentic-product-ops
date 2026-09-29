import base64
import hashlib

import httpx
import pytest

from agentic_product_ops.adapters.repository.github import MockGitHubReader


def test_pinned_blob_and_no_code_execution():
    raw = b"raise RuntimeError('must never execute')\ndef export_report(): pass\n"
    sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()

    def handler(request):
        if "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": "a" * 40, "tree": {"sha": "b" * 40}})
        if "/trees/" in request.url.path:
            assert request.url.path.endswith("b" * 40)
            return httpx.Response(
                200,
                json={
                    "sha": "b" * 40,
                    "truncated": False,
                    "tree": [
                        {
                            "path": "report.py",
                            "mode": "100644",
                            "type": "blob",
                            "size": len(raw),
                            "sha": sha,
                        }
                    ],
                },
            )
        assert request.url.path.endswith(sha)
        return httpx.Response(
            200,
            json={
                "encoding": "base64",
                "content": base64.b64encode(raw).decode(),
                "sha": sha,
                "size": len(raw),
            },
        )

    adapter = MockGitHubReader({"reporting": "example/reporting"}, httpx.MockTransport(handler))
    snapshot = adapter.inspect("reporting", "a" * 40)
    assert snapshot.files[0].symbols == ("export_report",)
    with pytest.raises(ValueError, match="held"):
        adapter.inspect("reporting", "main")
    with pytest.raises(ValueError, match="held"):
        adapter.inspect("other", "a" * 40)
    adapter.close()


def test_truncated_tree_not_treated_as_complete():
    def handler(request):
        if "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": "a" * 40, "tree": {"sha": "b" * 40}})
        return httpx.Response(200, json={"sha": "b" * 40, "truncated": True, "tree": []})

    adapter = MockGitHubReader(
        {"reporting": "example/reporting"},
        httpx.MockTransport(handler),
    )
    with pytest.raises(ValueError, match="held"):
        adapter.inspect("reporting", "a" * 40)
    adapter.close()
