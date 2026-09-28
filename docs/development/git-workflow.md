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

### 2. Team Branches

Each developer works on their own feature branch.

#### Member 1 — Backend + Integration

Branch: `feature/member1-backend-core-intelligence`

Responsibilities:

- NestJS Backend
- Core API
- Validation
- Health/Readiness
- Logging
- Correlation IDs
- Docker/Compose
- Integration
- Regression
- Release preparation

#### Member 2 — VS Code + Frontend

Branch: `feature/member2-vscode-frontend`

Responsibilities:

- VS Code Extension
- React Webview
- Developer UI
- Client API integration
- Extension testing
- Frontend build

#### Member 3 — AI Engine

Branch: `feature/member3-ai`

Responsibilities:

- FastAPI AI Engine
- AI orchestration
- Agents
- Ollama provider
- LLM integration
- AI tests
- AI evaluation
- AI-specific Docker work

#### Member 4

Member 4 is currently unavailable.

Do not create a separate active development dependency on Member 4. Their original integration/DevOps/testing/documentation work has been redistributed between Member 1 and Member 3.

### 3. Main Branch

The `main` branch is the stable team branch.

Developers should NOT directly develop on:

`main`

Only tested and reviewed changes should enter `main`.

Recommended flow:

```text
Member branch
      ↓
Commit
      ↓
Push
      ↓
Pull Request
      ↓
Code Review
      ↓
Tests
      ↓
Merge
      ↓
main
```

### 4. First-Time Setup

Every team member should clone the repository:

```bash
git clone https://github.com/sigmaboy143/AI-Code-Understanding-Assistant.git
```

Enter the project:

```bash
cd AI-Code-Understanding-Assistant
```

Check the branches:

```bash
git branch -a
```

Fetch the latest remote information:

```bash
git fetch origin
```

### 5. Before Starting Any Work

Always update your branch before beginning work.

```bash
git fetch origin
git status
```

Make sure there are no unexpected local modifications.

Then move to your own feature branch.

Example for Member 1:

```bash
git switch feature/member1-backend-core-intelligence
```

Example for Member 2:

```bash
git switch feature/member2-vscode-frontend
```

Example for Member 3:

```bash
git switch feature/member3-ai
```

Then:

```bash
git pull --ff-only origin <your-branch>
```

### 6. Daily Development Workflow

Every developer should follow:

1. Pull latest branch
2. Work only inside assigned area
3. Run tests
4. Review git diff
5. Commit
6. Push
7. Inform the team

Example:

```bash
git status
```

After making changes:

```bash
git diff
```

Check which files changed:

```bash
git status --short
```

Run project tests.

Then commit:

```bash
git add <only-your-files>
git commit -m "feat: add code analysis capability"
```

Push:

```bash
git push origin <your-branch>
```

### 7. Commit Rules

Use small, meaningful commits.

Recommended format:

```text
feat: add code explanation analysis
fix: correct ollama timeout handling
test: add adapter regression coverage
docs: update deployment guide
chore: update docker configuration
refactor: simplify analysis service
```

Avoid commits such as:

```text
update
changes
final
final2
working
new
test
```

A commit should explain what changed.

### 8. Important Rule — Never Commit Secrets

Never commit:

- `.env`
- `.env.local`
- `.env.production`
- API keys
- passwords
- tokens
- private keys
- `.pem`
- `.p12`
- credentials
- GitHub tokens
- Ollama credentials

Use:

`.env.example`

Example:

```bash
MODEL=llama3
PROVIDER=ollama
PROVIDER_BASE_URL=http://localhost:11434
```

The actual `.env` remains local.

### 9. Before Every Push

Run:

```bash
git status --short
```

Then:

```bash
git diff --check
```

Then run the tests relevant to your change.

For backend:

```bash
cd apps/api
npm test
npm run test:e2e
npm run build
npm run lint
```

For AI Engine:

```bash
cd apps/ai-engine
python -m pytest tests -q
```

Then return to repository root:

```bash
cd ../..
```

Only push after the checks pass.

### 10. Pull Request Workflow

When your feature is ready:

```text
feature branch
      ↓
push
      ↓
GitHub Pull Request
      ↓
team review
      ↓
CI checks
      ↓
approval
      ↓
merge
```

PR title example:

```text
feat: add AI code understanding workflow
```

PR description should contain:

- What changed
- Why it changed
- How it was tested
- Known limitations

Do not merge a PR just because the code compiles.

### 11. Working With Another Member's Branch

Do NOT copy random files manually between branches.

Example:

Member 1 needs to inspect Member 3's work:

```bash
git fetch origin
```

Then inspect:

```bash
git log --oneline origin/feature/member3-ai
```

If a specific directory must be imported temporarily, use a controlled Git restore/worktree approach.

Do NOT blindly run:

```bash
git merge feature/member3-ai
```

unless the team has explicitly decided that a full branch merge is required.

This is especially important because the project contains separate Backend and AI Engine ownership.

### 12. Integration Branch Strategy

When integrating the whole system:

```text
Member 1 branch
      +
Member 2 branch
      +
Member 3 branch
      ↓
Integration / reviewed PRs
      ↓
main
```

The final repository should contain:

```text
apps/api
apps/ai-engine
apps/vscode
docs
compose.yaml
README.md
```

The final integration should be tested together, not only branch-by-branch.

### 13. Docker Storage

Docker files belong in the repository.

Example:

```text
apps/api/Dockerfile
apps/api/.dockerignore

apps/ai-engine/Dockerfile
apps/ai-engine/.dockerignore

compose.yaml
```

Ollama itself does NOT need to be stored as project source code.

For the current local architecture:

```text
VS Code
    ↓
NestJS API
    ↓
AI Engine
    ↓
Ollama on developer machine
    ↓
LLM
```

Docker Compose stores the configuration for the Backend + AI Engine.

### 14. Documentation Storage

All project documentation should remain in GitHub:

```text
docs/
README.md
```

Recommended documentation:

```text
docs/architecture/
    system-architecture.md
    integration-contracts.md

docs/development/
    environment.md
    troubleshooting.md

docs/deployment/
    deployment-guide.md

docs/testing/
    testing-guide.md
```

This prevents important setup knowledge from being lost inside individual developers' computers.

### 15. Releases / Stable Versions

When a major milestone is completed, create a Git tag.

Example:

```bash
git tag -a v0.1.0 -m "First integrated prototype"
git push origin v0.1.0
```

Later:

```text
v0.1.0  Prototype
v0.2.0  AI integration
v0.3.0  Full E2E
v1.0.0  Hackathon release
```

Tags give the team permanent references to working versions.

### 16. Backup Strategy

GitHub should be the team's central source of truth.

Every developer should regularly push completed work:

```text
Local code
   ↓
Git commit
   ↓
GitHub feature branch
   ↓
Pull Request
   ↓
main
```

Do not keep the only copy of important work on one laptop.

### 17. Current Project Rule

For this project, before saying:

"My work is completed"

the developer should provide:

```text
Branch:
Commit SHA:
Tests:
Build:
Push:
Known limitations:
```

Example:

```text
Branch: feature/member1-backend-core-intelligence
Commit: f197155
Tests: PASS
Build: PASS
Push: SUCCESS
Known limitation: qwen3 integration still being finalized
```

This makes team status easy to track.

### 18. Very Important — AGENTS.md

For the current project workflow:

`AGENTS.md`

must remain untracked and untouched.

Do NOT run:

```bash
git add AGENTS.md
```

Do NOT commit it.

Before every commit, confirm:

```bash
git status --short
```

It should remain outside the staged changes.

### 19. Final Team Workflow

The simplest team rule is:

```text
                    GitHub Repository
                           │
             ┌─────────────┼─────────────┐
             │             │             │
          Member 1      Member 2      Member 3
          Backend       VS Code        AI Engine
             │             │             │
             └─────────────┼─────────────┘
                           ↓
                    Pull Requests
                           ↓
                       Review + CI
                           ↓
                         main
                           ↓
                  Release / Submission
```

Nobody should depend on files existing only on their personal computer.

The GitHub repository + reviewed commits + documented setup + tagged releases should be the team's source of truth.
