"""Verify the loopback container API's honest default-deny configuration without credentials."""

import argparse
import json
from urllib.parse import urlsplit

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    location = urlsplit(args.api_url)
    if (
        location.hostname not in {"127.0.0.1", "localhost"}
        or location.scheme != "http"
        or location.username
    ):
        raise SystemExit("Only a disposable loopback API is allowed.")
    with httpx.Client(
        base_url=args.api_url, timeout=5, trust_env=False, follow_redirects=False
    ) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        command = client.post(
            "/v1/intakes",
            json={"source": "Unprivileged probe"},
            headers={"Idempotency-Key": "container-probe"},
        )
    if (
        health.status_code != 200
        or health.json()["publication"] != "disabled"
        or ready.status_code != 503
        or command.status_code != 401
    ):
        raise SystemExit("Container default-deny/readiness check failed.")
    print(
        json.dumps(
            {
                "health": 200,
                "readiness": 503,
                "unauthenticated_command": 401,
                "publication": "disabled",
            }
        )
    )


if __name__ == "__main__":
    main()
