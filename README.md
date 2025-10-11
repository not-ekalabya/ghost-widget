
# Ghost Widget (Background Companion Overlay)

Ghost Widget is a lightweight desktop overlay that wraps a "BackgroundCompanion" background worker. It provides a modern, always-on-top translucent panel for:

- Starting/stopping background recording or capture loops
- Sending ad-hoc questions/queries to the companion and viewing responses
- Editing and saving runtime configuration (API key, capture interval, watched directories)
- A compact activity log and UI for managing the companion

The overlay is implemented with PyQt (PyQt6 preferred, falls back to PyQt5) and communicates with the companion via thread-safe queues. The UI includes a hotkey to toggle visibility.

## Features

- Modern glassmorphism-style overlay with draggable header.
- Chat-style tab for asking questions and seeing formatted responses (supports basic Markdown rendering; uses the `markdown` package if installed).
- Settings tab to edit API key (masked), capture interval, and watched directories.
- Start/Stop recording controls with status indicator and activity log.
- Global hotkey toggle (default: Ctrl+Alt+`) to show/hide the overlay.
- Graceful background runner that attempts to adapt to common `BackgroundCompanion` method names (start/stop/ask etc.).

## Requirements

- Python 3.8+ (tested with modern interpreters)
- One of: `PyQt6` or `PyQt5`
- Optional but recommended: `markdown` (for better Markdown -> HTML conversion)
- `pynput` for the global hotkey listener

Install with pip:

```powershell
python -m pip install PyQt6 pynput markdown
# or if you prefer PyQt5:
python -m pip install PyQt5 pynput markdown
```

If you only install what you need, the overlay will still run, but some features (rich Markdown rendering or the hotkey) may be degraded.

## Project layout

- `main.py` - The overlay UI and companion runner. This file instantiates the overlay, starts the hotkey listener, and manages queues between the UI and the companion thread.
- `backend.py` - (Optional) Your `BackgroundCompanion` implementation which the overlay will try to import. The overlay is resilient to slightly different method names and will attempt sensible fallbacks.
- `README.md` - This file.

> Note: The overlay reads and writes a config file at `~/.background_companion_overlay_config.json` (per-user). It will create a default config if none exists.

## Configuration

The overlay exposes a small set of runtime configuration values in the Settings tab and persists them to a JSON config in the user's home directory. The keys are:

- `api_key` (string) — optional API key used by the companion. The UI masks this value.
- `interval` (int) — capture interval in seconds.
- `watch_dirs` (list[str]) — directories the companion should watch.
- `always_recent` (int) — internal companion option for how many recent items to surface (default: 3).

You can also provide configuration by implementing `BackgroundCompanion` in `backend.py` and accepting these parameters (the overlay will pass them at instantiation):

```
BackgroundCompanion(api_key=<str>, capture_interval=<int>, watch_dirs=<list[str]>, always_recent=<int>)
```

The overlay will also set environment variables `GOOGLE_API_KEY` and `GEMINI_API_KEY` if an API key is provided by the UI or (in development) the runner may set a placeholder key.

## Running

Run the overlay with:

```powershell
python main.py
```

The overlay will:

1. Load or create a default config file.
2. Instantiate the `CompanionRunner` thread which attempts to import and instantiate `BackgroundCompanion` from `backend.py`.
3. Start a global hotkey listener in a daemon thread to toggle visibility (default hotkey is `Ctrl+Alt+``). The overlay polls a queue to receive the toggle.

If `backend.py` is not present or `BackgroundCompanion` cannot be instantiated, the overlay still runs and the UI can be used to manage configuration or view logs.

## How the overlay talks to your companion

- Communication is done with thread-safe `Queue` objects between the UI thread and the companion runner thread.
- The runner tries common method names for control: `start` / `run` / `begin` for starting; `stop` / `shutdown` / `close` for stopping; `ask` / `query` / `send_prompt` / `chat` for query/ask semantics.
- If your companion offers different method names, adapt it or add simple wrappers that match those common names.

## Development notes

- The UI uses a custom `MarkdownTextEdit` which preserves the original markdown when copying and provides a simple Markdown -> HTML converter when the `markdown` package is missing.
- To enable richer code highlighting and fenced code blocks output, install the `markdown` package and optionally `Pygments` for code highlighting.
- The runner is intentionally defensive: it will try to set attributes on an instantiated companion (like `capture_interval`, `watch_dirs`) and call commonly-named methods but will log helpful messages if methods are missing.

## Security & Privacy

- API keys entered in the Settings tab are stored locally in the per-user JSON config in your home directory. The UI masks the field, but the key is stored in plaintext in that file by default.
- Do not commit your API keys or config file to version control. Treat `~/.background_companion_overlay_config.json` as sensitive.
- The overlay intentionally sets environment variables (`GOOGLE_API_KEY`, `GEMINI_API_KEY`) when an API key is present; ensure you trust any code that runs in the same environment.

## Troubleshooting

- If the overlay fails to start due to missing Qt bindings, install `PyQt6` or `PyQt5` with pip.
- If the global hotkey doesn't work, ensure `pynput` is installed and that your OS allows global hotkeys from Python apps. On some platforms, accessibility/permissions are required.
- If your `BackgroundCompanion` raises exceptions on instantiation, check the activity log in the Settings tab for traceback details.
- For Markdown rendering issues, install the `markdown` package.

## Extending / Integration

- Implement `BackgroundCompanion` in `backend.py` with the expected constructor signature (see Configuration above) and common method names for start/stop/ask. The overlay's runner will attempt to work with many reasonable shapes.
- If your companion exposes a client object for direct calls, the runner will attempt to call `client.send()` where appropriate.

## License

This repository does not include an explicit license file. Add a `LICENSE` if you want to open-source the project under a specific license.

## Contributing

If you'd like to contribute, please:

1. Fork the repo
2. Add tests and ensure the overlay still launches on both PyQt6 and PyQt5
3. Open a PR with a clear description of the change

---

If you want, I can also:

- Add a small `requirements.txt` or `pyproject.toml` for reproducible installs
- Create a minimal `backend.py` example that implements `BackgroundCompanion` so the overlay demonstrates full functionality out of the box

Tell me which you'd like next and I’ll add it.

