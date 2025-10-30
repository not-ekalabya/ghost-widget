# Firestore Chat Storage - Quick Reference

## Setup (3 Steps)

### 1. Install Package
```bash
pip install firebase-admin
```

### 2. Get Credentials
1. Firebase Console → Project Settings → Service Accounts
2. Generate New Private Key → Download JSON

### 3. Update firestore_chat.py
Replace `FIREBASE_CONFIG` with your credentials from the downloaded JSON file:
```python
FIREBASE_CONFIG = {
    "type": "service_account",
    "project_id": "YOUR_PROJECT_ID",
    "private_key_id": "YOUR_PRIVATE_KEY_ID",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "YOUR_SERVICE_ACCOUNT_EMAIL",
    "client_id": "YOUR_CLIENT_ID",
    # ... copy other fields from JSON
}
```

## Test
```bash
python test_firestore_chat.py
```

## How It Works

### Automatic Saving
When user sends a question and gets a response, it's automatically saved to Firestore.

**Location in code:** main.py:2074-2085
```python
elif typ == "RESPONSE":
    # ... save response ...
    self._save_chat_to_firestore(response_text)
```

### Manual Retrieval
Call this method to retrieve chat history:
```python
self.retrieve_user_chats(limit=10)  # Get last 10 chats
```

## Data Structure
```json
{
  "user_id": "firebase_uid",
  "message": "User question",
  "response": "AI response",
  "timestamp": "auto",
  "created_at": "2025-01-15T10:30:00Z",
  "metadata": {
    "email": "user@example.com",
    "display_name": "John Doe"
  }
}
```

## Key Files

| File | Purpose |
|------|---------|
| `firestore_chat.py` | Core Firestore chat manager |
| `main.py` | Integration with UI (lines 56-62, 541-546, 604-726, 1615-1616, 2074-2085) |
| `test_firestore_chat.py` | Test script |
| `FIRESTORE_SETUP.md` | Full setup guide |
| `requirements.txt` | Added firebase-admin |

## API Quick Reference

### Save Chat
```python
result = chat_manager.save_chat(
    user_id="user123",
    message="What is Python?",
    response="Python is...",
    metadata={"email": "user@example.com"}
)
# Returns: {"success": True, "document_id": "abc123"}
```

### Retrieve Chats
```python
result = chat_manager.retrieve_chats(
    user_id="user123",
    limit=10
)
# Returns: {"success": True, "chats": [...], "count": 10}
```

### Get Specific Chat
```python
result = chat_manager.get_chat_by_id("doc_id")
# Returns: {"success": True, "chat": {...}}
```

### Delete Chat
```python
result = chat_manager.delete_chat("doc_id")
# Returns: {"success": True, "message": "..."}
```

### Delete All User Chats
```python
result = chat_manager.delete_user_chats("user123")
# Returns: {"success": True, "deleted_count": 5}
```

## Common Issues

| Issue | Solution |
|-------|----------|
| "Firestore not available" | Install: `pip install firebase-admin` |
| "Permission denied" | Update Firestore security rules |
| Chats not saving | Check user is authenticated |
| "Import error" | Verify firebase-admin installed |

## Firestore Security Rules
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /chats/{chatId} {
      allow read, write: if request.auth != null &&
                            resource.data.user_id == request.auth.uid;
    }
  }
}
```

## Cost
**Free Tier (Daily):**
- 50,000 reads
- 20,000 writes
- 1GB storage

**Pricing:**
- $0.06 per 100K reads
- $0.18 per 100K writes
- $0.18 per GB/month storage

## Important Notes

1. **Credentials**: Never commit Firebase credentials to Git
2. **Background**: All operations run in background threads (non-blocking)
3. **Authentication**: User must be signed in to save/retrieve chats
4. **Collection**: Default collection name is "chats"
5. **Thread-Safe**: Singleton pattern ensures single Firebase connection

## Quick Test
```bash
# 1. Update credentials in firestore_chat.py
# 2. Run test
python test_firestore_chat.py

# Expected output:
# ✅ Firebase Admin SDK initialized successfully
# ✅ Chat saved successfully!
# ✅ Retrieved 2 chats successfully!
```

## Need Help?
- Full guide: `FIRESTORE_SETUP.md`
- Summary: `IMPLEMENTATION_SUMMARY.md`
- Test script: `test_firestore_chat.py`
