-- Add cost_saved_usd for DBs created before it was in 001
ALTER TABLE requests ADD COLUMN IF NOT EXISTS cost_saved_usd NUMERIC(10, 6) DEFAULT 0;
