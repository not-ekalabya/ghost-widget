# Firebase Google Sign-In Setup Guide

This guide will help you set up Google Sign-In authentication for the Ghost Widget application using Firebase and Pyrebase4.

## Prerequisites

- Python 3.7 or higher
- A Google account
- Firebase project (free tier is sufficient)

## Step 1: Install Dependencies

Install the required packages:

```bash
pip install pyrebase4 requests
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

## Step 2: Create a Firebase Project

1. Go to the [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project" or select an existing project
3. Follow the setup wizard:
   - Enter a project name (e.g., "Ghost Widget")
   - (Optional) Disable Google Analytics if you don't need it
   - Click "Create Project"
4. Once created, click "Continue" to open your project

## Step 3: Enable Google Authentication

1. In your Firebase project, click on **"Authentication"** in the left sidebar
2. Click on the **"Get Started"** button if it's your first time
3. Click on the **"Sign-in method"** tab at the top
4. Find **"Google"** in the list of providers
5. Click on "Google" to configure it
6. Toggle the **"Enable"** switch to ON
7. Select a "Project support email" (your email)
8. Click **"Save"**

## Step 4: Get Your Firebase Configuration

1. In Firebase Console, click the gear icon ⚙️ next to "Project Overview"
2. Select **"Project settings"**
3. Scroll down to **"Your apps"** section
4. Click on the web icon `</>` (or select your existing web app)
5. If creating new: Register your app with a nickname (e.g., "Ghost Widget")
6. Copy the Firebase configuration object

You'll see something like this:

```javascript
const firebaseConfig = {
  apiKey: "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  authDomain: "your-project.firebaseapp.com",
  databaseURL: "https://your-project.firebaseio.com",
  projectId: "your-project",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "123456789012",
  appId: "1:123456789012:web:abcdef123456"
};
```

## Step 5: Get Google OAuth Credentials

This is important for Google Sign-In to work!

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your Firebase project from the dropdown at the top
3. Go to **"APIs & Services"** > **"Credentials"**
4. Click **"Create Credentials"** > **"OAuth client ID"**
5. If prompted, configure the OAuth consent screen first:
   - Click "Configure Consent Screen"
   - Select "External" user type
   - Fill in:
     - App name: Ghost Widget
     - User support email: your email
     - Developer contact: your email
   - Click "Save and Continue"
   - Skip Scopes (click "Save and Continue")
   - Add test users if needed
   - Click "Save and Continue"

6. Back to "Create OAuth client ID":
   - Application type: **"Desktop app"**
   - Name: Ghost Widget Desktop
   - Click **"Create"**

7. You'll see a dialog with your credentials:
   - **Client ID**: `xxxxxxxxx.apps.googleusercontent.com`
   - **Client Secret**: `GOCSPX-xxxxxxxxxxxxxxx`
   - **Download JSON** (optional, for backup)

## Step 6: Create Your Configuration File

1. In your project directory, copy `firebase_config.example.json` to `firebase_config.json`:
   ```bash
   copy firebase_config.example.json firebase_config.json
   ```

2. Open `firebase_config.json` and fill in ALL the values:

```json
{
  "apiKey": "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "authDomain": "your-project.firebaseapp.com",
  "databaseURL": "https://your-project.firebaseio.com",
  "storageBucket": "your-project.appspot.com",
  "messagingSenderId": "123456789012",
  "appId": "1:123456789012:web:abcdef123456",
  "google_client_id": "123456789012-abcdefghijklmnop.apps.googleusercontent.com",
  "google_client_secret": "GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx"
}
```

**Important:**
- Replace ALL placeholder values with your actual Firebase and Google credentials
- Add `firebase_config.json` to your `.gitignore` (already done)
- **Never commit this file to version control!**

## Step 7: Test Your Authentication

1. Run your Ghost Widget application:
   ```bash
   python main.py
   ```

2. Navigate to the **"Auth"** tab

3. Click **"Sign in with Google"**

4. Your browser will open with Google's sign-in page

5. Choose your Google account

6. Grant permissions to the app

7. You'll see "Authentication Successful!" in the browser

8. Return to the app - you should see your email and name displayed!

## How Google Sign-In Works

### OAuth Flow:

1. **User clicks "Sign in with Google"**
   - App opens browser to Google's OAuth page
   - Local server starts on `localhost:8080` to receive callback

2. **User authenticates with Google**
   - User selects Google account
   - Grants permissions
   - Google redirects to `http://localhost:8080/callback` with auth code

3. **App exchanges code for tokens**
   - Gets Google ID token
   - Exchanges ID token for Firebase auth token
   - Stores user data (email, name, etc.)

4. **User is authenticated**
   - App shows user info
   - Token is valid for 1 hour
   - Can be refreshed using refresh token

## Troubleshooting

### "Firebase Auth not initialized"
- Make sure `firebase_config.json` exists in your project directory
- Check that the file contains valid JSON
- Verify all required fields are present

### "Google OAuth Client ID not configured"
- You forgot to add `google_client_id` to `firebase_config.json`
- Make sure you created OAuth credentials in Google Cloud Console
- The Client ID should end with `.apps.googleusercontent.com`

### "Google OAuth Client Secret not configured"
- You forgot to add `google_client_secret` to `firebase_config.json`
- The secret usually starts with `GOCSPX-`

### "Authentication timeout or cancelled"
- You took too long to sign in (> 2 minutes)
- You closed the browser before completing sign-in
- Try again and complete the process faster

### "Token exchange failed"
- Check that your Google OAuth credentials are correct
- Make sure you selected "Desktop app" type (not Web application)
- Verify the redirect URI is `http://localhost:8080/callback`

### "Firebase sign-in failed"
- Make sure Google sign-in is enabled in Firebase Console
- Check that your Firebase API key is correct
- Verify your Firebase project is active

### Browser doesn't open
- Check your default browser settings
- Try manually copying the URL from console
- Make sure port 8080 is not blocked by firewall

### "pyrebase4 not found" or "requests not found"
- Install dependencies: `pip install pyrebase4 requests`
- Or use: `pip install -r requirements.txt`

## Security Best Practices

1. **Keep credentials secret**
   - Never commit `firebase_config.json`
   - Don't share your OAuth client secret
   - Rotate credentials if exposed

2. **Use environment variables (optional)**
   - For production, consider using env vars
   - Keep backup of credentials in secure location

3. **Token management**
   - Tokens expire after 1 hour
   - Use refresh token to extend session
   - Sign out clears all tokens

4. **OAuth consent screen**
   - Use verified app for production
   - Add privacy policy and terms of service
   - Request only necessary scopes

## Features

✅ Google OAuth 2.0 authentication
✅ Browser-based sign-in flow
✅ Automatic token management
✅ User profile information (email, name, photo)
✅ Token refresh support
✅ Anonymous authentication (optional)
✅ Sign out functionality
✅ Modern, clean UI
✅ Secure credential storage

## API Reference

### FirebaseAuth Methods

```python
from firebase_auth import FirebaseAuth

# Initialize
auth = FirebaseAuth(config_file="firebase_config.json")

# Sign in with Google
result = auth.sign_in_with_google()
# Opens browser, returns user data

# Check authentication
if auth.is_authenticated():
    user_id = auth.get_user_id()
    email = auth.get_user_email()
    name = auth.get_user_display_name()
    token = auth.get_id_token()

# Refresh token
result = auth.refresh_token()

# Sign out
result = auth.sign_out()

# Anonymous sign in (optional)
result = auth.sign_in_anonymous()
```

## Firebase Console - User Management

View and manage authenticated users:

1. Go to your Firebase project
2. Click **"Authentication"** > **"Users"** tab
3. See all users who signed in
4. View user details (email, ID, sign-in method)
5. Disable or delete users if needed

## Next Steps

- Add user profile management
- Integrate authentication with your backend
- Set up Firebase Realtime Database or Firestore
- Add additional OAuth providers (GitHub, Facebook, etc.)
- Implement role-based access control

## Resources

- [Firebase Authentication Docs](https://firebase.google.com/docs/auth)
- [Google OAuth Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Firebase Console](https://console.firebase.google.com/)
- [Google Cloud Console](https://console.cloud.google.com/)
- [Pyrebase4 GitHub](https://github.com/nhorvath/Pyrebase4)

## Support

If you encounter issues:
1. Check Firebase Console for error logs
2. Verify all credentials in `firebase_config.json`
3. Ensure Google sign-in is enabled in Firebase
4. Check that OAuth credentials are correct (Desktop app type)
5. Make sure port 8080 is available

Good luck! 🚀
