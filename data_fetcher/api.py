from fastapi import FastAPI
import uvicorn
from datetime import datetime
import main as fetcher

app = FastAPI()

@app.get("/fetch")
async def fetch_data():
    """Trigger data fetching process"""
    try:
        fetcher.main()
        return {"status": "success", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "OK", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)