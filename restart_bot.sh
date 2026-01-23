#!/bin/bash
# Quick restart script for the bot

echo "🔄 Restarting bot container..."
docker-compose restart bot

echo "📋 Showing last 30 lines of logs..."
docker-compose logs --tail=30 bot

echo ""
echo "✅ Bot restarted. Use 'docker-compose logs -f bot' to follow logs."
