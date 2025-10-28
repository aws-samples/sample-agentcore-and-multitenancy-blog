# Multi-Tenant Customer Support with Amazon Bedrock AgentCore

A sophisticated multi-tenant AI customer support system built on Amazon Bedrock AgentCore, demonstrating complete tenant isolation across two distinct business domains: gaming console support and financial services.

## 🏗️ Architecture Overview

This project showcases advanced multi-tenancy patterns in AI agent systems, featuring:

- **Complete Tenant Isolation**: Separate agents, knowledge bases, and tools per tenant
- **Domain-Specific Intelligence**: Gaming console support vs. financial advisory services  
- **Dynamic Resource Management**: Account-agnostic deployment with automatic configuration
- **Scalable Infrastructure**: Serverless architecture with AgentCore runtime

## 🎯 Business Domains

### Basic Tier - Gaming Console Support
- **Customer Profile Management**: Retrieve customer information and preferences
- **Warranty Services**: Check warranty status and coverage details
- **Technical Support**: Product troubleshooting and issue resolution
- **Policy Guidance**: Access to warranty and support policies

### Premium Tier - Financial Services
- **Client Portfolio Management**: Comprehensive portfolio analysis and reporting
- **Investment Advisory**: Risk assessment and investment recommendations
- **Wealth Management**: Assets under management and performance tracking
- **Financial Planning**: Strategic financial guidance and coordination

## 🚀 Quick Start

### Prerequisites

- **AWS Account** with Bedrock access enabled
- **AWS CLI** configured with appropriate permissions
- **Python 3.8+** and pip
- **Docker** or Finch for containerization
- **Git** for repository management

### One-Command Deployment

```bash
git clone <repository-url>
cd agentcore-multitenancy
chmod +x deploy.sh
./deploy.sh
```

That's it! The deployment script will:
1. Detect your AWS account and region
2. Create all necessary AWS resources
3. Configure tenant-specific agents
4. Set up authentication and routing
5. Deploy the complete multi-tenant system

### Launch the Demo

```bash
# Start AgentCore runtime
agentcore launch

# In another terminal, start the web interface
streamlit run app.py --server.port 8501
```

Access the demo at `http://localhost:8501`

## 🏛️ Technical Architecture

### Multi-Tenancy Strategy

```
┌─────────────────┐    ┌─────────────────┐
│   Basic Tier    │    │  Premium Tier   │
│  (Gaming)       │    │  (Financial)    │
├─────────────────┤    ├─────────────────┤
│ • main.py       │    │ • main_premium.py│
│ • Gaming KB     │    │ • Financial KB  │
│ • Basic Tools   │    │ • Premium Tools │
│ • Basic Profile │    │ • Premium Profile│
└─────────────────┘    └─────────────────┘
         │                       │
         └───────┬───────────────┘
                 │
    ┌─────────────────────────┐
    │   Shared Infrastructure │
    │ • Cognito Auth         │
    │ • MCP Gateway          │
    │ • AgentCore Runtime    │
    │ • SSM Configuration    │
    └─────────────────────────┘
```

### Key Components

- **Amazon Bedrock AgentCore**: Serverless AI agent runtime
- **Strands Framework**: Agent orchestration and tool integration
- **Model Context Protocol (MCP)**: Tool integration and routing
- **Amazon Cognito**: JWT-based authentication
- **AWS Lambda**: Backend service functions
- **SSM Parameter Store**: Configuration management

## 🔧 Configuration Management

The system uses dynamic configuration to eliminate hardcoded values:

### Automatic Configuration
- **AWS Account Detection**: Automatically detects your account ID and region
- **Resource ARN Generation**: Creates account-specific ARNs for all resources
- **Inference Profile Creation**: Sets up tenant-specific model access
- **Parameter Store Integration**: Stores all configuration in SSM

### Configuration Files
```
config/
├── parameters.template.yaml    # Configuration template
├── deployment_config.json      # Runtime configuration
└── .bedrock_agentcore.yaml    # AgentCore deployment config
```

## 🛠️ Development

### Project Structure

```
agentcore-multitenancy/
├── main.py                     # Basic tier entrypoint
├── main_premium.py            # Premium tier entrypoint
├── agent_config/              # Basic tier configuration
│   ├── agent.py              # Agent implementation
│   ├── context.py            # Context management
│   └── utils.py              # Utilities
├── agent_config_premium/      # Premium tier configuration
│   ├── agent.py              # Premium agent implementation
│   ├── context.py            # Premium context management
│   └── utils.py              # Premium utilities
├── scripts/                   # Deployment and management scripts
│   ├── configure_deployment.py   # Dynamic configuration
│   ├── create_inference_profiles.py  # Model setup
│   ├── agentcore_gateway.py      # Gateway management
│   ├── agentcore_memory.py       # Memory management
│   └── prereq.sh                 # Infrastructure setup
├── prerequisite/              # Infrastructure components
│   ├── lambda/               # Backend Lambda functions
│   └── policies/             # Knowledge base content
├── test/                     # Test suite
└── .kiro/                    # Kiro IDE configuration
    └── steering/             # Development guidelines
```

### Adding New Tenants

1. **Create Agent Configuration**:
   ```bash
   cp -r agent_config agent_config_new_tenant
   ```

2. **Create Entrypoint**:
   ```bash
   cp main.py main_new_tenant.py
   ```

3. **Update Configuration**:
   - Modify `scripts/configure_deployment.py`
   - Add tenant-specific tools and knowledge base
   - Update `.bedrock_agentcore.yaml`

4. **Deploy**:
   ```bash
   ./deploy.sh
   ```

### Cleanup

```bash
# Remove all resources
chmod +x scripts/cleanup.sh
./scripts/cleanup.sh
```

## 📚 Documentation

- **[Deployment Guide](DEPLOYMENT.md)**: Detailed deployment instructions
- **[Architecture Guide](.kiro/steering/agentcore-multitenancy-architecture.md)**: Development guidelines and best practices
- **[API Documentation](prerequisite/lambda/api_spec.json)**: Tool and API specifications

## 🤝 Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/new-tenant`
3. **Follow the steering guidelines**: Check `.kiro/steering/` for development standards
4. **Test thoroughly**: Run the full test suite
5. **Submit a pull request**: Include detailed description and test results


---