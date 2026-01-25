import logging
from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.analytics_service import AnalyticsService
from app.services.user_service import UserService
import matplotlib.pyplot as plt
import io
import uuid

logger = logging.getLogger(__name__)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} requested stats.")
    
    # Optional: get days from args
    days = 30
    if context.args and context.args[0].isdigit():
        days = int(context.args[0])

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id)
        
        analytics_service = AnalyticsService(session)
        stats = await analytics_service.get_networking_stats(db_user.id, days=days)
        
        if stats["total_new_contacts"] == 0:
            await update.message.reply_text(f"За последние {days} дней новых контактов не найдено.")
            return

        # Format Text Report
        text = f"📊 *Нетворкинг: Последние {days} дней*\n\n"
        text += f"🆕 Новых контактов: {stats['total_new_contacts']}\n"
        
        if stats["by_event"]:
            text += "\n📍 *По мероприятиям:*\n"
            for event, count in stats["by_event"].items():
                text += f"• {event}: {count}\n"
        
        funnel = stats["funnel"]
        text += f"\n🛤 *Воронка:*\n"
        text += f"├── Контакты: {funnel['contacts']}\n"
        text += f"├── Follow-up отправлен: {funnel['follow_ups']}\n"
        text += f"├── Ответы получены: {funnel['responses']}\n"
        text += f"└── Встречи: {funnel['meetings']}\n"
        
        if stats["by_role"]:
            text += "\n👤 *Топ ролей:*\n"
            for role, count in stats["by_role"].items():
                text += f"• {role}: {count}\n"

        # Inactive contacts
        inactive = await analytics_service.get_inactive_contacts(db_user.id, days=14)
        if inactive:
            text += f"\n💡 *Инсайт:* Есть {len(inactive)} контактов, с которыми ты давно не общался. /find заброшенные"

        await update.message.reply_text(text, parse_mode="Markdown")

        # Visualization (Pie Chart for events)
        if stats["by_event"] and len(stats["by_event"]) > 1:
             try:
                 plt.figure(figsize=(8, 6))
                 labels = list(stats["by_event"].keys())
                 sizes = list(stats["by_event"].values())
                 plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
                 plt.title(f"Распределение по ивентам ({days} дней)")
                 
                 buf = io.BytesIO()
                 plt.savefig(buf, format='png')
                 buf.seek(0)
                 plt.close()
                 
                 await update.message.reply_photo(photo=buf)
             except Exception as e:
                 logger.error(f"Error generating chart: {e}")
