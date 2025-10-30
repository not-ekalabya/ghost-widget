"""
Analytics tracking module for Ghost Widget
Tracks user behavior and usage patterns for cost analysis and optimization
"""

import json
import os
from datetime import datetime
from pathlib import Path
import threading
import requests
import uuid

# Optional Firebase Admin SDK for future cloud sync
try:
    import firebase_admin
    from firebase_admin import credentials
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False


class AnalyticsTracker:
    """
    Tracks user behavior using Firebase Analytics for usage monitoring and cost optimization
    """

    def __init__(self, config_path="firebase_config.json", user_id="default_user"):
        """
        Initialize the analytics tracker

        Args:
            config_path: Path to Firebase configuration JSON
            user_id: Unique identifier for the user
        """
        self.user_id = user_id
        self.session_start = datetime.now()
        self.client_id = str(uuid.uuid4())  # Unique client ID for GA4
        self.daily_stats = {
            'video_analyses': 0,
            'questions_asked': 0,
            'autonomous_generations': 0,
            'frames_captured': 0,
            'frames_skipped': 0,  # For smart frame detection
            'recording_minutes': 0,
            'gemini_tokens_input': 0,
            'gemini_tokens_output': 0,
            'claude_tokens_input': 0,
            'claude_tokens_output': 0,
            'cost_estimate': 0.0,
        }
        self.lock = threading.Lock()

        # Initialize analytics (local tracking, Firebase optional)
        try:
            config_path = Path(config_path)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    firebase_config = json.load(f)
                self.project_id = "ghost-widget-7000"
                self.measurement_id = "G-XGLGL9E2TJ" # replace with google-config
                # Try dedicated GA4 API secret first, fall back to apiKey (for backwards compatibility)
                self.api_secret = "AIzaSyBsig0QxBmVelZQwef23-MoTFdeuZM5P-4"
            else:
                self.project_id = None
                self.measurement_id = None
                self.api_secret = None

            # Enable local tracking (always works)
            self.enabled = True
            print(f"[OK] Analytics initialized for user: {user_id}")

            # Firebase cloud sync via GA4 Measurement Protocol
            self.firebase_enabled = False
            if self.measurement_id and self.api_secret:
                print(f"   Firebase Analytics: {self.measurement_id} (cloud sync enabled)")
                self.firebase_enabled = True
                # Track app start
                self._send_to_firebase('app_start', {})
            else:
                print(f"   Firebase Analytics: disabled (missing configuration)")

        except Exception as e:
            print(f"[WARNING] Failed to initialize analytics: {e}")
            print(f"   Analytics will continue with basic tracking.")
            self.enabled = True  # Still enable basic tracking

    def _send_to_firebase(self, event_name, params):
        """
        Send event to Firebase Analytics via GA4 Measurement Protocol
        https://developers.google.com/analytics/devguides/collection/protocol/ga4
        """
        if not self.firebase_enabled:
            return

        try:
            # GA4 Measurement Protocol endpoint
            url = f"https://www.google-analytics.com/mp/collect?measurement_id={self.measurement_id}&api_secret={self.api_secret}"

            # Prepare the payload
            payload = {
                "client_id": self.client_id,
                "user_id": self.user_id,
                "events": [{
                    "name": event_name,
                    "params": params
                }]
            }

            # Send asynchronously to avoid blocking
            threading.Thread(target=self._send_request, args=(url, payload), daemon=True).start()

        except Exception as e:
            print(f"[WARNING] Failed to send analytics to Firebase: {e}")

    def _send_request(self, url, payload):
        """Helper to send the actual HTTP request"""
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 204:
                print(f"[ANALYTICS] ✓ Event sent to Firebase")
            else:
                print(f"[ANALYTICS] ✗ Firebase response: {response.status_code}")
        except Exception as e:
            print(f"[WARNING] Analytics request failed: {e}")

    def track_event(self, event_name, params=None):
        """
        Track a custom event

        Args:
            event_name: Name of the event
            params: Dictionary of event parameters
        """
        if not self.enabled:
            return

        try:
            params = params or {}
            params['user_id'] = self.user_id
            params['timestamp'] = datetime.now().isoformat()

            # Log event locally
            print(f"[ANALYTICS] {event_name} - {params}")

            # Send to Firebase Analytics
            self._send_to_firebase(event_name, params)

        except Exception as e:
            print(f"[WARNING] Analytics tracking error: {e}")

    def track_video_analysis(self, duration_seconds, frames_captured, frames_skipped=0, cost=0.0):
        """Track a video analysis event"""
        with self.lock:
            self.daily_stats['video_analyses'] += 1
            self.daily_stats['frames_captured'] += frames_captured
            self.daily_stats['frames_skipped'] += frames_skipped
            self.daily_stats['recording_minutes'] += duration_seconds / 60
            self.daily_stats['cost_estimate'] += cost

        self.track_event('video_analysis', {
            'duration_seconds': duration_seconds,
            'frames_captured': frames_captured,
            'frames_skipped': frames_skipped,
            'skip_rate': (frames_skipped / (frames_captured + frames_skipped)) if (frames_captured + frames_skipped) > 0 else 0,
            'cost_usd': cost,
        })

    def track_question(self, model_used, tokens_input, tokens_output, cost=0.0):
        """Track a question/answer event"""
        with self.lock:
            self.daily_stats['questions_asked'] += 1
            if model_used.lower() == 'claude':
                self.daily_stats['claude_tokens_input'] += tokens_input
                self.daily_stats['claude_tokens_output'] += tokens_output
            else:
                self.daily_stats['gemini_tokens_input'] += tokens_input
                self.daily_stats['gemini_tokens_output'] += tokens_output
            self.daily_stats['cost_estimate'] += cost

        self.track_event('question_asked', {
            'model': model_used,
            'tokens_input': tokens_input,
            'tokens_output': tokens_output,
            'cost_usd': cost,
        })

    def track_autonomous_generation(self, cost=0.0):
        """Track an autonomous content generation event"""
        with self.lock:
            self.daily_stats['autonomous_generations'] += 1
            self.daily_stats['cost_estimate'] += cost

        self.track_event('autonomous_generation', {
            'cost_usd': cost,
        })

    def track_session_start(self):
        """Track when user starts a recording session"""
        self.session_start = datetime.now()
        self.track_event('session_start', {
            'user_id': self.user_id,
        })

    def track_session_end(self):
        """Track when user ends a recording session"""
        session_duration = (datetime.now() - self.session_start).total_seconds()

        with self.lock:
            stats = self.daily_stats.copy()

        self.track_event('session_end', {
            'session_duration_seconds': session_duration,
            'video_analyses': stats['video_analyses'],
            'questions_asked': stats['questions_asked'],
            'autonomous_generations': stats['autonomous_generations'],
            'recording_minutes': stats['recording_minutes'],
            'frames_captured': stats['frames_captured'],
            'frames_skipped': stats['frames_skipped'],
            'cost_estimate_usd': stats['cost_estimate'],
        })

    def get_daily_stats(self):
        """Get current daily statistics"""
        with self.lock:
            return self.daily_stats.copy()

    def print_daily_summary(self):
        """Print a summary of today's usage"""
        stats = self.get_daily_stats()

        print("\n" + "="*60)
        print("📊 DAILY USAGE SUMMARY")
        print("="*60)
        print(f"👤 User: {self.user_id}")
        print(f"📹 Video Analyses: {stats['video_analyses']}")
        print(f"   ├─ Recording Time: {stats['recording_minutes']:.1f} minutes")
        print(f"   ├─ Frames Captured: {stats['frames_captured']}")
        print(f"   └─ Frames Skipped: {stats['frames_skipped']} ({stats['frames_skipped']/(stats['frames_captured']+stats['frames_skipped'])*100 if (stats['frames_captured']+stats['frames_skipped']) > 0 else 0:.1f}%)")
        print(f"❓ Questions Asked: {stats['questions_asked']}")
        print(f"🤖 Autonomous Generations: {stats['autonomous_generations']}")
        print(f"\n💰 TOKEN USAGE:")
        print(f"   Gemini: {stats['gemini_tokens_input']:,} input, {stats['gemini_tokens_output']:,} output")
        print(f"   Claude: {stats['claude_tokens_input']:,} input, {stats['claude_tokens_output']:,} output")
        print(f"\n💵 ESTIMATED COST: ${stats['cost_estimate']:.4f}")
        print("="*60 + "\n")

    def reset_daily_stats(self):
        """Reset daily statistics (call at midnight or on new day)"""
        with self.lock:
            for key in self.daily_stats:
                if isinstance(self.daily_stats[key], int):
                    self.daily_stats[key] = 0
                elif isinstance(self.daily_stats[key], float):
                    self.daily_stats[key] = 0.0
