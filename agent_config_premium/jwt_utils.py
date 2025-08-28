import json
import base64

def extract_tenant_id_from_jwt(token: str) -> str:
    """Extract tenant_id from JWT token without external dependencies"""
    try:
        print(f"🔍 DEBUG: Raw JWT token (first 50 chars): {token[:50]}...")
        
        # JWT format: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            print(f"🔍 DEBUG: Invalid JWT format, parts count: {len(parts)}")
            return 'basic'
            
        # Decode payload (add padding if needed)
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)  # Add padding
        decoded_bytes = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded_bytes.decode('utf-8'))
        
        print(f"🔍 DEBUG: JWT claims: {claims}")
        
        tenant_id = claims.get('custom:tenant_id', 'basic')
        print(f"🔍 DEBUG: Found tenant_id in claims: {tenant_id}")
        return tenant_id
    except Exception as e:
        print(f"🔍 DEBUG: JWT parsing failed: {e}")
        # Fallback to basic if JWT parsing fails
        return 'basic'
