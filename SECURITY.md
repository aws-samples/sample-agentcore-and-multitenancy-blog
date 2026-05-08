# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it
responsibly. **Do not open a public issue.**

Instead, please send an email to [INSERT SECURITY EMAIL] with:

- A description of the vulnerability
- Steps to reproduce the issue
- Any potential impact
- Suggested fix (if you have one)

## Response Timeline

- We will acknowledge receipt within 48 hours
- We will provide an initial assessment within 7 days
- We will work with you to understand and resolve the issue promptly

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| Latest  | Yes                |

## Security Best Practices

When deploying this project:

- Never commit credentials or secrets to the repository
- Use AWS IAM roles with least-privilege permissions
- Keep dependencies up to date
- Review the `credentials/` directory — test credentials are for local development only
- Rotate API keys and tokens regularly
