from bot.handlers.start import router as start_router
from bot.handlers.accounts import router as accounts_router
from bot.handlers.posts import router as posts_router
from bot.handlers.verification import router as verification_router
from bot.handlers.admin import router as admin_router

all_routers = [
    start_router,
    accounts_router,
    verification_router,
    admin_router,
    posts_router,  # Place posts_router last so general text doesn't swallow commands
]
