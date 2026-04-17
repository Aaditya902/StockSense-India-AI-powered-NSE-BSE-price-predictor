"""
Router: Upstox OAuth2 + Status
Handles the one-time login flow to get the access token.

Endpoints:
  GET /upstox/login     → redirect to Upstox login page
  GET /upstox/callback  → receive auth code, exchange for token
  GET /upstox/status    → check if token is valid
  GET /upstox/logout    → clear token
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse

router = APIRouter(prefix="/upstox", tags=["Upstox"])


@router.get("/login")
def upstox_login():
    """
    Redirect user to Upstox login page.
    After login, Upstox redirects back to /upstox/callback?code=xxx
    """
    from backend.services.upstox_service import get_login_url
    url = get_login_url()
    return RedirectResponse(url)


@router.get("/callback")
def upstox_callback(code: str = None, error: str = None):
    """
    Upstox redirects here after login with ?code=xxx
    We exchange the code for an access token.
    """
    if error:
        return HTMLResponse(f"""
        <html><body style="font-family:monospace;padding:40px;background:#080c10;color:#ff4d6a">
        <h2>Upstox login failed</h2>
        <p>Error: {error}</p>
        <a href="/" style="color:#3b9eff">← Back to app</a>
        </body></html>
        """)

    if not code:
        return HTMLResponse("""
        <html><body style="font-family:monospace;padding:40px;background:#080c10;color:#ff4d6a">
        <h2>No code received</h2>
        <p>Make sure your redirect URI matches exactly what is set in Upstox developer console.</p>
        <a href="/upstox/login" style="color:#3b9eff">Try again</a>
        </body></html>
        """)

    try:
        from backend.services.upstox_service import exchange_code_for_token
        token = exchange_code_for_token(code)
        return HTMLResponse(f"""
        <html><body style="font-family:monospace;padding:40px;background:#080c10;color:#22d47a">
        <h2>✓ Upstox connected successfully</h2>
        <p>Live real-time data is now active.</p>
        <p style="color:#5a7a94;font-size:12px">Token valid for ~23 hours. Revisit this page tomorrow to refresh.</p>
        <br>
        <a href="/" style="color:#3b9eff;font-size:16px">→ Go to StockSense</a>
        </body></html>
        """)
    except Exception as e:
        return HTMLResponse(f"""
        <html><body style="font-family:monospace;padding:40px;background:#080c10;color:#ff4d6a">
        <h2>Token exchange failed</h2>
        <p>{str(e)}</p>
        <a href="/upstox/login" style="color:#3b9eff">Try again</a>
        </body></html>
        """)


@router.get("/status")
def upstox_status():
    """Check if Upstox token is valid and live data is active."""
    from backend.services.upstox_service import has_valid_token, load_token
    import time

    token = load_token()
    return JSONResponse({
        "connected":   has_valid_token(),
        "login_url":   "/upstox/login",
        "message":     "Live data active" if token else "Visit /upstox/login to enable live data",
    })


@router.get("/logout")
def upstox_logout():
    """Clear the stored token."""
    import os
    try:
        os.remove("upstox_token.json")
    except Exception:
        pass
    from backend.services import upstox_service
    upstox_service._access_token = None
    upstox_service._token_expiry  = 0
    return JSONResponse({"message": "Logged out from Upstox"})