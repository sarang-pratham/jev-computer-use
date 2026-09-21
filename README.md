# JEV Computer Use

An experimental macOS computer-use runtime where JEV selects semantic actions
from an Accessibility (AX) observation.

The current implementation contains the AX-to-JEV operation boundary, a
PyObjC executor, a live frontmost-application AX reader, a JEV API client,
and a state-machine agent loop.

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

Run the state-machine agent with JEV:

```bash
cp .env.example .env
uv run python main.py run "Click the Search button"
```

Before acting, an OpenRouter structured-output request identifies the target
application from the free-form goal. The agent then activates the running
application or opens it through macOS before reading its Accessibility tree.

The default OpenRouter model is `openrouter/free`. Set `OPENROUTER_API_KEY` in
`.env` before running the agent; it is used to identify the target application
from the goal and to provide text when JEV selects `TYPE_TEXT`.

The process will eventually need macOS Accessibility permission under System
Settings → Privacy & Security → Accessibility when it starts observing or
controlling other applications.
