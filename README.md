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
uv run jx "Click the Search button"
```

The longer `uv run python main.py run "..."` form remains available.

Before acting, an OpenRouter structured-output request identifies an explicit
application or a supported capability such as `web_browser` or `camera`. The
agent resolves capabilities to configured defaults, then activates the
application before reading its Accessibility tree.

The default OpenRouter model is `openrouter/free`. Set `OPENROUTER_API_KEY` in
`.env` before running the agent; it is used to identify the target application
from the goal and to provide text when JEV selects `TYPE_TEXT`.

The default capability applications are configurable with `DEFAULT_BROWSER`,
`DEFAULT_CAMERA`, and `DEFAULT_CALENDAR`.

The process will eventually need macOS Accessibility permission under System
Settings → Privacy & Security → Accessibility when it starts observing or
controlling other applications.
