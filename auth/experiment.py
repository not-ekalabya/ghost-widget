import sys
import json
import requests
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import threading

API_KEY = "AIzaSyBsig0QxBmVelZQwef23-MoTFdeuZM5P-4"
REDIRECT_URI = "http://localhost:8080/callback"
TOKEN_FILE = "firebase_token.json"

class CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        if "/callback" in self.path:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            CallbackHandler.auth_code = params.get("code", [None])[0]

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"You may close this window.")
        else:
            self.send_response(404)
            self.end_headers()

class GoogleAuthApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Firebase Google Auth")
        self.resize(300, 200)

        self.label = QLabel("Not signed in", alignment=Qt.AlignmentFlag.AlignCenter)
        self.login_btn = QPushButton("Sign in with Google")
        self.logout_btn = QPushButton("Logout")

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.login_btn)
        layout.addWidget(self.logout_btn)
        self.setLayout(layout)

        self.login_btn.clicked.connect(self.login)
        self.logout_btn.clicked.connect(self.logout)

        self.auto_login()

    def auto_login(self):
        creds = self.load_tokens()
        if creds:
            id_token, refresh_token = creds
            if self.refresh_token(refresh_token):
                self.label.setText("✅ Auto-logged in!")
                return

        self.label.setText("Not Signed In")

    def login(self):
        # Step 1: Start local server
        server = HTTPServer(("localhost", 8080), CallbackHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        # Step 2: Open Firebase Google login popup
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id=816342083028-te98svps0mjo5230g3aasfipt8qr824g.apps.googleusercontent.com&"
            f"redirect_uri={REDIRECT_URI}&"
            "response_type=code&"
            "scope=openid%20email"
        )

        import webbrowser
        webbrowser.open(auth_url)

        # Wait for Google login
        while CallbackHandler.auth_code is None:
            QApplication.processEvents()

        auth_code = CallbackHandler.auth_code
        server.shutdown()

        self.exchange_code_for_tokens(auth_code)

    def exchange_code_for_tokens(self, code):
        # Step 1: Exchange code with Google
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "code": code,
            "client_id": "816342083028-te98svps0mjo5230g3aasfipt8qr824g.apps.googleusercontent.com",
            "client_secret": "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",
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        r = requests.post(token_url, data=payload).json()

        if "id_token" not in r:
            print("Google token exchange failed:", r)
            self.label.setText("❌ Auth Failed at Google")
            return

        id_token = r["id_token"]

        # Step 2: Sign in to Firebase
        firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={API_KEY}"
        payload = {
            "postBody": f"id_token={id_token}&providerId=google.com",
            "requestUri": REDIRECT_URI,
            "returnIdpCredential": True,
            "returnSecureToken": True
        }
        fr = requests.post(firebase_url, json=payload).json()

        if "refreshToken" in fr:
            self.save_tokens(fr["idToken"], fr["refreshToken"])
            self.label.setText("✅ Signed in Successfully!")
        else:
            self.label.setText("❌ Firebase Login Failed")
            print(fr)

    def refresh_token(self, refresh_token):
        url = f"https://securetoken.googleapis.com/v1/token?key={API_KEY}"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        r = requests.post(url, data=payload).json()
        if "id_token" in r:
            self.save_tokens(r["id_token"], r["refresh_token"])
            return True
        return False

    def logout(self):
        try:
            open(TOKEN_FILE, "w").close()
        except:
            pass
        self.label.setText("Logged out")

    def save_tokens(self, id_token, refresh_token):
        with open(TOKEN_FILE, "w") as f:
            json.dump({"id": id_token, "refresh": refresh_token}, f)

    def load_tokens(self):
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
                return data.get("id"), data.get("refresh")
        except:
            return None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GoogleAuthApp()
    window.show()
    sys.exit(app.exec())
