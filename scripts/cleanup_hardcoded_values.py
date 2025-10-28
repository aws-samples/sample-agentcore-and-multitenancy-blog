#!/usr/bin/env python3
"""
Clean up hardcoded values from the codebase.
This script identifies and replaces hardcoded account IDs, ARNs, and other values.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Hardcoded values to replace
HARDCODED_PATTERNS = [
    (r'962309198534', '${AWS_ACCOUNT_ID}'),
    (r'us-east-1_JlX0bKAgU', '${COGNITO_USER_POOL_ID}'),
    (r'1amjs2urmd54i5hlerind8b7sg', '${COGNITO_CLIENT_ID}'),
    (r'arn:aws:bedrock:us-east-1:962309198534:application-inference-profile/[a-zA-Z0-9]+', 
     'arn:aws:bedrock:${AWS_REGION}:${AWS_ACCOUNT_ID}:application-inference-profile/${INFERENCE_PROFILE_ID}'),
    (r'arn:aws:bedrock-agentcore:us-east-1:962309198534:runtime/[a-zA-Z0-9-]+',
     'arn:aws:bedrock-agentcore:${AWS_REGION}:${AWS_ACCOUNT_ID}:runtime/${AGENT_ID}'),
    (r'arn:aws:iam::962309198534:role/[a-zA-Z0-9-]+',
     'arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}'),
]

def find_files_with_hardcoded_values(directory: str = ".") -> List[Path]:
    """Find all files that contain hardcoded values"""
    files_with_hardcoded = []
    
    # File patterns to check
    patterns = ["*.py", "*.yaml", "*.yml", "*.json"]
    
    for pattern in patterns:
        for file_path in Path(directory).rglob(pattern):
            # Skip certain directories
            if any(skip in str(file_path) for skip in ['.venv', '__pycache__', '.git', 'lambda_package']):
                continue
                
            try:
                content = file_path.read_text()
                if '962309198534' in content or 'us-east-1_JlX0bKAgU' in content:
                    files_with_hardcoded.append(file_path)
            except (UnicodeDecodeError, PermissionError):
                continue
    
    return files_with_hardcoded

def create_template_file(file_path: Path) -> Path:
    """Create a template version of the file with placeholders"""
    template_path = file_path.with_suffix(file_path.suffix + '.template')
    
    content = file_path.read_text()
    
    # Replace hardcoded values with placeholders
    for pattern, replacement in HARDCODED_PATTERNS:
        content = re.sub(pattern, replacement, content)
    
    template_path.write_text(content)
    return template_path

def main():
    """Main function to clean up hardcoded values"""
    print("🧹 Scanning for hardcoded values...")
    
    files_with_hardcoded = find_files_with_hardcoded_values()
    
    if not files_with_hardcoded:
        print("✅ No hardcoded values found!")
        return
    
    print(f"📋 Found {len(files_with_hardcoded)} files with hardcoded values:")
    
    for file_path in files_with_hardcoded:
        print(f"   - {file_path}")
    
    print("\n🔧 Creating template files...")
    
    # Create templates directory
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    
    for file_path in files_with_hardcoded:
        # Create template in templates directory
        relative_path = file_path.relative_to(".")
        template_path = templates_dir / relative_path.with_suffix(relative_path.suffix + '.template')
        
        # Ensure parent directories exist
        template_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create template content
        content = file_path.read_text()
        for pattern, replacement in HARDCODED_PATTERNS:
            content = re.sub(pattern, replacement, content)
        
        template_path.write_text(content)
        print(f"✅ Created template: {template_path}")
    
    print(f"\n📁 Templates created in: {templates_dir}")
    print("💡 Use these templates as reference for parameterized deployment")

if __name__ == "__main__":
    main()