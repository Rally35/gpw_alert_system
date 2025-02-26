import os
import json
import logging
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import pandas as pd
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dashboard')

app = FastAPI(title="GPW Alert System Dashboard")

# Templates and static files setup
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Database connection
def get_db_connection():
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_user = os.environ.get('DB_USER', 'user')
    db_password = os.environ.get('DB_PASSWORD', 'password')
    db_name = os.environ.get('DB_NAME', 'stocks')
    
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"
    return create_engine(connection_string)

# Get list of available symbols
def get_symbols():
    engine = get_db_connection()
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT DISTINCT symbol
                    FROM historical_stock_prices
                    ORDER BY symbol
                """)
            )
            
            symbols = [row[0] for row in result]
            
            # If no symbols found in database, fall back to config file
            if not symbols:
                logger.warning("No symbols found in database, falling back to config file")
                try:
                    config_path = os.environ.get('CONFIG_PATH', '/app/config/symbols.json')
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        symbols = config.get("symbols", [])
                except Exception as config_err:
                    logger.error(f"Error loading config file: {str(config_err)}")
                    # Fall back to hardcoded symbols
                    symbols = ["PKO", "PKN", "PZU", "PEO", "KGH", "LPP"]
            
            logger.info(f"Found {len(symbols)} symbols: {symbols}")
            return symbols
    except Exception as e:
        logger.error(f"Error getting symbols: {str(e)}")
        # Fall back to hardcoded symbols in case of error
        return ["PKO", "PKN", "PZU", "PEO", "KGH", "LPP"]

# Get stock data for a symbol
def get_stock_data(symbol, days=30):
    engine = get_db_connection()
    try:
        with engine.connect() as conn:
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM historical_stock_prices
                WHERE symbol = :symbol
                AND timestamp > NOW() - INTERVAL '{days} days'
                ORDER BY timestamp
            """
            
            df = pd.read_sql(text(query), conn, params={"symbol": symbol})
            
            if df.empty:
                logger.warning(f"No data found for symbol {symbol} for the last {days} days")
            else:
                logger.info(f"Retrieved {len(df)} data points for {symbol}")
            
            # Calculate moving averages
            if len(df) > 0:
                df['ma50'] = df['close'].rolling(window=min(50, len(df))).mean()
                df['ma100'] = df['close'].rolling(window=min(100, len(df))).mean()
            
            return df
    except Exception as e:
        logger.error(f"Error getting stock data for {symbol}: {str(e)}")
        return pd.DataFrame()

# Get recent alerts
def get_recent_alerts(days=7):
    engine = get_db_connection()
    try:
        with engine.connect() as conn:
            query = """
                SELECT id, symbol, strategy, signal_type, price, 
                       volume, ma50, ma100, created_at, sent_at, status
                FROM alerts
                WHERE created_at > NOW() - INTERVAL :days DAY
                ORDER BY created_at DESC
            """
            
            df = pd.read_sql(text(query), conn, params={"days": days})
            logger.info(f"Retrieved {len(df)} recent alerts")
            return df.to_dict(orient='records')
    except Exception as e:
        logger.error(f"Error getting alerts: {str(e)}")
        return []

# Get backtest results
def get_backtest_results(symbol=None, limit=10):
    try:
        url = f"http://backtester:8004/results?limit={limit}"
        if symbol:
            url += f"&symbol={symbol}"
            
        logger.info(f"Requesting backtest results from: {url}")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            results = response.json().get('results', [])
            logger.info(f"Retrieved {len(results)} backtest results")
            return results
        else:
            logger.error(f"Failed to get backtest results: HTTP {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error getting backtest results: {str(e)}")
        return []

# Get system health data
def get_system_health():
    engine = get_db_connection()
    try:
        with engine.connect() as conn:
            query = """
                SELECT component, status, last_check, details
                FROM system_health
                WHERE last_check > NOW() - INTERVAL '1 day'
                ORDER BY last_check DESC
            """
            
            df = pd.read_sql(text(query), conn)
            
            # Get latest status for each component
            components = {}
            for _, row in df.iterrows():
                if row['component'] not in components:
                    components[row['component']] = {
                        'status': row['status'],
                        'last_check': row['last_check'],
                        'details': row['details']
                    }
            
            logger.info(f"Retrieved health status for {len(components)} components")
            return list(components.items())
    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        return []

# Routes
@app.get("/")
async def home(request: Request):
    symbols = get_symbols()
    logger.info(f"Rendering home page with {len(symbols)} symbols")
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "symbols": symbols}
    )

@app.get("/backtest")
async def backtest_page(request: Request):
    symbols = get_symbols()
    logger.info(f"Rendering backtest page with {len(symbols)} symbols")
    return templates.TemplateResponse(
        "backtest.html", 
        {"request": request, "symbols": symbols}
    )

@app.post("/run_backtest")
async def run_backtest(
    symbol: str = Form(...),
    strategy: str = Form(...),
    short_ma: int = Form(50),
    long_ma: int = Form(100),
    initial_capital: float = Form(10000.0),
    start_date: str = Form(...),
    end_date: str = Form(...)
):
    try:
        # Create request to backtester service
        data = {
            "symbol": symbol,
            "strategy": strategy,
            "parameters": {
                "short_ma": short_ma,
                "long_ma": long_ma,
                "initial_capital": initial_capital,
                "start_date": start_date,
                "end_date": end_date
            }
        }
        
        logger.info(f"Running backtest for {symbol} from {start_date} to {end_date}")
        response = requests.post(
            "http://backtester:8004/backtest",
            json=data,
            timeout=60
        )
        
        if response.status_code == 200:
            logger.info(f"Backtest completed successfully for {symbol}")
            # Redirect to backtest results page
            return RedirectResponse(url="/backtest?success=true", status_code=303)
        else:
            error = response.json().get("detail", "Unknown error")
            logger.error(f"Backtest failed: {error}")
            return RedirectResponse(
                url=f"/backtest?error={error}&symbol={symbol}", 
                status_code=303
            )
            
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        return RedirectResponse(
            url=f"/backtest?error={str(e)}&symbol={symbol}", 
            status_code=303
        )

@app.get("/api/symbols")
async def api_symbols():
    symbols = get_symbols()
    return {"symbols": symbols}

@app.get("/api/stock/{symbol}")
async def api_stock_data(symbol: str, days: int = 30):
    df = get_stock_data(symbol, days)
    
    if df.empty:
        logger.warning(f"No data found for symbol {symbol}")
        return JSONResponse(
            status_code=404,
            content={"message": f"No data found for symbol {symbol}"}
        )
    
    # Convert to records for JSON serialization
    result = {
        "symbol": symbol,
        "data": []
    }
    
    for _, row in df.iterrows():
        result["data"].append({
            "timestamp": row["timestamp"].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
            "ma50": float(row["ma50"]) if not pd.isna(row["ma50"]) else None,
            "ma100": float(row["ma100"]) if not pd.isna(row["ma100"]) else None
        })
    
    return result

@app.get("/api/alerts")
async def api_alerts(days: int = 7):
    alerts = get_recent_alerts(days)
    return {"alerts": alerts}

@app.get("/api/backtests")
async def api_backtests(symbol: str = None):
    results = get_backtest_results(symbol)
    return {"results": results}

@app.get("/api/backtest/equity_curve")
async def api_equity_curve(symbol: str, start_date: str, end_date: str = None,
                          short_ma: int = 50, long_ma: int = 100, initial_capital: float = 10000.0):
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        
    try:
        logger.info(f"Getting equity curve for {symbol} from {start_date} to {end_date}")
        response = requests.get(
            f"http://backtester:8004/equity_curve?symbol={symbol}&start_date={start_date}&end_date={end_date}"
            f"&short_ma={short_ma}&long_ma={long_ma}&initial_capital={initial_capital}",
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            error = response.json().get("detail", "Unknown error")
            logger.error(f"Error getting equity curve: {error}")
            return JSONResponse(
                status_code=400,
                content={"error": error}
            )
    except Exception as e:
        logger.error(f"Exception when getting equity curve: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/api/health")
async def api_health():
    health_data = get_system_health()
    
    # Overall system status
    overall_status = "OK"
    for component, data in health_data:
        if data["status"] != "OK":
            overall_status = "ERROR"
            break
    
    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "components": dict(health_data)
    }

# Healthcheck endpoint
@app.get("/healthcheck")
async def healthcheck():
    try:
        # Check database connection
        engine = get_db_connection()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        logger.info("Healthcheck passed")
        return {"status": "OK", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Healthcheck failed: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

# Add data seed endpoint for emergency cases
@app.get("/api/seed_test_data")
async def seed_test_data():
    try:
        engine = get_db_connection()
        with engine.connect() as conn:
            # Insert some test data for PKO
            for i in range(100):
                date = (datetime.now() - timedelta(days=100-i)).strftime('%Y-%m-%d')
                # Generate some fake price data that looks like a trend
                base_price = 40.0 + i * 0.1 + (i % 7) * 0.2
                conn.execute(
                    text("""
                        INSERT INTO historical_stock_prices 
                        (symbol, timestamp, open, high, low, close, volume)
                        VALUES (:symbol, :timestamp, :open, :high, :low, :close, :volume)
                        ON CONFLICT (symbol, timestamp) DO NOTHING
                    """),
                    {
                        "symbol": "PKO",
                        "timestamp": date,
                        "open": base_price,
                        "high": base_price + 0.5,
                        "low": base_price - 0.3,
                        "close": base_price + 0.1,
                        "volume": 1000000 + (i * 10000)
                    }
                )
            conn.commit()
            
        logger.info("Seeded test data for PKO")
        return {"status": "OK", "message": "Test data has been seeded for PKO"}
    except Exception as e:
        logger.error(f"Error seeding test data: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "ERROR", "error": str(e)}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)