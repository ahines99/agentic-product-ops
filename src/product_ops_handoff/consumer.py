"""Independent public-contract reference consumer; does not schedule or execute approved work."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator


def digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def parse(raw: bytes | str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    if len(raw) > 1_000_000:
        raise ValueError("handoff exceeds bound")
    return json.loads(raw, object_pairs_hook=object_pairs)


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("aware timestamp required")
    return parsed


class ReferenceConsumer:
    def __init__(
        self,
        database_path: Path,
        *,
        keys: Mapping[tuple[str, str], Ed25519PublicKey],
        workspace: str,
        teams: tuple[str, ...],
        repositories: tuple[str, ...],
        policy_versions: tuple[str, ...],
        allow_mock_transport: bool = False,
    ) -> None:
        if not keys or not workspace or not teams or not policy_versions:
            raise ValueError("explicit consumer trust and scope required")
        self.keys, self.workspace, self.teams = dict(keys), workspace, set(teams)
        self.repositories, self.policy_versions = set(repositories), set(policy_versions)
        self.allow_mock = allow_mock_transport
        schema = json.loads(
            files("product_ops_handoff")
            .joinpath("handoff-v2.schema.json")
            .read_text(encoding="utf-8")
        )
        self.validator = Draft202012Validator(schema)
        if database_path.is_symlink():
            raise ValueError("consumer database cannot be a link")
        self.database = sqlite3.connect(database_path)
        existing = {
            row[0]
            for row in self.database.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if existing - {"delivery_intakes", "delivery_heads", "delivery_work_items"}:
            self.database.close()
            raise ValueError("reference consumer requires its own database")
        self.database.executescript("""
            CREATE TABLE IF NOT EXISTS delivery_intakes (
              issuer TEXT NOT NULL, specification_id TEXT NOT NULL, revision INTEGER NOT NULL,
              specification_digest TEXT NOT NULL, envelope_digest TEXT NOT NULL,
              original_bytes BLOB NOT NULL,
              PRIMARY KEY (issuer, specification_id, revision));
            CREATE TABLE IF NOT EXISTS delivery_heads (
              issuer TEXT NOT NULL, specification_id TEXT NOT NULL, revision INTEGER NOT NULL,
              specification_digest TEXT NOT NULL, PRIMARY KEY (issuer, specification_id));
            CREATE TABLE IF NOT EXISTS delivery_work_items (
              issuer TEXT NOT NULL, specification_id TEXT NOT NULL, revision INTEGER NOT NULL,
              local_id TEXT NOT NULL, provider_id TEXT NOT NULL, approved_digest TEXT NOT NULL,
              status TEXT NOT NULL,
              PRIMARY KEY (issuer, specification_id, revision, local_id));
            CREATE TRIGGER IF NOT EXISTS delivery_intakes_no_update
              BEFORE UPDATE ON delivery_intakes
              BEGIN SELECT RAISE(ABORT, 'immutable intake'); END;
            CREATE TRIGGER IF NOT EXISTS delivery_intakes_no_delete
              BEFORE DELETE ON delivery_intakes
              BEGIN SELECT RAISE(ABORT, 'immutable intake'); END;
        """)

    def close(self) -> None:
        self.database.close()

    def verify(self, raw: bytes, *, expected_digest: str, now: datetime) -> dict[str, Any]:
        try:
            envelope = parse(raw)
            self.validator.validate(envelope)
            payload = envelope["payload"]
            key = self.keys[(payload["issuer"], payload["key_id"])]
            actual = digest(payload)
            if actual != envelope["payload_digest"] or envelope["algorithm"] != "Ed25519":
                raise ValueError("signed digest mismatch")
            key.verify(
                base64.b64decode(envelope["signature"], validate=True),
                b"AgenticProductOps/Handoff/v2\x00" + actual.encode(),
            )
            issued, expires = timestamp(payload["issued_at"]), timestamp(payload["expires_at"])
            if (
                now.tzinfo is None
                or not issued <= now < expires
                or not 0 < (expires - issued).total_seconds() <= 3600
            ):
                raise ValueError("handoff time invalid")
            if payload["audience"] != "agentic-delivery-os" or (
                payload["mode"] == "mock_transport" and not self.allow_mock
            ):
                raise ValueError("consumer mode denied")
            self._bindings(payload, expected_digest)
            result: dict[str, Any] = payload
            return result
        except Exception:
            raise ValueError("handoff rejected by public contract or trust policy") from None

    def _bindings(self, payload: dict[str, Any], expected_digest: str) -> None:
        spec, approval, plan = payload["specification"], payload["approval"], payload["plan"]
        for value, field in ((spec, "content_digest"), (plan, "content_digest")):
            if digest({k: v for k, v in value.items() if k != field}) != value[field]:
                raise ValueError("nested digest mismatch")
        if (
            spec["content_digest"] != expected_digest
            or not spec["work_items"]
            or not spec["requirements"]
        ):
            raise ValueError("unexpected or empty approved work")
        if spec["risk"]["tier"] not in {0, 1} or any(
            w["risk_tier"] not in {0, 1} or w["risk_tier"] < spec["risk"]["tier"]
            for w in spec["work_items"]
        ):
            raise ValueError("consumer risk tier denied")
        if (
            spec["source_statements"][0]["id"] != "S0"
            or hashlib.sha256(spec["source_statements"][0]["text"].encode()).hexdigest()
            != spec["source_digest"]
        ):
            raise ValueError("source binding mismatch")
        if any(
            s["text"] not in spec["source_statements"][0]["text"] for s in spec["source_statements"]
        ):
            raise ValueError("source excerpt mismatch")
        if (
            approval["decision"] != "approve"
            or approval["specification_id"] != spec["specification_id"]
            or approval["revision"] != spec["revision"]
            or approval["content_digest"] != expected_digest
            or plan["specification_digest"] != expected_digest
            or approval["scope"]["plan_digest"] != plan["content_digest"]
            or {
                plan["workspace_id"],
                approval["scope"]["workspace_id"],
                spec["approval_policy"]["workspace_id"],
            }
            != {self.workspace}
            or {
                approval["policy_version"],
                spec["risk"]["policy_version"],
                spec["approval_policy"]["policy_version"],
            }
            - self.policy_versions
        ):
            raise ValueError("approval scope mismatch")
        if (
            len(
                {
                    approval["policy_version"],
                    spec["risk"]["policy_version"],
                    spec["approval_policy"]["policy_version"],
                }
            )
            != 1
        ):
            raise ValueError("policy versions disagree")
        work = {w["local_id"]: w for w in spec["work_items"]}
        requirements = {r["id"]: r for r in spec["requirements"]}
        if len(work) != len(spec["work_items"]) or len(requirements) != len(spec["requirements"]):
            raise ValueError("duplicate work or requirement")
        identifiers = [
            *(s["id"] for s in spec["source_statements"]),
            *requirements,
            *(q["id"] for q in spec["unresolved_questions"]),
            *(a["id"] for a in spec["assumptions"]),
            *work,
            *(a["id"] for w in work.values() for a in w["acceptance_criteria"]),
            *spec["provenance"]["policy_refs"],
            *spec["provenance"]["clarification_refs"],
        ]
        evidence = spec["repository_context"]["evidence"] if spec["repository_context"] else []
        identifiers.extend(e["id"] for e in evidence)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("duplicate contract identity")
        references = {
            "explicit_source": {s["id"] for s in spec["source_statements"]},
            "repository_evidence": {e["id"] for e in evidence},
            "policy": set(spec["provenance"]["policy_refs"]),
            "human_clarification": set(spec["provenance"]["clarification_refs"]),
        }
        for requirement in requirements.values():
            confidence = Decimal(str(requirement["confidence"]))
            if (
                not confidence.is_finite()
                or not 0 <= confidence <= 1
                or not set(requirement["source_refs"])
                <= references.get(requirement["provenance"], set())
            ):
                raise ValueError("invalid requirement provenance or confidence")
        if any(
            r["needs_human_decision"] or r["provenance"] == "safe_inference"
            for r in requirements.values()
        ):
            raise ValueError("requirements need human decision")
        if any(q["blocking"] and q["resolution"] is None for q in spec["unresolved_questions"]):
            raise ValueError("unresolved material ambiguity")
        answers = {a["id"]: a for a in payload["clarifications"]}
        if len(answers) != len(payload["clarifications"]) or set(answers) != set(
            spec["provenance"]["clarification_refs"]
        ):
            raise ValueError("clarification provenance mismatch")
        for question in spec["unresolved_questions"]:
            if question["resolution"] is None:
                continue
            matched = [a for a in answers.values() if a["question_id"] == question["id"]]
            if len(matched) != 1 or any(
                (
                    matched[0]["question_text"] != question["question"],
                    matched[0]["answer"] != question["resolution"],
                    matched[0]["actor_id"] != question["resolved_by"],
                    matched[0]["resolved_at"] != question["resolved_at"],
                    matched[0]["specification_id"] != spec["specification_id"],
                    matched[0]["workspace_id"] != self.workspace,
                    matched[0]["base_revision"] >= spec["revision"],
                )
            ):
                raise ValueError("clarification answer mismatch")
        teams = {w["proposed_team_id"] for w in work.values()}
        repositories = {w["repository_id"] for w in work.values() if w["repository_id"] is not None}
        if (
            not teams <= self.teams
            or not repositories <= self.repositories
            or set(approval["scope"]["team_ids"]) != teams
            or set(approval["scope"]["repository_ids"]) != repositories
        ):
            raise ValueError("consumer repository/team scope denied")
        if (
            spec["repository_context"]
            and spec["repository_context"]["repository_id"] not in self.repositories
        ):
            raise ValueError("consumer repository context denied")
        covered: set[str] = set()
        edges: set[tuple[str, str]] = set()
        for item in work.values():
            if (
                not set(item["requirement_ids"]) <= requirements.keys()
                or not set(item["dependencies"]) <= work.keys()
                or item["local_id"] in item["dependencies"]
            ):
                raise ValueError("invalid work references")
            edges.update((item["local_id"], dep) for dep in item["dependencies"])
            for criterion in item["acceptance_criteria"]:
                if criterion["provenance"] == "requires_human_decision" or not set(
                    criterion["requirement_ids"]
                ) <= set(item["requirement_ids"]):
                    raise ValueError("criterion not approved or traceable")
                covered.update(criterion["requirement_ids"])
        if covered != requirements.keys() or edges != {
            (d["work_item_id"], d["depends_on"]) for d in spec["dependencies"]
        }:
            raise ValueError("coverage/dependency mismatch")
        pending = {identity: set(item["dependencies"]) for identity, item in work.items()}
        while pending:
            ready = {identity for identity, deps in pending.items() if not deps & pending.keys()}
            if not ready:
                raise ValueError("cyclic approved work")
            pending = {
                identity: deps for identity, deps in pending.items() if identity not in ready
            }
        keys = [o["operation_key"] for o in plan["operations"]]
        if (
            len(set(keys)) != len(keys)
            or keys != approval["scope"]["operation_keys"]
            or len(keys) != approval["scope"]["allowed_mutation_count"]
        ):
            raise ValueError("operation scope mismatch")
        if [r["operation_key"] for r in payload["publications"]] != keys or [
            d["operation_key"] for d in payload["dispatches"]
        ] != keys:
            raise ValueError("incomplete publication evidence")
        start, end = timestamp(approval["issued_at"]), timestamp(approval["expires_at"])
        if (
            not 0
            < (end - start).total_seconds()
            <= min(3600, spec["approval_policy"]["max_age_seconds"])
        ):
            raise ValueError("approval lifetime invalid")
        for operation, receipt, dispatch in zip(
            plan["operations"], payload["publications"], payload["dispatches"], strict=True
        ):
            if (
                digest({k: v for k, v in operation.items() if k != "request_digest"})
                != operation["request_digest"]
            ):
                raise ValueError("operation digest mismatch")
            if (
                receipt["status"] != "SUCCEEDED"
                or receipt["provider_id"] != operation["target_id"]
                or receipt["request_digest"] != operation["request_digest"]
                or dispatch["request_digest"] != operation["request_digest"]
                or dispatch["mode"] != payload["mode"]
                or dispatch["approval_id"] != approval["approval_id"]
                or dispatch["specification_digest"] != expected_digest
                or dispatch["plan_digest"] != plan["content_digest"]
                or not start <= timestamp(dispatch["dispatch_at"]) < end
                or not timestamp(dispatch["dispatch_at"])
                <= timestamp(receipt["observed_at"])
                <= timestamp(payload["issued_at"])
            ):
                raise ValueError("publication/authorization receipt mismatch")
        issues = {o["work_item_id"]: o for o in plan["operations"] if o["kind"] == "issue_create"}
        if issues.keys() != work.keys() or len(issues) != sum(
            o["kind"] == "issue_create" for o in plan["operations"]
        ):
            raise ValueError("published issue mapping incomplete")
        team_map = {b["local_id"]: b["provider_id"] for b in plan["scope"]["teams"]}
        project_map = {b["local_id"]: b["provider_id"] for b in plan["scope"]["projects"]}
        label_map = {b["local_id"]: b["provider_id"] for b in plan["scope"]["labels"]}
        seen: set[str] = set()
        relations: set[tuple[str, str]] = set()
        target_to_local = {o["target_id"]: identity for identity, o in issues.items()}
        for operation in plan["operations"]:
            wire = parse(operation["payload"])
            if (
                wire["id"] != operation["target_id"]
                or not set(operation["prerequisite_keys"]) <= seen
            ):
                raise ValueError("native dispatch order or target mismatch")
            seen.add(operation["operation_key"])
            if operation["kind"] == "issue_create":
                item = work[operation["work_item_id"]]
                if (
                    set(wire)
                    - {
                        "id",
                        "title",
                        "description",
                        "teamId",
                        "projectId",
                        "labelIds",
                        "useDefaultTemplate",
                    }
                    or wire["useDefaultTemplate"] is not False
                    or operation["prerequisite_keys"]
                    or wire["title"] != item["title"]
                    or operation["team_id"] != item["proposed_team_id"]
                    or wire["teamId"] != team_map[item["proposed_team_id"]]
                    or wire.get("projectId") != project_map.get(item["proposed_project_id"])
                    or sorted(wire["labelIds"])
                    != sorted(label_map[label] for label in item["proposed_labels"])
                    or f"Digest: {expected_digest}" not in wire["description"]
                    or f"Operation: {operation['operation_key']}" not in wire["description"]
                ):
                    raise ValueError("native issue scope differs from approved work")
            else:
                if (
                    set(wire) != {"id", "type", "issueId", "relatedIssueId"}
                    or wire["type"] != "blocks"
                ):
                    raise ValueError("native relation scope mismatch")
                before, after = (
                    target_to_local[wire["issueId"]],
                    target_to_local[wire["relatedIssueId"]],
                )
                if set(operation["prerequisite_keys"]) != {
                    issues[before]["operation_key"],
                    issues[after]["operation_key"],
                }:
                    raise ValueError("native relation prerequisites mismatch")
                relations.add((after, before))
        if relations != edges or len(relations) != sum(
            o["kind"] == "relation_create" for o in plan["operations"]
        ):
            raise ValueError("native dependencies differ from approved work")

    def consume(self, raw: bytes, *, expected_digest: str, now: datetime) -> dict[str, Any]:
        payload = self.verify(raw, expected_digest=expected_digest, now=now)
        spec = payload["specification"]
        issuer, identity, revision = payload["issuer"], spec["specification_id"], spec["revision"]
        raw_digest = hashlib.sha256(raw).hexdigest()
        with self.database:
            self.database.execute("BEGIN IMMEDIATE")
            head = self.database.execute(
                "SELECT revision, specification_digest FROM delivery_heads "
                "WHERE issuer=? AND specification_id=?",
                (issuer, identity),
            ).fetchone()
            if head and (
                revision < head[0] or (revision == head[0] and expected_digest != head[1])
            ):
                raise ValueError("superseded or conflicting approved revision")
            existing = self.database.execute(
                "SELECT envelope_digest FROM delivery_intakes "
                "WHERE issuer=? AND specification_id=? AND revision=?",
                (issuer, identity, revision),
            ).fetchone()
            if existing:
                if existing[0] != raw_digest:
                    raise ValueError("immutable intake revision conflict")
                return {
                    "state": "ALREADY_ACCEPTED",
                    "approved_digest": expected_digest,
                    "revision": revision,
                }
            self.database.execute(
                "INSERT INTO delivery_intakes VALUES (?, ?, ?, ?, ?, ?)",
                (issuer, identity, revision, expected_digest, raw_digest, raw),
            )
            self.database.execute(
                "INSERT INTO delivery_heads VALUES (?, ?, ?, ?) "
                "ON CONFLICT(issuer, specification_id) "
                "DO UPDATE SET revision=excluded.revision, "
                "specification_digest=excluded.specification_digest",
                (issuer, identity, revision, expected_digest),
            )
            self.database.execute(
                "UPDATE delivery_work_items SET status='SUPERSEDED' "
                "WHERE issuer=? AND specification_id=? AND revision<?",
                (issuer, identity, revision),
            )
            for operation in payload["plan"]["operations"]:
                if operation["kind"] == "issue_create":
                    self.database.execute(
                        "INSERT INTO delivery_work_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            issuer,
                            identity,
                            revision,
                            operation["work_item_id"],
                            operation["target_id"],
                            expected_digest,
                            "APPROVED_PENDING_EXECUTION",
                        ),
                    )
        return {"state": "ACCEPTED", "approved_digest": expected_digest, "revision": revision}
