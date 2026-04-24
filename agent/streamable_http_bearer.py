# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
StreamableHTTP Client Transport with Bearer Token Authentication.

Extends the MCP StreamableHTTPTransport to add Bearer token auth
for communication with AgentCore Gateway using CUSTOM_JWT authorizer.

The same user JWT that was validated by the Runtime's Inbound JWT Authorizer
is forwarded to the Gateway, which validates it against the same Cognito pool.
No second app client or managed credential is needed.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Generator

import httpx
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.streamable_http import (
    GetSessionIdCallback,
    streamablehttp_client,
)
from mcp.shared._httpx_utils import McpHttpClientFactory, create_mcp_http_client
from mcp.shared.message import SessionMessage


class BearerTokenAuth(httpx.Auth):
    """HTTPX Auth class that adds a Bearer token to requests."""

    def __init__(self, token: str):
        self.token = token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


@asynccontextmanager
async def streamablehttp_client_with_bearer(
    url: str,
    token: str,
    headers: dict[str, str] | None = None,
    timeout: float | timedelta = 30,
    sse_read_timeout: float | timedelta = 60 * 5,
    terminate_on_close: bool = True,
    httpx_client_factory: McpHttpClientFactory = create_mcp_http_client,
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
        GetSessionIdCallback,
    ],
    None,
]:
    """
    Client transport for Streamable HTTP with Bearer token auth.

    Enables communication with AgentCore Gateway using CUSTOM_JWT authorizer.
    Forwards the user's JWT that was already validated by the Runtime.
    """
    async with streamablehttp_client(
        url=url,
        headers=headers,
        timeout=timeout,
        sse_read_timeout=sse_read_timeout,
        terminate_on_close=terminate_on_close,
        httpx_client_factory=httpx_client_factory,
        auth=BearerTokenAuth(token),
    ) as result:
        yield result
