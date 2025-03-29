from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import logging
import os
from datetime import datetime, timedelta
import backtest

# Create logs directory if it doesn't exist
os.makedirs("/app/logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/backtester_api.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('backtester_api')

app = FastAPI(title="Stock Strategy Backtester API")

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str
    parameters: Optional[Dict[str, Any]] = None

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "OK", "timestamp": datetime.now().isoformat()}

@app.post("/backtest")
async def run_backtest(request: BacktestRequest):
    """Run a backtest for a specific symbol and strategy"""
    try:
        results = backtest.run_backtest(
            request.symbol,
            request.strategy,
            request.parameters
        )

        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])

        return results
    except Exception as e:
        logger.error(f"Error in backtest endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/results")
async def get_results(symbol: Optional[str] = None, limit: int = 10):
    """Get backtest results for a specific symbol or all symbols"""
    try:
        results = backtest.get_backtest_results(symbol, limit)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in results endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/equity_curve")
async def get_equity_curve(
    symbol: str,
    start_date: str,
    end_date: Optional[str] = None,
    strategy: str = "moving_average",
    short_ma: int = 50,
    long_ma: int = 100,
    initial_capital: float = 10000.0
):
    """Get equity curve data for a specific backtest configuration"""
    try:
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        params = {
            "short_ma": short_ma,
            "long_ma": long_ma,
            "initial_capital": initial_capital
        }

        results = backtest.get_backtest_equity_curve(
            symbol,
            start_date,
            end_date,
            strategy,
            params
        )

        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])

        return results
    except Exception as e:
        logger.error(f"Error in equity_curve endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
