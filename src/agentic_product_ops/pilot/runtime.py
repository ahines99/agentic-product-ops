"""Local pilot dependencies, live provider guards and explicit native publication assembly."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from agentic_product_ops.adapters.identity.contracts import Principal
from agentic_product_ops.adapters.identity.local import LocalOperatorAuthenticator
from agentic_product_ops.adapters.linear.intake import LinearIssueReader, LinearSource
from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.adapters.linear.native_plan import LinearScope, NativePlan, ProviderBinding
from agentic_product_ops.adapters.model.anthropic import AnthropicProvider
from agentic_product_ops.adapters.model.contracts import ModelBudget, RuntimeConfiguration
from agentic_product_ops.adapters.persistence.encryption import StorageEncryption
from agentic_product_ops.adapters.persistence.store import Missing, Store, artifacts, engine
from agentic_product_ops.adapters.repository.names import RepositoryNames
from agentic_product_ops.adapters.repository.selection import RepositoryResolver
from agentic_product_ops.api.app import create_app
from agentic_product_ops.cli import bounded_read
from agentic_product_ops.domain.contracts import SpecificationApproval, WorkSpecification
from agentic_product_ops.pilot.config import (
    PilotSettings,
    read_secrets,
    read_settings,
    secret_from_env,
)
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.linear_source import validate_linear_source
from agentic_product_ops.services.native_publication import NativePublisher
from agentic_product_ops.services.revisions import revise_specification
from agentic_product_ops.services.risk_reassessment import RiskCommand, reassess_risk
from agentic_product_ops.services.signed_handoff import export_signed_handoff
from agentic_product_ops.services.spending import SpendingProvider, spending_summary
from agentic_product_ops.workflows.activities import GovernanceActivities


def discover_linear(token: SecretStr, team: UUID) -> LinearScope:
    provisional = LinearScope(
        organization_id=UUID(int=0),
        actor_id=UUID(int=0),
        teams=(ProviderBinding(local_id="product", provider_id=team),),
    )
    adapter = NativeGraphQLAdapter(
        provisional,
        token=token,
        token_kind="api_key",  # noqa: S106
        scopes=("read",),
        allow_network=True,
    )
    try:
        result = adapter._query(
            "query PilotIdentity($team: String!) { organization { id } "
            "viewer { id } team(id: $team) { id } }",
            {"team": str(team)},
        )
        if result["team"]["id"] != str(team):
            raise ValueError("Linear team mismatch")
        return LinearScope(
            organization_id=UUID(result["organization"]["id"]),
            actor_id=UUID(result["viewer"]["id"]),
            teams=provisional.teams,
        )
    finally:
        adapter.close()


class PilotRuntime:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.settings: PilotSettings = read_settings(directory)
        self.secrets = read_secrets(directory)
        self.store = Store(
            engine(self.settings.database_url),
            encryption=StorageEncryption(
                {"pilot-v1": bytes.fromhex(self.secrets["storage_key"])}, "pilot-v1"
            ),
        )
        self.policy = ServerPolicy(
            version="pilot-v1",
            workspace_id=self.settings.workspace,
            teams=tuple(b.local_id for b in self.settings.linear_scope.teams),
            repositories=(),
            allow_any_repository=True,
            approvers=(self.settings.operator,),
            security_approvers=(self.settings.operator,),
        )
        self.authority = Authority(
            self.store,
            workspace=self.settings.workspace,
            issuer="https://localhost/product-ops/operator",
            administrators=(self.settings.operator,),
        )
        self.auth = LocalOperatorAuthenticator(
            self.authority,
            token=SecretStr(self.secrets["operator_token"]),
            subject=self.settings.subject,
        )
        self.configuration = RuntimeConfiguration(
            configuration_id="anthropic-pilot-v3",
            provider_id="anthropic-messages",
            model=self.settings.model,
            budget=ModelBudget(
                max_calls=6,
                max_input_bytes=200000,
                max_output_tokens=8000,
                max_estimated_cost=Decimal(self.settings.maximum_spend),
                input_cost_per_million=Decimal("8"),
                output_cost_per_million=Decimal("20"),
            ),
        )

    def provider(self) -> SpendingProvider:
        provider = AnthropicProvider(
            model=self.settings.model,
            api_key=secret_from_env(Path(self.settings.anthropic_key_file), "ANTHROPIC_API_KEY"),
            allow_paid_execution=self.settings.allow_paid_execution,
        )
        return SpendingProvider(
            self.store,
            self.settings.workspace,
            self.settings.spend_authorization,
            provider,
            model=self.settings.model,
            maximum=Decimal(self.settings.maximum_spend),
            input_rate=self.configuration.budget.input_cost_per_million,
            output_rate=self.configuration.budget.output_cost_per_million,
        )

    def read_linear_source(self, reference: str) -> LinearSource:
        adapter = NativeGraphQLAdapter(
            self.settings.linear_scope,
            token=secret_from_env(Path(self.settings.linear_key_file), "LINEAR_API_KEY"),
            token_kind="api_key",  # noqa: S106
            scopes=("read",),
            allow_network=True,
            allow_mutations=False,
        )
        try:
            return LinearIssueReader(adapter).read(reference)
        finally:
            adapter.close()

    def source_guard(self, identifier: str) -> None:
        validate_linear_source(
            self.store, self.settings.workspace, identifier, self.read_linear_source
        )

    def readiness(self) -> dict[str, Any]:
        try:
            heartbeat = json.loads(bounded_read(self.directory / "worker-heartbeat.json", 1024))
            age = (datetime.now(UTC) - datetime.fromisoformat(heartbeat["at"])).total_seconds()
            recent = 0 <= age <= 10
        except (OSError, ValueError, KeyError, TypeError):
            recent = False
        active = self.authority.resolve_subject(self.settings.subject) is not None
        return {
            "ready": recent and active and self.settings.allow_paid_execution,
            "scope": "local_pilot_intake",
            "worker_heartbeat_recent": recent,
            "operator_active": active,
            "paid_execution_authorized": self.settings.allow_paid_execution,
            "publication_enabled": self.settings.allow_publication,
            "external_acceptance_verified": False,
        }

    def activities(self) -> GovernanceActivities:
        return GovernanceActivities(
            self.store,
            self.policy,
            authority=self.authority,
            linear_scope=self.settings.linear_scope,
            revision_configuration=self.configuration,
            revision_provider=self.provider,
        )

    def analyze(self, identifier: str, revision: int, digest: str, key: str) -> dict[str, Any]:
        actor = self.auth.authenticate(self.secrets["operator_token"])
        if actor is None or "intake_reader" not in actor.roles:
            raise PolicyError("current operator intake grant required")
        self.source_guard(identifier)
        spec = WorkSpecification.model_validate_json(
            json.dumps(self.store.get(self.settings.workspace, "specification", identifier))
        )
        if (spec.revision, spec.content_digest) != (revision, digest):
            raise PolicyError("stale analysis request")
        self.store.command(
            self.settings.workspace,
            actor.actor_id,
            key,
            {
                "action": "explicit_analysis",
                "id": identifier,
                "digest": digest,
                "runtime": self.configuration.model_dump(mode="json"),
            },
            lambda conn: {"intent_recorded": True},
        )
        result = revise_specification(
            self.store,
            identifier,
            digest,
            self.policy,
            self.configuration,
            self.provider(),
            initial=spec.provenance.mode == "unrecognized_input"
            and not spec.provenance.clarification_refs,
        )
        return result.model_dump(mode="json")

    def records(
        self, identifier: str
    ) -> tuple[WorkSpecification, NativePlan, SpecificationApproval]:
        workspace = self.settings.workspace
        spec = WorkSpecification.model_validate_json(
            json.dumps(self.store.get(workspace, "specification", identifier))
        )
        decision = self.store.get(workspace, "decision", identifier, spec.revision)
        approval = SpecificationApproval.model_validate_json(
            json.dumps(self.store.get(workspace, "approval", decision["approval_id"]))
        )
        plan = NativePlan.model_validate_json(
            json.dumps(self.store.get(workspace, "publication_plan", identifier, spec.revision))
        )
        return spec, plan, approval

    def evidence(self, identifier: str) -> dict[str, Any]:
        actor = self.auth.authenticate(self.secrets["operator_token"])
        if actor is None:
            raise PolicyError("active operator required")
        workspace = self.settings.workspace
        with self.store.database.connect() as conn:
            revisions: list[int] = list(
                conn.execute(
                    select(artifacts.c.revision)
                    .where(
                        artifacts.c.workspace == workspace,
                        artifacts.c.kind == "specification",
                        artifacts.c.identity == identifier,
                    )
                    .limit(1001)
                ).scalars()
            )
            executions: list[str] = list(
                conn.execute(
                    select(artifacts.c.identity)
                    .where(
                        artifacts.c.workspace == workspace,
                        artifacts.c.kind == "revision_intent",
                    )
                    .limit(1001)
                ).scalars()
            )
        if len(revisions) > 1000 or len(executions) > 1000:
            raise PolicyError("pilot evidence query bound")
        digests = {
            self.store.get(workspace, "specification", identifier, n)["content_digest"]
            for n in revisions
        }
        attempts = []
        for execution in executions:
            intent = self.store.get(workspace, "revision_intent", execution)
            if intent["base_digest"] not in digests:
                continue
            try:
                result = self.store.get(workspace, "revision_result", execution)
            except Missing:
                result = {"state": "PAUSED", "reason": "unfinished_intent", "receipts": []}
            attempts.append(
                {
                    "configuration_id": intent["configuration"]["configuration_id"],
                    "started_at": intent["created_at"],
                    "execution_digest": execution,
                    "state": result["state"],
                    "reason": result["reason"],
                    "receipts": result["receipts"],
                }
            )
        return {
            "specification_id": identifier,
            "attempts": sorted(attempts, key=lambda a: a["started_at"]),
            "spending": spending_summary(self.store, workspace, self.settings.spend_authorization),
        }

    def publish(self, identifier: str, actor: Principal, command_key: str) -> dict[str, Any]:
        if not self.settings.allow_publication:
            raise PolicyError("live publication is not enabled for this pilot")
        self.authority.check(actor)
        self.source_guard(identifier)
        spec, plan, approval = self.records(identifier)
        if actor.actor_id != approval.actor_id:
            raise PolicyError("publication operator differs from approver")
        self.store.command(
            self.settings.workspace,
            actor.actor_id,
            command_key,
            {
                "action": "native_publish",
                "specification": spec.content_digest,
                "approval": str(approval.approval_id),
            },
            lambda conn: {"intent_recorded": True},
        )
        adapter = NativeGraphQLAdapter(
            self.settings.linear_scope,
            token=secret_from_env(Path(self.settings.linear_key_file), "LINEAR_API_KEY"),
            token_kind="api_key",  # noqa: S106
            scopes=("read", "write"),
            allow_network=True,
            allow_mutations=True,
        )
        try:
            receipts = NativePublisher(
                self.store, adapter, self.authority, source_guard=self.source_guard
            ).publish(spec, plan, approval, self.policy)
            result = {
                "mode": "live_provider",
                "specification_digest": spec.content_digest,
                "receipts": [r.model_dump(mode="json") for r in receipts],
                "complete": len(receipts) == len(plan.operations)
                and all(r.status == "SUCCEEDED" for r in receipts),
            }
            if result["complete"]:
                with self.store.database.begin() as conn:
                    self.store.put(
                        conn,
                        self.settings.workspace,
                        "publication",
                        identifier,
                        spec.revision,
                        result,
                    )
            return result
        finally:
            adapter.close()

    def handoff(self, identifier: str) -> dict[str, Any]:
        self.source_guard(identifier)
        spec, _, approval = self.records(identifier)
        artifact = export_signed_handoff(
            self.store,
            self.authority,
            self.policy,
            specification_id=str(spec.specification_id),
            approval_id=str(approval.approval_id),
            issuer="product-ops-local",
            key_id="pilot-v1",
            signing_key=Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(self.secrets["signing_key"])
            ),
            now=datetime.now(UTC),
        )
        return artifact.model_dump(mode="json")

    def risk(
        self, identifier: str, actor: Principal, command: RiskCommand, key: str
    ) -> dict[str, Any]:
        if not self.settings.allow_paid_execution:
            raise PolicyError("paid risk review is disabled")
        return reassess_risk(
            self.store,
            self.authority,
            self.policy,
            self.configuration,
            self.provider(),
            identifier,
            actor,
            command,
            key,
        ).model_dump(mode="json")

    def app(self) -> FastAPI:
        resolver = RepositoryResolver(
            allow_github=True,
            github_token=(
                secret_from_env(Path(self.settings.github_key_file), "GITHUB_TOKEN")
                if self.settings.github_key_file
                else None
            ),
        )
        return create_app(
            self.store,
            self.policy,
            self.auth,
            self.authority,
            self.settings.linear_scope,
            repository_resolver=resolver,
            force_model_intake=True,
            publication_handler=self.publish,
            readiness=self.readiness,
            risk_handler=self.risk,
            linear_source_reader=self.read_linear_source,
            repository_names=RepositoryNames(
                tuple(Path(p) for p in self.settings.repository_search_roots)
            ),
            source_guard=self.source_guard,
            intake_queue_enabled=self.settings.allow_paid_execution,
        )
