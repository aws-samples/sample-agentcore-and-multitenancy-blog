# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Tenant context management using Python ContextVar for async-safe isolation.

Each request carries tenant identity (tier, clinic_id, user_id) which flows through
to tools, memory, and document retrieval to enforce data isolation.
"""

from contextvars import ContextVar
from typing import Optional
import asyncio


class TenantContext:
    """
    Manages per-request tenant state for multi-tenant isolation.

    Uses both class-level state (for persistence across agent calls within a process)
    and ContextVar (for async-safe per-coroutine isolation).

    Key identifiers:
      - tenant_id: Service tier (basic/premium)
      - clinic_id: Clinic identifier (e.g., 'clinic-a', 'hospital-a')
      - user_id: User identifier
      - actor_id: Hierarchical key for memory isolation ({tier}-{clinic}-{user})
      - s3_prefix: Document scope prefix ({tier}-tier/{clinic}/)
    """

    # Global state for persistence across agent calls
    _gateway_token: Optional[str] = None
    _response_queue: Optional[asyncio.Queue] = None
    _agent = None
    _tenant_id: Optional[str] = None
    _clinic_id: Optional[str] = None
    _user_id: Optional[str] = None
    _actor_id: Optional[str] = None
    _s3_prefix: Optional[str] = None
    _memory_id: Optional[str] = None
    _role: Optional[str] = None

    # ContextVars for async-safe per-coroutine isolation
    _gateway_token_ctx: ContextVar[Optional[str]] = ContextVar("gateway_token", default=None)
    _response_queue_ctx: ContextVar[Optional[asyncio.Queue]] = ContextVar("response_queue", default=None)
    _agent_ctx: ContextVar = ContextVar("agent", default=None)
    _tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
    _clinic_id_ctx: ContextVar[Optional[str]] = ContextVar("clinic_id", default=None)
    _user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
    _actor_id_ctx: ContextVar[Optional[str]] = ContextVar("actor_id", default=None)
    _s3_prefix_ctx: ContextVar[Optional[str]] = ContextVar("s3_prefix", default=None)
    _memory_id_ctx: ContextVar[Optional[str]] = ContextVar("memory_id", default=None)
    _role_ctx: ContextVar[Optional[str]] = ContextVar("role", default=None)

    @classmethod
    def _get(cls, global_attr: str, ctx_var: ContextVar) -> Optional:
        val = getattr(cls, global_attr)
        if val is not None:
            return val
        try:
            return ctx_var.get()
        except LookupError:
            return None

    @classmethod
    def _set(cls, global_attr: str, ctx_var: ContextVar, value) -> None:
        setattr(cls, global_attr, value)
        ctx_var.set(value)

    # --- Accessors ---

    @classmethod
    def get_gateway_token(cls) -> Optional[str]:
        return cls._get("_gateway_token", cls._gateway_token_ctx)

    @classmethod
    def set_gateway_token(cls, token: str) -> None:
        cls._set("_gateway_token", cls._gateway_token_ctx, token)

    @classmethod
    def get_response_queue(cls) -> Optional[asyncio.Queue]:
        return cls._get("_response_queue", cls._response_queue_ctx)

    @classmethod
    def set_response_queue(cls, queue: asyncio.Queue) -> None:
        cls._set("_response_queue", cls._response_queue_ctx, queue)

    @classmethod
    def get_agent(cls):
        return cls._get("_agent", cls._agent_ctx)

    @classmethod
    def set_agent(cls, agent) -> None:
        cls._set("_agent", cls._agent_ctx, agent)

    @classmethod
    def get_tenant_id(cls) -> Optional[str]:
        return cls._get("_tenant_id", cls._tenant_id_ctx)

    @classmethod
    def set_tenant_id(cls, tenant_id: str) -> None:
        cls._set("_tenant_id", cls._tenant_id_ctx, tenant_id)

    @classmethod
    def get_clinic_id(cls) -> Optional[str]:
        return cls._get("_clinic_id", cls._clinic_id_ctx)

    @classmethod
    def set_clinic_id(cls, clinic_id: str) -> None:
        cls._set("_clinic_id", cls._clinic_id_ctx, clinic_id)

    @classmethod
    def get_user_id(cls) -> Optional[str]:
        return cls._get("_user_id", cls._user_id_ctx)

    @classmethod
    def set_user_id(cls, user_id: str) -> None:
        cls._set("_user_id", cls._user_id_ctx, user_id)

    @classmethod
    def get_actor_id(cls) -> Optional[str]:
        val = cls._get("_actor_id", cls._actor_id_ctx)
        if val:
            return val
        # Fallback: construct from available context
        tier = cls.get_tenant_id() or "basic"
        clinic = cls.get_clinic_id() or "demo-clinic"
        user = cls.get_user_id() or "demo-user"
        return f"{tier}-{clinic}-{user}"

    @classmethod
    def set_actor_id(cls, actor_id: str) -> None:
        cls._set("_actor_id", cls._actor_id_ctx, actor_id)

    @classmethod
    def get_s3_prefix(cls) -> Optional[str]:
        val = cls._get("_s3_prefix", cls._s3_prefix_ctx)
        if val:
            return val
        tier = cls.get_tenant_id() or "basic"
        clinic = cls.get_clinic_id() or "demo-clinic"
        return f"{tier}-tier/{clinic}/"

    @classmethod
    def set_s3_prefix(cls, s3_prefix: str) -> None:
        cls._set("_s3_prefix", cls._s3_prefix_ctx, s3_prefix)

    @classmethod
    def get_memory_id(cls) -> Optional[str]:
        return cls._get("_memory_id", cls._memory_id_ctx)

    @classmethod
    def set_memory_id(cls, memory_id: str) -> None:
        cls._set("_memory_id", cls._memory_id_ctx, memory_id)

    @classmethod
    def get_role(cls) -> Optional[str]:
        return cls._get("_role", cls._role_ctx)

    @classmethod
    def set_role(cls, role: str) -> None:
        cls._set("_role", cls._role_ctx, role)
