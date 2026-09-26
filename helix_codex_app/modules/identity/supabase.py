"""Small Supabase Auth PKCE client for the public pilot bridge."""
from __future__ import annotations

from urllib.parse import urlencode

import httpx


class SupabaseAuthError(RuntimeError):
    """Supabase rejected or could not complete the auth exchange."""


def authorize_url(base_url: str, redirect_uri: str, *, state: str, challenge: str) -> str:
    """Build the GitHub authorization URL without exposing any secret."""
    params = urlencode(
        {
            "provider": "github",
            "redirect_to": redirect_uri,
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{base_url.rstrip('/')}/auth/v1/authorize?{params}"


async def exchange_code(
    base_url: str,
    anon_key: str,
    code: str,
    verifier: str,
) -> dict[str, object]:
    """Exchange a one-use PKCE code and return the verified user payload."""
    headers = {"apikey": anon_key, "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/auth/v1/token?grant_type=pkce",
            headers=headers,
            json={"auth_code": code, "code_verifier": verifier},
        )
        if response.is_error:
            raise SupabaseAuthError("Supabase authorization code exchange failed", status=response.status_code, detail=_safe_error_detail(response))
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise SupabaseAuthError("Supabase did not return an access token")
        user_response = await client.get(
            f"{base_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": anon_key, "authorization": f"Bearer {token}"},
        )
        if user_response.is_error:
            raise SupabaseAuthError("Supabase user verification failed", status=user_response.status_code, detail=_safe_error_detail(user_response))
        user = user_response.json()
        if not isinstance(user, dict) or not user.get("id") or not user.get("email"):
            raise SupabaseAuthError("Supabase user profile is incomplete")
        return user

def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict):
        for key in ("error_code", "error", "msg", "message", "error_description"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value[:200]
    return "supabase_auth_error"