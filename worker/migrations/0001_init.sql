-- TTrade D1 Schema — initial migration
CREATE TABLE IF NOT EXISTS signal_evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id TEXT NOT NULL UNIQUE,
  ticker TEXT NOT NULL,
  direction TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  market_state TEXT NOT NULL,
  all_gates_passed INTEGER NOT NULL DEFAULT 0,
  signal_score REAL,
  component_scores_json TEXT,
  action_taken TEXT,
  strategy_version TEXT,
  config_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gate_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id TEXT NOT NULL,
  gate_name TEXT NOT NULL,
  passed INTEGER NOT NULL DEFAULT 0,
  measured_value TEXT,
  threshold TEXT,
  config_version TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS execution_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id TEXT NOT NULL UNIQUE,
  signal_id TEXT,
  event_type TEXT NOT NULL,
  order_id TEXT,
  spread_json TEXT,
  mid_price REAL,
  limit_price REAL,
  fill_price REAL,
  timestamp TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  position_id TEXT NOT NULL UNIQUE,
  signal_id TEXT,
  execution_id TEXT,
  ticker TEXT NOT NULL,
  direction TEXT NOT NULL,
  entry_debit REAL,
  spread_json TEXT,
  status TEXT NOT NULL,
  opened_at TEXT,
  closed_at TEXT,
  exit_reason TEXT,
  exit_credit REAL,
  pnl_pct REAL,
  pnl_dollars REAL,
  mfe REAL,
  mae REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id TEXT NOT NULL UNIQUE,
  execution_id TEXT,
  signal_id TEXT,
  ticker TEXT NOT NULL,
  direction TEXT NOT NULL,
  signal_score REAL,
  entry_debit REAL,
  exit_credit REAL,
  pnl_pct REAL,
  pnl_dollars REAL,
  hold_duration_hours REAL,
  exit_reason TEXT,
  setup_grade TEXT,
  execution_grade TEXT,
  outcome_grade TEXT,
  failure_tags_json TEXT,
  counterfactuals_json TEXT,
  review_notes TEXT,
  strategy_version TEXT,
  config_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weekly_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id TEXT NOT NULL UNIQUE,
  week_start TEXT NOT NULL,
  week_end TEXT NOT NULL,
  total_signals INTEGER,
  total_trades INTEGER,
  win_rate REAL,
  total_pnl REAL,
  report_json TEXT,
  generated_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS config_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  config_hash TEXT NOT NULL UNIQUE,
  config_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  synced_at TEXT NOT NULL,
  record_type TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signal_evaluations(ticker);
CREATE INDEX IF NOT EXISTS idx_gate_results_signal ON gate_results(signal_id);
CREATE INDEX IF NOT EXISTS idx_executions_signal ON execution_events(signal_id);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_reviews_signal ON trade_reviews(signal_id);
