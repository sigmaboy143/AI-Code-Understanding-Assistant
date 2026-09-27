# AI Code Understanding Assistant

## GitHub Team Workflow & Project Storage Guide

### 1. Repository Structure

Keep the complete project inside one private GitHub repository:

`AI-Code-Understanding-Assistant`

Recommended repository structure:

```text
AI-Code-Understanding-Assistant/
│
├── apps/
│   ├── api/
│   │   ├── src/
│   │   ├── test/
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   └── ...
│   │
│   ├── ai-engine/
│   │   ├── app/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── ...
│   │
│   └── vscode/
│       ├── extension/
│       ├── webview-ui/
│       └── ...
│
├── docs/
│   ├── architecture/
│   ├── development/
│   ├── deployment/
│   └── testing/
│
├── compose.yaml
├── .env.example
├── .gitignore
├── README.md
└── ...
```
