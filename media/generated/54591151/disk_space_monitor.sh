#######################################################################
# Script: disk_space_monitor.sh
# Description: Monitors disk space usage on the root partition (/).
# Sends an email alert if disk usage exceeds 80%.
# Author: CoderAgent
# Date: 2024-01-25
#######################################################################

#!/bin/bash

# Email configuration
EMAIL="admin@example.com"
SUBJECT="Disk Space Alert"

# Get the hostname
HOSTNAME=$(hostname)

# Get the current date and time
DATE=$(date)

# Get the disk space usage percentage for the root partition (/)
DISK_USAGE=$(df -h / | awk 'NR==2{print $5}' | tr -d '%')

# Check if the disk usage exceeds 80%
if [ "$DISK_USAGE" -gt 80 ]; then
    # Create the email body
    EMAIL_BODY="Warning: Disk space usage on ${HOSTNAME} is critical.\n"
    EMAIL_BODY+="Current disk usage: ${DISK_USAGE}%\n"
    EMAIL_BODY+="Date and Time: ${DATE}\n"

    # Send the email using mail command
    echo -e "$EMAIL_BODY" | mail -s "$SUBJECT" "$EMAIL"

    # Alternative: Send the email using sendmail
    # echo -e "Subject: $SUBJECT\n$EMAIL_BODY" | sendmail $EMAIL

    echo "Email alert sent to $EMAIL"
else
    echo "Disk space usage is below 80% ($DISK_USAGE%). No alert sent."
fi

# Exit with success
exit 0
