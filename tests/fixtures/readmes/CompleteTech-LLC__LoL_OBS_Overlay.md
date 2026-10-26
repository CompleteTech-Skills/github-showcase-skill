<p align="center"><img src="assets/banner.jpg" alt="Abstract glowing isometric streaming overlay panels with rank hexagons, bar charts and a match strip around a live broadcast monitor, in teal and amber on midnight navy." width="100%"></p>

# LoL OBS Overlay

Real-time League of Legends account monitor that generates auto-updating OBS overlays for streamers.

It is a Python command-line tool for League streamers. It reads your ranked data and recent matches from the Riot Games API, detects which account is active in the local League client, and writes HTML overlay files that an OBS Browser Source can display. Status: early prototype with no automated tests; it needs your own Riot API key.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env        # then set RIOT_API_KEY in .env
python main.py monitor
```

Get a key from the [Riot Developer Portal](https://developer.riotgames.com/). Start a League game and the monitor detects the active account, writes the overlays to `obs_data/`, and refreshes them every 5 seconds by default.

## Commands

| Command | What it does |
|---|---|
| `python main.py monitor` | Watch for the League client, detect account switches, keep overlays updated. |
| `python main.py detect` | Test League client detection and show the current active account. |
| `python main.py lookup <game_name> <tag_line> [region]` | Look up an account, its ranked info and today's matches. |
| `python main.py overlay <game_name> <tag_line> [region]` | Generate overlay files once for one account. |
| `python main.py help` | Show usage. |

Example: `python main.py overlay CoachRogue2 Fill euw1`

## OBS setup

1. Run `python main.py monitor` so the files exist.
2. In OBS, add a Browser Source.
3. Set the URL to the overlay file, for example `file:///YOUR_PATH/obs_data/04_combined_overlay.html`.
4. Set width 800 and height 200 for the combined overlay.
5. Enable "Refresh browser when scene becomes active".

The exporter writes five files to `obs_data/` (created automatically):

- `01_rank_overlay.html`: current rank and LP
- `02_daily_stats_overlay.html`: today's game statistics
- `03_recent_matches_overlay.html`: recent match history
- `04_combined_overlay.html`: all-in-one display
- `05_accounts_overlay.html`: accounts seen today

## Configuration

Settings come from `.env` (see `.env.example` for the full list). The ones most people change:

```bash
RIOT_API_KEY=your_key_here
GAME_CHECK_INTERVAL=1          # seconds between checks for an active game
ACCOUNT_REFRESH_INTERVAL=60    # seconds between data refreshes when idle
OVERLAY_UPDATE_INTERVAL=5      # seconds between overlay updates during a game
RATE_LIMIT_DELAY=0.1           # delay between API requests, in seconds
SESSION_TIMEOUT=30             # HTTP request timeout, in seconds
CURRENT_SEASON=2025            # season year shown in the overlays
```

`REGION` pins a region; otherwise the tool tries a default list of regions when it looks up an account (`euw1`, `na1`, `eun1`, `kr`, `br1`, `jp1`, `oc1`, `ru`, `tr1`, `la1`, `la2`). `RIOT_REGION_DETECTION_ORDER` overrides that list.

## How it works

1. `monitor` starts and polls the League client's local Live Client API.
2. When a game starts, it identifies the active account.
3. It fetches rank and match data from the Riot API and writes the overlay files.
4. It keeps refreshing during the game and handles switches between accounts.

## Layout

```
main.py                  # CLI entry point
src/
  api/                   # Riot API client and configuration
  data/                  # account lookup, match history, ranked info
  detection/             # League client detection and session management
  overlay/               # overlay generation (obs_overlay.py, generate_overlay.py)
  utils/                 # console and formatting helpers
.env.example             # settings template
requirements.txt         # Python dependencies
```

## License

MIT, see [LICENSE](LICENSE). Respect the Riot Games API Terms of Service and rate limits.

This tool is not affiliated with Riot Games. League of Legends is a trademark of Riot Games, Inc.
