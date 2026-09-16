# LTspice MCP for macOS

Model Context Protocol (MCP) server that lets agents and MCP clients control LTspice on macOS for simulation, schematic generation, data extraction, verification, and rendering.

This project is designed for practical automation: reliable runs, reproducible artifacts, and outputs that match LTspice behavior closely.

Inspired by:
- [gtnoble/ngspice-mcp](https://github.com/gtnoble/ngspice-mcp)
- [luc-me/ltspiceMCP](https://github.com/luc-me/ltspiceMCP)

## What You Can Do

- Run LTspice simulations from MCP (`simulateNetlistFile`, `runSimulation`, queue tools).
- Generate and refine schematics (`createSchematic*`, lint/clean/debug tools).
- Render real LTspice images for schematics, plots, and symbols.
- Query RAW vectors and analysis metrics (bandwidth, margins, rise/fall, settling).
- Automate `.meas` and assertion-driven verification workflows.
- Run stepped and Monte Carlo studies with structured results.

## Quick Start (5 Minutes)

### 1) Prerequisites

- macOS with LTspice installed (`/Applications/LTspice.app` expected by default).
- Python 3.11+.
- `uv` (recommended) or `pip`.

### 2) Install

```bash
uv sync
```

If you prefer pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3) Start the MCP daemon

```bash
./scripts/ltspice_mcp_daemon.sh start
./scripts/ltspice_mcp_daemon.sh status
```

Default endpoint:
- `http://127.0.0.1:8765/mcp`

### 4) Grant macOS permissions once

Required for screenshot/render and some UI automation features.

```bash
./scripts/ltspice_mcp_daemon.sh trigger-initial-permissions
./scripts/ltspice_mcp_daemon.sh check-accessibility
```

### 5) Run a smoke test

```bash
uv run python smoke_test_mcp.py \
  --transport streamable-http \
  --server-url http://127.0.0.1:8765/mcp
```

## Client Configuration

### URL-capable MCP clients

```toml
[mcp_servers.ltspice]
url = "http://127.0.0.1:8765/mcp"
enabled = true
```

### Claude Desktop via `mcp-remote`

```json
{
  "mcpServers": {
    "ltspice-mcp": {
      "command": "/opt/homebrew/bin/npx",
      "args": ["-y", "mcp-remote", "http://127.0.0.1:8765/mcp"]
    }
  }
}
```

### `stdio` (subprocess) mode

```json
{
  "mcpServers": {
    "ltspice-mcp": {
      "command": "ltspice-mcp",
      "args": ["--transport", "stdio"],
      "cwd": "/absolute/path/to/ltspice-mcp"
    }
  }
}
```

## Core Capabilities by Category

### Setup and diagnostics

- `getLtspiceStatus`, `getLtspiceUiStatus`
- `daemonDoctor`, `tailDaemonLog`, `getRecentErrors`, `getCaptureHealth`

### Simulation and queueing

- `simulateNetlist`, `simulateNetlistFile`, `runSimulation`
- `queueSimulationJob`, `listJobs`, `jobStatus`, `cancelJob`, `listJobHistory`

### Schematic workflows

- `createSchematic`, `createSchematicFromNetlist`, `createSchematicFromTemplate`
- `validateSchematic`, `lintSchematic`, `autoDebugSchematic`
- `inspectSchematicVisualQuality`, `autoCleanSchematicLayout`

### Data, measurements, and verification

- `getPlotNames`, `getVectorsInfo`, `getVectorData`, `getLocalExtrema`
- `getBandwidth`, `getGainPhaseMargin`, `getRiseFallTime`, `getSettlingTime`
- `parseMeasResults`, `runMeasAutomation`, `runVerificationPlan`, `runSweepStudy`

### Native LTspice rendering

- `renderLtspiceSchematicImage`
- `renderLtspicePlotImage`, `renderLtspicePlotPresetImage`
- `renderLtspiceSymbolImage`
- `startLtspiceRenderSession`, `endLtspiceRenderSession`

## Reliability Notes

- Streamable HTTP defaults are tuned for compatibility:
  - `json_response = true`
  - `stateless_http = true`
- UI integration is disabled by default (`LTSPICE_MCP_UI_ENABLED=0`).
- Schematic single-window updates are enabled by default.
- Rendering uses LTspice + ScreenCaptureKit direct-window capture.
- Run artifacts are stored per run to keep historical results stable.

## Daemon Operations

```bash
./scripts/ltspice_mcp_daemon.sh start
./scripts/ltspice_mcp_daemon.sh restart
./scripts/ltspice_mcp_daemon.sh stop
./scripts/ltspice_mcp_daemon.sh status
./scripts/ltspice_mcp_daemon.sh logs --lines 200
./scripts/ltspice_mcp_daemon.sh logs --follow
```

Permission helpers:

```bash
./scripts/ltspice_mcp_daemon.sh trigger-screen-recording-permission
./scripts/ltspice_mcp_daemon.sh trigger-accessibility-permission
```

## Windows

This server also runs natively on Windows (LTspice's original platform). macOS-only
pieces (ScreenCaptureKit capture, Accessibility-API text reading, AppleScript window
control, the bash daemon script) have real Windows equivalents implemented in
`src/ltspice_mcp/windows_ui.py`, dispatched automatically when `platform.system() ==
"Windows"`. macOS behavior is unchanged.

### LTspice binary detection

`LTSPICE_BINARY` is checked first (same as macOS). If unset, the server probes, in order:
- `%LOCALAPPDATA%\Programs\ADI\LTspice\LTspice.exe` (current LTspice installer default)
- `%LOCALAPPDATA%\LTspice\LTspice.exe`
- `%ProgramFiles%\ADI\LTspice\LTspice.exe`
- `%ProgramFiles%\ADI\LTspiceXVII\XVIIx64.exe`
- `%ProgramFiles(x86)%\LTC\LTspiceXVII\XVIIx64.exe` (older LTspice XVII releases)
- `%ProgramFiles(x86)%\LTC\LTspiceIV\scad3.exe` (legacy LTspice IV)
- a bounded 1-2-level-deep scan under those Program Files roots, only if none of the above exist

### Windows dependencies

Installed automatically as `sys_platform == 'win32'` extras via `pip install -e .`:
- `pywin32` — window discovery/automation (`win32gui`, `win32ui`, `win32process`)
- `Pillow` — PNG encode/decode for capture, downscaling, and dimension probing
- `mss` — full-screen region-grab fallback when `PrintWindow` yields a blank image

### Windows daemon script

`scripts/ltspice_mcp_daemon.sh` is bash-only; use the PowerShell equivalent instead:

```powershell
./scripts/ltspice_mcp_daemon.ps1 start
./scripts/ltspice_mcp_daemon.ps1 restart
./scripts/ltspice_mcp_daemon.ps1 stop
./scripts/ltspice_mcp_daemon.ps1 status
./scripts/ltspice_mcp_daemon.ps1 logs -Lines 200
./scripts/ltspice_mcp_daemon.ps1 logs -Follow
```

It tracks the background process's PID in `.mcp-workdir/daemon/ltspice-mcp-daemon.pid` and
writes stdout/stderr to a timestamped log file, mirroring the bash script's behavior. It
supports the same `LTSPICE_MCP_DAEMON_*` / `UV_BIN` environment overrides.

The bash script's `trigger-initial-permissions` / `check-accessibility` /
`trigger-accessibility-permission` / `trigger-screen-recording-permission` subcommands are
**not** implemented on Windows: those exist only to trigger macOS's one-time Accessibility
and Screen Recording consent dialogs, and Windows has no equivalent consent system for
window capture or UI automation, so there is nothing to port.

### What's still macOS-only

- **Window text reading is approximate, not equivalent.** `readLtspiceUiText` on Windows
  reads text via `WM_GETTEXT` on the matched window's child controls (edit/static), which
  works for simple dialogs and log-style windows but cannot read LTspice's self-drawn
  canvas content (schematic/plot panes) — the macOS Accessibility API can do a bit more
  here for dialog trees, but neither platform can read canvas-drawn content as text.
- The Swift/ScreenCaptureKit helper compilation path (`_ensure_screencapturekit_helper`
  and friends) is macOS-only and is simply not invoked on Windows; capture goes through
  `windows_ui.capture_window` (`PrintWindow`, with an `mss` full-screen-region fallback)
  instead.

## Testing

Run core tests:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Run real ScreenCaptureKit integration tests (opt-in):

```bash
LTSPICE_MCP_RUN_REAL_SCK=1 PYTHONPATH=src .venv/bin/python -m unittest tests.test_screencapturekit_integration -v
LTSPICE_MCP_RUN_REAL_SCK=1 PYTHONPATH=src .venv/bin/python -m unittest tests.test_plot_render_mcp_real -v
```

## Contributing

Contributions are welcome. Start with:
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [AGENT_README.md](AGENT_README.md) for agent-specific workflows

When filing bugs, include:
- MCP server version,
- LTspice version,
- transport mode,
- exact tool call + parameters,
- daemon log excerpts.

## Documentation Map

- [docs/README.md](docs/README.md)
- [AGENT_README.md](AGENT_README.md)
- [CHANGELOG.md](CHANGELOG.md)
- [COMPATIBILITY.md](COMPATIBILITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SUPPORT.md](SUPPORT.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [SECURITY.md](SECURITY.md)
- MCP resource: `docs://agent-readme`
- MCP tool: `readAgentGuide`

## Important Environment Variables

Core:
- `LTSPICE_BINARY`
- `LTSPICE_MCP_WORKDIR`
- `LTSPICE_MCP_TIMEOUT`
- `LTSPICE_MCP_TRANSPORT`
- `LTSPICE_MCP_HOST`
- `LTSPICE_MCP_PORT`
- `LTSPICE_MCP_STREAMABLE_HTTP_PATH`
- `LTSPICE_MCP_JSON_RESPONSE`
- `LTSPICE_MCP_STATELESS_HTTP`

UI/render:
- `LTSPICE_MCP_UI_ENABLED`
- `LTSPICE_MCP_SCHEMATIC_SINGLE_WINDOW`
- `LTSPICE_MCP_SCHEMATIC_LIVE_PATH`
- `LTSPICE_MCP_SCK_HELPER_DIR`
- `LTSPICE_MCP_SCK_HELPER_PATH`
- `LTSPICE_MCP_VERIFY_WINDOW_CLOSE`

Logging:
- `LTSPICE_MCP_LOG_LEVEL`
- `LTSPICE_MCP_TOOL_LOGGING`
- `LTSPICE_MCP_TOOL_LOG_MAX_ITEMS`
- `LTSPICE_MCP_TOOL_LOG_MAX_CHARS`
- `LTSPICE_MCP_DISABLE_UVICORN_NOISE_FILTERS`
- `LTSPICE_MCP_DAEMON_LOG_DIR`
