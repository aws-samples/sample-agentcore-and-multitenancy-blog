#!/usr/bin/python
"""
Healthcare Tools Test Suite

Tests the healthcare-specific Lambda tools through AgentCore gateways:
- patient_context: Patient metadata lookup
- clinic_config: Clinic configuration retrieval

Tests both basic and premium tier gateways with proper tenant isolation.
"""

import asyncio
import click
import json
import sys
import os
from bedrock_agentcore.identity.auth import requires_access_token
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.utils import get_ssm_parameter

gateway_access_token = None


@requires_access_token(
    provider_name=get_ssm_parameter("/app/healthcare/agentcore/cognito_provider"),
    scopes=[],
    auth_flow="M2M",
)
async def _get_access_token_manually(*, access_token: str):
    global gateway_access_token
    gateway_access_token = access_token
    return access_token


def test_gateway_tools(tier: str, clinic_id: str = "clinic-a"):
    """Test healthcare tools through the specified tier gateway"""
    
    print(f"\n{'='*60}")
    print(f"Testing {tier.upper()} Tier Gateway")
    print(f"Clinic: {clinic_id}")
    print(f"{'='*60}\n")
    
    # Fetch access token
    asyncio.run(_get_access_token_manually(access_token=""))
    
    # Load gateway configuration for the specified tier
    try:
        gateway_url = get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_url")
        print(f"✅ Gateway URL: {gateway_url}")
    except Exception as e:
        print(f"❌ Error reading gateway URL from SSM: {str(e)}")
        return False
    
    # Set up MCP client with tenant headers
    s3_prefix = f"{tier}-tier/{clinic_id}/"
    client = MCPClient(
        lambda: streamablehttp_client(
            gateway_url,
            headers={
                "Authorization": f"Bearer {gateway_access_token}",
                "X-Tenant-ID": tier,
                "X-Clinic-ID": clinic_id,
                "X-S3-Prefix": s3_prefix
            },
        )
    )
    
    try:
        with client:
            # List available tools
            tools = client.list_tools_sync()
            print(f"\n📋 Available Tools ({len(tools)}):")
            for tool in tools:
                tool_name = getattr(tool, '__name__', getattr(tool, 'name', 'unknown'))
                tool_doc = getattr(tool, '__doc__', 'No description')
                print(f"  - {tool_name}: {tool_doc[:80]}...")
            
            # Test 1: Get clinic configuration
            print(f"\n🧪 Test 1: Get Clinic Configuration")
            print(f"   Prompt: 'What services does this clinic offer?'")
            agent = Agent(tools=tools)
            response = agent("What services does this clinic offer?")
            print(f"   Response: {str(response)[:200]}...")
            
            # Test 2: List patients (if data exists)
            print(f"\n🧪 Test 2: List Patients")
            print(f"   Prompt: 'List all patients in this clinic'")
            response = agent("List all patients in this clinic")
            print(f"   Response: {str(response)[:200]}...")
            
            # Test 3: Get specific patient (if data exists)
            print(f"\n🧪 Test 3: Get Patient Details")
            print(f"   Prompt: 'Get details for patient P12345'")
            response = agent("Get details for patient P12345")
            print(f"   Response: {str(response)[:200]}...")
            
            print(f"\n✅ {tier.upper()} tier gateway tests completed successfully")
            return True
            
    except Exception as e:
        print(f"\n❌ Error testing {tier} tier gateway: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def verify_tool_registration(tier: str):
    """Verify tools are properly registered with the gateway"""
    
    print(f"\n{'='*60}")
    print(f"Verifying Tool Registration - {tier.upper()} Tier")
    print(f"{'='*60}\n")
    
    # Fetch access token
    asyncio.run(_get_access_token_manually(access_token=""))
    
    try:
        gateway_url = get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_url")
        print(f"✅ Gateway URL: {gateway_url}")
    except Exception as e:
        print(f"❌ Error reading gateway URL: {str(e)}")
        return False
    
    # Set up MCP client
    client = MCPClient(
        lambda: streamablehttp_client(
            gateway_url,
            headers={"Authorization": f"Bearer {gateway_access_token}"},
        )
    )
    
    try:
        with client:
            tools = client.list_tools_sync()
            tool_names = [getattr(t, '__name__', getattr(t, 'name', 'unknown')) for t in tools]
            
            print(f"\n📋 Registered Tools ({len(tools)}):")
            for name in tool_names:
                print(f"  ✓ {name}")
            
            # Check for expected healthcare tools
            expected_tools = ['patient_context', 'clinic_config']
            missing_tools = [t for t in expected_tools if t not in tool_names]
            
            if missing_tools:
                print(f"\n⚠️  Missing expected tools: {', '.join(missing_tools)}")
                return False
            else:
                print(f"\n✅ All expected healthcare tools are registered")
                return True
                
    except Exception as e:
        print(f"\n❌ Error verifying tool registration: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


@click.group()
def cli():
    """Healthcare Tools Test Suite
    
    Test healthcare-specific Lambda tools through AgentCore gateways.
    """
    pass


@cli.command()
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium", "both"], case_sensitive=False),
    default="both",
    help="Which tier gateway to test (default: both)"
)
@click.option(
    "--clinic-id",
    default="clinic-a",
    help="Clinic ID to use for testing (default: clinic-a)"
)
def test(tier, clinic_id):
    """Run comprehensive tool tests"""
    
    print("\n🏥 Healthcare Tools Test Suite")
    print("="*60)
    
    success = True
    
    if tier in ["basic", "both"]:
        if not test_gateway_tools("basic", clinic_id):
            success = False
    
    if tier in ["premium", "both"]:
        if not test_gateway_tools("premium", clinic_id):
            success = False
    
    print("\n" + "="*60)
    if success:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed")
        sys.exit(1)


@cli.command()
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium", "both"], case_sensitive=False),
    default="both",
    help="Which tier gateway to verify (default: both)"
)
def verify(tier):
    """Verify tool registration without running full tests"""
    
    print("\n🔍 Verifying Healthcare Tool Registration")
    print("="*60)
    
    success = True
    
    if tier in ["basic", "both"]:
        if not verify_tool_registration("basic"):
            success = False
    
    if tier in ["premium", "both"]:
        if not verify_tool_registration("premium"):
            success = False
    
    print("\n" + "="*60)
    if success:
        print("✅ Tool registration verified!")
    else:
        print("❌ Tool registration issues detected")
        sys.exit(1)


@cli.command()
@click.option("--tier", required=True, type=click.Choice(["basic", "premium"]))
@click.option("--prompt", "-p", required=True, help="Prompt to send to the agent")
@click.option("--clinic-id", default="clinic-a", help="Clinic ID (default: clinic-a)")
def query(tier, prompt, clinic_id):
    """Send a custom query to test the tools interactively"""
    
    print(f"\n🏥 Healthcare Agent Query - {tier.upper()} Tier")
    print(f"Clinic: {clinic_id}")
    print(f"Prompt: {prompt}")
    print("="*60 + "\n")
    
    # Fetch access token
    asyncio.run(_get_access_token_manually(access_token=""))
    
    try:
        gateway_url = get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_url")
    except Exception as e:
        print(f"❌ Error reading gateway URL: {str(e)}")
        sys.exit(1)
    
    s3_prefix = f"{tier}-tier/{clinic_id}/"
    client = MCPClient(
        lambda: streamablehttp_client(
            gateway_url,
            headers={
                "Authorization": f"Bearer {gateway_access_token}",
                "X-Tenant-ID": tier,
                "X-Clinic-ID": clinic_id,
                "X-S3-Prefix": s3_prefix
            },
        )
    )
    
    try:
        with client:
            agent = Agent(tools=client.list_tools_sync())
            response = agent(prompt)
            print(f"Response:\n{str(response)}\n")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
