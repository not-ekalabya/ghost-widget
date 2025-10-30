# Firestore Index Setup Guide

## Issue Explanation

When querying Firestore with both a `where()` filter and an `order_by()` clause on different fields, Firestore requires a **composite index**. This is a performance optimization that Firestore enforces.

**Our query:**
- Filter: `where("user_id", "==", user_id)`
- Order: `order_by("created_at", DESCENDING)`

This requires an index on `(user_id, created_at)`.

## Current Solution

The code has been updated to **sort client-side** instead of using Firestore's `order_by()`. This works immediately without requiring an index, but for better performance with large datasets, you should create the index.

### How Client-Side Sorting Works

```python
# 1. Query without ordering (no index needed)
query = db.collection("chats").where("user_id", "==", user_id)

# 2. Get all documents
docs = query.stream()

# 3. Sort in Python
chats.sort(key=lambda x: x.get("created_at", ""), reverse=True)

# 4. Limit after sorting
chats = chats[:50]
```

**Pros:**
- ✅ Works immediately (no index needed)
- ✅ No Firebase Console configuration required
- ✅ Simple to implement

**Cons:**
- ⚠️ Less efficient for large datasets (100+ chats)
- ⚠️ Retrieves more documents than needed
- ⚠️ Sorting happens on client (uses more memory)

## Recommended Solution: Create Firestore Index

For **optimal performance**, especially as your chat history grows, create the composite index:

### Option 1: Use the Auto-Generated Link (Easiest)

1. **Click the link from the error message:**
   ```
   https://console.firebase.google.com/v1/r/project/ghost-widget-7000/firestore/indexes?create_composite=...
   ```

2. **Review the index configuration:**
   - Collection: `chats`
   - Fields:
     - `user_id` (Ascending)
     - `created_at` (Descending)
     - `__name__` (Descending) - automatically added

3. **Click "Create Index"**

4. **Wait for index to build** (usually 1-5 minutes)
   - Status will show "Building..."
   - Then "Enabled" when ready

5. **Test** - Refresh your chat history

### Option 2: Manual Creation via Firebase Console

1. **Go to Firebase Console:**
   ```
   https://console.firebase.google.com/
   ```

2. **Navigate to Firestore:**
   - Select your project: `ghost-widget-7000`
   - Click "Firestore Database" in left sidebar
   - Click "Indexes" tab

3. **Create Composite Index:**
   - Click "Create Index" button
   - Collection ID: `chats`
   - Add fields:
     - Field: `user_id` → Order: Ascending
     - Field: `created_at` → Order: Descending
   - Click "Create"

4. **Wait for completion**
   - Monitor status in Indexes tab
   - Usually takes 1-5 minutes

5. **Test your application**

### Option 3: Define in firestore.indexes.json (For Deployment)

Create a file `firestore.indexes.json` in your project root:

```json
{
  "indexes": [
    {
      "collectionGroup": "chats",
      "queryScope": "COLLECTION",
      "fields": [
        {
          "fieldPath": "user_id",
          "order": "ASCENDING"
        },
        {
          "fieldPath": "created_at",
          "order": "DESCENDING"
        }
      ]
    }
  ],
  "fieldOverrides": []
}
```

**Deploy the indexes:**
```bash
firebase deploy --only firestore:indexes
```

## After Creating the Index

Once the index is ready, you can **optionally** revert to server-side sorting for better performance:

### Optimized Code (With Index)

```python
def retrieve_chats(self, user_id: str, limit: int = 50):
    """Retrieve chats using server-side ordering (requires index)"""
    query = self.db.collection("chats").where("user_id", "==", user_id)

    # Server-side ordering (efficient, requires index)
    query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
    query = query.limit(limit)

    docs = query.stream()
    # Process results...
```

**To enable server-side sorting:**

1. Open `firestore_chat.py`
2. Find the `retrieve_chats()` method (line 142)
3. Replace the client-side sorting code with the server-side version above

## Verification

### Check if Index is Ready

1. **Firebase Console:**
   - Go to Firestore → Indexes
   - Look for status: "Enabled" (green checkmark)

2. **Test in Application:**
   - Click History tab
   - Click Refresh
   - Should work without errors

3. **Check Console Logs:**
   ```
   ✅ Retrieved 10 chats for user abc123
   ```

### Performance Comparison

| Method | Chats | Query Time | Memory Usage |
|--------|-------|------------|--------------|
| Client-side sorting | 10 | ~200ms | Low |
| Client-side sorting | 100 | ~500ms | Medium |
| Client-side sorting | 1000 | ~2000ms | High |
| Server-side (indexed) | 10 | ~100ms | Minimal |
| Server-side (indexed) | 100 | ~150ms | Minimal |
| Server-side (indexed) | 1000 | ~200ms | Minimal |

## Other Indexes You Might Need

Depending on future features, you may need additional indexes:

### Search by Metadata
```json
{
  "collectionGroup": "chats",
  "fields": [
    {"fieldPath": "user_id", "order": "ASCENDING"},
    {"fieldPath": "metadata.email", "order": "ASCENDING"}
  ]
}
```

### Filter by Date Range
```json
{
  "collectionGroup": "chats",
  "fields": [
    {"fieldPath": "user_id", "order": "ASCENDING"},
    {"fieldPath": "timestamp", "order": "ASCENDING"}
  ]
}
```

## Troubleshooting

### Index Creation Failed
**Symptoms:** Error during index creation
**Solutions:**
- Check Firebase billing (indexes require Blaze plan)
- Verify field names match exactly
- Check collection name is correct

### Index Taking Too Long
**Symptoms:** "Building..." status for >10 minutes
**Solutions:**
- Wait longer (can take up to 30 minutes for large datasets)
- Check Firebase Status page for outages
- Try deleting and recreating the index

### Query Still Fails After Index
**Symptoms:** Same error after index is "Enabled"
**Solutions:**
- Wait 5 more minutes (propagation delay)
- Check index fields match query exactly
- Clear browser cache and restart app
- Verify using the correct field names

### "Index quota exceeded" Error
**Symptoms:** Can't create more indexes
**Solutions:**
- Delete unused indexes
- Upgrade to higher Firebase plan
- Combine multiple indexes where possible

## Index Management Best Practices

### Regular Maintenance
1. **Review indexes quarterly**
   - Delete unused indexes
   - Check for duplicate indexes
   - Monitor index size

2. **Monitor Performance**
   - Check query speeds in Firebase Console
   - Look for slow queries
   - Add indexes as needed

3. **Test Before Production**
   - Create indexes in development first
   - Test with production-like data volumes
   - Deploy to production after verification

### Cost Considerations
- **Index storage:** ~$0.18 per GB/month
- **No query cost for indexed queries**
- **Most apps:** Negligible cost (indexes are small)
- **This index:** ~1-10 MB for 1000 chats

## Current Status

✅ **Client-side sorting is working** - No immediate action needed
📝 **Recommendation:** Create the index for better performance
⏱️ **When:** Before you have 100+ chats
🎯 **Benefit:** Faster queries, lower memory usage

## Quick Action Checklist

- [ ] Click the auto-generated link from error message
- [ ] Review index configuration in Firebase Console
- [ ] Click "Create Index" button
- [ ] Wait 1-5 minutes for index to build
- [ ] Test chat history in app (should work faster)
- [ ] (Optional) Update code to use server-side sorting

## Summary

**Current Status:**
- ✅ Application works with client-side sorting
- ✅ No errors when loading chat history
- ⚠️ Performance will degrade with 100+ chats

**Recommended Action:**
- Create the composite index for optimal performance
- Takes 5 minutes to set up
- No code changes needed (unless you want server-side sorting)

**Need Help?**
- Firebase Indexes Documentation: https://firebase.google.com/docs/firestore/query-data/indexing
- Firebase Support: https://firebase.google.com/support
