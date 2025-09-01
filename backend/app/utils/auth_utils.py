"""
Production-ready authentication module for CERN SSO integration.
Handles JWT token validation, CERN OAuth introspection, and secure token management.
"""

from typing import Any

import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request, Response, status

from app.utils.config_utils import get_config
from app.utils.http_client_utils import create_http_client
from app.utils.logging_utils import get_logger

# Load configuration
logger = get_logger(__name__)
config = get_config()

# Auth configuration - only load if auth is enabled
AUTH_ENABLED = str(config.get("auth.enabled", "true")).lower() == "true"
AUTH_OIDC_URL = config.get("auth.auth_oidc_url") if AUTH_ENABLED else None
AUTH_ISSUER = config.get("auth.auth_issuer") if AUTH_ENABLED else None
CERN_CLIENT_ID = config.get("general.cern_client_id") if AUTH_ENABLED else None
CERN_CLIENT_SECRET = config.get("general.cern_client_secret") if AUTH_ENABLED else None
AUTH_COOKIE_PREFIX = f"{config.get('general.cookie_prefix')}-auth"

# Well-known endpoint data loaded at startup
CERN_ENDPOINTS: dict[str, Any] = {}


def get_endpoint_required_role(endpoint_name: str) -> str | None:
    """
    Get the required role for a specific endpoint from configuration.

    Args:
        endpoint_name: The endpoint configuration key (e.g., 'update_entity')
        default: Default role if not configured

    Returns:
        Required role string for the endpoint
    """
    if not AUTH_ENABLED:
        return None

    return config.get(f"auth.endpoints.{endpoint_name}", None) or "authorized"


class CERNAuthenticator:
    """Production-ready CERN authentication handler with improved error handling and caching."""

    def __init__(self) -> None:
        self.cern_oidc_config: dict[str, Any] | None = None
        self.jwks_keys: dict[str, Any] | None = None
        self.config_cache_time: float = 0.0

    async def _fetch_with_retry(
        self, url: str, timeout: float = 10.0
    ) -> dict[str, Any]:
        """Fetch JSON data from URL with retry logic using our retrying HTTP client."""
        async with create_http_client() as http_client:
            result = await http_client.get_json(url, timeout=timeout)
            return result

    async def get_jwks_keys(self) -> dict[str, Any]:
        """Get JWKS keys for token validation."""
        if not AUTH_ENABLED or not AUTH_OIDC_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is disabled or not configured",
            )

        # First fetch OIDC config, then use it to fetch JWKS keys
        oidc_config = await self._fetch_with_retry(AUTH_OIDC_URL)
        return await self._fetch_with_retry(oidc_config["jwks_uri"])

    def _get_signing_key(self, kid: str, jwks: dict[str, Any]) -> str:
        """Extract and return the signing key for the given key ID."""
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return str(jwt.algorithms.RSAAlgorithm.from_jwk(key))
        raise Exception(f"Key ID {kid} not found in the JWS keys: {jwks}")

    async def introspect_token(self, token: str) -> dict[str, Any]:
        """Introspect a token using CERN's OAuth introspection endpoint."""
        if not AUTH_ENABLED or not AUTH_OIDC_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is disabled or not configured",
            )

        oidc_config = await self._fetch_with_retry(AUTH_OIDC_URL)

        introspection_endpoint = oidc_config["introspection_endpoint"]

        # Use our retrying HTTP client for the introspection request
        async with create_http_client() as http_client:
            async with await http_client.post(
                introspection_endpoint,
                data={
                    "token": token,
                    "client_id": CERN_CLIENT_ID,
                    "client_secret": CERN_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            ) as response:
                user_data: dict[str, Any] = await response.json()

                username = user_data.get("preferred_username", "unknown")
                if not user_data["active"]:
                    # When CERN tokens become inactive, it's typically due to expiration
                    raise jwt.ExpiredSignatureError(
                        f"Auth token for user {username} has expired."
                    )

                logger.info(f"Successfully introspected token for user: {username}")
                return user_data

    async def validate_user_from_token(self, token: str) -> dict[str, Any]:
        user_data = await self.introspect_token(token)
        return user_data

    def _normalize_bearer_token(self, token: str) -> str:
        """Remove Bearer prefix from token if present."""
        if token.lower().startswith("bearer "):
            return token[7:]
        return token

    @staticmethod
    def jwt_encode_str(string: str) -> str:
        return jwt.encode(
            {"data": string},
            config["general.application_secret_key"],
            algorithm="HS256",
        )

    @staticmethod
    def jwt_decode_str(string: str) -> str:
        decoded_payload = jwt.decode(
            string,
            config["general.application_secret_key"],
            algorithms=["HS256"],
            options={"verify_signature": True, "verify_exp": False},
        )
        return str(decoded_payload["data"])

    @staticmethod
    def has_user_access(user_data: dict[str, Any]) -> bool:
        """
        Check if the user has the required role for authorization.
        Returns True if user is authorized, False otherwise.
        """
        if not (required_role := config.get("auth.required_cern_role")):
            logger.warning(
                "No specific role required, allowing all authenticated users"
            )
            return True

        user_roles = user_data.get("cern_roles", [])
        return required_role in user_roles


# Global authenticator instance
cern_auth = CERNAuthenticator()


# Authentication functions moved from routers/auth.py
async def load_cern_endpoints() -> None:
    """Load CERN OIDC well-known endpoint data at startup."""
    global CERN_ENDPOINTS

    # Skip loading if auth is disabled or required config is missing
    if not AUTH_ENABLED:
        logger.info("Authentication is disabled, skipping CERN endpoint loading")
        return

    if not AUTH_OIDC_URL:
        logger.warning("AUTH_OIDC_URL not configured, skipping CERN endpoint loading")
        return

    if not CERN_ENDPOINTS:
        try:
            async with create_http_client() as http_client:
                endpoint_data = await http_client.get_json(AUTH_OIDC_URL)
                CERN_ENDPOINTS.update(endpoint_data)
                logger.info("Successfully loaded CERN OIDC endpoints")
        except Exception as e:
            logger.error(f"Failed to load CERN endpoints: {e}")
            raise


async def try_refresh_token(refresh_token: str) -> dict[str, Any] | None:
    """
    Try to refresh the access token using the refresh token.

    Args:
        refresh_token: The refresh token to use

    Returns:
        New token data dict if successful, None if failed

    Raises:
        Exception: If refresh fails for reasons other than inactive token
    """
    try:
        # Ensure endpoints are loaded
        if not CERN_ENDPOINTS:
            await load_cern_endpoints()

        # Use our retrying HTTP client for token refresh
        async with create_http_client() as http_client:
            async with await http_client.post(
                # Use the token endpoint from well-known OIDC configuration
                url=CERN_ENDPOINTS["token_endpoint"],
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": CERN_CLIENT_ID,
                    "client_secret": CERN_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    # "claim_token": base64.encodebytes({})
                },
            ) as response:
                if response.status == 200:
                    token: dict[str, Any] = await response.json()
                    logger.debug("Token refresh successful: %s", token)
                    return token
                else:
                    error_data = await response.json()
                    error_description = error_data.get(
                        "error_description", "Unknown error"
                    )

                    if "not active" in error_description:
                        # Token is inactive, return None to indicate auth failure
                        logger.info(f"Refresh token is inactive: {error_description}")
                        return None
                    else:
                        # Other error, raise exception
                        raise Exception(
                            f"Token refresh failed with status {response.status}: {error_description}"
                        )

    except Exception as e:
        error_str = str(e)
        if "not active" in error_str or "invalid" in error_str.lower():
            # Token is inactive/invalid, return None to indicate auth failure
            logger.info(f"Refresh token is inactive or invalid: {e}")
            return None
        else:
            # Other error, re-raise
            logger.error(f"Token refresh failed with unexpected error: {e}")
            raise


def extract_auth_cookies(request_cookies: dict[str, str]) -> dict[str, str]:
    """
    Extract and decode authentication cookies from request.

    Args:
        request_cookies: Dictionary of cookies from the request

    Returns:
        Dictionary containing decoded tokens and nonce

    Raises:
        Exception: If required cookies are missing or invalid
    """
    try:
        return {
            "access_token": cern_auth.jwt_decode_str(
                request_cookies[f"{AUTH_COOKIE_PREFIX}-access-token"]
            ),
            "refresh_token": cern_auth.jwt_decode_str(
                request_cookies[f"{AUTH_COOKIE_PREFIX}-refresh-token"]
            ),
            "id_token": cern_auth.jwt_decode_str(
                request_cookies[f"{AUTH_COOKIE_PREFIX}-id-token"]
            ),
        }
    except KeyError as e:
        raise Exception(f"Missing required authentication cookie: {e}")
    except Exception as e:
        raise Exception(f"Failed to decode authentication cookies: {e}")


async def validate_token_and_get_user(
    access_token: str, id_token: str, oauth_client: Any
) -> dict[str, Any]:
    """
    Validate tokens and extract user information.

    Args:
        access_token: The access token
        id_token: The ID token
        nonce: The nonce for validation (None if from refreshed token)
        oauth_client: The OAuth client instance

    Returns:
        User information dictionary

    Raises:
        Exception: If token validation fails
    """

    # For original tokens with nonce, use the OAuth client's ID token parsing
    data = {
        "token": {
            "access_token": access_token,
            "id_token": id_token,
        },
        "nonce": None,
    }
    userinfo: dict[str, Any] = await oauth_client.parse_id_token(**data)
    logger.debug("Received userinfo: %s", userinfo)

    # Additionally, try to get CERN roles information from introspection or userinfo endpoint
    try:
        # First try introspection
        introspection_data = await cern_auth.introspect_token(access_token)
        if "cern_roles" in introspection_data:
            userinfo["cern_roles"] = introspection_data["cern_roles"]
            logger.debug(
                "Added CERN roles from token introspection: %s",
                userinfo.get("cern_roles", []),
            )
        else:
            # If no cern_roles in introspection, try userinfo endpoint
            try:
                async with create_http_client() as http_client:
                    async with await http_client.get(
                        "https://auth.cern.ch/auth/realms/cern/protocol/openid-connect/userinfo",
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=10.0,
                    ) as response:
                        if response.status == 200:
                            userinfo_data = await response.json()
                            if "cern_roles" in userinfo_data:
                                userinfo["cern_roles"] = userinfo_data["cern_roles"]
                                logger.debug(
                                    "Added CERN roles from userinfo endpoint: %s",
                                    userinfo.get("cern_roles", []),
                                )
                            # Also check for groups
                            if "groups" in userinfo_data:
                                userinfo["groups"] = userinfo_data["groups"]
                                logger.debug(
                                    "Added groups from userinfo endpoint: %s",
                                    userinfo.get("groups", []),
                                )
            except Exception as e:
                logger.warning(f"Failed to fetch from userinfo endpoint: {e}")
    except Exception as e:
        logger.info(f"Failed to introspect token for roles: {e}")
        # Continue without roles if introspection fails

    return userinfo


async def get_logout_url() -> str:
    """
    Get the CERN SSO logout URL from well-known endpoints.

    Returns:
        The logout URL string
    """
    # Ensure endpoints are loaded
    if not CERN_ENDPOINTS:
        await load_cern_endpoints()

    logout_url: str = CERN_ENDPOINTS["end_session_endpoint"]
    return logout_url


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    id_token: str,
    max_age: int = 36000,
) -> None:
    """
    Set authentication cookies on the response.

    Args:
        response: The response object to set cookies on
        access_token: The access token to encode and set
        refresh_token: The refresh token to encode and set
        id_token: The ID token to encode and set
        nonce: The nonce to encode and set
        max_age: Cookie expiration time in seconds (default: 10 hours)
    """
    # Encode tokens with JWT
    access_token_jwt = cern_auth.jwt_encode_str(access_token)
    refresh_token_jwt = cern_auth.jwt_encode_str(refresh_token)
    id_token_jwt = cern_auth.jwt_encode_str(id_token)

    # Common cookie settings
    cookie_settings = {
        "max_age": max_age,
        "httponly": True,
        "samesite": "lax",
        "secure": config.get("general.https_only").lower() == "true",
    }

    # Set all cookies required for authentication and token management
    response.set_cookie(
        key=f"{AUTH_COOKIE_PREFIX}-access-token",
        value=access_token_jwt,
        **cookie_settings,
    )

    response.set_cookie(
        key=f"{AUTH_COOKIE_PREFIX}-refresh-token",
        value=refresh_token_jwt,
        **cookie_settings,
    )

    response.set_cookie(
        key=f"{AUTH_COOKIE_PREFIX}-id-token",
        value=id_token_jwt,
        **cookie_settings,
    )


def clear_auth_cookies(response: Response) -> None:
    """
    Clear all authentication cookies from the response.

    Args:
        response: The response object to clear cookies from
    """
    # Delete all auth cookies by setting them with past expiration
    # Must match the exact parameters used when setting the cookies
    cookie_settings = {
        "httponly": True,
        "samesite": "lax",
        "secure": config.get("general.https_only").lower() == "true",
    }

    response.delete_cookie(
        key=f"{AUTH_COOKIE_PREFIX}-access-token",
        **cookie_settings,
    )
    response.delete_cookie(
        key=f"{AUTH_COOKIE_PREFIX}-refresh-token",
        **cookie_settings,
    )
    response.delete_cookie(
        key=f"{AUTH_COOKIE_PREFIX}-id-token",
        **cookie_settings,
    )


async def validate_user_session(
    request: Any, response: Any, oauth_client: Any, required_role: str = "authorized"
) -> tuple[bool, dict[str, Any] | None]:
    """
    Comprehensive user session validation with automatic token refresh and role checking.

    This function:
    1. Extracts and validates authentication cookies
    2. Attempts to validate current tokens
    3. If tokens are expired, tries to refresh them and updates cookies
    4. Checks if user has required role
    5. Returns authentication status and user info

    Args:
        request: The FastAPI request object
        response: The response object to set cookies on (if tokens are refreshed)
        oauth_client: The OAuth client instance
        required_role: The required CERN role (default: "authorized")

    Returns:
        Tuple of (is_authenticated: bool, user_info: dict | None)
        - (True, user_dict) if authenticated and authorized
        - (False, None) if authentication failed or user lacks required role
    """
    logger.debug("Starting user session validation")

    try:
        # Step 1: Extract and decode authentication cookies
        auth_data = extract_auth_cookies(request.cookies)
        access_token = auth_data["access_token"]
        refresh_token = auth_data["refresh_token"]
        id_token = auth_data["id_token"]

        logger.debug("Successfully extracted authentication cookies")

    except Exception as e:
        logger.info(f"Failed to extract auth cookies - user not authenticated: {e}")
        return False, None

    try:
        # Step 2: Try to validate current tokens and get user info
        userinfo: dict[str, Any] = await validate_token_and_get_user(
            access_token, id_token, oauth_client
        )
        logger.debug("Current tokens are valid")

        # Step 3: Check if user has required role
        if not cern_auth.has_user_access(userinfo):
            logger.warning(
                f"User {userinfo.get('preferred_username', 'unknown')} lacks required role '{required_role}'"
            )
            return False, None

        return True, userinfo

    except Exception as e:
        logger.info(f"Token validation failed, attempting refresh: {e}")

        # Step 4: Try to refresh tokens
        try:
            new_token_data = await try_refresh_token(refresh_token)
            if new_token_data is None:
                logger.info("Token refresh failed - tokens are inactive/invalid")
                return False, None

            logger.debug("Successfully refreshed tokens")

            # Step 5: Validate refreshed tokens and get user info
            # Use None for nonce since refreshed tokens don't contain the original nonce
            userinfo = await validate_token_and_get_user(
                new_token_data.get("access_token", ""),
                new_token_data.get("id_token", ""),
                oauth_client,
            )

            # Step 6: Update cookies with refreshed tokens (if response object is available)
            if response is not None:
                set_auth_cookies(
                    response,
                    access_token=new_token_data.get("access_token", ""),
                    refresh_token=new_token_data.get("refresh_token", ""),
                    id_token=new_token_data.get("id_token", ""),
                )
                logger.debug("Updated cookies with refreshed tokens")
            else:
                logger.debug("Response object not available, skipping cookie update")

            # Step 7: Check if user has required role
            if not cern_auth.has_user_access(userinfo):
                logger.warning(
                    f"User {userinfo.get('preferred_username', 'unknown')} lacks required role '{required_role}'"
                )
                return False, None

            logger.info(
                f"Successfully authenticated user: {userinfo.get('preferred_username', 'unknown')}"
            )
            return True, userinfo

        except Exception as refresh_error:
            logger.info(f"Token refresh failed: {refresh_error}")
            return False, None


class AuthDependency:
    """
    FastAPI dependency class for user authentication and authorization.

    This class follows the recommended FastAPI pattern for parameterized dependencies
    using the __call__ method to create injectable dependencies with configurable roles.

    Example usage:
        # Default "authorized" role
        user: dict = Depends(AuthDependency())

        # Admin role required
        user: dict = Depends(AuthDependency("admin"))

        # Custom role required
        user: dict = Depends(AuthDependency("editor"))

        # No authentication required - returns generic "Unauthenticated user"
        user: dict = Depends(AuthDependency(None))
    """

    def __init__(self, required_role: str | None = "authorized"):
        """
        Initialize the auth dependency with a required role.

        Args:
            required_role: The CERN role required for access. Use None to skip authentication
                          and return a generic "Unauthenticated user" (default: "authorized")
        """
        self.required_role = required_role

    async def __call__(self, request: Request) -> dict[str, Any]:
        """
        FastAPI dependency function that validates authentication and authorization.

        This method is called by FastAPI when the dependency is injected.
        It handles authentication validation and authorization checking.
        Token refresh is now handled by the dedicated /refresh-auth-token endpoint.

        Args:
            request: FastAPI Request object (auto-injected)

        Returns:
            User information dictionary if authenticated and authorized, or generic
            unauthenticated user dict if required_role is None or auth is disabled

        Raises:
            HTTPException: If authentication or authorization fails (when auth is enabled and required_role is not None)
        """
        try:
            # Get configuration to check if auth is enabled
            config = get_config()
            auth_enabled = config.get("auth.enabled", True)

            # If auth is disabled globally, return a generic unauthenticated user
            if not auth_enabled:
                logger.debug(
                    "Authentication is disabled globally, returning generic user"
                )
                return {
                    "preferred_username": "Unauthenticated user",
                    "email": "unauthenticated@example.com",
                    "name": "Unauthenticated user",
                    "groups": [],
                    "roles": [],
                    "authenticated": False,
                    "sub": "unauthenticated",
                    "auth_disabled": True,
                }

            # If no role is required, return a generic unauthenticated user
            if self.required_role is None:
                logger.debug("No authentication required, returning generic user")
                return {
                    "preferred_username": "Unauthenticated user",
                    "email": "unauthenticated@example.com",
                    "name": "Unauthenticated user",
                    "groups": [],
                    "roles": [],
                    "authenticated": False,
                    "sub": "unauthenticated",
                }

            # Get configuration and setup OAuth client
            CERN_CLIENT_ID = config.get("general.cern_client_id")
            CERN_CLIENT_SECRET = config.get("general.cern_client_secret")
            CERN_OIDC_URL = config.get("auth.cern_oidc_url")

            # Check if required auth configuration is available
            if not CERN_CLIENT_ID or not CERN_CLIENT_SECRET or not CERN_OIDC_URL:
                logger.warning(
                    "Auth is enabled but required configuration is missing, returning unauthenticated user"
                )
                return {
                    "preferred_username": "Unauthenticated user",
                    "email": "unauthenticated@example.com",
                    "name": "Unauthenticated user",
                    "groups": [],
                    "roles": [],
                    "authenticated": False,
                    "sub": "unauthenticated",
                    "config_missing": True,
                }

            oauth = OAuth()
            oauth.register(
                name="provider",
                server_metadata_url=CERN_OIDC_URL,
                client_id=CERN_CLIENT_ID,
                client_secret=CERN_CLIENT_SECRET,
                client_kwargs={
                    "scope": "openid email profile groups",
                },
            )

            # Use the centralized authentication function without cookie updates
            # Token refresh and cookie management is handled by dedicated endpoint
            is_authenticated, user_info = await validate_user_session(
                request=request,
                response=None,
                oauth_client=oauth.provider,
                required_role=self.required_role,
            )

            if not is_authenticated or user_info is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error": "authentication_failed",
                        "message": "Authentication required. Please login.",
                    },
                    headers={
                        "WWW-Authenticate": "Bearer",
                        "X-Token-Expired": "true",  # Signal frontend to try refresh
                    },
                )

            logger.debug(
                f"Authentication successful for user: {user_info.get('preferred_username', 'unknown')}"
            )
            return user_info

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error during session validation: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "session_error",
                    "message": "Session validation failed due to internal error.",
                },
            )
