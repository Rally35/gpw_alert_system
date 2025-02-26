import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import create_engine, text
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('alert_system')

# Database connection
def get_db_connection():
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_user = os.environ.get('DB_USER', 'user')
    db_password = os.environ.get('DB_PASSWORD', 'password')
    db_name = os.environ.get('DB_NAME', 'stocks')
    
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"
    return create_engine(connection_string)

# Get pending alerts
def get_pending_alerts(engine):
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, symbol, strategy, signal_type, price, 
                           volume, ma50, ma100, created_at
                    FROM alerts
                    WHERE status = 'PENDING'
                    ORDER BY created_at
                """)
            )
            
            alerts = []
            for row in result:
                alerts.append({
                    "id": row.id,
                    "symbol": row.symbol,
                    "strategy": row.strategy,
                    "signal_type": row.signal_type,
                    "price": row.price,
                    "volume": row.volume,
                    "ma50": row.ma50,
                    "ma100": row.ma100,
                    "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })
            
            return alerts
    except Exception as e:
        logger.error(f"Error getting pending alerts: {str(e)}")
        return []

# Mark alert as sent
def mark_alert_sent(engine, alert_id):
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE alerts
                    SET status = 'SENT', sent_at = NOW()
                    WHERE id = :alert_id
                """),
                {"alert_id": alert_id}
            )
            conn.commit()
            logger.info(f"Marked alert {alert_id} as sent")
    except Exception as e:
        logger.error(f"Error marking alert as sent: {str(e)}")

# Send email
def send_email(alerts, recipients):
    if not alerts:
        logger.info("No alerts to send")
        return
    
    try:
        email_host = os.environ.get('EMAIL_HOST')
        email_port = int(os.environ.get('EMAIL_PORT', 587))
        email_user = os.environ.get('EMAIL_USER')
        email_password = os.environ.get('EMAIL_PASSWORD')
        
        if not all([email_host, email_user, email_password]):
            logger.error("Email configuration missing")
            return
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"GPW Alert System: {len(alerts)} New Trading Signals"
        
        # Create email body
        body = f"""
        <html>
        <head>
            <style>
                table {{
                    border-collapse: collapse;
                    width: 100%;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                .buy {{
                    color: green;
                    font-weight: bold;
                }}
                .sell {{
                    color: red;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <h2>GPW Trading Signals</h2>
            <p>The following trading signals have been generated:</p>
            
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Signal</th>
                    <th>Strategy</th>
                    <th>Price</th>
                    <th>MA50</th>
                    <th>MA100</th>
                    <th>Volume</th>
                    <th>Time</th>
                </tr>
        """
        
        for alert in alerts:
            signal_class = "buy" if alert["signal_type"] == "BUY" else "sell"
            body += f"""
                <tr>
                    <td>{alert["symbol"]}</td>
                    <td class="{signal_class}">{alert["signal_type"]}</td>
                    <td>{alert["strategy"]}</td>
                    <td>{alert["price"]:.2f}</td>
                    <td>{alert["ma50"]:.2f}</td>
                    <td>{alert["ma100"]:.2f}</td>
                    <td>{alert["volume"]}</td>
                    <td>{alert["created_at"]}</td>
                </tr>
            """
        
        body += """
            </table>
            
            <p>This is an automated message from the GPW Alert System.</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Send email
        with smtplib.SMTP(email_host, email_port) as server:
            server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
        
        logger.info(f"Email sent to {len(recipients)} recipients with {len(alerts)} alerts")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        return False

# Get email recipients
def get_recipients():
    # In a real system, this would come from a database or config file
    recipients_env = os.environ.get('EMAIL_RECIPIENTS', '')
    if recipients_env:
        return [email.strip() for email in recipients_env.split(',')]
    else:
        # Default recipient for testing
        return ['admin@example.com']

# Record health status
def update_health_status(engine, status, details=None):
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO system_health (component, status, details)
                    VALUES (:component, :status, :details)
                """),
                {
                    "component": "alert_system",
                    "status": status,
                    "details": details
                }
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to update health status: {str(e)}")

# Main function
def main():
    logger.info("Starting alert system")
    
    try:
        # Get database connection
        engine = get_db_connection()
        
        # Get pending alerts
        alerts = get_pending_alerts(engine)
        
        if not alerts:
            logger.info("No pending alerts")
            update_health_status(engine, "OK", "No pending alerts")
            return
        
        logger.info(f"Found {len(alerts)} pending alerts")
        
        # Get recipients
        recipients = get_recipients()
        
        if not recipients:
            logger.error("No recipients configured")
            update_health_status(engine, "ERROR", "No recipients configured")
            return
        
        # Send email
        if send_email(alerts, recipients):
            # Mark alerts as sent
            for alert in alerts:
                mark_alert_sent(engine, alert["id"])
            
            update_health_status(engine, "OK", f"Sent {len(alerts)} alerts")
        else:
            update_health_status(engine, "ERROR", "Failed to send alerts")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        try:
            update_health_status(engine, "ERROR", str(e))
        except:
            pass

if __name__ == "__main__":
    main()