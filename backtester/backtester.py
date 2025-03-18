import os
import json
import logging
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/backtester.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('backtester')

# Database connection
def get_db_connection():
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_user = os.environ.get('DB_USER', 'user')
    db_password = os.environ.get('DB_PASSWORD', 'password')
    db_name = os.environ.get('DB_NAME', 'stocks')
    
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"
    return create_engine(connection_string)

# Get historical data for backtesting
def get_historical_data(engine, symbol, start_date, end_date):
    try:
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM historical_stock_prices
            WHERE symbol = :symbol 
            AND timestamp BETWEEN :start_date AND :end_date
            ORDER BY timestamp
        """
        
        params = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date
        }
        
        df = pd.read_sql(text(query), engine, params=params)
        
        if df.empty:
            logger.warning(f"No historical data found for {symbol} between {start_date} and {end_date}")
            return None
            
        return df
    except Exception as e:
        logger.error(f"Error getting historical data: {str(e)}")
        return None

# Moving Average Crossover Strategy Backtester
def backtest_ma_crossover(data, short_ma=50, long_ma=100, initial_capital=10000.0):
    if data is None or len(data) < long_ma:
        return None
    
    # Create a copy of the dataframe
    df = data.copy()
    
    # Calculate moving averages
    df['MA_short'] = df['close'].rolling(window=short_ma).mean()
    df['MA_long'] = df['close'].rolling(window=long_ma).mean()
    
    # Generate signals
    df['signal'] = 0
    df.loc[df['MA_short'] > df['MA_long'], 'signal'] = 1
    
    # Generate trading orders
    df['position'] = df['signal'].diff()
    
    # Calculate strategy returns
    df['returns'] = np.log(df['close'] / df['close'].shift(1))
    df['strategy_returns'] = df['signal'].shift(1) * df['returns']
    
    # Calculate cumulative returns
    df['cumulative_returns'] = df['returns'].cumsum().apply(np.exp)
    df['strategy_cumulative_returns'] = df['strategy_returns'].cumsum().apply(np.exp)
    
    # Calculate account value
    df['portfolio_value'] = initial_capital * df['strategy_cumulative_returns']
    
    # Calculate drawdown
    df['peak'] = df['portfolio_value'].cummax()
    df['drawdown'] = (df['peak'] - df['portfolio_value']) / df['peak']
    
    # Calculate trading metrics
    total_days = (df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).days
    years = total_days / 365.25
    
    buy_signals = df[df['position'] == 1]
    sell_signals = df[df['position'] == -1]
    
    total_trades = len(buy_signals) + len(sell_signals)
    
    # Count winning trades
    winning_trades = 0
    for i in range(len(buy_signals)):
        try:
            buy_price = buy_signals['close'].iloc[i]
            if i < len(sell_signals):
                sell_price = sell_signals['close'].iloc[i]
                if sell_price > buy_price:
                    winning_trades += 1
        except:
            pass
    
    # Calculate metrics
    final_value = df['portfolio_value'].iloc[-1] if not df.empty else initial_capital
    total_return = ((final_value - initial_capital) / initial_capital) * 100
    annualized_return = ((1 + total_return/100) ** (1/years) - 1) * 100 if years > 0 else 0
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    max_drawdown = df['drawdown'].max() * 100
    
    # Calculate Sharpe ratio (annualized)
    risk_free_rate = 0.02  # 2% risk-free rate assumption
    sharpe_ratio = ((annualized_return/100 - risk_free_rate) / (df['strategy_returns'].std() * np.sqrt(252))) if df['strategy_returns'].std() > 0 else 0
    
    results = {
        "start_date": df['timestamp'].iloc[0],
        "end_date": df['timestamp'].iloc[-1],
        "initial_capital": float(initial_capital),
        "final_capital": float(final_value),
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "total_trades": int(total_trades),
        "winning_trades": int(winning_trades),
        "win_rate": float(win_rate),
        "max_drawdown": float(max_drawdown),
        "sharpe_ratio": float(sharpe_ratio),
        "parameters": {
            "short_ma": short_ma,
            "long_ma": long_ma
        },
        "equity_curve": df[['timestamp', 'portfolio_value']].to_dict(orient='records'),
        "signals": df[df['position'] != 0][['timestamp', 'position', 'close']].to_dict(orient='records')
    }
    
    return results

# Save backtest results to database
def save_backtest_results(engine, symbol, strategy, results):
    try:
        if results is None:
            return False
            
        with engine.connect() as conn:
            # Insert into backtest_results table
            query = """
                INSERT INTO backtest_results
                (symbol, strategy, start_date, end_date, initial_capital,
                final_capital, total_return, annualized_return, total_trades,
                winning_trades, win_rate, max_drawdown, sharpe_ratio, parameters)
                VALUES
                (:symbol, :strategy, :start_date, :end_date, :initial_capital,
                :final_capital, :total_return, :annualized_return, :total_trades,
                :winning_trades, :win_rate, :max_drawdown, :sharpe_ratio, :parameters)
                RETURNING id
            """
            
            parameters = json.dumps(results['parameters'])
            
            result = conn.execute(
                text(query),
                {
                    "symbol": symbol,
                    "strategy": strategy,
                    "start_date": results['start_date'],
                    "end_date": results['end_date'],
                    "initial_capital": results['initial_capital'],
                    "final_capital": results['final_capital'],
                    "total_return": results['total_return'],
                    "annualized_return": results['annualized_return'],
                    "total_trades": results['total_trades'],
                    "winning_trades": results['winning_trades'],
                    "win_rate": results['win_rate'],
                    "max_drawdown": results['max_drawdown'],
                    "sharpe_ratio": results['sharpe_ratio'],
                    "parameters": parameters
                }
            )
            
            backtest_id = result.fetchone()[0]
            conn.commit()
            
            logger.info(f"Saved backtest results for {symbol} ({strategy}) with ID {backtest_id}")
            return backtest_id
    except Exception as e:
        logger.error(f"Error saving backtest results: {str(e)}")
        return None

# Run backtest for a specific symbol and strategy
def run_backtest(symbol, strategy, params=None):
    try:
        engine = get_db_connection()
        
        # Default parameters
        if strategy == "moving_average":
            default_params = {
                "short_ma": 50,
                "long_ma": 100,
                "initial_capital": 10000.0,
                "start_date": (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d'),
                "end_date": datetime.now().strftime('%Y-%m-%d')
            }
        else:
            logger.error(f"Unsupported strategy: {strategy}")
            return None
            
        # Merge default params with provided params
        if params:
            for key, value in params.items():
                default_params[key] = value
        
        params = default_params
        
        # Get historical data
        data = get_historical_data(
            engine, 
            symbol, 
            params['start_date'], 
            params['end_date']
        )
        
        if data is None:
            return {"error": f"No data available for {symbol}"}
            
        # Run appropriate backtest strategy
        if strategy == "moving_average":
            results = backtest_ma_crossover(
                data, 
                short_ma=params['short_ma'], 
                long_ma=params['long_ma'],
                initial_capital=params['initial_capital']
            )
        else:
            return {"error": f"Unsupported strategy: {strategy}"}
            
        if results:
            # Save results to database
            backtest_id = save_backtest_results(engine, symbol, strategy, results)
            results["backtest_id"] = backtest_id
            
            # Return results without the equity curve to reduce response size
            summary = {k: v for k, v in results.items() if k != 'equity_curve'}
            summary["equity_curve_length"] = len(results.get('equity_curve', []))
            
            return summary
        else:
            return {"error": "Failed to generate backtest results"}
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        return {"error": str(e)}

# Get all backtest results for a specific symbol
def get_backtest_results(symbol=None, limit=10):
    try:
        engine = get_db_connection()

        with engine.connect() as conn:
            if symbol:
                query = """
                    SELECT id, symbol, strategy, start_date, end_date, 
                    initial_capital, final_capital, total_return, 
                    annualized_return, total_trades, winning_trades, 
                    win_rate, max_drawdown, sharpe_ratio, parameters, created_at
                    FROM backtest_results
                    WHERE symbol = :symbol
                    ORDER BY created_at DESC
                    LIMIT :limit
                """
                result = conn.execute(
                    text(query),
                    {"symbol": symbol, "limit": limit}
                )
            else:
                query = """
                    SELECT id, symbol, strategy, start_date, end_date, 
                    initial_capital, final_capital, total_return, 
                    annualized_return, total_trades, winning_trades, 
                    win_rate, max_drawdown, sharpe_ratio, parameters, created_at
                    FROM backtest_results
                    ORDER BY created_at DESC
                    LIMIT :limit
                """
                result = conn.execute(
                    text(query),
                    {"limit": limit}
                )

            results = []
            for row in result:
                # Serialize parameters correctly
                params_json = row.parameters
                if isinstance(params_json, dict):
                    parameters = params_json
                elif isinstance(params_json, str):
                    parameters = json.loads(params_json)
                else:
                    parameters = {}

                results.append({
                    "id": row.id,
                    "symbol": row.symbol,
                    "strategy": row.strategy,
                    "start_date": row.start_date.strftime('%Y-%m-%d'),
                    "end_date": row.end_date.strftime('%Y-%m-%d'),
                    "initial_capital": float(row.initial_capital),
                    "final_capital": float(row.final_capital),
                    "total_return": float(row.total_return),
                    "annualized_return": float(row.annualized_return),
                    "total_trades": row.total_trades,
                    "winning_trades": row.winning_trades,
                    "win_rate": float(row.win_rate),
                    "max_drawdown": float(row.max_drawdown),
                    "sharpe_ratio": float(row.sharpe_ratio),
                    "parameters": parameters,
                    "created_at": row.created_at.strftime('%Y-%m-%d %H:%M:%S')
                })

            return results
    except Exception as e:
        logger.error(f"Error getting backtest results: {str(e)}")
        return []

# Get equity curve data for a specific backtest
def get_backtest_equity_curve(symbol, start_date, end_date, strategy, params):
    try:
        engine = get_db_connection()
        
        # Get historical data
        data = get_historical_data(
            engine, 
            symbol, 
            start_date, 
            end_date
        )
        
        if data is None:
            return {"error": f"No data available for {symbol}"}
            
        # Run appropriate backtest strategy
        if strategy == "moving_average":
            short_ma = params.get('short_ma', 50)
            long_ma = params.get('long_ma', 100)
            initial_capital = params.get('initial_capital', 10000.0)
            
            results = backtest_ma_crossover(
                data, 
                short_ma=short_ma, 
                long_ma=long_ma,
                initial_capital=initial_capital
            )
            
            if results:
                return {
                    "equity_curve": results['equity_curve'],
                    "signals": results['signals']
                }
        
        return {"error": "Failed to generate equity curve"}
    except Exception as e:
        logger.error(f"Error getting equity curve: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    os.makedirs("/app/logs", exist_ok=True)
    
    # Test backtester
    results = run_backtest("PKO", "moving_average")
    print(results)
