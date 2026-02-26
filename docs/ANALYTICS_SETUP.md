# Firebase Analytics Setup

## Important: GA4 API Secret Required

The analytics implementation now uses Google Analytics 4 (GA4) Measurement Protocol to send events to Firebase Analytics. To make this work properly, you need to configure a GA4 API Secret.

### How to Get Your GA4 API Secret

1. Go to the [Firebase Console](https://console.firebase.google.com/)
2. Select your project: **ghost-widget-7000**
3. Click on the gear icon (Settings) and select **Project settings**
4. Go to the **Integrations** tab
5. Find **Google Analytics** and click **Manage**
6. In the Google Analytics interface, go to **Admin** (bottom left)
7. Under **Property** column, click **Data Streams**
8. Select your Web data stream
9. Scroll down to **Measurement Protocol API secrets**
10. Click **Create** to generate a new API secret
11. Give it a name like "Ghost Widget Desktop App"
12. Copy the generated secret value

### Update Your Configuration

Add the API secret to your `firebase_config.json` file:

```json
{
  "apiKey": "YOUR_FIREBASE_API_KEY",
  "authDomain": "your-project.firebaseapp.com",
  "projectId": "your-project-id",
  "databaseURL": "https://your-project-default-rtdb.firebaseio.com/",
  "storageBucket": "your-project.firebasestorage.app",
  "google_client_id": "your-google-client-id.apps.googleusercontent.com",
  "google_client_secret": "your-google-client-secret",
  "messagingSenderId": "1234567890",
  "appId": "1:816342083028:web:0e0d8aa40d66bf858f2241",
  "measurementId": "G-XGLGL9E2TJ",
  "ga4_api_secret": "YOUR_API_SECRET_HERE"
}
```

### Alternative: Use the apiKey Field

Currently, the implementation tries to use the `apiKey` field as the API secret. However, this is not correct. The `apiKey` is for Firebase SDK authentication, not for GA4 Measurement Protocol.

Update `analytics.py` line 62 to use the correct field:

```python
self.api_secret = firebase_config.get("ga4_api_secret")  # Use dedicated field
```

## What Gets Tracked

The following events are now sent to Firebase Analytics:

- **app_start** - When the app launches
- **session_start** - When recording starts
- **session_end** - When recording ends (includes session metrics)
- **video_analysis** - Each time a video is analyzed
- **question_asked** - Each time a user asks a question
- **autonomous_generation** - Each autonomous content generation

## Viewing Analytics

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Navigate to **Analytics** → **Events**
4. You should see events appearing in real-time
5. For active users, go to **Analytics** → **Dashboard**

## Troubleshooting

### Events Not Appearing

1. Check console logs for `[ANALYTICS] ✓ Event sent to Firebase` messages
2. If you see `✗ Firebase response: XXX`, the API secret might be incorrect
3. Events can take 24-48 hours to appear in some Firebase Analytics reports
4. Real-time events should appear within minutes in the Firebase Console

### Need the `requests` Library

The analytics implementation requires the `requests` library. Install it with:

```bash
pip install requests
```
