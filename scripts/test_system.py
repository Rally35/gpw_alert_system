#!/usr/bin/env python3
import requests
import time
import json
import sys

# Base URLs
DATA_FETCHER_URL = "http://localhost:8001"
STRATEGY_URL = "http://localhost:8002"
ALERT_URL = "http://localhost:8003"
DASHBOARD_URL = "http://localhost:8000"
BACKTESTER_URL = "http://localhost:8004"

def check_service(name, url, endpoint="/health"):
    """Check if a service is running"""
    try:
        response = requests.get(f"{url}{endpoint}", timeout=5)
        if response.status_code == 200:
            print(f"✅ {name} is running")
            return True
        else:
            print(f"❌ {name} failed: Status code {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ {name} is not accessible: {str(e)}")
        return False

def test_data_flow():
    """Test the full data flow through the system"""
    # Step 1: Trigger data fetching
    print("\n🔍 Testing data flow...")
    print("Step 1: Fetching data...")
    try:
        response = requests.get(f"{DATA_FETCHER_URL}/fetch", timeout=60)
        if response.status_code == 200:
            print("✅ Data fetching successful")
        else:
            print(f"❌ Data fetching failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Data fetching request failed: {str(e)}")
        return False
    
    # Wait for processing
    print("Waiting for data processing...")
    time.sleep(5)
    
    # Step 2: Trigger strategy analysis
    print("Step 2: Running strategy analysis...")
    try:
        response = requests.get(f"{STRATEGY_URL}/analyze", timeout=60)
        if response.status_code == 200:
            print("✅ Strategy analysis successful")
        else:
            print(f"❌ Strategy analysis failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Strategy analysis request failed: {str(e)}")
        return False
    
    # Wait for processing
    print("Waiting for analysis processing...")
    time.sleep(5)
    
    # Step 3: Check for generated alerts
    print("Step 3: Checking for alerts...")
    try:
        response = requests.get(f"{DASHBOARD_URL}/api/alerts", timeout=10)
        if response.status_code == 200:
            alerts = response.json().get("alerts", [])
            if alerts:
                print(f"✅ Found {len(alerts)} alerts in the system")
            else:
                print("ℹ️ No alerts found, but API is working")
        else:
            print(f"❌ Alerts API failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Alerts API request failed: {str(e)}")
        return False
    
    print("\n✅ System data flow test completed successfully!")
    return True

def test_backtest_function():
    """Test backtest functionality"""
    print("\n🔍 Testing backtesting functionality...")
    try:
        test_data = {
            "symbol": "PKO",
            "strategy": "moving_average",
            "parameters": {
                "short_ma": 50,
                "long_ma": 100,
                "initial_capital": 10000.0,
                "start_date": "2020-01-01",
                "end_date": "2021-01-01"
            }
        }
        
        response = requests.post(f"{BACKTESTER_URL}/backtest", json=test_data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if "total_return" in result:
                print(f"✅ Backtest executed successfully, return: {result['total_return']:.2f}%")
                return True
            else:
                print(f"❌ Backtest response missing expected data")
                return False
        else:
            print(f"❌ Backtest request failed: {response.status_code}")
            error_details = response.json().get("detail", "Unknown error")
            print(f"   Error details: {error_details}")
            return False
    except Exception as e:
        print(f"❌ Backtest test failed: {str(e)}")
        return False

def main():
    """Main test function"""
    print("🔍 GPW Alert System Test")
    print("========================\n")
    
    # Check if all services are running
    services_ok = True
    services_ok &= check_service("Data Fetcher", DATA_FETCHER_URL)
    services_ok &= check_service("Strategy Analyzer", STRATEGY_URL)
    services_ok &= check_service("Alert System", ALERT_URL)
    services_ok &= check_service("Backtester", BACKTESTER_URL)
    services_ok &= check_service("Dashboard", DASHBOARD_URL)
    
    if not services_ok:
        print("\n❌ Not all services are running. Please check Docker containers.")
        sys.exit(1)
    
    # Test the data flow
    flow_ok = test_data_flow()
    
    # Test backtesting
    backtest_ok = test_backtest_function()
    
    if flow_ok and backtest_ok:
        print("\n✅ All tests passed! System is working correctly.")
    else:
        print("\n❌ Some tests failed. Check logs for more details.")
        sys.exit(1)

if __name__ == "__main__":
    main()