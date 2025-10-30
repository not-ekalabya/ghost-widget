# Firestore Chat Storage Setup Guide

This guide explains how to set up Firestore chat storage for the Ghost Widget application.

## Overview

The Firestore chat storage feature allows users to:
- Automatically save all chat conversations to Firebase Firestore
- Retrieve their chat history at any time
- Store chats with user-specific identification
- Include metadata like email and display name

## Prerequisites

1. **Python Dependencies**
   ```bash
   pip install firebase-admin
   ```

2. **Firebase Project**
   - A Firebase project with Firestore enabled
   - A service account with Firestore access

## Setup Instructions

### Step 1: Get Firebase Service Account Credentials

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project (ghost-widget-7000)
3. Click on the gear icon → Project Settings
4. Go to "Service Accounts" tab
5. Click "Generate New Private Key"
6. Download the JSON file (it will contain your credentials)

### Step 2: Update Firestore Chat Configuration

Open `firestore_chat.py` and update the `FIREBASE_CONFIG` dictionary with your service account credentials:

```python
FIREBASE_CONFIG = {
    "type": "service_account",
    "project_id": "ghost-widget-7000",  # Your project ID
    "private_key_id": "YOUR_PRIVATE_KEY_ID",  # From downloaded JSON
    "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n",  # From downloaded JSON
    "client_email": "YOUR_SERVICE_ACCOUNT_EMAIL",  # From downloaded JSON (e.g., firebase-adminsdk-xxxxx@your-project.iam.gserviceaccount.com)
    "client_id": "YOUR_CLIENT_ID",  # From downloaded JSON
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "YOUR_CLIENT_CERT_URL"  # From downloaded JSON
}
```

### Step 3: Configure Firestore Database

1. In Firebase Console, go to Firestore Database
2. Create a database (if not already created)
3. Choose "Start in production mode" or "Start in test mode"
4. Set up security rules:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Chat collection - users can only read/write their own chats
    match /chats/{chatId} {
      allow read, write: if request.auth != null &&
                            resource.data.user_id == request.auth.uid;
    }
  }
}
```

### Step 4: Test the Setup

Run the test script to verify everything is working:

```bash
python test_firestore_chat.py
```

Expected output:
```
============================================================
Testing Firestore Chat Manager
============================================================

1. Initializing Firestore Chat Manager...
✅ Firebase Admin SDK initialized successfully
✅ Firestore client connected to collection: chats
✅ Firestore Chat Manager initialized successfully

2. Using test user ID: test_user_123

3. Testing save_chat()...
✅ Chat saved successfully: abc123...
   Document ID: abc123...

4. Saving another test chat...
✅ Second chat saved successfully!
   Document ID: def456...

5. Testing retrieve_chats()...
✅ Retrieved 2 chats successfully!
   ...
```

## Usage in the Application

### Automatic Chat Saving

Chats are automatically saved when:
1. User is authenticated with Firebase Auth
2. User sends a question in the chat
3. AI provides a response

The chat is saved with:
- User ID (from Firebase Auth)
- Question text
- Response text
- Timestamp
- User metadata (email, display name)

### Retrieving Chat History

To retrieve chat history, call the `retrieve_user_chats()` method:

```python
# In main.py
self.retrieve_user_chats(limit=10)  # Get last 10 chats
```

You can also add a button in the UI to trigger this method.

## Data Structure

Each chat document in Firestore contains:

```json
{
  "user_id": "user_firebase_uid",
  "message": "User's question",
  "response": "AI's response",
  "message_type": "question",
  "timestamp": "Firestore server timestamp",
  "created_at": "2025-01-15T10:30:00.000Z",
  "metadata": {
    "email": "user@example.com",
    "display_name": "User Name"
  }
}
```

## API Methods

### FirestoreChatManager

#### `save_chat(user_id, message, response, message_type="question", metadata=None)`
Saves a chat conversation to Firestore.

**Parameters:**
- `user_id` (str): User's unique ID from Firebase Auth
- `message` (str): User's question/message
- `response` (str): AI's response
- `message_type` (str): Type of message (default: "question")
- `metadata` (dict): Additional metadata (optional)

**Returns:**
```python
{
    "success": True/False,
    "message": "Status message",
    "document_id": "firestore_doc_id"  # If successful
}
```

#### `retrieve_chats(user_id, limit=50, order_by="created_at", descending=True)`
Retrieves chat history for a user.

**Parameters:**
- `user_id` (str): User's unique ID
- `limit` (int): Maximum number of chats to retrieve (default: 50)
- `order_by` (str): Field to sort by (default: "created_at")
- `descending` (bool): Sort order (default: True)

**Returns:**
```python
{
    "success": True/False,
    "message": "Status message",
    "chats": [...],  # List of chat documents
    "count": 10  # Number of chats retrieved
}
```

#### `get_chat_by_id(document_id)`
Retrieves a specific chat by document ID.

#### `delete_chat(document_id)`
Deletes a specific chat.

#### `delete_user_chats(user_id)`
Deletes all chats for a specific user.

## Troubleshooting

### Error: "Firestore is not available"
- Check that firebase-admin is installed: `pip install firebase-admin`
- Verify FIREBASE_CONFIG credentials are correct
- Check Firebase project has Firestore enabled

### Error: "Permission denied"
- Verify Firestore security rules allow authenticated users to read/write
- Check that the service account has proper permissions

### Error: "User not authenticated"
- Ensure user is signed in with Firebase Auth before using chat
- Check firebase_auth.is_authenticated() returns True

### No chats saved
- Check console logs for error messages
- Verify _save_chat_to_firestore() is being called
- Check Firestore console to see if documents are being created

## Security Considerations

1. **Service Account Key**: The service account private key provides admin access. Keep it secure and never commit it to version control.

2. **Firestore Rules**: Update security rules to match your authentication setup:
   ```javascript
   // Only allow users to access their own chats
   match /chats/{chatId} {
     allow read, write: if request.auth.uid == resource.data.user_id;
   }
   ```

3. **Environment Variables**: For production, consider using environment variables instead of hardcoding credentials:
   ```python
   import os
   FIREBASE_CONFIG = {
       "private_key": os.environ.get("FIREBASE_PRIVATE_KEY"),
       # ... other fields
   }
   ```

## Cost Considerations

Firestore pricing is based on:
- Number of document reads/writes
- Amount of data stored
- Network bandwidth

For typical usage (100-1000 chats per user):
- Writes: ~$0.18 per 100K writes
- Reads: ~$0.06 per 100K reads
- Storage: ~$0.18 per GB/month

Free tier includes:
- 50K document reads/day
- 20K document writes/day
- 1GB storage

## Additional Features

### Custom Collection Name
To use a different collection name, modify `firestore_chat.py`:

```python
def __init__(self):
    # ...
    self.collection_name = "my_custom_collection"
```

### Adding More Metadata
You can extend the metadata saved with each chat:

```python
result = self.chat_manager.save_chat(
    user_id=user_id,
    message=question,
    response=response,
    metadata={
        "email": user_email,
        "display_name": display_name,
        "session_id": session_id,  # Add custom fields
        "device": "desktop",
        "version": "1.0.0"
    }
)
```

## Support

For issues or questions:
1. Check Firebase Console logs
2. Review application console output
3. Verify Firestore security rules
4. Check service account permissions
