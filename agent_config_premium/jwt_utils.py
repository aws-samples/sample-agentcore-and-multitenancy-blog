import json
import base64
from typing import Dict, Any


def extract_tenant_id_from_jwt(token: str) -> str:
    """
    DEPRECATED: Use extract_tenant_info_from_jwt() instead.
    Kept for backward compatibility.
    """
    tenant_info = extract_tenant_info_from_jwt(token)
    return tenant_info['tier']


def extract_tenant_info_from_jwt(token: str) -> Dict[str, Any]:
    """
    Extract complete tenant information from JWT token for healthcare multi-tenancy.
    
    Returns dict with:
        - tier: Service tier (basic/premium)
        - clinic_id: Clinic identifier (e.g., 'clinic-a', 'hospital-a')
        - user_id: User identifier from cognito:username
        - actor_id: Hierarchical identifier for memory isolation (tier-clinic-user)
        - tenant_key: Combined tier-clinic key for routing
        - memory_id: Memory resource identifier
        - s3_prefix: Document scope prefix for S3 access
        - role: User role (optional)
    """
    try:
        print(f"🔍 DEBUG: Raw JWT token (first 50 chars): {token[:50]}...")
        
        # JWT format: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            print(f"🔍 DEBUG: Invalid JWT format, parts count: {len(parts)}")
            return _get_fallback_tenant_info()
            
        # Decode payload (add padding if needed)
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)  # Add padding
        decoded_bytes = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded_bytes.decode('utf-8'))
        
        print(f"🔍 DEBUG: JWT claims: {claims}")
        
        # Extract tenant information
        tier = claims.get('custom:tenant_id', 'premium')  # Premium tier default
        clinic_id = claims.get('custom:clinic_id', 'demo-hospital')
        username = claims.get('cognito:username', 'demo-user')
        role = claims.get('custom:role', 'user')
        
        # Extract user_id from username (handle email format)
        user_id = username.split('@')[0] if '@' in username else username
        
        # Construct hierarchical actor_id for memory isolation
        actor_id = f"{tier}-{clinic_id}-{user_id}"
        
        # Construct tenant_key for routing
        tenant_key = f"{tier}-{clinic_id}"
        
        # Construct S3 prefix for document access
        s3_prefix = f"{tier}-tier/{clinic_id}/"
        
        # Determine memory resource ID
        memory_id = f"healthcare-{tier}-memory"
        
        tenant_info = {
            'tier': tier,
            'clinic_id': clinic_id,
            'user_id': user_id,
            'actor_id': actor_id,
            'tenant_key': tenant_key,
            'memory_id': memory_id,
            's3_prefix': s3_prefix,
            'role': role,
            'username': username
        }
        
        print(f"🔍 DEBUG: Extracted tenant info: {tenant_info}")
        return tenant_info
        
    except Exception as e:
        print(f"🔍 DEBUG: JWT parsing failed: {e}")
        return _get_fallback_tenant_info()


def _get_fallback_tenant_info() -> Dict[str, Any]:
    """
    Fallback tenant information when JWT parsing fails.
    Returns demo hospital configuration for premium tier testing.
    """
    print("⚠️  WARNING: Using fallback tenant info (demo-hospital)")
    return {
        'tier': 'premium',
        'clinic_id': 'demo-hospital',
        'user_id': 'demo-user',
        'actor_id': 'premium-demo-hospital-demo-user',
        'tenant_key': 'premium-demo-hospital',
        'memory_id': 'healthcare-premium-memory',
        's3_prefix': 'premium-tier/demo-hospital/',
        'role': 'user',
        'username': 'demo-user'
    }
