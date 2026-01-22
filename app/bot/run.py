import logging
from app.bot.main import create_bot

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    bot = create_bot()
    if bot:
        print("Starting Bot Polling...")
        bot.run_polling()
    else:
        print("Bot creation failed.")

if __name__ == '__main__':
    main()
