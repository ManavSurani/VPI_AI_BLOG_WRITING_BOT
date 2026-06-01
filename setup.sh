#!/bin/bash

echo "========================================="
echo "  VN Code Pro Blog Bot — Setup Script    "
echo "========================================="
echo ""

# 1. Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

# 2. Create and activate virtual environment
echo "⏳ Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 3. Install packages
echo "⏳ Installing required packages..."
pip install -r requirements.txt -q
echo "✅ Packages installed successfully."

# 4. Process .env file for Run Times
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found. Please create it first."
    exit 1
fi

echo "⏳ Setting up automated schedule (cron)..."

# Remove any old blog-bot cron jobs (clean slate)
crontab -l | grep -v "/var/www/blog-bot/main.py" | crontab -

CRON_ADDED=0

# Extract all RUN_TIME_* variables and add them to cron
while IFS='=' read -r key value; do
    if [[ $key == RUN_TIME_* && -n $value && ! $key == \#* ]]; then
        # value is HH:MM in IST
        IST_HOUR=$(echo "$value" | cut -d':' -f1)
        IST_MIN=$(echo "$value" | cut -d':' -f2)
        
        # Convert IST to UTC (subtract 5 hours 30 mins)
        UTC_MIN=$((10#$IST_MIN - 30))
        UTC_HOUR=$((10#$IST_HOUR - 5))
        
        if [ $UTC_MIN -lt 0 ]; then
            UTC_MIN=$((UTC_MIN + 60))
            UTC_HOUR=$((UTC_HOUR - 1))
        fi
        
        if [ $UTC_HOUR -lt 0 ]; then
            UTC_HOUR=$((UTC_HOUR + 24))
        fi
        
        # Format for crontab
        CRON_CMD="$UTC_MIN $UTC_HOUR * * * /var/www/blog-bot/venv/bin/python /var/www/blog-bot/main.py >> /var/www/blog-bot/cron.log 2>&1"
        
        # Add to crontab
        (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
        
        echo "   → ⏰ Scheduled at $value IST (runs as $UTC_HOUR:$UTC_MIN UTC)"
        CRON_ADDED=$((CRON_ADDED + 1))
    fi
done < ".env"

echo ""
if [ $CRON_ADDED -gt 0 ]; then
    echo "✅ Setup complete! $CRON_ADDED automated run(s) scheduled."
    echo "   Bot will now run automatically. No further action needed."
else
    echo "⚠️  Setup finished, but NO RUN_TIME entries found in .env."
    echo "   Bot will not run automatically until you add them."
fi
echo "========================================="
