"""Local pilot dependencies, live provider guards and explicit native publication assembly."""

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from agentic_product_ops.adapters.identity.contracts import Principal
from agentic_product_ops.adapters.identity.local import LocalOperatorAuthenticator
from agentic_product_ops.adapters.linear.intake import LinearIssueReader, LinearSource
from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.adapters.linear.native_plan import LinearScope, NativePlan, ProviderBinding
from agentic_product_ops.adapters.linear.offline import OperationEvidence
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
from agentic_product_ops.policies.validation import LowRiskCodePolicy, PolicyError, ServerPolicy
from agentic_product_ops.services.authority import ActorGrant, Authority
from agentic_product_ops.services.decisions import current_decision
from agentic_product_ops.services.delivery_progress import delivery_progress
from agentic_product_ops.services.documentation import constrained_policy
from agentic_product_ops.services.linear_source import validate_linear_source
from agentic_product_ops.services.native_publication import NativePublisher
from agentic_product_ops.services.publication_state import publication_state
from agentic_product_ops.services.revisions import revise_specification
from agentic_product_ops.services.risk_reassessment import RiskCommand, reassess_risk
from agentic_product_ops.services.signed_handoff import (
    dispatch_approval_id,
    export_signed_handoff,
)
from agentic_product_ops.services.spending import SpendingProvider, spending_summary
from agentic_product_ops.workflows.activities import GovernanceActivities
from agentic_product_ops.workflows.lifecycle import State


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
        policy_class = LowRiskCodePolicy if self.settings.low_risk_code_handoff else ServerPolicy
        self.base_policy = policy_class(
            # Detailed tickets use format v2 (Repository line, fixed escaping); earlier
            # requests stay under the policy version they were approved with.
            version=self.settings.ticket_policy if self.settings.detailed_tickets else "pilot-v1",
            workspace_id=self.settings.workspace,
            teams=tuple(b.local_id for b in self.settings.linear_scope.teams),
            repositories=(),
            allow_any_repository=True,
            approvers=(self.settings.operator,),
            security_approvers=(self.settings.operator,),
        )
        self.policy = (
            constrained_policy(self.base_policy, self.settings.documentation_capability)
            if self.settings.documentation_capability
            else self.base_policy
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

    def provider(self, request: str | None = None) -> SpendingProvider:
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
            request_scope=request if self.settings.request_maximum_spend else None,
            request_maximum=Decimal(self.settings.request_maximum_spend)
            if self.settings.request_maximum_spend and request
            else None,
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
            provider_per_request=True,
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
            self.provider(identifier),
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
        decision = current_decision(self.store, workspace, identifier, spec.revision)
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
                self.store,
                adapter,
                self.authority,
                source_guard=self.source_guard,
                allow_revision_republication=self.settings.allow_revision_republication,
            ).publish(spec, plan, approval, self.policy)
            return self._publication_result(identifier, spec, plan, receipts)
        finally:
            adapter.close()

    def reconcile(self, identifier: str, actor: Principal) -> dict[str, Any]:
        """Observe recorded intents read-only. Allowed with publication off or approval expired.

        Every revision with a recorded plan is visited, so a write left uncertain by an earlier
        revision stays reachable after a later revision exists.
        """
        self.authority.check(actor)
        workspace = self.settings.workspace
        current, _, _ = self.records(identifier)
        revisions: list[tuple[WorkSpecification, NativePlan]] = []
        for revision in range(1, current.revision + 1):
            try:
                plan = NativePlan.model_validate_json(
                    json.dumps(self.store.get(workspace, "publication_plan", identifier, revision))
                )
            except Missing:
                continue
            spec = WorkSpecification.model_validate_json(
                json.dumps(self.store.get(workspace, "specification", identifier, revision))
            )
            revisions.append((spec, plan))
        adapter = NativeGraphQLAdapter(
            self.settings.linear_scope,
            token=secret_from_env(Path(self.settings.linear_key_file), "LINEAR_API_KEY"),
            token_kind="api_key",  # noqa: S106
            # The write scope only satisfies relation preflight; disabled mutations cannot send.
            scopes=("read", "write"),
            allow_network=True,
            allow_mutations=False,
        )
        try:
            publisher = NativePublisher(self.store, adapter, self.authority)
            observed = {
                spec.revision: publisher.reconcile(spec, plan, self.policy)
                for spec, plan in revisions
            }
        finally:
            adapter.close()
        spec, plan = revisions[-1]
        result = self._publication_result(identifier, spec, plan, observed[spec.revision])
        return {
            **result,
            "earlier_revisions": {
                str(revision): [r.model_dump(mode="json") for r in receipts]
                for revision, receipts in observed.items()
                if revision != spec.revision and receipts
            },
        }

    def _publication_result(
        self,
        identifier: str,
        spec: WorkSpecification,
        plan: NativePlan,
        receipts: tuple[OperationEvidence, ...],
    ) -> dict[str, Any]:
        result = {
            "mode": "live_provider",
            "specification_digest": spec.content_digest,
            "receipts": [r.model_dump(mode="json") for r in receipts],
            "complete": len(receipts) == len(plan.operations)
            and all(r.status == "SUCCEEDED" for r in receipts),
        }
        if result["complete"]:
            with self.store.database.begin() as conn:
                # The ticket's Product-Ops-Specification line resolves through this index.
                self.store.put(
                    conn,
                    self.settings.workspace,
                    "handoff_index",
                    spec.content_digest,
                    1,
                    {"specification_id": identifier, "revision": spec.revision},
                )
            try:
                return self.store.get(
                    self.settings.workspace, "publication", identifier, spec.revision
                )
            except Missing:
                pass
            with self.store.database.begin() as conn:
                self.store.put(
                    conn, self.settings.workspace, "publication", identifier, spec.revision, result
                )
        return result

    def handoff_reader_matches(self, bearer: str) -> bool:
        if not self.settings.handoff_reader_token_file:
            return False
        expected = secret_from_env(
            Path(self.settings.handoff_reader_token_file), "HANDOFF_READER_TOKEN"
        ).get_secret_value()
        return hmac.compare_digest(
            hashlib.sha256(bearer.encode()).digest(), hashlib.sha256(expected.encode()).digest()
        )

    def handoff_for_digest(self, bearer: str, digest: str) -> dict[str, Any]:
        """Signed handoff for the exact specification a ticket names; Delivery OS reads this.

        The reader token can do nothing else. The specification must still be current, fully
        published and within the handoff policy; export_signed_handoff rechecks all of it.
        """
        if not self.handoff_reader_matches(bearer):
            raise PolicyError("handoff reader credential required")
        if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise PolicyError("invalid specification digest")
        index = self.store.get(self.settings.workspace, "handoff_index", digest)
        spec, _, _ = self.records(index["specification_id"])
        if spec.content_digest != digest:
            raise PolicyError("specification superseded since publication")
        return self.handoff(index["specification_id"])

    def delivery_status(self, identifier: str) -> dict[str, Any]:
        """Read-only delivery progress from Linear for a published specification."""
        _, plan, _ = self.records(identifier)
        adapter = NativeGraphQLAdapter(
            self.settings.linear_scope,
            token=secret_from_env(Path(self.settings.linear_key_file), "LINEAR_API_KEY"),
            token_kind="api_key",  # noqa: S106
            scopes=("read",),
            allow_network=True,
        )
        try:
            issues = [
                adapter._query(
                    "query ProductOpsProgress($id: String!) { issue(id: $id) { identifier "
                    "state { name type } labels(first: 20) { nodes { name } } } }",
                    {"id": str(operation.target_id)},
                )["issue"]
                for operation in plan.operations
                if operation.kind == "issue_create"
            ]
        finally:
            adapter.close()
        return delivery_progress([issue for issue in issues if issue])

    def state(self, identifier: str) -> dict[str, Any]:
        state = publication_state(
            self.store, self.settings.workspace, identifier, datetime.now(UTC)
        )
        result: dict[str, Any] = {
            "specification_id": identifier,
            "state": state.value if state else "PRE_DECISION_WORKFLOW",
            "source": "durable_records",
        }
        if state in {State.PUBLISHED, State.HANDOFF_READY}:
            try:
                result["delivery"] = self.delivery_status(identifier)
            except Exception:
                result["delivery"] = {"overall": "UNAVAILABLE", "grants_authority": False}
        return result

    def delivery_label(self) -> dict[str, Any]:
        """Find or create the delivery-ready team label and bind it in this profile's scope.

        Binding it only makes the label available; the plan applies it only when the handoff
        policy allows delivery for a specification (pickup contract v1).
        """
        from agentic_product_ops.adapters.linear.labels import ensure_team_label
        from agentic_product_ops.adapters.linear.native_plan import DELIVERY_READY_LABEL

        scope = self.settings.linear_scope
        if len(scope.teams) != 1:
            raise PolicyError("delivery label requires exactly one configured team")
        adapter = NativeGraphQLAdapter(
            scope,
            token=secret_from_env(Path(self.settings.linear_key_file), "LINEAR_API_KEY"),
            token_kind="api_key",  # noqa: S106
            scopes=("read", "write"),
            allow_network=True,
            allow_mutations=True,
        )
        try:
            label = ensure_team_label(adapter, scope.teams[0].provider_id, DELIVERY_READY_LABEL)
        finally:
            adapter.close()
        bindings = [b for b in scope.labels if b.local_id != DELIVERY_READY_LABEL]
        bindings.append(ProviderBinding(local_id=DELIVERY_READY_LABEL, provider_id=label))
        settings = self.settings.model_copy(
            update={"linear_scope": scope.model_copy(update={"labels": tuple(bindings)})}
        )
        PilotSettings.model_validate_json(settings.model_dump_json())
        target = self.directory / "pilot.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(settings.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(target)
        self.settings = settings
        return {"label": DELIVERY_READY_LABEL, "provider_id": str(label), "bound": True}

    def renew_grant(self, days: int = 30) -> dict[str, Any]:
        """Issue the next grant revision for the same operator, subject, roles and scope.

        Approvals bound to the previous grant become stale and need a fresh human decision.
        """
        if not 1 <= days <= 30:
            raise PolicyError("grant renewal is limited to 30 days")
        workspace, operator = self.settings.workspace, self.settings.operator
        previous = ActorGrant.model_validate_json(
            json.dumps(self.store.get(workspace, "actor_grant", operator))
        )
        if (
            not previous.enabled
            or self.authority.is_revoked("actor", operator)
            or self.authority.is_revoked("subject", previous.subject)
        ):
            raise PolicyError("a disabled or revoked identity cannot be renewed")
        now = self.authority.clock()
        grant = previous.model_copy(
            update={
                "revision": previous.revision + 1,
                "issued_at": now,
                "expires_at": now + timedelta(days=days),
            }
        )
        self.authority.register(grant, administrator=operator)
        return {"revision": grant.revision, "expires_at": grant.expires_at.isoformat()}

    def revoke(
        self, kind: Literal["actor", "subject", "token", "approval"], identity: str
    ) -> dict[str, Any]:
        """Monotonic local revocation; there is deliberately no command that undoes it."""
        self.authority.revoke(kind, identity, administrator=self.settings.operator)
        return {"revoked": kind}

    def handoff(self, identifier: str) -> dict[str, Any]:
        self.source_guard(identifier)
        spec, plan, _ = self.records(identifier)
        # The approval that authorized the writes, which a later renewal does not replace.
        approval_id = dispatch_approval_id(self.store, self.settings.workspace, plan)
        artifact = export_signed_handoff(
            self.store,
            self.authority,
            self.policy,
            specification_id=str(spec.specification_id),
            approval_id=approval_id,
            issuer="product-ops-local",
            key_id="pilot-v1",
            signing_key=Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(self.secrets["signing_key"])
            ),
            now=datetime.now(UTC),
        )
        return artifact.model_dump(mode="json")

    def advance_delivery(self, identifier: str) -> dict[str, Any]:
        """Publish and deliver only enrolled, already human-approved, handoff-eligible work."""
        if identifier not in self.settings.delivery_specification_ids:
            raise PolicyError("work is not enrolled for automatic delivery")
        actor = self.auth.authenticate(self.secrets["operator_token"])
        if actor is None:
            raise PolicyError("active operator required")
        spec, _, approval = self.records(identifier)
        if spec.risk.tier not in self.policy.handoff_tiers or approval.decision != "approve":
            raise PolicyError("work is not eligible for delivery")
        try:
            return self.store.get(
                self.settings.workspace, "delivery_receipt", identifier, spec.revision
            )
        except Missing:
            pass
        published = self.publish(identifier, actor, "auto-publish-" + spec.content_digest)
        if not published["complete"]:
            raise PolicyError("publication is incomplete or uncertain")
        envelope = self.handoff(identifier)
        if self.settings.delivery_key_file is None or self.settings.delivery_port is None:
            raise PolicyError("delivery endpoint is not configured")
        token = secret_from_env(Path(self.settings.delivery_key_file), "DELIVERY_OPERATOR_TOKEN")
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
            response = client.post(
                f"http://127.0.0.1:{self.settings.delivery_port}/handoffs/product-ops",
                json=envelope,
                headers={
                    "Authorization": "Bearer " + token.get_secret_value(),
                    "X-Approved-Specification-Digest": spec.content_digest,
                },
            )
        if response.status_code != 202 or len(response.content) > 16000:
            raise PolicyError("Delivery OS did not acknowledge admission")
        receipt = response.json()
        if (
            not isinstance(receipt, dict)
            or receipt.get("approved_specification_digest") != spec.content_digest
        ):
            raise PolicyError("Delivery OS acknowledged different work")
        UUID(receipt["workflow_id"])
        with self.store.database.begin() as conn:
            self.store.put(
                conn,
                self.settings.workspace,
                "delivery_receipt",
                identifier,
                spec.revision,
                receipt,
            )
        return receipt

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
            self.provider(identifier),
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
            decision_queue_enabled=self.settings.documentation_capability is None,
            console_port=self.settings.api_port if self.settings.local_console_enabled else None,
            console_publication_enabled=self.settings.allow_publication,
            repository_resolver=resolver,
            force_model_intake=True,
            publication_handler=self.publish,
            reconciliation_handler=self.reconcile,
            state_handler=self.state,
            readiness=self.readiness,
            handoff_reader=self.handoff_for_digest,
            risk_handler=self.risk,
            linear_source_reader=self.read_linear_source,
            repository_names=RepositoryNames(
                tuple(Path(p) for p in self.settings.repository_search_roots)
            ),
            source_guard=self.source_guard,
            intake_queue_enabled=self.settings.allow_paid_execution,
        )
