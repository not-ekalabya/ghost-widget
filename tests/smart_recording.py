"""
Unified test script for condensed video recording approach
Tests both full recording (for review) and condensed recording (for analysis)
"""

import sys
import time
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
import mss


class CondensedVideoRecorder:
    """Records frames and creates condensed version with only changed frames"""

    def __init__(self, similarity_threshold=0.95):
        """
        Args:
            similarity_threshold: Skip frames with >N similarity (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold
        self.last_frame_hash = None
        self.interesting_frames = []
        self.all_frames = []  # Keep all frames for full video
        self.frames_kept_indices = []  # Track which frames were kept

    def _compute_frame_hash(self, frame):
        """Compute perceptual hash of frame"""
        try:
            small_frame = cv2.resize(frame, (32, 32))
            gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            avg = gray.mean()
            hash_bits = (gray > avg).flatten()
            return hash_bits
        except Exception as e:
            print(f"Error computing hash: {e}")
            return None

    def _compute_similarity(self, hash1, hash2):
        """Compute similarity between two hashes"""
        if hash1 is None or hash2 is None:
            return 0.0
        matches = np.sum(hash1 == hash2)
        return matches / len(hash1)

    def add_frame(self, frame):
        """
        Add a frame and decide if it should be kept in condensed version

        Returns:
            bool: True if frame was kept, False if skipped
        """
        frame_copy = frame.copy()
        self.all_frames.append(frame_copy)
        frame_index = len(self.all_frames) - 1

        frame_hash = self._compute_frame_hash(frame)

        # First frame is always kept
        if self.last_frame_hash is None:
            self.last_frame_hash = frame_hash
            self.interesting_frames.append(frame_copy)
            self.frames_kept_indices.append(frame_index)
            return True

        # Compare with last frame
        similarity = self._compute_similarity(self.last_frame_hash, frame_hash)

        if similarity <= self.similarity_threshold:
            # Frame is different enough - keep it!
            self.last_frame_hash = frame_hash
            self.interesting_frames.append(frame_copy)
            self.frames_kept_indices.append(frame_index)
            return True
        else:
            # Frame is too similar - skip it in condensed version
            return False

    def save_videos(self, full_video_path, condensed_video_path, fps=1):
        """
        Save both full and condensed videos

        Returns:
            dict: Statistics about both videos
        """
        if not self.all_frames:
            print("No frames to save!")
            return None

        height, width = self.all_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')

        # Save FULL video (all frames for review)
        full_writer = cv2.VideoWriter(str(full_video_path), fourcc, fps, (width, height))
        if full_writer.isOpened():
            for frame in self.all_frames:
                full_writer.write(frame)
            full_writer.release()

        # Save CONDENSED video (only interesting frames for analysis)
        condensed_writer = cv2.VideoWriter(str(condensed_video_path), fourcc, fps, (width, height))
        if condensed_writer.isOpened():
            for frame in self.interesting_frames:
                condensed_writer.write(frame)
            condensed_writer.release()

        # Calculate statistics
        full_size = full_video_path.stat().st_size if full_video_path.exists() else 0
        condensed_size = condensed_video_path.stat().st_size if condensed_video_path.exists() else 0

        frames_total = len(self.all_frames)
        frames_kept = len(self.interesting_frames)
        frames_skipped = frames_total - frames_kept
        skip_rate = (frames_skipped / frames_total * 100) if frames_total > 0 else 0

        full_duration = frames_total / fps
        condensed_duration = frames_kept / fps

        return {
            'full_video': {
                'path': str(full_video_path),
                'frames': frames_total,
                'duration': full_duration,
                'size_bytes': full_size,
            },
            'condensed_video': {
                'path': str(condensed_video_path),
                'frames': frames_kept,
                'duration': condensed_duration,
                'size_bytes': condensed_size,
            },
            'statistics': {
                'frames_skipped': frames_skipped,
                'skip_rate': skip_rate,
                'compression_ratio': (frames_kept / frames_total) if frames_total > 0 else 0,
            }
        }


def test_unified_recording():
    """
    Unified test that simulates real screen recording with condensed video approach
    Saves both full recording (for review) and condensed recording (for analysis)
    """

    print("=" * 80)
    print("UNIFIED TEST: CONDENSED VIDEO RECORDING")
    print("=" * 80)
    print()
    print("This test will:")
    print("  1. Capture real screen frames at 1 FPS for 40 seconds")
    print("  2. Create FULL video (all frames - for your review)")
    print("  3. Create CONDENSED video (only changed frames - sent to Gemini)")
    print("  4. Show cost comparison between full vs condensed")
    print("  5. Save both videos in test_recordings/ folder")
    print()
    print("Starting 40-second recording in 3 seconds...")
    time.sleep(3)
    print()

    # Setup
    test_dir = Path("test_recordings")
    test_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_video_path = test_dir / f"full_recording_{timestamp}.mp4"
    condensed_video_path = test_dir / f"condensed_recording_{timestamp}.mp4"

    recording_fps = 1
    recording_duration = 40  # seconds
    similarity_threshold = 0.95

    print(f"Recording parameters:")
    print(f"  Duration: {recording_duration} seconds")
    print(f"  FPS: {recording_fps}")
    print(f"  Similarity threshold: {similarity_threshold * 100}%")
    print()
    print("-" * 80)
    print()

    # Create recorder
    recorder = CondensedVideoRecorder(similarity_threshold=similarity_threshold)

    # Record frames from actual screen
    print("[RECORDING] Capturing your screen...")
    print()

    start_time = time.time()
    frame_count = 0
    frames_kept = 0

    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor

        while time.time() - start_time < recording_duration:
            frame_start = time.time()

            # Capture screen
            screenshot = sct.grab(monitor)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Add to recorder
            was_kept = recorder.add_frame(frame)
            frame_count += 1
            if was_kept:
                frames_kept += 1

            # Progress indicator
            elapsed = time.time() - start_time
            skip_rate = ((frame_count - frames_kept) / frame_count * 100) if frame_count > 0 else 0
            print(f"\r  Frame {frame_count}/{recording_duration} | Kept: {frames_kept} | Skipped: {frame_count - frames_kept} | Skip rate: {skip_rate:.1f}%", end='', flush=True)

            # Sleep to maintain FPS
            sleep_time = max(0, (1.0 / recording_fps) - (time.time() - frame_start))
            time.sleep(sleep_time)

    print()
    print()
    print("[OK] Recording complete!")
    print()
    print("-" * 80)
    print()

    # Save both videos
    print("[SAVING] Saving videos...")
    stats = recorder.save_videos(full_video_path, condensed_video_path, fps=recording_fps)

    if not stats:
        print("[ERROR] Failed to save videos")
        return

    # Display results
    print()
    print("=" * 80)
    print("RECORDING RESULTS")
    print("=" * 80)
    print()

    print("[FULL VIDEO] (for review):")
    print(f"   Path: {stats['full_video']['path']}")
    print(f"   Frames: {stats['full_video']['frames']}")
    print(f"   Duration: {stats['full_video']['duration']:.1f} seconds")
    print(f"   Size: {stats['full_video']['size_bytes'] / 1024:.1f} KB")
    print()

    print("[CONDENSED] (sent to Gemini):")
    print(f"   Path: {stats['condensed_video']['path']}")
    print(f"   Frames: {stats['condensed_video']['frames']}")
    print(f"   Duration: {stats['condensed_video']['duration']:.1f} seconds")
    print(f"   Size: {stats['condensed_video']['size_bytes'] / 1024:.1f} KB")
    print()

    print("[STATISTICS]:")
    print(f"   Frames skipped: {stats['statistics']['frames_skipped']}")
    print(f"   Skip rate: {stats['statistics']['skip_rate']:.1f}%")
    print(f"   Compression: {stats['statistics']['compression_ratio'] * 100:.1f}% of original")
    print()

    # Cost analysis
    print("=" * 80)
    print("COST ANALYSIS")
    print("=" * 80)
    print()

    # Gemini charges 258 tokens per second of video
    full_tokens = stats['full_video']['duration'] * 258
    condensed_tokens = stats['condensed_video']['duration'] * 258

    cost_per_million = 0.10  # Gemini Flash Lite input cost
    full_cost = (full_tokens / 1_000_000) * cost_per_million
    condensed_cost = (condensed_tokens / 1_000_000) * cost_per_million
    savings = full_cost - condensed_cost
    savings_percent = (savings / full_cost * 100) if full_cost > 0 else 0

    print("Cost per analysis:")
    print(f"   Full video:      {full_tokens:6,.0f} tokens = ${full_cost:.6f}")
    print(f"   Condensed video: {condensed_tokens:6,.0f} tokens = ${condensed_cost:.6f}")
    print(f"   SAVINGS:         {full_tokens - condensed_tokens:6,.0f} tokens = ${savings:.6f} ({savings_percent:.1f}%)")
    print()

    # Monthly projection
    print("-" * 80)
    print("MONTHLY PROJECTION (Regular User - 4 hrs/day, 360 analyses/month)")
    print("-" * 80)
    print()

    analyses_per_month = 360 * 30  # 360 per day, 30 days

    monthly_full_cost = full_cost * analyses_per_month
    monthly_condensed_cost = condensed_cost * analyses_per_month
    monthly_savings = monthly_full_cost - monthly_condensed_cost

    print(f"Monthly cost with FULL videos:      ${monthly_full_cost:.2f}")
    print(f"Monthly cost with CONDENSED videos: ${monthly_condensed_cost:.2f}")
    print(f"Monthly SAVINGS:                    ${monthly_savings:.2f} ({savings_percent:.1f}%)")
    print()

    # Profit margin
    plan_price = 12.00
    other_costs = 1.20  # Questions + Mem0

    total_cost_full = monthly_full_cost + other_costs
    total_cost_condensed = monthly_condensed_cost + other_costs

    margin_full = ((plan_price - total_cost_full) / plan_price * 100)
    margin_condensed = ((plan_price - total_cost_condensed) / plan_price * 100)

    print("PROFIT MARGIN ($12/month Personal Plan):")
    print(f"   With full videos:      ${total_cost_full:.2f} cost = {margin_full:6.1f}% margin")
    print(f"   With condensed videos: ${total_cost_condensed:.2f} cost = {margin_condensed:6.1f}% margin")
    print(f"   IMPROVEMENT:           ${total_cost_full - total_cost_condensed:.2f} saved = {margin_condensed - margin_full:6.1f}% better margin")
    print()

    # Summary
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print()
    print("[OK] Test complete! You can now:")
    print(f"   1. Play FULL video:      {full_video_path}")
    print(f"      -> See everything that was captured")
    print()
    print(f"   2. Play CONDENSED video: {condensed_video_path}")
    print(f"      -> See only what would be sent to Gemini")
    print()
    print(f"   3. Compare the two videos side-by-side")
    print(f"      -> Notice how condensed video skips static frames")
    print()
    print("[INFO] Based on your activity during the test:")
    skip_rate = stats['statistics']['skip_rate']
    if savings_percent > 70:
        print(f"   -> Your screen was mostly STATIC ({skip_rate:.0f}% similar frames)")
        print(f"   -> Condensed approach saved {savings_percent:.0f}% cost!")
    elif savings_percent > 40:
        print(f"   -> Your screen had MODERATE activity ({skip_rate:.0f}% similar frames)")
        print(f"   -> Condensed approach saved {savings_percent:.0f}% cost")
    else:
        print(f"   -> Your screen was very ACTIVE ({skip_rate:.0f}% similar frames)")
        print(f"   -> Condensed approach saved {savings_percent:.0f}% cost")
    print()


if __name__ == "__main__":
    test_unified_recording()
