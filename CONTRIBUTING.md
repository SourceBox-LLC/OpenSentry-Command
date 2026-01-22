# Contributing to OpenSentry

First off, thanks for taking the time to contribute! OpenSentry is an open-source project and we welcome contributions from everyone.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Guidelines](#coding-guidelines)
- [Submitting Changes](#submitting-changes)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

OpenSentry consists of multiple components:

| Component | Language | Repository |
|-----------|----------|------------|
| **Command Center** | Python/Flask | [OpenSentry-Command](https://github.com/SourceBox-LLC/OpenSentry-Command) |
| **Basic Node** | C++ | [OpenSentry-Node](https://github.com/SourceBox-LLC/OpenSentry-Node) |
| **Motion Node** | C++ | [OpenSentry-MotionNode](https://github.com/SourceBox-LLC/OpenSentry-MotionNode) |
| **Face Detection Node** | C++ | [OpenSentry-FaceDetectionNode](https://github.com/SourceBox-LLC/OpenSentry-FaceDetectionNode) |
| **Object Detection Node** | C++ | [OpenSentry-ObjectDetectionNode](https://github.com/SourceBox-LLC/OpenSentry-ObjectDetectionNode) |

## How to Contribute

There are many ways to contribute:

- **Report bugs** - Found something broken? [Open a bug report](https://github.com/SourceBox-LLC/OpenSentry-Command/issues/new?template=bug_report.yml)
- **Suggest features** - Have an idea? [Open a feature request](https://github.com/SourceBox-LLC/OpenSentry-Command/issues/new?template=feature_request.yml)
- **Improve documentation** - Typos, clarifications, examples
- **Submit code** - Bug fixes, new features, refactoring
- **Review pull requests** - Help review code from other contributors
- **Help others** - Answer questions in Discussions

## Development Setup

### Command Center (Python)

```bash
# Clone the repository
git clone https://github.com/SourceBox-LLC/OpenSentry-Command.git
cd OpenSentry-Command

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Run locally (without Docker)
python -m opensentry_command.app
```

### Camera Nodes (C++)

```bash
# Clone a node repository
git clone https://github.com/SourceBox-LLC/OpenSentry-Node.git
cd OpenSentry-Node

# Install dependencies (Ubuntu/Debian)
sudo apt-get install build-essential cmake \
    libopencv-dev libavahi-client-dev \
    libpaho-mqtt-dev libpaho-mqttpp-dev

# Build
mkdir build && cd build
cmake ..
make -j$(nproc)

# Run (requires camera)
./OpenSentry_Node
```

### Docker Development

```bash
# Build and run with Docker
docker compose up --build

# Rebuild after changes
docker compose down
docker compose up --build -d

# View logs
docker compose logs -f
```

## Project Structure

### Command Center

```
opensentry_command/
├── __init__.py          # Flask app factory
├── app.py               # Entry point
├── models/
│   └── database.py      # SQLAlchemy models (User, Camera, Media, AuditLog)
├── routes/
│   ├── auth.py          # Authentication routes
│   ├── api.py           # REST API endpoints (cameras, recordings, snapshots)
│   └── main.py          # Main dashboard routes
├── services/
│   ├── camera.py        # Camera streaming, recording, ffmpeg transcoding
│   └── mqtt.py          # MQTT client for node communication
├── static/
│   ├── css/             # Stylesheets
│   └── js/              # JavaScript
└── templates/           # Jinja2 HTML templates
```

### Camera Nodes

```
src/
└── main.cpp             # Single-file node implementation
                         # - Camera capture (OpenCV)
                         # - RTSP streaming (FFmpeg/MediaMTX)
                         # - mDNS announcement (Avahi)
                         # - MQTT communication
                         # - Detection logic (varies by node)
```

## Coding Guidelines

### Python (Command Center)

- Follow [PEP 8](https://pep8.org/) style guide
- Use type hints where practical
- Keep functions focused and under 50 lines when possible
- Document complex logic with comments
- Use meaningful variable and function names

```python
# Good
def get_camera_status(camera_id: str) -> dict:
    """Retrieve current status for a camera."""
    ...

# Avoid
def get(id):
    ...
```

### C++ (Camera Nodes)

- Use consistent indentation (4 spaces)
- Follow naming conventions:
  - `camelCase` for variables and functions
  - `PascalCase` for classes
  - `UPPER_SNAKE_CASE` for constants
- Keep functions focused
- Document parameters and return values

```cpp
// Good
bool publishMqttStatus(const std::string& topic, const std::string& payload) {
    // ...
}

// Avoid
bool pub(string t, string p) { ... }
```

### General Guidelines

- Write clear commit messages (see below)
- Keep PRs focused on a single change
- Add tests for new functionality (when test infrastructure exists)
- Update documentation if changing behavior
- Don't introduce new dependencies without discussion

## Submitting Changes

### 1. Fork and Clone

```bash
# Fork on GitHub, then:
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

### 3. Make Your Changes

- Write clean, well-documented code
- Test your changes locally
- Update documentation if needed

### 4. Commit Your Changes

Write clear commit messages:

```
feat: add object detection alert notifications

- Add toast notifications for object detection events
- Add notification toggle in settings
- Store preference in localStorage
```

Use conventional commit prefixes:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `refactor:` - Code change that neither fixes a bug nor adds a feature
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then open a Pull Request on GitHub.

### PR Guidelines

- Fill out the PR template completely
- Link related issues
- Include screenshots for UI changes
- Ensure CI passes (when available)
- Be responsive to review feedback

## Reporting Bugs

Before reporting:
1. Check the [existing issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues)
2. Check the [documentation](https://opensentry.fly.dev/docs.html)

When reporting:
- Use the [bug report template](https://github.com/SourceBox-LLC/OpenSentry-Command/issues/new?template=bug_report.yml)
- Include steps to reproduce
- Include relevant logs (`docker compose logs -f`)
- Include your environment (OS, Docker version, etc.)

## Requesting Features

- Use the [feature request template](https://github.com/SourceBox-LLC/OpenSentry-Command/issues/new?template=feature_request.yml)
- Describe the problem you're trying to solve
- Explain your proposed solution
- Be open to discussion and alternatives

## Questions?

- Check the [Documentation](https://opensentry.fly.dev/docs.html)
- Open a [Discussion](https://github.com/SourceBox-LLC/OpenSentry-Command/discussions)
- Look at existing [Issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues)

---

Thank you for contributing to OpenSentry!
