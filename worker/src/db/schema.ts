import {
  integer,
  real,
  sqliteTable,
  text,
} from "drizzle-orm/sqlite-core";

export const signalEvaluations = sqliteTable("signal_evaluations", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  signalId: text("signal_id").notNull().unique(),
  ticker: text("ticker").notNull(),
  direction: text("direction").notNull(),
  timestamp: text("timestamp").notNull(),
  marketState: text("market_state").notNull(),
  allGatesPassed: integer("all_gates_passed", { mode: "boolean" }).notNull(),
  signalScore: real("signal_score"),
  componentScoresJson: text("component_scores_json"),
  actionTaken: text("action_taken"),
  strategyVersion: text("strategy_version"),
  configHash: text("config_hash"),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});

export const gateResults = sqliteTable("gate_results", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  signalId: text("signal_id").notNull(),
  gateName: text("gate_name").notNull(),
  passed: integer("passed", { mode: "boolean" }).notNull(),
  measuredValue: real("measured_value"),
  threshold: real("threshold"),
  configVersion: text("config_version"),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});

export const executionEvents = sqliteTable("execution_events", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  executionId: text("execution_id").notNull().unique(),
  signalId: text("signal_id"),
  eventType: text("event_type").notNull(),
  orderId: text("order_id"),
  spreadJson: text("spread_json"),
  midPrice: real("mid_price"),
  limitPrice: real("limit_price"),
  fillPrice: real("fill_price"),
  timestamp: text("timestamp").notNull(),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});

export const positions = sqliteTable("positions", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  positionId: text("position_id").notNull().unique(),
  signalId: text("signal_id"),
  executionId: text("execution_id"),
  ticker: text("ticker").notNull(),
  direction: text("direction").notNull(),
  entryDebit: real("entry_debit"),
  spreadJson: text("spread_json"),
  status: text("status").notNull(),
  openedAt: text("opened_at"),
  closedAt: text("closed_at"),
  exitReason: text("exit_reason"),
  exitCredit: real("exit_credit"),
  pnlPct: real("pnl_pct"),
  pnlDollars: real("pnl_dollars"),
  mfe: real("mfe"),
  mae: real("mae"),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});

export const tradeReviews = sqliteTable("trade_reviews", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  reviewId: text("review_id").notNull().unique(),
  executionId: text("execution_id"),
  signalId: text("signal_id"),
  ticker: text("ticker").notNull(),
  direction: text("direction").notNull(),
  signalScore: real("signal_score"),
  entryDebit: real("entry_debit"),
  exitCredit: real("exit_credit"),
  pnlPct: real("pnl_pct"),
  pnlDollars: real("pnl_dollars"),
  holdDurationHours: real("hold_duration_hours"),
  exitReason: text("exit_reason"),
  setupGrade: text("setup_grade"),
  executionGrade: text("execution_grade"),
  outcomeGrade: text("outcome_grade"),
  failureTagsJson: text("failure_tags_json"),
  counterfactualsJson: text("counterfactuals_json"),
  reviewNotes: text("review_notes"),
  strategyVersion: text("strategy_version"),
  configHash: text("config_hash"),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});

export const weeklyReports = sqliteTable("weekly_reports", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  reportId: text("report_id").notNull().unique(),
  weekStart: text("week_start").notNull(),
  weekEnd: text("week_end").notNull(),
  totalSignals: integer("total_signals"),
  totalTrades: integer("total_trades"),
  winRate: real("win_rate"),
  totalPnl: real("total_pnl"),
  reportJson: text("report_json"),
  generatedAt: text("generated_at").notNull(),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});

export const configVersions = sqliteTable("config_versions", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  configHash: text("config_hash").notNull().unique(),
  configJson: text("config_json").notNull(),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});

export const syncLog = sqliteTable("sync_log", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  syncedAt: text("synced_at").notNull(),
  recordType: text("record_type").notNull(),
  recordCount: integer("record_count").notNull(),
  status: text("status").notNull(),
  createdAt: text("created_at").notNull().default("CURRENT_TIMESTAMP"),
});
