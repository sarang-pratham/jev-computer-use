# JEV Computer Use

An experimental macOS computer-use runtime where JEV selects semantic actions
from an Accessibility (AX) observation.

The current implementation contains the AX-to-JEV operation boundary, a
PyObjC executor, and a live frontmost-application AX reader. It does not yet
include the JEV API client or the agent loop.

The operation mapping lives under `ax/operations/`, and AX transport code
lives under `ax/`.

## Development

```bash
uv run python -m unittest discover -v
```

Inspect the frontmost application's accessible controls:

```bash
uv run python main.py inspect
```

If permission is missing, open the correct settings pane automatically:

```bash
uv run python main.py inspect --open-settings
```

The process will eventually need macOS Accessibility permission under System
Settings → Privacy & Security → Accessibility when it starts observing or
controlling other applications.
