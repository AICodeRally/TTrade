-- Add AI analysis columns to signal_evaluations
ALTER TABLE signal_evaluations ADD COLUMN ai_conviction REAL;
ALTER TABLE signal_evaluations ADD COLUMN ai_analysis_json TEXT;

-- Add AI review column to trade_reviews
ALTER TABLE trade_reviews ADD COLUMN ai_review_json TEXT;
