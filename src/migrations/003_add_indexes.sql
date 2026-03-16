-- Indexes for common dashboard query patterns: filter by model, tag, and time range
CREATE INDEX IF NOT EXISTS idx_requests_model_used     ON requests(model_used);
CREATE INDEX IF NOT EXISTS idx_requests_difficulty_tag ON requests(difficulty_tag);
CREATE INDEX IF NOT EXISTS idx_requests_created_at     ON requests(created_at DESC);
