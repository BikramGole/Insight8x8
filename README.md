<<<<<<< HEAD
# Insight8x8

Insight8x8 is your personal AI-powered chess analysis companion. Explore your Chess.com games using just your username, uncover mistakes and missed opportunities with Stockfish, and get clear, human friendly explanations of why each move matters. Don't just see your blunders. Understand them, learn from them, and become a better player.

## What it does

- **Username-first onboarding** — paste any public Chess.com username; no password, API key, or account linking is required.
- **Complete public archive** — monthly archives are downloaded in parallel, normalized, and cached locally for fast repeat visits.
- **Move-by-move replay** — flip the board, step through the game, jump to any move, watch automatic playback, and inspect captured material.
- **Stockfish analysis** — evaluate every position locally with configurable search depth and time per move.
- **Plain-language coaching** — each move shows the best move, evaluation before and after, centipawn loss, a classification (blunder, mistake, inaccuracy, best/good), top candidate moves with principal variations, and tactical opportunities.
- **Openings and patterns** — see rating progression, results, activity, time-control mix, frequent opponents, and opening win rates. Click an opening or opponent to filter the match history instantly.
- **Compare players** — check another public Chess.com account and review your direct encounters.
- **Favorites and exports** — save games, then export the current scope as PGN or CSV.

## Quick start

```bash
# 1. Install the GUI dependency (python-chess is vendored in vendor/chess)
pip install -r requirements.txt

# 2. Launch Insight8x8
python3 insight8x8.py
```

Enter a Chess.com username on the landing page and choose **Analyze my games**. The first load can take a minute for a large archive; later visits use the local cache.

Stockfish is optional but required for engine explanations. If it is not on your `PATH`, open **Engine settings** in the dashboard sidebar (or press `Ctrl+,`) and select the Stockfish executable. You can also set `STOCKFISH_PATH` before launching the app.

## Running the tests

```bash
python3 -m unittest discover -v -p 'test_*.py'
```

The suite uses an offscreen Qt platform and a temporary SQLite database; it does not call Chess.com. It also contains a fake UCI engine so the full analysis pipeline can be tested without installing Stockfish.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+1` … `Ctrl+6` | Switch between Overview, Match history, Openings, Compare, Favorites, and Export |
| `Ctrl+F` | Focus the match-history search field |
| `F5` | Refresh Chess.com archives |
| `Ctrl+,` | Open Engine settings |
| `Enter` | Connect a username / replay the selected game |
| `←` / `→` / `Space` (in replay) | Previous move / next move / play or pause |

Right-click a game in Match history to analyze it, toggle its favorite state, or copy its Chess.com link.

## Analysis output

For each analyzed move, Insight8x8 reports:

1. The move played and the engine's best move.
2. Evaluations before and after, from the mover's point of view.
3. Centipawn loss and a classification such as `blunder`, `mistake`, `inaccuracy`, or `best/good`.
4. Up to three candidate moves with short principal variations.
5. Tactical opportunities such as missed mates or winning material.

Chess.com accuracy is used when the source provides it. Insight8x8 never invents an evaluation: if Stockfish is not configured, the analysis panel explains how to enable it instead of showing fabricated scores.

## Configuration

| Setting | Where | Default |
| --- | --- | --- |
| Stockfish executable | Engine settings or `STOCKFISH_PATH` | Detected from `PATH` |
| Search depth | Engine settings | 12 |
| Time per position | Engine settings | 150 ms |
| Local database | `INSIGHT8X8_DB` | `data/insight8x8.db` |
| Chess.com user agent | `CHESSCOM_USER_AGENT` | `Insight8x8/1.0 (...)` |
| Chess.com request interval | `CHESSCOM_MIN_INTERVAL` | Built-in rate limit |
| Chess.com workers | `CHESSCOM_MAX_WORKERS` | Built-in parallel limit |

Settings such as the last username, engine path, depth, and movetime are stored with `QSettings`; cached games and favorites are stored in the local SQLite database.

## Project structure

```text
insight8x8.py        Main PyQt6 application, pages, filters, exports, orchestration
viewers.py           Game replay and analysis dialog
ui_widgets.py        Board, charts, stat cards, avatars, shared drawing helpers
engine.py            Stockfish UCI wrapper, classifications, candidate and tactic detection
chesscom.py          Public Chess.com API client, PGN parsing, normalization, caching
store.py             SQLite cache and favorites
workers.py           Background QThread workers
utils.py             Formatting and filter helpers
test_insight8x8.py   Unit and GUI smoke tests
vendor/chess/        Vendored python-chess (see vendor/CHESS_LICENSE.txt)
data/                Local SQLite cache (generated at runtime)
```

## Privacy

Only public Chess.com profile, statistics, and game archive data is requested. No password is collected. Analysis runs locally through Stockfish. Favorites, settings, and cached archives stay on your machine.

## Troubleshooting

- **"Stockfish is not configured"** — install Stockfish or select its executable in Engine settings.
- **Archive warnings / offline mode** — Insight8x8 keeps previously cached games available and shows a retry hint; press `F5` when the connection returns.
- **Large archive is slow** — lower the analysis depth or increase/decrease time per position in Engine settings; archive loading itself is cached after the first run.
- **No games match filters** — use **Clear filters** to reset search, dates, sorting, and pagination.

## License

Third-party `python-chess` is vendored under its terms in `vendor/CHESS_LICENSE.txt`. Stockfish is not bundled; install it separately if you want local engine analysis.
=======
>>>>>>> origin/main
