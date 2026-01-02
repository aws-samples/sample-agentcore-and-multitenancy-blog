from .agent import CustomerSupport
from contextvars import ContextVar
from typing import Optional
import asyncio


class CustomerSupportContext:
    """
    Enhanced Context Manager for Healthcare Multi-Tenant Clinical Document Assistant.
    
    Manages both tier-level (basic/premium) and clinic-level context for complete
    tenant isolation and proper resource routing.
    """

    # Global state for tokens that persist across agent calls
    _google_token: Optional[str] = None
    _gateway_token: Optional[str] = None
    _response_queue: Optional[asyncio.Queue] = None
    _agent: Optional[CustomerSupport] = None
    _tenant_id: Optional[str] = None  # Tier level (basic/premium)
    
    # Enhanced healthcare multi-tenancy context
    _clinic_id: Optional[str] = None  # Clinic identifier
    _user_id: Optional[str] = None  # User identifier
    _actor_id: Optional[str] = None  # Memory isolation identifier
    _tenant_key: Optional[str] = None  # Combined tier-clinic key
    _s3_prefix: Optional[str] = None  # Document scope prefix
    _memory_id: Optional[str] = None  # Memory resource identifier
    _role: Optional[str] = None  # User role
    
    # Context variables for application state
    _google_token_ctx: ContextVar[Optional[str]] = ContextVar(
        "google_token", default=None
    )
    _gateway_token_ctx: ContextVar[Optional[str]] = ContextVar(
        "gateway_token", default=None
    )
    _response_queue_ctx: ContextVar[Optional[asyncio.Queue]] = ContextVar(
        "response_queue", default=None
    )
    _agent_ctx: ContextVar[Optional[CustomerSupport]] = ContextVar(
        "agent", default=None
    )
    _tenant_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "tenant_id", default=None
    )
    
    # Enhanced healthcare context variables
    _clinic_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "clinic_id", default=None
    )
    _user_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "user_id", default=None
    )
    _actor_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "actor_id", default=None
    )
    _tenant_key_ctx: ContextVar[Optional[str]] = ContextVar(
        "tenant_key", default=None
    )
    _s3_prefix_ctx: ContextVar[Optional[str]] = ContextVar(
        "s3_prefix", default=None
    )
    _memory_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "memory_id", default=None
    )
    _role_ctx: ContextVar[Optional[str]] = ContextVar(
        "role", default=None
    )

    @classmethod
    def get_google_token_ctx(
        cls,
    ) -> Optional[str]:
        # First try to get from global state for persistence across calls
        if cls._google_token:
            return cls._google_token
        try:
            return cls._google_token_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_google_token_ctx(cls, token: str) -> None:
        # Set both global state and context variable
        cls._google_token = token
        cls._google_token_ctx.set(token)

    @classmethod
    def get_response_queue_ctx(
        cls,
    ) -> Optional[asyncio.Queue]:
        # First try to get from global state for persistence across calls
        if cls._response_queue:
            return cls._response_queue
        try:
            return cls._response_queue_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_response_queue_ctx(cls, queue: asyncio.Queue) -> None:
        # Set both global state and context variable
        cls._response_queue = queue
        cls._response_queue_ctx.set(queue)

    @classmethod
    def get_gateway_token_ctx(
        cls,
    ) -> Optional[str]:
        # First try to get from global state for persistence across calls
        if cls._gateway_token:
            return cls._gateway_token
        try:
            return cls._gateway_token_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_gateway_token_ctx(cls, token: str) -> None:
        # Set both global state and context variable
        cls._gateway_token = token
        cls._gateway_token_ctx.set(token)

    @classmethod
    def get_agent_ctx(
        cls,
    ) -> Optional[CustomerSupport]:
        # First try to get from global state for persistence across calls
        if cls._agent:
            return cls._agent
        try:
            return cls._agent_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_agent_ctx(cls, agent: CustomerSupport) -> None:
        # Set both global state and context variable
        cls._agent = agent
        cls._agent_ctx.set(agent)

    @classmethod
    def get_tenant_id_ctx(cls) -> Optional[str]:
        """Get tier level (basic/premium)"""
        if cls._tenant_id:
            return cls._tenant_id
        try:
            return cls._tenant_id_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_tenant_id_ctx(cls, tenant_id: str) -> None:
        """Set tier level (basic/premium)"""
        cls._tenant_id = tenant_id
        cls._tenant_id_ctx.set(tenant_id)

    # Enhanced healthcare multi-tenancy context methods
    
    @classmethod
    def get_clinic_id_ctx(cls) -> Optional[str]:
        """Get clinic identifier (e.g., 'clinic-a', 'hospital-a')"""
        if cls._clinic_id:
            return cls._clinic_id
        try:
            return cls._clinic_id_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_clinic_id_ctx(cls, clinic_id: str) -> None:
        """Set clinic identifier"""
        cls._clinic_id = clinic_id
        cls._clinic_id_ctx.set(clinic_id)

    @classmethod
    def get_user_id_ctx(cls) -> Optional[str]:
        """Get user identifier"""
        if cls._user_id:
            return cls._user_id
        try:
            return cls._user_id_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_user_id_ctx(cls, user_id: str) -> None:
        """Set user identifier"""
        cls._user_id = user_id
        cls._user_id_ctx.set(user_id)

    @classmethod
    def get_actor_id_ctx(cls) -> Optional[str]:
        """Get hierarchical actor_id for memory isolation (tier-clinic-user)"""
        if cls._actor_id:
            return cls._actor_id
        try:
            return cls._actor_id_ctx.get()
        except LookupError:
            # Fallback: construct from available context
            tier = cls.get_tenant_id_ctx() or 'basic'
            clinic = cls.get_clinic_id_ctx() or 'demo-clinic'
            user = cls.get_user_id_ctx() or 'demo-user'
            return f"{tier}-{clinic}-{user}"

    @classmethod
    def set_actor_id_ctx(cls, actor_id: str) -> None:
        """Set hierarchical actor_id for memory isolation"""
        cls._actor_id = actor_id
        cls._actor_id_ctx.set(actor_id)

    @classmethod
    def get_tenant_key_ctx(cls) -> Optional[str]:
        """Get combined tier-clinic key for routing (e.g., 'basic-clinic-a')"""
        if cls._tenant_key:
            return cls._tenant_key
        try:
            return cls._tenant_key_ctx.get()
        except LookupError:
            # Fallback: construct from existing context
            tier = cls.get_tenant_id_ctx() or 'basic'
            clinic = cls.get_clinic_id_ctx() or 'demo-clinic'
            return f"{tier}-{clinic}"

    @classmethod
    def set_tenant_key_ctx(cls, tenant_key: str) -> None:
        """Set combined tier-clinic key"""
        cls._tenant_key = tenant_key
        cls._tenant_key_ctx.set(tenant_key)

    @classmethod
    def get_s3_prefix_ctx(cls) -> Optional[str]:
        """Get S3 document prefix for clinic isolation (e.g., 'basic-tier/clinic-a/')"""
        if cls._s3_prefix:
            return cls._s3_prefix
        try:
            return cls._s3_prefix_ctx.get()
        except LookupError:
            # Fallback: construct from existing context
            tier = cls.get_tenant_id_ctx() or 'basic'
            clinic = cls.get_clinic_id_ctx() or 'demo-clinic'
            return f"{tier}-tier/{clinic}/"

    @classmethod
    def set_s3_prefix_ctx(cls, s3_prefix: str) -> None:
        """Set S3 document prefix"""
        cls._s3_prefix = s3_prefix
        cls._s3_prefix_ctx.set(s3_prefix)

    @classmethod
    def get_memory_id_ctx(cls) -> Optional[str]:
        """Get memory resource identifier (e.g., 'healthcare-basic-memory')"""
        if cls._memory_id:
            return cls._memory_id
        try:
            return cls._memory_id_ctx.get()
        except LookupError:
            # Fallback: construct from tier
            tier = cls.get_tenant_id_ctx() or 'basic'
            return f"healthcare-{tier}-memory"

    @classmethod
    def set_memory_id_ctx(cls, memory_id: str) -> None:
        """Set memory resource identifier"""
        cls._memory_id = memory_id
        cls._memory_id_ctx.set(memory_id)

    @classmethod
    def get_role_ctx(cls) -> Optional[str]:
        """Get user role"""
        if cls._role:
            return cls._role
        try:
            return cls._role_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_role_ctx(cls, role: str) -> None:
        """Set user role"""
        cls._role = role
        cls._role_ctx.set(role)
