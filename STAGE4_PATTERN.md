# Stage 4: Modular Architecture Pattern

## Overview

Stage 4 introduces a handler registration pattern to make the codebase more maintainable and extensible.

## Implementation Pattern

### 1. Add `register_handlers()` to Each Handler Module

Each handler module should export a `register_handlers(app: Application)` function that registers its handlers:

```python
# Example: app/bot/handlers/example_handlers.py
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

async def my_command(update, context):
    # Handler implementation
    pass

async def my_callback(update, context):
    # Callback implementation
    pass

def register_handlers(app: Application):
    """Register example handlers."""
    app.add_handler(CommandHandler("example", my_command))
    app.add_handler(CallbackQueryHandler(my_callback, pattern="^example_"))
```

### 2. Registration Module

The `app/bot/registration.py` module centralizes handler registration:

```python
def register_all_handlers(app: Application):
    """Register all bot handlers."""
    from app.bot.handlers import info_handlers, profile_handlers, contact_handlers

    info_handlers.register_handlers(app)
    profile_handlers.register_handlers(app)
    contact_handlers.register_handlers(app)
    # ... etc
```

### 3. Simplified main.py

The `create_bot()` function in `main.py` becomes much simpler:

```python
def create_bot():
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register all handlers using the modular pattern
    from app.bot.registration import register_all_handlers
    register_all_handlers(app)

    return app
```

## Benefits

1. **Separation of Concerns**: Each handler module is self-contained
2. **Easy Extension**: Adding new features only requires modifying the relevant module
3. **Maintainability**: No more giant main.py with hundreds of lines of registration
4. **Testability**: Each module can be tested independently

## Completed Examples

- ✅ `info_handlers.py` - Implements `register_handlers()` pattern

## TODO: Apply Pattern to Remaining Modules

The following modules need `register_handlers()` functions added:

- [ ] analytics_handlers.py
- [ ] assets_handler.py
- [ ] card_handlers.py
- [ ] contact_detail_handlers.py
- [ ] contact_handlers.py
- [ ] credentials_handlers.py
- [ ] event_handlers.py
- [ ] integration_handlers.py
- [ ] match_handlers.py
- [ ] menu_handlers.py
- [ ] osint_handlers.py
- [ ] profile_handlers.py
- [ ] prompt_handlers.py
- [ ] reminder_handlers.py
- [ ] search_handlers.py

## Migration Notes

For complex handlers with ConversationHandlers, the pattern looks like:

```python
def register_handlers(app: Application):
    """Register handlers with conversations."""
    # Create conversation handler
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler)],
        states={
            STATE1: [MessageHandler(filters.TEXT, handle_state1)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv)

    # Register other handlers
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^pattern_"))
```

## Current Implementation Status

**Completed**: Stages 1-3 + Stage 4 foundation
- Stage 1: File structure unified ✅
- Stage 2: View layer extracted ✅
- Stage 3: Infrastructure and services refactored ✅
- Stage 4: Registration pattern demonstrated ✅ (partial)

**Next Steps**: Apply `register_handlers()` pattern to all remaining modules and simplify main.py completely.
