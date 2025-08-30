#!/bin/bash

# Description: This script monitors disk space usage and sends alerts when thresholds are exceeded.
# Author: CoderAgent
# Date: October 26, 2023

# Configuration section
THRESHOLD_WARNING=80  # Warning threshold (percentage)
THRESHOLD_CRITICAL=95 # Critical threshold (percentage)
RECIPIENT_EMAIL="[email protected]" # Email address to send alerts to
LOG_FILE="/var/log/disk_space_monitor.log" # Log file location

# Function to send email alert
send_alert() {
  SUBJECT="Disk Space Alert: $(hostname) - $1"
  BODY="Disk: $2\nUsage: $3%\nThreshold: $1"
  echo "$BODY" | mail -s "$SUBJECT" "$RECIPIENT_EMAIL"
  echo "$(date) - ALERT: $SUBJECT - $BODY" >> "$LOG_FILE"
}

# Function to check disk space
check_disk_space() {
  df -h | grep -vE '^Filesystem|tmpfs|cdrom' | awk '{print $5 " " $6}' | while read -r usage mount_point; do
    usage_percent=$(echo $usage | sed 's/%//g')

    if [[ "$usage_percent" -ge "$THRESHOLD_CRITICAL" ]]; then
      send_alert "Critical" "$mount_point" "$usage_percent"
    elif [[ "$usage_percent" -ge "$THRESHOLD_WARNING" ]]; then
      send_alert "Warning" "$mount_point" "$usage_percent"
    fi
  done
}

# Main script logic
check_disk_space

# Log the execution
echo "$(date) - Disk space check completed." >> "$LOG_FILE"

# Error handling: Check if df command failed
if [ $? -ne 0 ]; then
  echo "$(date) - ERROR: df command failed. Please check the system." >> "$LOG_FILE"
  exit 1
fi

exit 0

# To run this script in the background, you can use either '&' or 'nohup'.
# Using '&':
#   ./disk_space_monitor.sh &
# This will run the script in the background.  However, if you close the terminal, the script will be terminated.

# Using 'nohup':
#   nohup ./disk_space_monitor.sh > /dev/null 2>&1 &
# This is the recommended approach. 'nohup' ensures that the script continues to run even after you close the terminal.
# The '> /dev/null 2>&1' redirects both standard output and standard error to /dev/null, so you won't see any output in the terminal.

# To schedule this script to run periodically, you can use 'cron'.
# To edit the cron table, run 'crontab -e'.  Add a line like this to run the script every 10 minutes:
# */10 * * * * /path/to/disk_space_monitor.sh


# Make sure the script is executable:
# chmod +x disk_space_monitor.sh