# Contributing to SourceBox Sentry

Thanks for your interest in SourceBox Sentry. This document explains how you can help, and what we accept.

## We do not currently accept external code contributions

SourceBox Sentry is **source-available under AGPL-3.0**. The source is open so you can audit it, self-host it, and learn from it — but we do not accept pull requests from outside the core team at this time.

External pull requests opened against this repository will be automatically closed with a link back to this document. This is not personal — we keep the contribution surface narrow so we can move fast, retain clean copyright, and avoid the overhead of a Contributor License Agreement.

## What we *do* welcome

| Channel | What to use it for |
|---------|--------------------|
| [Issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues) | Bug reports, reproducible problems, security disclosures |
| [Discussions](https://github.com/SourceBox-LLC/OpenSentry-Command/discussions) | Feature ideas, questions, deployment help |
| Forks | Self-hosting, private modifications (see AGPL-3.0 for your obligations if you redistribute) |

A clear bug report with steps to reproduce is genuinely valuable — please open one if you hit something broken.

### Reporting bugs

Before filing, check [existing issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues). Include:

- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs (redact any secrets)
- Environment (OS, Python version, browser if UI-related)

### Reporting security issues

See [SECURITY.md](SECURITY.md). Do **not** file public issues for vulnerabilities.

## Self-hosting and development setup

SourceBox Sentry has two main components:

| Component | Language | Repository |
|-----------|----------|------------|
| **Command Center** | Python (FastAPI) + React | [OpenSentry-Command](https://github.com/SourceBox-LLC/OpenSentry-Command) |
| **CloudNode** | Rust | [OpenSentry-CloudNode](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) |

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
./target/release/sourcebox-sentry-cloudnode setup
```

See the [CloudNode README](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) for full setup instructions.

## License

SourceBox Sentry Command Center is licensed under [AGPL-3.0](LICENSE). If you self-host a modified version and offer it to users over a network, AGPL §13 requires you to make your modifications available to those users. Read the license before deploying.

---

Thank you for your interest in SourceBox Sentry.
