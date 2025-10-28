#!/bin/bash

# Multi-Tenant Deployment Testing Script

set -e

echo "🧪 Testing Multi-Tenant Deployment"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_test() {
    echo -e "${GREEN}[TEST]${NC} $1"
}

print_result() {
    echo -e "${YELLOW}[RESULT]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Activate virtual environment
source .venv/bin/activate

print_test "Testing basic tier tools (gaming console)..."
python test/test_gateway.py --prompt "Check warranty with serial number ABC12345678" --tenant basic

print_test "Testing premium tier tools (financial services)..."
python test/test_gateway.py --prompt "Get client profile for client ID FIN001" --tenant premium

print_test "Testing memory functionality..."
python test/test_memory.py load-conversation
python test/test_memory.py list-memory

print_test "Testing agent configurations..."
if [ -f ".bedrock_agentcore.yaml" ]; then
    echo "✅ AgentCore configuration found"
    grep -q "customersupport:" .bedrock_agentcore.yaml && echo "✅ Basic agent configured"
    grep -q "customersupport_premium:" .bedrock_agentcore.yaml && echo "✅ Premium agent configured"
else
    print_error "AgentCore configuration not found"
fi

print_test "Verifying SSM parameters..."
./scripts/list_ssm_parameters.sh

print_result "Deployment testing completed!"
echo ""
echo "🎯 Next steps:"
echo "1. Run: agentcore launch"
echo "2. Run: streamlit run app.py --server.port 8501"
echo "3. Test both basic and premium tiers in the web interface"