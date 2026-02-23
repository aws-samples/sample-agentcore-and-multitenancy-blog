#!/usr/bin/python
import click
import boto3
import sys
from botocore.exceptions import ClientError
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType
from utils import get_aws_region

# AWS clients
REGION = get_aws_region()
ssm = boto3.client("ssm", region_name=REGION)
memory_client = MemoryClient()


def store_memory_id_in_ssm(param_name: str, memory_id: str):
    ssm.put_parameter(Name=param_name, Value=memory_id, Type="String", Overwrite=True)
    click.echo(f"🔐 Stored memory_id in SSM: {param_name}")


def get_memory_id_from_ssm(param_name: str):
    try:
        response = ssm.get_parameter(Name=param_name)
        return response["Parameter"]["Value"]
    except ClientError as e:
        raise click.ClickException(f"❌ Could not retrieve memory_id from SSM: {e}")


def delete_ssm_param(param_name: str):
    try:
        ssm.delete_parameter(Name=param_name)
        click.echo(f"🧹 Deleted SSM parameter: {param_name}")
    except ClientError as e:
        click.echo(f"⚠️ Failed to delete SSM parameter: {e}")


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Memory Management CLI for Healthcare Multi-Tenancy.

    Create and manage AgentCore memory resources for the healthcare clinical
    document processing platform with tier-based isolation.
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option(
    "--name", default="healthcare_basic_memory", help="Name of the memory resource (e.g., healthcare_basic_memory)"
)
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium"], case_sensitive=False),
    default="basic",
    help="Tier level for the memory resource (basic or premium)",
)
@click.option(
    "--ssm-param",
    help="SSM parameter to store memory_id (auto-generated if not provided)",
)
@click.option(
    "--event-expiry-days",
    type=int,
    help="Number of days before events expire (default: 90 for basic, 180 for premium)",
)
def create(name, tier, ssm_param, event_expiry_days):
    """Create a new AgentCore memory resource for healthcare multi-tenancy.
    
    Creates tier-specific memory with namespace templates for clinic and user isolation.
    
    Examples:
        # Create basic tier memory
        python agentcore_memory.py create --name healthcare-basic-memory --tier basic
        
        # Create premium tier memory with custom expiry
        python agentcore_memory.py create --name healthcare-premium-memory --tier premium --event-expiry-days 365
    """
    click.echo(f"🚀 Creating Healthcare AgentCore memory: {name}")
    click.echo(f"📍 Region: {REGION}")
    click.echo(f"🏥 Tier: {tier}")
    
    # Auto-generate SSM parameter if not provided
    if not ssm_param:
        ssm_param = f"/app/healthcare/memory/{tier}_id"
    
    # Set default expiry based on tier
    if not event_expiry_days:
        event_expiry_days = 180 if tier == "premium" else 90
    
    click.echo(f"⏱️  Event expiry: {event_expiry_days} days")

    # Tier-specific namespace templates for clinic and user isolation
    # Note: Each strategy can only have ONE namespace
    if tier == "basic":
        strategies = [
            {
                StrategyType.SEMANTIC.value: {
                    "name": "clinical_facts",
                    "description": "Clinical facts and patient information",
                    "namespaces": ["clinic/{actorId}/facts/{sessionId}"],
                },
            },
            {
                StrategyType.SUMMARY.value: {
                    "name": "conversation_summary",
                    "description": "Conversation summaries for clinical interactions",
                    "namespaces": ["clinic/{actorId}/summaries/{sessionId}"],
                },
            },
        ]
        description = "Memory for healthcare basic tier clinical document processing"
    else:  # premium
        strategies = [
            {
                StrategyType.SEMANTIC.value: {
                    "name": "clinical_insights",
                    "description": "Advanced clinical insights and analytics",
                    "namespaces": ["clinic/{actorId}/insights/{sessionId}"],
                },
            },
            {
                StrategyType.SUMMARY.value: {
                    "name": "advanced_summary",
                    "description": "Advanced conversation summaries with clinical context",
                    "namespaces": ["clinic/{actorId}/summaries/{sessionId}"],
                },
            },
            {
                StrategyType.USER_PREFERENCE.value: {
                    "name": "user_preferences",
                    "description": "User preferences and clinical workflow settings",
                    "namespaces": ["clinic/{actorId}/preferences"],
                },
            },
        ]
        description = "Memory for healthcare premium tier advanced clinical analytics"

    try:
        click.echo("🔄 Creating memory resource...")
        memory = memory_client.create_memory_and_wait(
            name=name,
            strategies=strategies,
            description=description,
            event_expiry_days=event_expiry_days,
        )
        memory_id = memory["id"]
        click.echo(f"✅ Memory created successfully: {memory_id}")

    except Exception as e:
        if "already exists" in str(e):
            click.echo("📋 Memory already exists, finding existing resource...")
            memories = memory_client.list_memories()
            memory_id = next(
                (m["id"] for m in memories if name in m.get("name", "")), None
            )
            if memory_id:
                click.echo(f"✅ Using existing memory: {memory_id}")
            else:
                click.echo("❌ Could not find existing memory resource", err=True)
                sys.exit(1)
        else:
            click.echo(f"❌ Error creating memory: {str(e)}", err=True)
            sys.exit(1)

    try:
        store_memory_id_in_ssm(ssm_param, memory_id)
        click.echo("🎉 Memory setup completed successfully!")
        click.echo(f"   Memory ID: {memory_id}")
        click.echo(f"   SSM Parameter: {ssm_param}")
        click.echo(f"   Tier: {tier}")
        click.echo(f"\n💡 Namespace template uses {{actorId}} for user-level isolation:")
        click.echo(f"   Format: {tier}-{{clinic_id}}-{{user_id}}")

    except Exception as e:
        click.echo(f"⚠️  Memory created but failed to store in SSM: {str(e)}", err=True)


@cli.command()
def create_all():
    """Create both basic and premium tier memory resources.
    
    This is a convenience command that creates:
    - healthcare-basic-memory (90 day expiry)
    - healthcare-premium-memory (180 day expiry)
    
    Example:
        python agentcore_memory.py create-all
    """
    click.echo("🚀 Creating both Healthcare AgentCore memory resources")
    click.echo(f"📍 Region: {REGION}")
    
    # Create basic tier memory
    click.echo("\n" + "="*60)
    click.echo("Creating Basic Tier Memory")
    click.echo("="*60)
    ctx = click.get_current_context()
    ctx.invoke(create, name="healthcare_basic_memory", tier="basic")
    
    # Create premium tier memory
    click.echo("\n" + "="*60)
    click.echo("Creating Premium Tier Memory")
    click.echo("="*60)
    ctx.invoke(create, name="healthcare_premium_memory", tier="premium")
    
    click.echo("\n" + "="*60)
    click.echo("🎉 Both memory resources created successfully!")
    click.echo("="*60)


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete_all(confirm):
    """Delete both basic and premium tier memory resources.
    
    Example:
        python agentcore_memory.py delete-all --confirm
    """
    click.echo("🗑️  Deleting both Healthcare AgentCore memory resources")
    
    # Confirmation prompt
    if not confirm:
        if not click.confirm(
            "⚠️  Are you sure you want to delete BOTH memory resources? This action cannot be undone."
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)
    
    success_count = 0
    ctx = click.get_current_context()
    
    # Delete basic tier memory
    try:
        click.echo("\n🗑️  Deleting basic tier memory...")
        ctx.invoke(delete, tier="basic", confirm=True)
        success_count += 1
    except Exception as e:
        click.echo(f"⚠️  Failed to delete basic tier memory: {e}")
    
    # Delete premium tier memory
    try:
        click.echo("\n🗑️  Deleting premium tier memory...")
        ctx.invoke(delete, tier="premium", confirm=True)
        success_count += 1
    except Exception as e:
        click.echo(f"⚠️  Failed to delete premium tier memory: {e}")
    
    if success_count > 0:
        click.echo(f"\n🎉 Deleted {success_count} memory resource(s) successfully")
    else:
        click.echo("\n❌ No memory resources were deleted", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--memory-id",
    help="Memory ID to delete (if not provided, will read from SSM parameter)",
)
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium"], case_sensitive=False),
    help="Tier level (required if memory-id not provided)",
)
@click.option(
    "--ssm-param",
    help="SSM parameter to retrieve memory_id from (auto-generated if tier provided)",
)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(memory_id, tier, ssm_param, confirm):
    """Delete an AgentCore memory resource.
    
    Examples:
        # Delete basic tier memory
        python agentcore_memory.py delete --tier basic --confirm
        
        # Delete specific memory by ID
        python agentcore_memory.py delete --memory-id mem-abc123 --confirm
    """

    # If no memory ID provided, try to read from SSM
    if not memory_id:
        if not tier and not ssm_param:
            click.echo(
                "❌ Either --memory-id, --tier, or --ssm-param must be provided",
                err=True,
            )
            sys.exit(1)
        
        # Auto-generate SSM parameter if tier provided
        if tier and not ssm_param:
            ssm_param = f"/app/healthcare/memory/{tier}_id"
        
        try:
            memory_id = get_memory_id_from_ssm(ssm_param)
            click.echo(f"📖 Using memory ID from SSM ({ssm_param}): {memory_id}")
        except Exception:
            click.echo(
                f"❌ No memory ID found in SSM parameter: {ssm_param}",
                err=True,
            )
            sys.exit(1)

    # Confirmation prompt
    if not confirm:
        if not click.confirm(
            f"⚠️  Are you sure you want to delete memory {memory_id}? This action cannot be undone."
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)

    click.echo(f"🗑️  Deleting memory: {memory_id}")

    try:
        memory_client.delete_memory(memory_id=memory_id)
        click.echo(f"✅ Memory deleted successfully: {memory_id}")
    except Exception as e:
        click.echo(f"❌ Error deleting memory: {str(e)}", err=True)
        sys.exit(1)

    # Delete SSM parameter if provided
    if ssm_param:
        delete_ssm_param(ssm_param)
    elif tier:
        delete_ssm_param(f"/app/healthcare/memory/{tier}_id")
    
    click.echo("🎉 Memory and SSM parameter deleted successfully")


if __name__ == "__main__":
    cli()
