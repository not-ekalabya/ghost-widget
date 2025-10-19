"""
Firebase Authentication Module with Google Sign-In

This module provides Firebase Google OAuth authentication using google-auth-oauthlib.
Supports both desktop OAuth flow and Firebase REST API.

Install dependencies:
    pip install pyrebase4 google-auth-oauthlib google-auth requests
"""

import pyrebase
import json
import webbrowser
import threading
import time
from typing import Optional, Dict, Any
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests


# Global variable to store OAuth code
_oauth_code = None
_oauth_server = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback from Google"""

    def do_GET(self):
        global _oauth_code
        # Parse the authorization code from the URL
        query_components = parse_qs(urlparse(self.path).query)

        if 'code' in query_components:
            _oauth_code = query_components['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write("""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h2 style="color: #10B981;">✓ Authentication Successful!</h2>
                    <p>You can close this window and return to the app.</p>
                    <script>window.close();</script>
                </body>
                </html>
            """.encode())
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write("""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h2 style="color: #EF4444;">✗ Authentication Failed</h2>
                    <p>No authorization code received.</p>
                </body>
                </html>
            """.encode())

    def log_message(self, format, *args):
        """Suppress log messages"""
        pass


class FirebaseAuth:
    """Firebase Authentication Manager with Google Sign-In"""

    def __init__(self, config: Optional[Dict[str, str]] = None, config_file: Optional[str] = None, persist_auth: bool = True):
        """
        Initialize Firebase Auth with configuration

        Args:
            config: Firebase configuration dictionary
            config_file: Path to JSON config file
            persist_auth: Whether to persist authentication state (default: True)
        """
        if config_file:
            config_path = Path(config_file)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
            else:
                raise FileNotFoundError(f"Firebase config file not found: {config_file}")

        if not config:
            raise ValueError("Firebase configuration is required")

        # Validate required fields
        required_fields = ["apiKey", "authDomain", "databaseURL", "storageBucket"]
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        # Initialize Firebase
        self.config = config
        self.firebase = pyrebase.initialize_app(config)
        self.auth = self.firebase.auth()
        self.current_user = None
        self.api_key = config['apiKey']
        self.persist_auth = persist_auth
        self.auth_cache_file = Path.home() / ".ghost_widget_auth.json"

        # Try to restore previous session
        if self.persist_auth:
            self._load_auth_state()

    def sign_in_with_google(self, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> Dict[str, Any]:
        """
        Sign in with Google using OAuth 2.0

        Args:
            client_id: Google OAuth client ID (from firebase_config.json if available)
            client_secret: Google OAuth client secret

        Returns:
            Dictionary with success status and user data
        """
        global _oauth_code, _oauth_server

        try:
            # Get OAuth credentials from config
            if not client_id and 'google_client_id' in self.config:
                client_id = self.config['google_client_id']
            if not client_secret and 'google_client_secret' in self.config:
                client_secret = self.config['google_client_secret']

            if not client_id:
                return {
                    "success": False,
                    "message": "Google OAuth Client ID not configured. Add 'google_client_id' to firebase_config.json"
                }

            # OAuth endpoints
            redirect_uri = "http://localhost:8080/callback"
            auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
            token_url = "https://oauth2.googleapis.com/token"

            # Build authorization URL
            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "offline",
                "prompt": "consent"
            }

            auth_request_url = f"{auth_url}?" + "&".join([f"{k}={v}" for k, v in params.items()])

            # Start local server to handle callback
            _oauth_code = None
            _oauth_server = HTTPServer(('localhost', 8080), OAuthCallbackHandler)

            def run_server():
                _oauth_server.handle_request()

            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()

            # Open browser for authentication
            print("🔐 Opening Google Sign-In in your browser...")
            webbrowser.open(auth_request_url)

            # Wait for callback (with timeout)
            server_thread.join(timeout=120)  # 2 minute timeout

            if not _oauth_code:
                return {
                    "success": False,
                    "message": "Authentication timeout or cancelled. Please try again."
                }

            # Exchange code for tokens
            if not client_secret:
                return {
                    "success": False,
                    "message": "Google OAuth Client Secret not configured. Add 'google_client_secret' to firebase_config.json"
                }

            token_data = {
                "code": _oauth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }

            print("🔄 Exchanging OAuth code for tokens...")
            token_response = requests.post(token_url, data=token_data)
            token_result = token_response.json()

            if 'error' in token_result:
                error_msg = f"Token exchange failed: {token_result.get('error_description', token_result['error'])}"
                print(f"❌ {error_msg}")
                return {
                    "success": False,
                    "message": error_msg
                }

            print("✅ Successfully got Google tokens")
            id_token = token_result['id_token']

            # Sign in to Firebase with Google ID token
            print("🔄 Signing in to Firebase with Google ID token...")
            firebase_signin_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={self.api_key}"
            firebase_data = {
                "postBody": f"id_token={id_token}&providerId=google.com",
                "requestUri": redirect_uri,
                "returnIdpCredential": True,
                "returnSecureToken": True
            }

            firebase_response = requests.post(firebase_signin_url, json=firebase_data)
            firebase_result = firebase_response.json()

            if 'error' in firebase_result:
                error_msg = f"Firebase sign-in failed: {firebase_result.get('error', {}).get('message', 'Unknown error')}"
                print(f"❌ {error_msg}")
                print(f"Full error: {firebase_result}")
                return {
                    "success": False,
                    "message": error_msg
                }

            # Store user data
            print("✅ Firebase sign-in successful!")
            self.current_user = {
                "idToken": firebase_result['idToken'],
                "refreshToken": firebase_result['refreshToken'],
                "localId": firebase_result['localId'],
                "email": firebase_result.get('email', ''),
                "displayName": firebase_result.get('displayName', ''),
                "photoUrl": firebase_result.get('photoUrl', ''),
                "expiresIn": firebase_result.get('expiresIn', 3600)
            }

            print(f"👤 User: {self.current_user.get('email')} ({self.current_user.get('displayName')})")

            # Save auth state for persistence
            if self.persist_auth:
                self._save_auth_state()

            return {
                "success": True,
                "message": "Google Sign-In successful!",
                "user": self.current_user
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Google Sign-In error: {str(e)}"
            }

    def sign_in_anonymous(self) -> Dict[str, Any]:
        """Sign in anonymously"""
        try:
            user = self.auth.sign_in_anonymous()
            self.current_user = {
                "idToken": user['idToken'],
                "refreshToken": user['refreshToken'],
                "localId": user['localId'],
                "expiresIn": user.get('expiresIn', 3600)
            }

            # Save auth state for persistence
            if self.persist_auth:
                self._save_auth_state()

            return {
                "success": True,
                "message": "Signed in anonymously",
                "user": self.current_user
            }
        except Exception as e:
            return {"success": False, "message": f"Anonymous sign-in failed: {str(e)}"}

    def refresh_token(self, refresh_token: Optional[str] = None) -> Dict[str, Any]:
        """Refresh authentication token"""
        try:
            if not refresh_token and self.current_user:
                refresh_token = self.current_user.get('refreshToken')

            if not refresh_token:
                return {"success": False, "message": "No refresh token available"}

            user = self.auth.refresh(refresh_token)

            # Update current user with new token but preserve other data
            if self.current_user:
                self.current_user.update({
                    "idToken": user['idToken'],
                    "refreshToken": user['refreshToken'],
                    "expiresIn": user.get('expiresIn', 3600)
                })
            else:
                self.current_user = {
                    "idToken": user['idToken'],
                    "refreshToken": user['refreshToken'],
                    "userId": user.get('userId'),
                    "expiresIn": user.get('expiresIn', 3600)
                }

            # Save updated auth state
            if self.persist_auth:
                self._save_auth_state()

            return {
                "success": True,
                "message": "Token refreshed successfully",
                "user": self.current_user
            }
        except Exception as e:
            return {"success": False, "message": f"Token refresh failed: {str(e)}"}

    def sign_out(self) -> Dict[str, str]:
        """Sign out current user"""
        self.current_user = None
        # Clear persisted auth state
        if self.persist_auth:
            self._clear_auth_state()
        return {"success": True, "message": "Signed out successfully"}

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get current authenticated user"""
        return self.current_user

    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated"""
        return self.current_user is not None

    def get_user_id(self) -> Optional[str]:
        """Get current user's ID"""
        if self.current_user:
            return self.current_user.get('localId') or self.current_user.get('userId')
        return None

    def get_id_token(self) -> Optional[str]:
        """Get current user's authentication token"""
        if self.current_user:
            return self.current_user.get('idToken')
        return None

    def get_user_email(self) -> Optional[str]:
        """Get current user's email"""
        if self.current_user:
            return self.current_user.get('email')
        return None

    def get_user_display_name(self) -> Optional[str]:
        """Get current user's display name"""
        if self.current_user:
            return self.current_user.get('displayName')
        return None

    def _save_auth_state(self):
        """Save authentication state to file for persistence"""
        if not self.persist_auth or not self.current_user:
            return

        try:
            auth_data = {
                "user": self.current_user,
                "saved_at": time.time()
            }

            with open(self.auth_cache_file, 'w') as f:
                json.dump(auth_data, f)

            print(f"✅ Authentication state saved")
        except Exception as e:
            print(f"⚠️ Failed to save auth state: {e}")

    def _load_auth_state(self) -> bool:
        """Load and validate saved authentication state"""
        if not self.persist_auth or not self.auth_cache_file.exists():
            return False

        try:
            with open(self.auth_cache_file, 'r') as f:
                auth_data = json.load(f)

            saved_at = float(auth_data.get('saved_at', 0))
            user_data = auth_data.get('user', {})

            # Check if token is expired (tokens expire after 1 hour = 3600 seconds)
            expires_in = int(user_data.get('expiresIn', 3600))
            time_elapsed = time.time() - saved_at

            if time_elapsed < expires_in:
                # Token is still valid
                self.current_user = user_data
                print(f"✅ Restored authentication session for {self.get_user_email()}")
                return True
            else:
                # Token expired, try to refresh
                print("🔄 Auth token expired, attempting to refresh...")
                refresh_token = user_data.get('refreshToken')

                if refresh_token:
                    result = self.refresh_token(refresh_token)
                    if result['success']:
                        print("✅ Successfully refreshed auth token")
                        self._save_auth_state()  # Save the new token
                        return True
                    else:
                        print(f"❌ Token refresh failed: {result['message']}")
                        self._clear_auth_state()
                        return False
                else:
                    print("❌ No refresh token available")
                    self._clear_auth_state()
                    return False

        except Exception as e:
            print(f"⚠️ Failed to load auth state: {e}")
            self._clear_auth_state()
            return False

    def _clear_auth_state(self):
        """Clear saved authentication state"""
        try:
            if self.auth_cache_file.exists():
                self.auth_cache_file.unlink()
                print("✅ Cleared saved authentication state")
        except Exception as e:
            print(f"⚠️ Failed to clear auth state: {e}")


# Example usage
if __name__ == "__main__":
    # Example Firebase configuration
    config = {
      "apiKey": "AIzaSyBsig0QxBmVelZQwef23-MoTFdeuZM5P-4",
      "authDomain": "ghost-widget-7000.firebaseapp.com",
      "projectId": "ghost-widget-7000",
      "databaseURL": "https://ghost-widget-7000-default-rtdb.firebaseio.com/",
      "storageBucket": "ghost-widget-7000.firebasestorage.app",
      "google_client_id": "816342083028-te98svps0mjo5230g3aasfipt8qr824g.apps.googleusercontent.com",
      "google_client_secret": "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",
      "messagingSenderId": "816342083028",
      "appId": "1:816342083028:web:0e0d8aa40d66bf858f2241",
      "measurementId": "G-XGLGL9E2TJ"
    }

    # {
    #     "apiKey": "YOUR_FIREBASE_API_KEY",
    #     "authDomain": "your-project.firebaseapp.com",
    #     "databaseURL": "https://your-project.firebaseio.com",
    #     "storageBucket": "your-project.appspot.com",
    #     "google_client_id": "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com",
    #     "google_client_secret": "YOUR_GOOGLE_CLIENT_SECRET"
    # }

    firebase_auth = FirebaseAuth(config=config)

    # Sign in with Google
    result = firebase_auth.sign_in_with_google()
    print("Sign in result:", result)

    if firebase_auth.is_authenticated():
        print(f"User ID: {firebase_auth.get_user_id()}")
        print(f"Email: {firebase_auth.get_user_email()}")
        print(f"Name: {firebase_auth.get_user_display_name()}")
