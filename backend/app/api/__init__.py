from .auth import router as auth_router
from .organizations import router as organizations_router
from .projects import router as projects_router
from .users import router as users_router

API_ROUTERS = (auth_router, users_router, organizations_router, projects_router)

__all__ = ["API_ROUTERS"]
