#!/bin/bash

# Script Name: disk_monitor.sh
# Description: This script monitors disk space and sends an alert if it falls below a certain threshold.

# Define the disk space threshold (in percentage).  Alert will be triggered if disk usage exceeds this.
THRESHOLD=90

# Define the log file.
LOG_FILE="/var/log/disk_monitor.log"

# Function to check disk space usage.
check_disk_space() {
  # Get the disk usage percentage.
  usage=$(df -h / | awk 'NR==2{print $5}' | tr -d '%')

  # Log the current disk usage.
  echo "$(date): Disk usage is $usage%" >> $LOG_FILE

  # Check if the disk usage is above the threshold.
  if (( $(echo "$usage > $THRESHOLD" | bc -l) )); then
    alert_user "Disk space is above $THRESHOLD% ($usage%)."
  fi
}

# Function to send an alert to the user.
alert_user() {
  message="$1"
  subject="Disk Space Alert"
  recipient="root"  # Change this to the desired recipient.

  echo "$message" | mail -s "$subject" "$recipient"
  echo "$(date): ALERT: $message" >> $LOG_FILE
}

# Main function to run the disk space check.
main() {
  check_disk_space
}

# Run the main function.
main

# Make the script executable
# chmod +x disk_monitor.sh

# To run automatically, add it to cron using crontab -e
# Example: Add the following line to run every 5 minutes
# */5 * * * * /path/to/disk_monitor.sh
