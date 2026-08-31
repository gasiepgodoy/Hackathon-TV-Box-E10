-- Schema inicial PostgreSQL (complementar ao SQLAlchemy)
-- Tabelas criadas automaticamente via init_db; índices adicionais aqui.

CREATE INDEX IF NOT EXISTS idx_event_updates_recorded_at ON event_updates (recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_updates_collected_at ON event_updates (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_metrics_key ON event_metrics (metric_key);
