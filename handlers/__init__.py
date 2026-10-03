"""Barcha handlerlarni bitta routerga yig'ish. Har bir bot (dispatcher) uchun yangi router yaratiladi."""
from aiogram import Router

from .admin import create_admin_router
from .admin_series import create_series_admin_router
from .common import create_common_router
from .logos import create_logos_router
from .secret import create_secret_router
from .user import create_user_router


def build_router(is_main: bool) -> Router:
    root = Router()
    root.include_router(create_common_router())
    if is_main:
        root.include_router(create_secret_router())  # /shahriboi faqat asosiy botda
    root.include_router(create_admin_router(is_main))
    root.include_router(create_series_admin_router())
    root.include_router(create_logos_router())
    root.include_router(create_user_router())
    return root
