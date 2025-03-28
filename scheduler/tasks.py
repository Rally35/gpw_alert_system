import os
import logging
from celery import Celery
from celery.schedules import crontab
import requests
import time
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('scheduler')

# Setup Celery
redis_host = os.environ.get('REDIS_HOST', 'redis')
app = Celery('tasks', broker=f'redis://{redis_host}:6379/0')

# Database connection
def get_db_connection():
    db_host = os.environ.get('DB_HOST', 'database')
    db_user = os.environ.get('DB_USER', 'user')
    db_password = os.environ.get('DB_PASSWORD', 'password')
    db_name = os.environ.get('DB_NAME', 'stocks')
    
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"
    return create_engine(connection_string)

# Record task execution in database
def record_task_execution(name, status, details=None):
    try:
        engine = get_db_connection()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO system_health 
                    (component, status, details)
                    VALUES (:component, :status, :details)
                """),
                {
                    "component": f"scheduler_{name}",
                    "status": status,
                    "details": details
                }
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to record task execution: {str(e)}")

# Tasks
@app.task
def run_data_fetcher():
    logger.info("Running data_fetcher task")
    try:
        # Call the data_fetcher service
        response = requests.get("http://data_fetcher:8001/fetch", timeout=300)
        
        if response.status_code == 200:
            logger.info("Data fetcher executed successfully")
            record_task_execution("data_fetcher", "OK")
            return True
        else:
            logger.error(f"Data fetcher failed with status: {response.status_code}")
            record_task_execution("data_fetcher", "ERROR", f"Status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error running data_fetcher: {str(e)}")
        record_task_execution("data_fetcher", "ERROR", str(e))
        return False

@app.task
def run_strategy_analyzer():
    logger.info("Running strategy_analyzer task")
    try:
        # Call the strategy_analyzer service
        response = requests.get("http://strategy_analyzer:8002/analyze", timeout=300)
        
        if response.status_code == 200:
            logger.info("Strategy analyzer executed successfully")
            record_task_execution("strategy_analyzer", "OK")
            return True
        else:
            logger.error(f"Strategy analyzer failed with status: {response.status_code}")
            record_task_execution("strategy_analyzer", "ERROR", f"Status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error running strategy_analyzer: {str(e)}")
        record_task_execution("strategy_analyzer", "ERROR", str(e))
        return False

@app.task
def run_alert_system():
    logger.info("Running alert_system task")
    try:
        # Call the alert_system service
        response = requests.get("http://alert_system:8003/send", timeout=300)
        
        if response.status_code == 200:
            logger.info("Alert system executed successfully")
            record_task_execution("alert_system", "OK")
            return True
        else:
            logger.error(f"Alert system failed with status: {response.status_code}")
            record_task_execution("alert_system", "ERROR", f"Status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error running alert_system: {str(e)}")
        record_task_execution("alert_system", "ERROR", str(e))
        return False

# Schedule tasks
app.conf.beat_schedule = {
    'fetch-data-every-4-hours': {
        'task': 'tasks.run_data_fetcher',
        'schedule': crontab(hour='*/4', minute=0),  # Every 4 hours
    },
    'analyze-strategies-hourly': {
        'task': 'tasks.run_strategy_analyzer',
        'schedule': crontab(hour='*/6', minute=0),  # Every 6 hours
    },
    'send-alerts-hourly': {
        'task': 'tasks.run_alert_system',
        'schedule': crontab(hour='*/6', minute=0),  # Every 2 hours
    },
}

# For manual testing
if __name__ == "__main__":
    # Sleep to ensure other services are up
    time.sleep(10)
    
    # Run tasks sequentially
    run_data_fetcher()
    time.sleep(5)
    run_strategy_analyzer()
    time.sleep(5)
    run_alert_system()
