# Learnings

Behaviour of the upstream CLI and of Qt that cost time to discover, kept here so
the next change does not rediscover it.

## Filter the upstream provider list

- **Symptom.** `codexbar usage --provider all` returns dozens of provider names,
  most of them without an active usage window, and the UI filled up with empty
  cards.
- **Cause.** The CLI folds its inventory of *supported* providers into the same
  JSON as the ones you actually use.
- **Fix.** Show only records that carry a usage window, an account identity or
  credit data.
- **Evidence.** A real local CLI run produced exactly one usable record.

## Keep the daily token history independent of the CLI's window

- **Symptom.** `codexbar cost` reports daily token data over a limited window;
  as months pass, older days disappear from the UI.
- **Cause.** The CLI summarises recent local logs. It is not a long-term store,
  and the application had none of its own.
- **Fix.** Merge `daily[].date` and `daily[].totalTokens` into a JSON history on
  the device. A new value updates that day's record; records older than 365 days
  are dropped. Monthly totals and daily rows are rendered from this history, not
  from the CLI response.
- **Prevention.** Tell the user how many days the history actually covers.
  Never assume an external CLI's response is unbounded history.
- **Evidence.** Four days were imported from real Codex CLI output; unit tests
  cover the merge, the monthly total, parsing and a JSON round trip.

## Pick a single-instance guard that matches the environment

- **Symptom.** With the window closed but the tray icon alive, launching again
  created a second tray icon and a second process.
- **Cause.** Closing the window does not end the process, and nothing locked it.
- **Failed attempt.** `QLocalServer` could not open a listener in this KDE/Qt
  environment — it failed with `Unknown error`.
- **Fix.** A `QSharedMemory` guard tied to process lifetime. The first process
  creates a small shared segment; a second process cannot, and exits before it
  builds a window or a tray icon.
- **Evidence.** With the first instance running under the offscreen platform, a
  second `python3 app.py` exited with the "already running" message.

## The colour of a state must have one source

- **Symptom.** The current-state card stayed green at 2% remaining.
- **Cause.** The state was computed in `pace_state()` but the card's colour was
  hard-coded green in the stylesheet, so the two could never disagree loudly —
  the text changed and the box did not.
- **Fix.** Generate the stylesheet per state (`pace_style()`), have the card set
  a `paceState` property on itself, and let the chip, the chrome and every
  provider bar read the same palette entry.
- **Evidence.** `test_card_state_matches_the_worst_provider_row` pins the card
  and its rows to the same bands across six usage pairs.
