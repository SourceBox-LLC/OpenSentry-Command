# Contributing to OpenSentry

Thanks for your interest in contributing! OpenSentry is open source and we welcome contributions from everyone.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

OpenSentry has two main components:

| Component | Language | Repository |
|-----------|----------|------------|
| **Command Center** | Python (FastAPI) + React | [OpenSentry-Command](https://github.com/SourceBox-LLC/OpenSentry-Command) |
| **CloudNode** | Rust | [OpenSentry-CloudNode](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) |

## How to Contribute

- **Report bugs** -- [Open an issue](https://github.com/SourceBox-LLC/OpenSentry-Command/issues/new)
- **Suggest features** -- [Start a discussion](https://github.com/SourceBox-LLC/OpenSentry-Command/discussions)
- **Improve documentation** -- Typos, clarifications, examples
- **Submit code** -- Bug fixes, new features, refactoring
- **Review pull requests** -- Help review code from other contributors

## Development Setup

### Command Center

```bash
# Backend
cd backend
cp .env.example .env
uv sync
uv run python start.py       # http://localhost:8000

# Frontend
cd frontend
cp .env.example .env
npm install
npm run dev                   # http://localhost:5173
```

### CloudNode

```bash
cd OpenSentry-CloudNode
cargo build --release
./target/release/opensentry-cloudnode setup
```

See the [CloudNode README](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) for full setup instructions.

## Project Structure

### Command Center

```
backend/
├── app/
│   ├── main.py           # FastAPI app, CORS, SPA middleware
│   ├── api/              # Route handlers (cameras, nodes, hls, streams, audit, webhooks)
│   ├── core/             # Auth (Clerk JWT), config, database
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   └── services/         # Tigris storage, codec probing
├── pyproject.toml
└── start.py

frontend/
└── src/
    ├── pages/            # Page components
    └── components/       # Reusable UI components
```

### CloudNode

```
src/
├── main.rs               # CLI entry point
├── dashboard.rs           # Live TUI dashboard
├── api/                   # Cloud API client + WebSocket
├── camera/                # Platform-specific camera detection
├── config/                # Config loading (SQLite → YAML → env → CLI)
├── node/                  # Node lifecycle orchestration
├── server/                # HTTP server (warp)
├── setup/                 # Interactive setup wizard
├── streaming/             # HLS generation and upload
└── storage/               # SQLite database
```

## Coding Guidelines

### Python (Command Center Backend)

- Follow [PEP 8](https://pep8.org/)
- Use type hints where practical
- Keep functions focused and under 50 lines when possible
- Use meaningful names

```python
# Good
def get_camera_status(camera_id: str) -> dict:
    """Retrieve current status for a camera."""
    ...

# Avoid
def get(id):
    ...
```

### JavaScript / React (Frontend)

- Functional components with hooks
- Use Clerk hooks (`useAuth`, `useOrganization`) for auth state
- CSS classes for styling (dark theme, no Tailwind)

### Rust (CloudNode)

- No `unwrap()` outside of tests -- use `?` or `anyhow::Context`
- All errors use the custom `Error` enum
- Platform-specific code in `camera/platform/`

## Submitting Changes

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/OpenSentry-Command.git
cd OpenSentry-Command
git remote add upstream https://github.com/SourceBox-LLC/OpenSentry-Command.git
```

### 2. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

### 3. Commit Your Changes

Use conventional commit messages:

```
feat: add camera group filtering to dashboard

- Add group selector dropdown
- Filter camera grid by selected group
- Persist selection in localStorage
```

Prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

### 4. Open a Pull Request

```bash
git push origin feature/your-feature-name
```

Then open a PR on GitHub. Include:
- A clear description of what changed and why
- Screenshots for UI changes
- Links to related issues

## Reporting Bugs

Before reporting, check [existing issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues).

Include:
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs
- Environment (OS, Python version, browser)

---

Thank you for contributing to OpenSentry!
