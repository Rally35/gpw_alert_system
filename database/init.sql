-- Create schema for GPW Alert System

-- Staging table for newly fetched data
CREATE TABLE IF NOT EXISTS staging_stock_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP(0) NOT NULL,
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_staging_symbol ON staging_stock_prices(symbol);
CREATE INDEX IF NOT EXISTS idx_staging_timestamp ON staging_stock_prices(timestamp);

-- Main historical data table with unique constraint
CREATE TABLE IF NOT EXISTS historical_stock_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP(0) NOT NULL,
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    CONSTRAINT unique_stock_entry UNIQUE (symbol, timestamp)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_historical_symbol ON historical_stock_prices(symbol);
CREATE INDEX IF NOT EXISTS idx_historical_timestamp ON historical_stock_prices(timestamp);

-- Alerts history table with JSONB for extra details
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'PENDING',
    details JSONB
);

-- System health monitoring table
CREATE TABLE IF NOT EXISTS system_health (
    id SERIAL PRIMARY KEY,
    component VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    last_check TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    entry_price DECIMAL(10,2) NOT NULL,
    stop_loss DECIMAL(10,2) NOT NULL,
    target DECIMAL(10,2) NOT NULL,
    entry_time TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'OTWARTA',
    details JSONB
);

-- Create or replace the trigger function
CREATE OR REPLACE FUNCTION staging_to_historical_trigger_fn()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO historical_stock_prices (symbol, timestamp, open, high, low, close, volume)
    VALUES (NEW.symbol, NEW.timestamp, NEW.open, NEW.high, NEW.low, NEW.close, NEW.volume)
    ON CONFLICT (symbol, timestamp) DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create the trigger on the staging table to fire after every INSERT or UPDATE
CREATE TRIGGER staging_to_historical_trigger
AFTER INSERT OR UPDATE ON staging_stock_prices
FOR EACH ROW
EXECUTE FUNCTION staging_to_historical_trigger_fn();

