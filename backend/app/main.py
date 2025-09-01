"""
This is the main FastAPI application file, which orchestrates the API,
database connections, and data processing modules.
"""

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse, Response

from app.routers import auth_router
from app.routers import entities_router as entities_router
from app.routers import navigation_router as navigation_router
from app.services.file_watcher import FileWatcherService
from app.storage.database import Database
from app.utils.auth_utils import load_cern_endpoints
from app.utils.config_utils import get_config
from app.utils.gclql_query_parser_utils import QueryParser
from app.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)
config = get_config()

database = Database()
query_parser = QueryParser(database=database)
file_watcher = FileWatcherService(database=database)


@asynccontextmanager
async def lifespan(_: FastAPI) -> Any:
    """Handles application startup and shutdown events."""
    setup_logging()

    # Run startup tasks sequentially for better reliability
    await database.setup(config)

    # Only load CERN endpoints if authentication is enabled
    if config.get("auth.enabled", True):
        logger.info("Authentication is enabled, loading CERN endpoints...")
        await load_cern_endpoints()
    else:
        logger.info("Authentication is disabled, skipping CERN endpoint loading")

    # Query parser setup depends on database being ready
    await query_parser.setup()

    # Start file watcher service
    await file_watcher.start()

    yield

    # Cleanup during shutdown
    await file_watcher.stop()
    await database.aclose()


app = FastAPI(
    title="Universal Metadata Browser API",
    description="API for querying and managing metadata entities.",
    lifespan=lifespan,
)


# Only add session middleware if auth is enabled
if config.get("auth.enabled", True):
    secret_key = config.get("general.application_secret_key")
    if not secret_key:
        logger.warning(
            "Auth is enabled but no secret key provided - session middleware disabled"
        )
    else:
        app.add_middleware(
            SessionMiddleware,
            secret_key=secret_key,
            https_only=config.get("general.https_only").lower() == "true",
            same_site="lax",
            max_age=3600,
            session_cookie=config.get(
                "general.cookie_prefix", "universal-metadata-browser"
            ),
            domain=None,  # Allow cookies to work on localhost and other domains
        )
        logger.info("Session middleware enabled")
else:
    logger.info("Session middleware disabled - auth is disabled")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.get("general.frontend_url")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware to log incoming requests."""
    try:
        response = await call_next(request)

        # Log the request after successful processing
        logger.info(
            f"[{response.status_code}] {request.method} {request.url.path} - {request.query_params}"
            if request.query_params
            else f"[{response.status_code}] {request.method} {request.url.path}"
        )

        return response
    except Exception as e:
        logger.error(f"Middleware error for {request.method} {request.url.path}: {e}")
        raise


@app.exception_handler(Exception)
async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch all unhandled exceptions and return a standardized 500 response."""
    logger.error(
        f"Unhandled exception for {request.method} {request.url}", exc_info=True
    )

    # Create standardized error response
    error_response = {
        "message": "An internal server error occurred. Please try again later.",
        "status": 500,
        "details": {
            "error": "internal_error",
            "message": f"Unhandled exception: {str(exc)}",
        },
    }

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response,
    )


# Initialize router dependencies
auth_router.init_dependencies(database)
entities_router.init_dependencies(database, query_parser)
navigation_router.init_dependencies(database)

# Include routers
app.include_router(auth_router.router)
app.include_router(entities_router.router)
app.include_router(navigation_router.router)


# Powered by friendship!
#                                                     /
#                                                   .7
#                                        \       , //
#                                        |\.--._/|//
#                                       /\ ) ) ).'/
#                                      /(  \  // /
#                                     /(   J`((_/ \
#                                    / ) | _\     /
#                                   /|)  \  eJ    L
#                                  |  \ L \   L   L
#                                 /  \  J  `. J   L
#                                 |  )   L   \/   \
#                                /  \    J   (\   /
#              _....___         |  \      \   \```
#       ,.._.-'        '''--...-||\     -. \   \
#     .'.=.'                    `         `.\ [ Y
#    /   /                                  \]  J
#   Y / Y                                    Y   L
#   | | |          \                         |   L
#   | | |           Y                        A  J
#   |   I           |                       /I\ /
#   |    \          I             \        ( |]/|
#   J     \         /._           /        -tI/ |
#    L     )       /   /'-------'J           `'-:.
#    J   .'      ,'  ,' ,     \   `'-.__          \
#     \ T      ,'  ,'   )\    /|        ';'---7   /
#      \|    ,'L  Y...-' / _.' /         \   /   /
#       J   Y  |  J    .'-'   /         ,--.(   /
#        L  |  J   L -'     .'         /  |    /\
#        |  J.  L  J     .-;.-/       |    \ .' /
#        J   L`-J   L____,.-'`        |  _.-'   |
#         L  J   L  J                  ``  J    |
#         J   L  |   L                     J    |
#          L  J  L    \                    L    \
#          |   L  ) _.'\                    ) _.'\
#          L    \('`    \                  ('`    \
#           ) _.'\`-....'                   `-....'
#          ('`    \
#           `-.___/   sk
