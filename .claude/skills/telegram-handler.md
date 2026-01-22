# Telegram Handler

Создает bot handler с middlewares.

## Usage
`/telegram-handler <тип> <описание>`

Типы: command, message, callback, voice, contact

## Instructions

1. **Handler** в `bot/handlers/`:
   ```python
   @require_user
   @log_handler
   @rate_limit
   async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
       try:
           user = context.user_data['db_user']
           db = context.user_data['db']

           service = Service(db)
           result = await service.method()

           await update.message.reply_text("...")
       except Exception as e:
           await handle_service_error(update, e)
   ```

2. **Keyboard** (если нужна) в `bot/keyboards/`

3. **Register** в `bot/main.py`:
   ```python
   app.add_handler(CommandHandler("cmd", handler))
   ```

4. **Test** в `tests/integration/handlers/`
