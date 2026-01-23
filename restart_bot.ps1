# Quick restart script for the bot (PowerShell)

Write-Host "🔄 Restarting bot container..." -ForegroundColor Yellow
docker-compose restart bot

Write-Host "`n📋 Showing last 30 lines of logs..." -ForegroundColor Cyan
docker-compose logs --tail=30 bot

Write-Host "`n✅ Bot restarted. Use 'docker-compose logs -f bot' to follow logs." -ForegroundColor Green
