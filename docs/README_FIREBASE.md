# Firebase Authentication Implementation for Ghost Widget

## Overview

This implementation adds Firebase Authentication to the Ghost Widget application using Pyrebase4, a Python wrapper for the Firebase API. Users can now sign up, sign in, and manage their authentication state directly from the application's UI.

## What's Been Implemented

### 1. Firebase Authentication Module (`firebase_auth.py`)

A complete authentication module with the following features:

- **User Registration (Sign Up)**
  - Email/password registration
  - Password validation (minimum 6 characters)
  - Error handling for duplicate emails, weak passwords, etc.

- **User Login (Sign In)**
  - Email/password authentication
  - Session token management
  - Automatic token refresh support

- **Anonymous Authentication**
  - Allow users to sign in without an account
  - Useful for testing or guest access

- **Session Management**
  - Sign out functionality
  - Token refresh (tokens expire after 1 hour)
  - Authentication state checking

- **User Information**
  - Get current user ID
  - Get authentication token
  - Check if user is authenticated

### 2. UI Integration (`main.py`)

A new "Auth" tab has been added to the Ghost Widget UI with:

- **Email and Password Input Fields**
  - Clean, modern design matching the app's aesthetic
  - Password field with hidden text

- **Authentication Buttons**
  - Sign Up: Create a new account
  - Sign In: Log into existing account
  - Anonymous Login: Sign in without credentials
  - Sign Out: End current session

- **User Information Display**
  - Shows authenticated user's email
  - Displays user ID
  - Shows token expiration time
  - Visual feedback for authentication status

- **Status Indicators**
  - Authentication status label
  - Success/error messages in activity log
  - Button state management (enabled/disabled based on auth state)

### 3. Configuration Files

- **`firebase_config.example.json`**: Template for Firebase configuration
- **`firebase_config.json`**: Your actual Firebase credentials (not tracked in git)
- **`.gitignore`**: Updated to exclude sensitive files
- **`requirements.txt`**: All necessary dependencies including pyrebase4

### 4. Documentation

- **`FIREBASE_SETUP.md`**: Comprehensive step-by-step setup guide
- **This README**: Implementation overview and usage instructions

## File Structure

```
ghost-widget/
├── firebase_auth.py              # Firebase authentication module
├── firebase_config.example.json  # Configuration template
├── firebase_config.json          # Your config (create this)
├── backend.py                     # Background companion (existing)
├── main.py                        # UI application (updated)
├── requirements.txt               # Python dependencies
├── .gitignore                     # Git ignore rules (updated)
├── FIREBASE_SETUP.md             # Setup instructions
└── README_FIREBASE.md            # This file
```

## Quick Start

### 1. Install Dependencies

```bash
pip install pyrebase4
# Or install all dependencies:
pip install -r requirements.txt
```

### 2. Set Up Firebase Project

1. Create a Firebase project at https://console.firebase.google.com/
2. Enable Email/Password authentication
3. Get your Firebase configuration
4. Create `firebase_config.json` from the template

Detailed instructions: See `FIREBASE_SETUP.md`

### 3. Run the Application

```bash
python main.py
```

### 4. Test Authentication

1. Open the app and navigate to the "Auth" tab
2. Enter an email and password
3. Click "Sign Up" to create an account
4. Try signing in with your credentials
5. Test anonymous login
6. Sign out when done

## Usage Examples

### In Your Code

```python
from firebase_auth import FirebaseAuth

# Initialize with config file
auth = FirebaseAuth(config_file="firebase_config.json")

# Sign up a new user
result = auth.sign_up("user@example.com", "securepass123")
if result['success']:
    print(f"User ID: {result['user']['localId']}")
    print(f"Token: {result['user']['idToken']}")

# Sign in existing user
result = auth.sign_in("user@example.com", "securepass123")
if result['success']:
    print("Login successful!")

# Check authentication status
if auth.is_authenticated():
    user_id = auth.get_user_id()
    token = auth.get_id_token()
    print(f"Authenticated as: {user_id}")

# Refresh expired token
result = auth.refresh_token()

# Sign out
auth.sign_out()
```

### In the UI

The Auth tab provides a visual interface for all authentication operations. Simply:

1. Enter your credentials
2. Click the appropriate button
3. View results in the user info area
4. Check the activity log for detailed messages

## Authentication Flow

### Sign Up Flow
```
User enters email + password
    ↓
Click "Sign Up"
    ↓
Firebase creates account
    ↓
Return user data + tokens
    ↓
Update UI with user info
    ↓
Enable Sign Out button
```

### Sign In Flow
```
User enters email + password
    ↓
Click "Sign In"
    ↓
Firebase validates credentials
    ↓
Return authentication token
    ↓
Update UI with user info
    ↓
Enable Sign Out button
```

### Token Refresh Flow
```
Token expires (after 1 hour)
    ↓
Call refresh_token()
    ↓
Firebase validates refresh token
    ↓
Return new authentication token
    ↓
Update stored token
```

## Security Considerations

1. **Never commit `firebase_config.json`** - It's in .gitignore for a reason
2. **Use strong passwords** - Enforce minimum 6 characters (Firebase requirement)
3. **Refresh tokens regularly** - Tokens expire after 1 hour
4. **Validate user input** - Email format and password strength
5. **Handle errors gracefully** - Don't expose internal error details to users

## Features

✅ Email/password registration
✅ Email/password login
✅ Anonymous authentication
✅ Sign out functionality
✅ Token refresh mechanism
✅ Authentication state management
✅ User information display
✅ Error handling with user-friendly messages
✅ Modern UI integration
✅ Secure credential storage
✅ Comprehensive documentation

## Troubleshooting

### "Firebase Auth not initialized"
- Create `firebase_config.json` with your Firebase credentials
- Check that the file is in the correct directory

### "pyrebase4 not found"
```bash
pip install pyrebase4
```

### "Invalid email or password"
- Enable Email/Password authentication in Firebase Console
- Check credentials are correct
- Ensure password is at least 6 characters

### "Email already exists"
- Use Sign In instead of Sign Up
- Or use a different email address

For more troubleshooting tips, see `FIREBASE_SETUP.md`

## API Reference

### FirebaseAuth Class Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `__init__(config, config_file)` | Initialize Firebase Auth | FirebaseAuth instance |
| `sign_up(email, password)` | Create new user account | Dict with success status and user data |
| `sign_in(email, password)` | Authenticate existing user | Dict with success status and user data |
| `sign_in_anonymous()` | Sign in anonymously | Dict with success status and user data |
| `sign_out()` | End current session | Dict with success status |
| `refresh_token(refresh_token)` | Refresh authentication token | Dict with new token |
| `is_authenticated()` | Check if user is signed in | Boolean |
| `get_user_id()` | Get current user ID | String or None |
| `get_id_token()` | Get authentication token | String or None |
| `get_current_user()` | Get full user data | Dict or None |
| `send_password_reset_email(email)` | Send password reset email | Dict with success status |

## Future Enhancements

Potential improvements for future versions:

- [ ] Password reset functionality in UI
- [ ] Email verification
- [ ] Social authentication (Google, Facebook, etc.)
- [ ] User profile management
- [ ] Multi-factor authentication (MFA)
- [ ] Remember me / persistent sessions
- [ ] Integration with backend data storage
- [ ] User roles and permissions
- [ ] Account deletion
- [ ] Email change functionality

## Resources

- **Firebase Console**: https://console.firebase.google.com/
- **Firebase Auth Docs**: https://firebase.google.com/docs/auth
- **Pyrebase4 GitHub**: https://github.com/nhorvath/Pyrebase4
- **Pyrebase4 PyPI**: https://pypi.org/project/Pyrebase4/

## Testing

### Manual Testing Checklist

- [ ] Install pyrebase4
- [ ] Create Firebase project
- [ ] Enable Email/Password authentication
- [ ] Create firebase_config.json
- [ ] Run application
- [ ] Test sign up with new email
- [ ] Test sign in with created account
- [ ] Test sign out
- [ ] Test anonymous login
- [ ] Verify error handling (wrong password, duplicate email, etc.)
- [ ] Check token expiration and refresh
- [ ] Verify UI updates correctly

### Test Account

For testing purposes, you can create a test account:
- Email: `test@example.com`
- Password: `test123456`

## Credits

Implementation by: Claude Code
Firebase Authentication: Google Firebase
Python Wrapper: Pyrebase4

## Support

For issues or questions:
1. Check `FIREBASE_SETUP.md` for setup help
2. Review Firebase Console for authentication status
3. Check application logs for detailed error messages
4. Verify firebase_config.json is correctly formatted

## License

This implementation follows the same license as the Ghost Widget project.
