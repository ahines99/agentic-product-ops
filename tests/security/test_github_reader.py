import base64
import hashlib

import httpx
import pytest

from agentic_product_ops.adapters.repository.github import MockGitHubReader


def test_pinned_blob_and_no_code_execution():
    raw = b"raise RuntimeError('must never execute')\ndef export_report(): pass\n"
    sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()

    def handler(request):
        if "/trees/" in request.url.path:
            assert request.url.path.endswith("a" * 40)
            return httpx.Response(
                200,
                json={
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
            200, json={"encoding": "base64", "content": base64.b64encode(raw).decode()}
        )

    adapter = MockGitHubReader({"reporting": "example/reporting"}, httpx.MockTransport(handler))
    snapshot = adapter.inspect("reporting", "a" * 40)
    assert snapshot.files[0].symbols == ("export_report",)
    with pytest.raises(ValueError, match="immutable"):
        adapter.inspect("reporting", "main")
    with pytest.raises(ValueError, match="allowlisted"):
        adapter.inspect("other", "a" * 40)
    adapter.close()


def test_truncated_tree_not_treated_as_complete():
    adapter = MockGitHubReader(
        {"reporting": "example/reporting"},
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"truncated": True, "tree": []})
        ),
    )
    with pytest.raises(ValueError, match="incomplete"):
        adapter.inspect("reporting", "a" * 40)
    adapter.close()
