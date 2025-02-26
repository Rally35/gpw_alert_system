# Create database directory if it doesn't exist
mkdir -p database

# Create a corrected init.sql file
cat > database/init.sql << 'EOF'
-- Create schema for GPW Alert System

-- Staging table for newly fetched data
CREATE TABLE IF NOT EXISTS staging_stock_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL
);

-- Main historical data table with unique constraint
CREATE TABLE IF NOT EXISTS historical_stock_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
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

-- Alerts history table
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    volume BIGINT,
    ma50 DECIMAL(10, 2),
    ma100 DECIMAL(10, 2),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'PENDING'
);

-- System health monitoring table
CREATE TABLE IF NOT EXISTS system_health (
    id SERIAL PRIMARY KEY,
    component VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    last_check TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);

-- Backtesting results table
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    initial_capital DECIMAL(12, 2) NOT NULL,
    final_capital DECIMAL(12, 2) NOT NULL,
    total_return DECIMAL(10, 2) NOT NULL,
    annualized_return DECIMAL(10, 2) NOT NULL,
    total_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    win_rate DECIMAL(10, 2) NOT NULL,
    max_drawdown DECIMAL(10, 2) NOT NULL,
    sharpe_ratio DECIMAL(10, 2),
    parameters JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
EOF