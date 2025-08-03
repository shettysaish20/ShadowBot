#!/bin/bash
INSTANCE_ID="i-0d9954ca7c78fcbef"

echo "🚀 Starting EC2 instance..."
aws ec2 start-instances --instance-ids $INSTANCE_ID
echo "⏳ Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID
echo "✅ Instance started!"