# JEV Computer Use

An experimental macOS computer-use runtime where JEV selects semantic actions
from an Accessibility (AX) observation.

The current implementation contains the AX-to-JEV operation boundary and a
PyObjC executor. It does not yet include the JEV API client, AX tree reader,
frontmost-app discovery, or the agent loop.

The operation mapping lives under `ax/operations/`, and AX transport code
lives under `ax/`.

## Development

```bash
uv run python -m unittest discover -v
```

The process will eventually need macOS Accessibility permission under System
Settings → Privacy & Security → Accessibility when it starts observing or
controlling other applications.
