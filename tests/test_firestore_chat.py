"""
Test script for Firestore Chat Manager

This script tests the basic functionality of saving and retrieving chats
from Firestore.

Usage:
    python test_firestore_chat.py
"""

from firestore_chat import FirestoreChatManager


def test_firestore_chat():
    """Test basic chat save and retrieve functionality"""
    print("=" * 60)
    print("Testing Firestore Chat Manager")
    print("=" * 60)

    # Initialize chat manager
    print("\n1. Initializing Firestore Chat Manager...")
    chat_manager = FirestoreChatManager()

    if not chat_manager.is_available():
        print("❌ Firestore Chat Manager is not available")
        print("⚠️ Make sure you have:")
        print("   - Installed firebase-admin: pip install firebase-admin")
        print("   - Updated FIREBASE_CONFIG in firestore_chat.py with your service account credentials")
        return

    print("✅ Firestore Chat Manager initialized successfully")

    # Test user ID
    test_user_id = "test_user_123"
    print(f"\n2. Using test user ID: {test_user_id}")

    # Test saving a chat
    print("\n3. Testing save_chat()...")
    save_result = chat_manager.save_chat(
        user_id=test_user_id,
        message="What is Python?",
        response="Python is a high-level, interpreted programming language known for its simplicity and readability.",
        message_type="question",
        metadata={
            "test": True,
            "source": "test_script"
        }
    )

    if save_result["success"]:
        print(f"✅ Chat saved successfully!")
        print(f"   Document ID: {save_result['document_id']}")
    else:
        print(f"❌ Failed to save chat: {save_result['message']}")
        return

    # Test saving another chat
    print("\n4. Saving another test chat...")
    save_result2 = chat_manager.save_chat(
        user_id=test_user_id,
        message="How do I install packages in Python?",
        response="You can install packages using pip: pip install package_name",
        message_type="question"
    )

    if save_result2["success"]:
        print(f"✅ Second chat saved successfully!")
        print(f"   Document ID: {save_result2['document_id']}")
    else:
        print(f"❌ Failed to save second chat: {save_result2['message']}")

    # Test retrieving chats
    print("\n5. Testing retrieve_chats()...")
    retrieve_result = chat_manager.retrieve_chats(
        user_id=test_user_id,
        limit=10
    )

    if retrieve_result["success"]:
        chats = retrieve_result["chats"]
        print(f"✅ Retrieved {len(chats)} chats successfully!")

        if chats:
            print("\n   Recent chats:")
            for i, chat in enumerate(chats[:3], 1):  # Show first 3
                print(f"\n   Chat {i}:")
                print(f"   Created: {chat.get('created_at', 'N/A')}")
                print(f"   Message: {chat.get('message', 'N/A')[:50]}...")
                print(f"   Response: {chat.get('response', 'N/A')[:50]}...")
        else:
            print("   No chats found")
    else:
        print(f"❌ Failed to retrieve chats: {retrieve_result['message']}")

    # Test getting a specific chat by ID
    if save_result["success"]:
        print(f"\n6. Testing get_chat_by_id() with ID: {save_result['document_id']}")
        get_result = chat_manager.get_chat_by_id(save_result['document_id'])

        if get_result["success"]:
            print("✅ Retrieved specific chat successfully!")
            chat = get_result["chat"]
            print(f"   Message: {chat.get('message', 'N/A')}")
            print(f"   Response: {chat.get('response', 'N/A')[:80]}...")
        else:
            print(f"❌ Failed to retrieve specific chat: {get_result['message']}")

    # Optional: Clean up test data
    print("\n7. Cleanup (optional)...")
    print("   To delete test chats, uncomment the cleanup section in the script")
    # Uncomment below to delete test chats:
    # delete_result = chat_manager.delete_user_chats(test_user_id)
    # if delete_result["success"]:
    #     print(f"✅ Deleted {delete_result['deleted_count']} test chats")
    # else:
    #     print(f"❌ Failed to delete test chats: {delete_result['message']}")

    print("\n" + "=" * 60)
    print("Testing completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_firestore_chat()
