#!/bin/bash
INSTANCE_ID="i-0d9954ca7c78fcbef"

echo "🛑 Stopping EC2 instance..."
aws ec2 stop-instances --instance-ids $INSTANCE_ID
echo "💰 Instance stopped - you're only paying for storage now!"