import sys
import os

# Add project root to sys.path to allow running this script directly
# We use insert(0) to prioritize local code over installed packages (critical for Docker dev with volumes)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import logging
from app.bot.main import create_bot

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
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
