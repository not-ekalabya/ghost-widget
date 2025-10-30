"""
Firestore Chat Storage Module

This module provides functionality to store and retrieve user-specific chats
in Firebase Firestore with hardcoded credentials.

Features:
- Save chat messages with user ID, timestamp, and message content
- Retrieve chat history for a specific user
- Automatic timestamp generation
- Error handling and logging

Install dependencies:
    pip install firebase-admin
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from typing import List, Dict, Any, Optional
import json


# Hardcoded Firebase credentials
FIREBASE_CONFIG = {
    "type": "service_account",
    "project_id": "ghost-widget-7000",
    "private_key_id": "327f4e72fc0e89b33182dedf499109e51122c3c9",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQDb/tXAWDrOd/GR\nVHkWXMiFYQAYPeVQhzF2Yp/TRt8R/xXzvdLa5DxaPnGWB5JLJpFShaV2DnJ5BKpg\nCRUDBKVIRUe5Bhz0W5tEtufpgdvy59X/f8YHnq+WkOEUjqQsA3mqAlRBkE9gu4y5\nU4bKwwestmGT2q9qYqZhL2PMcbflqbn32EexLVU3WjNsadY3BJV3OuGO8qynMrNE\nszD9ViBi1E8PNT2wJQrYJzRKVim0NNTQTEUozojpIfJhywTlIPD4wC8Y+BF22KPk\nSA6vblT4iUUFSyNXQ6FyeDFX6D6JeG08DQ/ExRcDSd+Pf34cpP4vboEEUhKnSMw+\nXdJd2VfRAgMBAAECggEAAS+xNJW4adw1t93nvtogCEmxawmlm4PCULjpbOwJHRsh\nO1/YeKIaCgNW/Q/sMKGNnEKCPBrwPRZsWl/SKckA0/a9Rni+kTn2CJUGUFKivmWU\ncgmpv+krWZ/mxtCaGNUP9xdTuWLI1GToHMIf8o0orm+K749fU/u7zL+PrAH0+ht0\noqSJv6s4XRaivl8uLqHusdhWHvyOALcxFmQkduStxHKsRpn2qu+B3YiCwbJXSQlV\nKTUTU+GW0/W1o9a0k5PG+zb4/uq5R9tcQMpCtIjY7/XNTjK7+sY0uUYPyQ4hFbYK\nqfe/KO2pFSywTFL1aYD+cujz7cJoNtiD6TRT07jzfQKBgQDuqhYIKMrrUr3J5Onv\n6tuXrbycPWJFy7oZ7cBHIq1z0tw8tfs1lbVeBBnzK09wXgiVIHEwIEFVFS37CS0K\ngfaBul1ZQ2dFkOOpUpcPLnZgNWBO//Itd7Ug2GEcEJ5XULB/FryulQQgy+evYUmF\nQcz5k9S2hM7DDfpiO2lRd52Q8wKBgQDr+ZqOxrRkKgIX9RUoWkZ0UFo4evHEiuw1\nrPwlOnbv1skKnbnDph32isK4yQrwQwkwqb6WlgNYFaDOYhLiRxfGd1tLRAVs30NH\nPuIwCqMmczsrC9aWB7LLvG/ZyzCXzJwx8SZq1sih3yxiu9xWsNMgWWPeQ96adnES\nRgGFEI3FKwKBgQDTyfGlKfXwX8t1lwMV2VcmwZEHIN3NTB2IltezCI3do3e3FFKp\nWYHJvV/9zyg+ceOx2kk3SNhRFWtpQtpKYcwLkQL3jH3fWNT+VAEjArsfYx5k3HHf\ncUQ1sm5yhjjNCRimntmvHyO7qtadZnrkmuC3dT0k/rOwmf3gIBK0ra4QiwKBgQDW\n7eWknb+4a7q0b3nx4yfA0V8bin+i8JXs3b5bekDSeuNqU/bbCPbJk+F/xT29UJGS\nTUlWhxRMqoZo9FMW3oH9NsFkcHQwkboJrnD+KPIpF1ORBZtR03k6sEuAJ93+pVKu\n+mJvdWoQZeFbnJg4LZ5fHIwl6dNbBP5AEptXw5gdOQKBgQDQl7uppWFd6OamUOhj\nWhEq5h6fqEN2jO7iSyrF6IbWsRa943p/9jyFwYWPBGh6tKNhbZQJuS+8f5/wd3j0\nyAwf7PSclR0AXGDhhRVMB2h8Q7ibDLIP4LgoH6A0b1ZLCSRnlUvxcWMt1wByLzz9\nzA5tZ/c792MuRFfi6lyM4+smAg==\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk-iddqd@ghost-widget-7000.iam.gserviceaccount.com",
    "client_id": "103726089880083606018",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-iddqd%40ghost-widget-7000.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}


class FirestoreChatManager:
    """Manages chat storage and retrieval in Firestore"""

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern to ensure only one Firebase app instance"""
        if cls._instance is None:
            cls._instance = super(FirestoreChatManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize Firestore connection with hardcoded credentials"""
        if not FirestoreChatManager._initialized:
            try:
                # Check if Firebase app is already initialized
                if not firebase_admin._apps:
                    # Create credentials from hardcoded config
                    cred = credentials.Certificate(FIREBASE_CONFIG)
                    firebase_admin.initialize_app(cred)
                    print("✅ Firebase Admin SDK initialized successfully")

                # Get Firestore client
                self.db = firestore.client()
                self.collection_name = "chats"
                FirestoreChatManager._initialized = True
                print(f"✅ Firestore client connected to collection: {self.collection_name}")

            except Exception as e:
                print(f"❌ Failed to initialize Firestore: {e}")
                import traceback
                traceback.print_exc()
                self.db = None

    def is_available(self) -> bool:
        """Check if Firestore is available"""
        return self.db is not None

    def save_chat(
        self,
        user_id: str,
        message: str,
        response: str,
        message_type: str = "question",
        metadata: Optional[Dict[str, Any]] = None,
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Save a chat message to Firestore

        Args:
            user_id: Unique identifier for the user
            message: User's message/question
            response: AI's response
            message_type: Type of message (default: "question")
            metadata: Additional metadata (optional)
            conversation_context: Previous conversation context for threading (optional)

        Returns:
            Dictionary with success status and document ID
        """
        if not self.is_available():
            return {
                "success": False,
                "message": "Firestore is not available"
            }

        try:
            # Prepare chat document
            chat_data = {
                "user_id": user_id,
                "message": message,
                "response": response,
                "message_type": message_type,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "created_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {},
                "conversation_context": conversation_context or {}
            }

            # Save to Firestore
            doc_ref = self.db.collection(self.collection_name).add(chat_data)
            doc_id = doc_ref[1].id

            print(f"✅ Chat saved successfully: {doc_id}")
            return {
                "success": True,
                "message": "Chat saved successfully",
                "document_id": doc_id
            }

        except Exception as e:
            error_msg = f"Failed to save chat: {str(e)}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": error_msg
            }

    def retrieve_chats(
        self,
        user_id: str,
        limit: int = 50,
        order_by: str = "created_at",
        descending: bool = True
    ) -> Dict[str, Any]:
        """
        Retrieve chat history for a specific user

        Args:
            user_id: Unique identifier for the user
            limit: Maximum number of chats to retrieve (default: 50)
            order_by: Field to order by (default: "created_at")
            descending: Sort in descending order (default: True)

        Returns:
            Dictionary with success status and list of chats
        """
        if not self.is_available():
            return {
                "success": False,
                "message": "Firestore is not available",
                "chats": []
            }

        try:
            # Query Firestore for user's chats (without ordering to avoid index requirement)
            query = self.db.collection(self.collection_name).where("user_id", "==", user_id)

            # Apply limit
            query = query.limit(limit * 2)  # Get more docs to sort client-side

            # Execute query
            docs = query.stream()

            # Convert to list of dictionaries
            chats = []
            for doc in docs:
                chat_data = doc.to_dict()
                chat_data["document_id"] = doc.id
                chats.append(chat_data)

            # Sort client-side
            if chats:
                try:
                    chats.sort(key=lambda x: x.get(order_by, ""), reverse=descending)
                except Exception as e:
                    print(f"⚠️ Sorting failed, returning unsorted: {e}")

            # Apply limit after sorting
            chats = chats[:limit]

            print(f"✅ Retrieved {len(chats)} chats for user {user_id}")
            return {
                "success": True,
                "message": f"Retrieved {len(chats)} chats",
                "chats": chats,
                "count": len(chats)
            }

        except Exception as e:
            error_msg = f"Failed to retrieve chats: {str(e)}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": error_msg,
                "chats": []
            }

    def update_chat(self, document_id: str, message: str, response: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Update an existing chat document in Firestore

        Args:
            document_id: Firestore document ID to update
            message: Updated message/title
            response: Updated response
            metadata: Updated metadata (optional)

        Returns:
            Dictionary with success status
        """
        if not self.is_available():
            return {
                "success": False,
                "message": "Firestore is not available"
            }

        try:
            doc_ref = self.db.collection(self.collection_name).document(document_id)

            # Update fields
            update_data = {
                "message": message,
                "response": response,
                "timestamp": firestore.SERVER_TIMESTAMP,
            }

            if metadata:
                update_data["metadata"] = metadata

            doc_ref.update(update_data)

            print(f"✅ Chat updated successfully: {document_id}")
            return {
                "success": True,
                "message": "Chat updated successfully",
                "document_id": document_id
            }

        except Exception as e:
            error_msg = f"Failed to update chat: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "message": error_msg
            }

    def get_chat_by_id(self, document_id: str) -> Dict[str, Any]:
        """
        Retrieve a specific chat by document ID

        Args:
            document_id: Firestore document ID

        Returns:
            Dictionary with success status and chat data
        """
        if not self.is_available():
            return {
                "success": False,
                "message": "Firestore is not available"
            }

        try:
            doc_ref = self.db.collection(self.collection_name).document(document_id)
            doc = doc_ref.get()

            if doc.exists:
                chat_data = doc.to_dict()
                chat_data["document_id"] = doc.id
                return {
                    "success": True,
                    "message": "Chat retrieved successfully",
                    "chat": chat_data
                }
            else:
                return {
                    "success": False,
                    "message": "Chat not found"
                }

        except Exception as e:
            error_msg = f"Failed to retrieve chat: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "message": error_msg
            }

    def delete_chat(self, document_id: str) -> Dict[str, str]:
        """
        Delete a specific chat by document ID

        Args:
            document_id: Firestore document ID

        Returns:
            Dictionary with success status
        """
        if not self.is_available():
            return {
                "success": False,
                "message": "Firestore is not available"
            }

        try:
            self.db.collection(self.collection_name).document(document_id).delete()
            print(f"✅ Chat deleted successfully: {document_id}")
            return {
                "success": True,
                "message": "Chat deleted successfully"
            }

        except Exception as e:
            error_msg = f"Failed to delete chat: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "message": error_msg
            }

    def delete_user_chats(self, user_id: str) -> Dict[str, Any]:
        """
        Delete all chats for a specific user

        Args:
            user_id: Unique identifier for the user

        Returns:
            Dictionary with success status and deletion count
        """
        if not self.is_available():
            return {
                "success": False,
                "message": "Firestore is not available",
                "deleted_count": 0
            }

        try:
            # Query all user's chats
            docs = self.db.collection(self.collection_name).where("user_id", "==", user_id).stream()

            # Delete each document
            deleted_count = 0
            for doc in docs:
                doc.reference.delete()
                deleted_count += 1

            print(f"✅ Deleted {deleted_count} chats for user {user_id}")
            return {
                "success": True,
                "message": f"Deleted {deleted_count} chats",
                "deleted_count": deleted_count
            }

        except Exception as e:
            error_msg = f"Failed to delete user chats: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "deleted_count": 0
            }


# Example usage
if __name__ == "__main__":
    # Initialize chat manager
    chat_manager = FirestoreChatManager()

    # Example user ID
    test_user_id = "user_123"

    # Save a chat
    result = chat_manager.save_chat(
        user_id=test_user_id,
        message="What is the weather today?",
        response="I don't have access to real-time weather data.",
        metadata={"source": "test"}
    )
    print(f"Save result: {result}")

    # Retrieve chats
    result = chat_manager.retrieve_chats(user_id=test_user_id, limit=10)
    print(f"Retrieve result: {result}")

    if result["success"] and result["chats"]:
        print("\nChats:")
        for chat in result["chats"]:
            print(f"  - {chat['created_at']}: {chat['message']}")
