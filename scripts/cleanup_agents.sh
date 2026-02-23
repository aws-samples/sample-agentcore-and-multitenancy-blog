#!/bin/bash

# Cleanup script to remove AgentCore configuration and start fresh
# This is needed when switching deployment types (container -> direct_code_deploy)

set -e

echo "🧹 Cleaning up AgentCore configuration..."

# Remove the bedrock agentcore yaml file
if [ -f ".bedrock_agentcore.yaml" ]; then
    echo "✅ Removing .bedrock_agentcore.yaml"
    rm -f .bedrock_agentcore.yaml
else
    echo "ℹ️  No .bedrock_agentcore.yaml found"
fi

# Remove the old agentcore.yaml if it exists
if [ -f ".agentcore.yaml" ]; then
    echo "✅ Removing .agentcore.yaml"
    rm -f .agentcore.yaml
else
    echo "ℹ️  No .agentcore.yaml found"
fi

# Remove agentcore config directory if it exists
if [ -d "$HOME/.agentcore" ]; then
    echo "⚠️  Found AgentCore config directory at $HOME/.agentcore"
    echo "   This contains your agent configurations."
    read -p "   Do you want to remove it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$HOME/.agentcore"
        echo "✅ Removed $HOME/.agentcore"
    else
        echo "ℹ️  Keeping $HOME/.agentcore"
    fi
fi

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Next steps:"
echo "1. Run: ./deploy.sh"
echo "2. This will generate fresh configuration with direct_code_deploy"
