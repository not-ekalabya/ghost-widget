import os
import time
import json
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from PIL import ImageGrab, Image
import threading
import argparse
import psutil
import re
from typing import List, Dict, Any
import io
import numpy as np
import pyperclip  # For clipboard operations
import cv2  # OpenCV for video encoding
import mss  # Fast screen capture
from queue import Queue, Empty  # For parallel video analysis
import hashlib  # For frame comparison

# Analytics tracking
try:
    from analytics import AnalyticsTracker
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    print("Warning: analytics module not available. Usage tracking disabled.")

# Local Memory System (privacy-focused, local-only storage)
try:
    from local_memory import LocalMemorySystem
    LOCAL_MEMORY_AVAILABLE = True
except ImportError:
    LOCAL_MEMORY_AVAILABLE = False
    print("Warning: local_memory module not available. Memory storage disabled.")

# Google grounding for web search
try:
    from google.genai import types
    GROUNDING_AVAILABLE = True
except ImportError:
    GROUNDING_AVAILABLE = False
    print("Warning: Google genai library doesn't support grounding. Using fallback search.")

# Anthropic Claude on Vertex AI integration
try:
    from anthropic import AnthropicVertex
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    print("Warning: anthropic package not installed. Install with: pip install 'anthropic[vertex]'")

# GitHub integration
try:
    from github_auth import get_github_auth
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    print("Warning: GitHub integration not available. Install with: pip install PyGithub")

class BackgroundCompanion:
    def __init__(self, api_key, capture_interval=10, watch_dirs=None, always_recent=3, autonomous_mode=False, autonomous_interval=180, autonomous_output="autonomous_content.txt", user_id="default_user", progress_callback=None, qa_model="gemini", recording_fps=1, analysis_interval=40, skip_static_threshold=70.0, save_recordings=False):
        """
        Initialize the background companion with RAG support and autonomous content generation

        Args:
            api_key: Google Gemini API key
            capture_interval: DEPRECATED - use analysis_interval instead
            watch_dirs: List of directories to watch for file context
            always_recent: Number of most recent contexts to always include (default: 3)
            autonomous_mode: Whether to run in autonomous mode
            autonomous_interval: Seconds between autonomous content generation
            autonomous_output: File path for autonomous content
            user_id: User identifier for per-user memory separation (default: "default_user")
            progress_callback: Callback function for progress updates (for GUI)
            qa_model: Model to use for question answering - "claude" or "gemini" (default: "gemini")
                     Note: Screenshot analysis always uses Gemini regardless of this setting
            recording_fps: Frames per second for video recording (default: 1)
            analysis_interval: Seconds between video analysis (default: 40)
            skip_static_threshold: Skip analysis if >N% of frames are static (default: 70.0)
                                   Set to 100 to never skip, 0 to always skip
            save_recordings: Whether to save video recordings and screenshots to disk (default: False)
                            Set to True to enable saving for debugging or review purposes
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-flash-lite-latest')
        self.api_key = api_key
        self.capture_interval = analysis_interval if analysis_interval else capture_interval  # Backward compatibility
        self.analysis_interval = analysis_interval if analysis_interval else capture_interval
        self.recording_fps = recording_fps
        self.running = False
        self.video_dir = Path("recordings")
        self.video_dir.mkdir(exist_ok=True)
        self.screenshot_dir = Path("screenshots")  # Keep for backward compatibility
        self.screenshot_dir.mkdir(exist_ok=True)
        self.watch_dirs = watch_dirs or []
        self.always_recent = always_recent
        self.autonomous_mode = autonomous_mode
        self.autonomous_interval = autonomous_interval
        self.autonomous_output = Path(autonomous_output)
        self.last_autonomous_check = 0
        self.progress_callback = progress_callback  # For GUI progress updates
        self.user_id = user_id  # Store user_id for per-user memory separation
        self.qa_model = qa_model.lower()  # Store preferred QA model ("claude" or "gemini")
        self.save_recordings = save_recordings  # Whether to save recordings/screenshots to disk

        # Video recording state
        self.video_writer = None
        self.current_video_path = None
        self.video_start_time = None
        self.screen_size = None  # Will be set on first recording

        # Smart frame detection and cost optimization
        self.last_frame_hash = None
        self.frames_skipped = 0
        self.frame_similarity_threshold = 0.95  # Frame comparison: skip if >95% similar
        self.skip_static_threshold = skip_static_threshold  # Skip entire analysis if >N% frames static

        # Condensed video approach - store frames in memory
        self.all_frames = []  # All captured frames for full video
        self.interesting_frames = []  # Only changed frames for condensed video
        self.frames_kept_indices = []  # Track which frames were kept

        # Analytics tracking
        self.analytics = None
        if ANALYTICS_AVAILABLE:
            try:
                self.analytics = AnalyticsTracker(user_id=user_id)
            except Exception as e:
                print(f"⚠️ Failed to initialize analytics: {e}")

        # Parallel video analysis queue and worker thread
        self.analysis_queue = Queue(maxsize=5)  # Limit queue to prevent memory issues
        self.analysis_thread = None
        self.analysis_running = False

        # Initialize Local Memory System (privacy-focused, local-only storage)
        self.use_local_memory = LOCAL_MEMORY_AVAILABLE
        self.local_memory = None
        if self.use_local_memory:
            try:
                # Initialize LocalMemorySystem with temporal awareness
                self.local_memory = LocalMemorySystem(
                    api_key=api_key,
                    user_id=self.user_id,
                    db_path="local_memory_db",  # Local storage directory
                    temporal_decay_days=30  # Temporal decay over 30 days
                )
                print(f"✓ Local memory system initialized for user: {self.user_id}")

                # Verify ChromaDB is working properly
                try:
                    stats = self.local_memory.get_stats()
                    print(f"✓ ChromaDB verified: {stats.get('total_memories', 0)} memories stored")
                except Exception as verify_err:
                    print(f"❌ ChromaDB verification failed: {verify_err}")
                    print("   Memory storage will NOT work without ChromaDB!")
                    print("   Please check your API key and ChromaDB installation")
                    self.use_local_memory = False
                    self.local_memory = None

            except Exception as e:
                print(f"❌ Failed to initialize ChromaDB: {e}")
                print("   Memory storage will NOT work!")
                print("   Please install ChromaDB: pip install chromadb")
                print("   And ensure your API key is valid")
                import traceback
                traceback.print_exc()
                self.use_local_memory = False
                self.local_memory = None

        # Initialize Claude for question answering (via Vertex AI)
        self.claude_client = None
        if CLAUDE_AVAILABLE:
            try:
                # Get Google Cloud project ID from environment or use default
                # User should set GOOGLE_CLOUD_PROJECT environment variable
                project_id = "ghost-widget-7000"
                region = "us-east5"

                self.claude_client = AnthropicVertex(project_id=project_id, region=region)
                print(f"OK Claude 4.5 Sonnet initialized via Vertex AI (project: {project_id}, region: {region})")
            except Exception as e:
                print(f"WARNING Failed to initialize Claude on Vertex AI: {e}")
                print("   Falling back to Gemini for question answering")
                self.claude_client = None

        # Define available tools for Gemini
        self.tools = self._define_tools()

    def _emit_progress(self, event_type: str, data: dict):
        """Emit progress update to GUI if callback is set"""
        if self.progress_callback:
            try:
                self.progress_callback(event_type, data)
            except Exception as e:
                print(f"Error in progress callback: {e}")
    
    def _define_tools(self):
        """Define tools for Gemini function calling"""
        return [
            {
                "function_declarations": [
                    {
                        "name": "read_file_as_text",
                        "description": "Read the contents of any file type as extracted text. Use this for text files, PDFs, Word documents (.docx), Excel files (.xlsx), PowerPoint (.pptx), and CSV files. This will return human-readable text content.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "The full path to the file to read. Supports: text, .pdf, .docx, .doc, .xlsx, .xls, .pptx, .csv, and more"
                                }
                            },
                            "required": ["file_path"]
                        }
                    },
                    {
                        "name": "read_file_with_vision",
                        "description": "Read and analyze a file using Gemini's vision capabilities. Use this for images (.png, .jpg, .jpeg, .gif, etc.), PDFs with complex layouts, or Word documents you want to analyze visually. Returns AI-generated description and extracted content.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "The full path to the file to analyze with vision AI"
                                }
                            },
                            "required": ["file_path"]
                        }
                    },
                    {
                        "name": "list_directory",
                        "description": "List files and directories in a given path",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "directory_path": {
                                    "type": "string",
                                    "description": "The directory path to list"
                                }
                            },
                            "required": ["directory_path"]
                        }
                    },
                    {
                        "name": "get_file_info",
                        "description": "Get metadata about a file (size, modified date, etc.)",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "The file path to get info about"
                                }
                            },
                            "required": ["file_path"]
                        }
                    },
                    {
                        "name": "search_files",
                        "description": "Search for files by name pattern. ONLY use this when you have a SPECIFIC file name or pattern from the captured context. DO NOT use for exploratory searching. If you don't know where a file is, ask the user instead.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "pattern": {
                                    "type": "string",
                                    "description": "The specific file name or pattern to search for (e.g., 'report.pdf', 'main.py', '*.config')"
                                },
                                "search_scope": {
                                    "type": "string",
                                    "description": "Search scope: 'watched' (default - watched directories), 'home' (user home directory), 'desktop' (desktop folder). NEVER use 'system' - it's too slow.",
                                    "enum": ["watched", "home", "desktop"]
                                },
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of results to return (default: 20)"
                                }
                            },
                            "required": ["pattern"]
                        }
                    },
                    {
                        "name": "get_recent_files",
                        "description": "Get recently modified files from watched directories",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "hours": {
                                    "type": "number",
                                    "description": "Number of hours to look back"
                                }
                            },
                            "required": ["hours"]
                        }
                    },
                    {
                        "name": "search_web",
                        "description": "Search the web for current information, facts, news, or real-time data using Google Search. Use this when you need information that may not be in the captured contexts or when you need up-to-date information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query (e.g., 'latest Python version', 'current weather in Tokyo', 'recent AI news')"
                                }
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "store_memory",
                        "description": "Store important information to long-term local memory with temporal awareness. Use this when you observe something significant, novel, or worth remembering about the user's screen activity. Memories are stored locally (privacy-focused) with semantic search and temporal decay. Only call this for truly important information, not routine/repetitive activity.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "The detailed content to store as a memory. Should be comprehensive and include context about what the user was doing."
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "A brief one-sentence summary of this memory"
                                },
                                "importance": {
                                    "type": "string",
                                    "description": "Importance level of this memory",
                                    "enum": ["low", "medium", "high"]
                                },
                                "tags": {
                                    "type": "array",
                                    "description": "Tags for categorizing this memory (e.g., ['coding', 'python', 'bug-fix'])",
                                    "items": {
                                        "type": "string"
                                    }
                                }
                            },
                            "required": ["content", "summary", "importance"]
                        }
                    },
                    {
                        "name": "github_get_commits",
                        "description": "Get recent commits from a GitHub repository. Requires GitHub authentication. Use this to get commit history, messages, authors, and code changes for blog posts or analysis.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo' (e.g., 'facebook/react', 'torvalds/linux')"
                                },
                                "count": {
                                    "type": "number",
                                    "description": "Number of commits to retrieve (default: 10, max: 50)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_get_repo_info",
                        "description": "Get detailed information about a GitHub repository including description, stars, forks, language, etc. Requires GitHub authentication.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo' (e.g., 'facebook/react', 'anthropics/anthropic-sdk-python')"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_search_repos",
                        "description": "Search for GitHub repositories by keyword. Requires GitHub authentication. Useful for finding repositories related to a topic.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query (e.g., 'machine learning python', 'react hooks', 'rust game engine')"
                                },
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of results to return (default: 10)"
                                }
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "github_get_user_repos",
                        "description": "Get all repositories for the authenticated GitHub user, sorted by most recently updated. Use this to discover and search through the user's repositories when they mention a project name without specifying the full repository path. Returns a list with 'full_name' field that contains the complete 'owner/repo' format you should use with other GitHub tools.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of repositories to return (default: 100)"
                                }
                            }
                        }
                    },
                    {
                        "name": "github_get_readme",
                        "description": "Get the README content from a GitHub repository. Useful for understanding what a repository is about and finding the right repository based on its description and documentation.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo' (e.g., 'facebook/react')"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_get_pull_requests",
                        "description": "Get pull requests from a GitHub repository. Returns comprehensive PR information including state, author, changes, reviews, and merge status.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "state": {
                                    "type": "string",
                                    "description": "PR state: 'open', 'closed', or 'all' (default: 'all')",
                                    "enum": ["open", "closed", "all"]
                                },
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of PRs to return (default: 30)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_get_issues",
                        "description": "Get issues from a GitHub repository. Returns issue information including state, labels, assignees, and comments.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "state": {
                                    "type": "string",
                                    "description": "Issue state: 'open', 'closed', or 'all' (default: 'all')",
                                    "enum": ["open", "closed", "all"]
                                },
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of issues to return (default: 30)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_get_branches",
                        "description": "Get branches from a GitHub repository. Returns branch names, protection status, and latest commit information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of branches to return (default: 30)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_get_commit_details",
                        "description": "Get detailed information about a specific commit including file changes, diffs, and statistics. Use this to analyze what changed in a particular commit.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "commit_sha": {
                                    "type": "string",
                                    "description": "The commit SHA or hash to retrieve details for"
                                }
                            },
                            "required": ["repo_name", "commit_sha"]
                        }
                    },
                    {
                        "name": "github_get_contributors",
                        "description": "Get contributors to a GitHub repository. Returns contributor usernames, contribution counts, and profile information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of contributors to return (default: 30)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_get_releases",
                        "description": "Get releases from a GitHub repository. Returns release tags, names, dates, release notes, and download URLs.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "max_results": {
                                    "type": "number",
                                    "description": "Maximum number of releases to return (default: 10)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_list_directory",
                        "description": "List contents of a directory in a GitHub repository. Returns files and subdirectories with their metadata. Use empty string for root directory.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "path": {
                                    "type": "string",
                                    "description": "Path within the repository (empty string for root directory, e.g., 'src' or 'docs/api')"
                                },
                                "ref": {
                                    "type": "string",
                                    "description": "Optional branch/tag/commit to read from (default: default branch)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                    {
                        "name": "github_read_file",
                        "description": "Read the complete content of a file from a GitHub repository. Returns the full file content as text.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "file_path": {
                                    "type": "string",
                                    "description": "Path to the file within the repository (e.g., 'README.md', 'src/main.py')"
                                },
                                "ref": {
                                    "type": "string",
                                    "description": "Optional branch/tag/commit to read from (default: default branch)"
                                }
                            },
                            "required": ["repo_name", "file_path"]
                        }
                    },
                    {
                        "name": "github_get_tree",
                        "description": "Get the complete file tree structure of a GitHub repository. Returns all files and directories recursively. Useful for understanding the full project structure.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "repo_name": {
                                    "type": "string",
                                    "description": "Repository name in format 'owner/repo'"
                                },
                                "ref": {
                                    "type": "string",
                                    "description": "Optional branch/tag/commit to read from (default: default branch)"
                                },
                                "recursive": {
                                    "type": "boolean",
                                    "description": "Get full tree recursively (default: true)"
                                }
                            },
                            "required": ["repo_name"]
                        }
                    },
                ]
            }
        ]
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using Gemini"""
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    
    def _capture_screenshot(self):
        """Capture current screenshot (kept for backward compatibility)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = self.screenshot_dir / f"screen_{timestamp}.png"

        try:
            screenshot = ImageGrab.grab()
            screenshot.save(screenshot_path)
            return str(screenshot_path)
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return None

    def _start_video_recording(self):
        """Start recording a new video chunk"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Get screen dimensions using a fresh mss instance
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Primary monitor
                width = monitor["width"]
                height = monitor["height"]
                self.screen_size = (width, height)

            # Initialize video writer with codec/container combinations that actually work
            import platform
            is_windows = platform.system() == 'Windows'

            if is_windows:
                # Windows: Use mp4v with .mp4 (universally playable) or MJPEG with .avi
                codecs_to_try = [
                    ('mp4v', 'MPEG-4', '.mp4'),  # Most compatible for Windows
                    ('MJPG', 'MJPEG', '.avi'),   # Works but larger files
                ]
            else:
                # Linux/Mac: Try h264, x264, or mp4v with .mp4
                codecs_to_try = [
                    ('avc1', 'H.264', '.mp4'),
                    ('X264', 'x264', '.mp4'),
                    ('mp4v', 'MPEG-4', '.mp4'),
                ]

            self.video_writer = None
            self.current_video_path = None

            for codec_code, codec_name, extension in codecs_to_try:
                try:
                    # Set filename with appropriate extension for codec
                    video_path = self.video_dir / f"recording_{timestamp}{extension}"

                    fourcc = cv2.VideoWriter_fourcc(*codec_code)
                    writer = cv2.VideoWriter(
                        str(video_path),
                        fourcc,
                        self.recording_fps,
                        self.screen_size
                    )
                    if writer.isOpened():
                        self.video_writer = writer
                        self.current_video_path = video_path
                        print(f"   🎬 Using: {codec_name} ({codec_code}) in {extension} container")
                        break
                    else:
                        writer.release()
                except Exception as e:
                    # Silently try next codec
                    continue

            if not self.video_writer or not self.video_writer.isOpened():
                raise Exception("Failed to initialize video writer with any codec")

            self.video_start_time = time.time()
            self.frames_skipped = 0  # Reset frame skip counter
            self.last_frame_hash = None  # Reset frame comparison

            # Reset frame storage for condensed video approach
            self.all_frames = []
            self.interesting_frames = []
            self.frames_kept_indices = []

            return True

        except Exception as e:
            print(f"Error starting video recording: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _capture_frame(self):
        """Capture a single frame and add it to the video with smart frame detection"""
        try:
            if not self.video_writer:
                return False

            # Capture screen using mss (faster than PIL) - create fresh instance each time
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Primary monitor
                screenshot = sct.grab(monitor)

                # Convert to numpy array and then to BGR for OpenCV
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                # Store a copy of the frame in memory for condensed video approach
                frame_copy = frame.copy()
                self.all_frames.append(frame_copy)
                frame_index = len(self.all_frames) - 1

                # Smart frame detection - compare with previous frame
                # Use perceptual hashing for efficient comparison
                frame_hash = self._compute_frame_hash(frame)

                is_similar = False
                if self.last_frame_hash is not None:
                    similarity = self._compute_hash_similarity(self.last_frame_hash, frame_hash)

                    # Check if frame is too similar (no significant change)
                    if similarity > self.frame_similarity_threshold:
                        self.frames_skipped += 1
                        is_similar = True
                        # DON'T update hash for similar frames to maintain comparison baseline

                # Only update hash if frame is different
                if not is_similar:
                    self.last_frame_hash = frame_hash
                    # Store this frame as "interesting" for condensed video
                    self.interesting_frames.append(frame_copy)
                    self.frames_kept_indices.append(frame_index)

                # Always write frame to full video writer for continuity
                self.video_writer.write(frame)

            return True

        except Exception as e:
            print(f"Error capturing frame: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _compute_frame_hash(self, frame):
        """Compute a perceptual hash of a frame for similarity comparison"""
        try:
            # Resize to small size for faster comparison
            small_frame = cv2.resize(frame, (32, 32))
            # Convert to grayscale
            gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            # Compute average hash
            avg = gray.mean()
            # Create binary hash
            hash_bits = (gray > avg).flatten()
            return hash_bits
        except Exception as e:
            print(f"Error computing frame hash: {e}")
            return None

    def _compute_hash_similarity(self, hash1, hash2):
        """Compute similarity between two frame hashes (0.0 to 1.0)"""
        try:
            if hash1 is None or hash2 is None:
                return 0.0
            # Compute Hamming distance
            matches = np.sum(hash1 == hash2)
            similarity = matches / len(hash1)
            return similarity
        except Exception as e:
            print(f"Error computing hash similarity: {e}")
            return 0.0

    def _stop_video_recording(self):
        """
        Stop recording and create both full and condensed videos

        Returns:
            dict: {
                'full_video_path': Path to full recording (all frames),
                'condensed_video_path': Path to condensed recording (only changed frames),
                'frames_total': Total frames captured,
                'frames_kept': Frames in condensed video,
                'frames_skipped': Frames skipped from condensed video,
                'skip_rate': Percentage of frames skipped,
                'compression_ratio': Ratio of condensed to full
            }
        """
        try:
            # Release the temporary video writer (we don't need its output)
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None

            # Delete the temporary full video file since we'll create new ones from memory
            if self.current_video_path and self.current_video_path.exists():
                try:
                    self.current_video_path.unlink()
                except:
                    pass

            self.current_video_path = None
            self.video_start_time = None

            # Check if we have frames to save
            if not self.all_frames:
                print(f"   ❌ No frames captured!")
                return None

            # Calculate statistics
            frames_total = len(self.all_frames)
            frames_kept = len(self.interesting_frames)
            frames_skipped = frames_total - frames_kept
            skip_rate = (frames_skipped / frames_total * 100) if frames_total > 0 else 0
            compression_ratio = (frames_kept / frames_total) if frames_total > 0 else 0

            print(f"   📊 Video stats: {frames_total} frames total, {frames_kept} kept ({compression_ratio*100:.1f}%), {frames_skipped} skipped ({skip_rate:.1f}%)")

            # Only save videos to disk if save_recordings is enabled
            if not self.save_recordings:
                print(f"   ℹ️ Recording saving disabled. Videos kept in memory only (set save_recordings=True to enable saving)")

                # Still need to create a TEMPORARY video for Gemini analysis
                # Use interesting frames if we have any, otherwise use all frames
                frames_to_analyze = self.interesting_frames if frames_kept > 0 else self.all_frames

                if frames_to_analyze:
                    # Get frame dimensions
                    height, width = frames_to_analyze[0].shape[:2]

                    # Determine codec/container based on platform
                    import platform
                    is_windows = platform.system() == 'Windows'

                    if is_windows:
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        extension = '.mp4'
                    else:
                        fourcc = cv2.VideoWriter_fourcc(*'avc1')
                        extension = '.mp4'

                    # Create temporary video file for analysis
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    temp_video_path = self.video_dir / f"temp_analysis_{timestamp}{extension}"
                    print(f"   📹 Creating temporary video for analysis...")

                    temp_writer = cv2.VideoWriter(
                        str(temp_video_path),
                        fourcc,
                        self.recording_fps,
                        (width, height)
                    )

                    if temp_writer.isOpened():
                        for frame in frames_to_analyze:
                            temp_writer.write(frame)
                        temp_writer.release()

                        # Verify temp video
                        if self._verify_video(temp_video_path):
                            print(f"   ✅ Temporary video created for analysis")
                            # Return temp video path for analysis
                            return {
                                'full_video_path': None,  # No saved full video
                                'condensed_video_path': str(temp_video_path),  # Temp video for analysis
                                'frames_total': frames_total,
                                'frames_kept': frames_kept,
                                'frames_skipped': frames_skipped,
                                'skip_rate': skip_rate,
                                'compression_ratio': compression_ratio,
                                'is_temp': True  # Flag to indicate this should be deleted after analysis
                            }
                        else:
                            print(f"   ⚠️ Temporary video verification failed")
                    else:
                        print(f"   ❌ Failed to create temporary video")

                # Fallback: return None if temp video creation failed
                return {
                    'full_video_path': None,
                    'condensed_video_path': None,
                    'frames_total': frames_total,
                    'frames_kept': frames_kept,
                    'frames_skipped': frames_skipped,
                    'skip_rate': skip_rate,
                    'compression_ratio': compression_ratio
                }

            # Get frame dimensions
            height, width = self.all_frames[0].shape[:2]

            # Determine codec/container based on platform
            import platform
            is_windows = platform.system() == 'Windows'

            if is_windows:
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                extension = '.mp4'
            else:
                fourcc = cv2.VideoWriter_fourcc(*'avc1')
                extension = '.mp4'

            # Generate timestamp for filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Save FULL video (all frames - for review)
            full_video_path = self.video_dir / f"full_recording_{timestamp}{extension}"
            print(f"   💾 Saving full video to disk...")
            full_writer = cv2.VideoWriter(
                str(full_video_path),
                fourcc,
                self.recording_fps,
                (width, height)
            )

            if full_writer.isOpened():
                for frame in self.all_frames:
                    full_writer.write(frame)
                full_writer.release()

                # Verify full video
                if self._verify_video(full_video_path):
                    print(f"   ✅ Full video saved: {full_video_path.name}")
                else:
                    print(f"   ⚠️ Full video may have issues: {full_video_path.name}")
            else:
                print(f"   ❌ Failed to create full video writer")
                return None

            # Save CONDENSED video (only interesting frames - for Gemini analysis)
            condensed_video_path = self.video_dir / f"condensed_recording_{timestamp}{extension}"
            print(f"   💾 Saving condensed video...")
            condensed_writer = cv2.VideoWriter(
                str(condensed_video_path),
                fourcc,
                self.recording_fps,
                (width, height)
            )

            if condensed_writer.isOpened():
                for frame in self.interesting_frames:
                    condensed_writer.write(frame)
                condensed_writer.release()

                # Verify condensed video
                if self._verify_video(condensed_video_path):
                    print(f"   ✅ Condensed video saved: {condensed_video_path.name}")
                else:
                    print(f"   ⚠️ Condensed video may have issues: {condensed_video_path.name}")
            else:
                print(f"   ❌ Failed to create condensed video writer")
                # Still return full video path
                return {
                    'full_video_path': str(full_video_path),
                    'condensed_video_path': None,
                    'frames_total': frames_total,
                    'frames_kept': frames_kept,
                    'frames_skipped': frames_skipped,
                    'skip_rate': skip_rate,
                    'compression_ratio': compression_ratio
                }

            # Return both paths and statistics
            return {
                'full_video_path': str(full_video_path),
                'condensed_video_path': str(condensed_video_path),
                'frames_total': frames_total,
                'frames_kept': frames_kept,
                'frames_skipped': frames_skipped,
                'skip_rate': skip_rate,
                'compression_ratio': compression_ratio
            }

        except Exception as e:
            print(f"Error stopping video recording: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _verify_video(self, video_path):
        """Verify that a video file is valid and playable"""
        try:
            # Try to open the video with OpenCV
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                cap.release()
                return False

            # Check that we can read at least one frame
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return False

            # Check file size is reasonable (not empty)
            file_size = video_path.stat().st_size
            if file_size < 1024:  # Less than 1KB is suspicious
                print(f"   ⚠️ Video file is too small ({file_size} bytes)")
                return False

            print(f"   ✅ Video verified: {file_size / 1024:.1f} KB")
            return True

        except Exception as e:
            print(f"   ⚠️ Video verification error: {e}")
            return False

    def _analyze_video_with_gemini(self, video_path, active_context, is_temp_file=False):
        """
        Analyze a video recording using Gemini Flash with vision capabilities.
        Uses Gemini's native video understanding to analyze the recording.
        """
        try:
            print(f"   📹 Uploading video to Gemini...")

            # Upload video file to Gemini Files API
            video_file = genai.upload_file(path=video_path)

            # Wait for processing to complete
            print(f"   ⏳ Processing video...")
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = genai.get_file(video_file.name)

            if video_file.state.name == "FAILED":
                raise ValueError(f"Video processing failed: {video_file.state.name}")

            print(f"   ✅ Video processed successfully")

            # Format context information
            file_list = active_context['files'][:10] if active_context['files'] else []
            file_info = '\n'.join([f"  - {f}" for f in file_list]) if file_list else "  None"
            apps_info = ', '.join(active_context['applications'][:10]) if active_context['applications'] else 'None'

            # Get existing related memories
            print("   🔍 Searching for related memories...")
            related_memories = self._get_related_memories_for_context(active_context, limit=5)

            existing_memories_str = ""
            if related_memories:
                print(f"   📚 Found {len(related_memories)} related memories")
                existing_memories_str = "\n**EXISTING RELATED MEMORIES (Build upon this knowledge):**\n"
                for idx, mem in enumerate(related_memories[:5], 1):
                    memory_text = mem.get('memory', '')
                    created_at = mem.get('created_at', '')
                    existing_memories_str += f"\n{idx}. [{created_at}] {memory_text[:200]}...\n"
            else:
                print("   📚 No related memories found - creating fresh context")

            # Create model with tools for video analysis
            model_with_tools = genai.GenerativeModel(
                'gemini-flash-lite-latest',
                tools=self.tools
            )

            prompt = f"""You are an advanced AI memory system analyzing the user's screen recording. Your PRIMARY DIRECTIVE is to STORE EVERYTHING related to work, coding, or learning - whether active or passive.

**Recording Duration:** Approximately {self.analysis_interval} seconds
**Active Applications:** {apps_info}

**Recently Accessed Files:**
{file_info}
{existing_memories_str}

**🎯 CRITICAL DIRECTIVE: STORE ALL WORK-RELATED ACTIVITY**

You must be AGGRESSIVE about storing memories. The user wants ALL work captured, including:
- ✅ Reading/reviewing code (VERY IMPORTANT - most of coding is reading!)
- ✅ Viewing documentation or tutorials
- ✅ Looking at files, even without editing
- ✅ Navigating project structure to understand it
- ✅ Observing errors or debugging output
- ✅ Any IDE, terminal, or development tool visible
- ✅ Reviewing pull requests, issues, or designs
- ✅ Planning or thinking about code (visible through open files/tabs)

**ONLY SKIP if the video shows:**
- ❌ Completely idle/blank screen with NO work-related content
- ❌ Pure entertainment (videos, games, social media with no work context)
- ❌ Generic desktop with absolutely no development tools or files visible

**IF IN DOUBT, STORE IT!** Better to have too many memories than miss important context.

**VIDEO ANALYSIS INSTRUCTIONS:**

Videos provide BETTER CONTEXT than static screenshots because you can see:
- Workflow patterns and sequences of actions
- Code being read, understood, or navigated
- Error resolution processes
- Navigation patterns through applications
- Which parts of code the user focuses on

**CRITICAL: PROJECT-SPECIFIC ANALYSIS**

The user works on MULTIPLE DIFFERENT PROJECTS. Your memories must be PROJECT-SPECIFIC, not generic!

❌ BAD: "User project path is C:\\Projects\\app"
❌ BAD: "Working on Python code"
❌ BAD: "Viewing code files"
✅ GOOD: "ghost-widget project: User reading backend.py video analysis implementation. Focused on _analyze_video_with_gemini method which uses Gemini Flash Lite for video understanding. Project is a PyQt6 desktop app for AI-powered screen capture with ChromaDB for memory storage."

**PROJECT IDENTIFICATION REQUIREMENTS:**
1. Extract project name from paths visible in video
2. Identify project type (web app, desktop app, API, etc.)
3. Note key technologies/frameworks used (from imports, file names, visible code)
4. Describe SPECIFIC work being done (which file, which function, what section of code)
5. Note what the user is LOOKING AT or FOCUSING ON (this is crucial for understanding!)

**YOU HAVE TOOLS - USE THEM TO ENRICH MEMORIES!**

BEFORE storing, use tools to gather MORE CONTEXT:
- `read_file_as_text`: Read the actual code file the user is viewing
- `list_directory`: See project structure and related files
- `get_file_info`: Get file metadata

This makes your memories MUCH MORE VALUABLE!

**IMPORTANCE CLASSIFICATION:**

ALWAYS use "high" importance for now (testing purposes).
The classification system exists but is not currently used:
- **"high"**: All work-related activity (ALWAYS USE THIS)
- **"medium"**: (Not currently used)
- **"low"**: (Not currently used)

**STORAGE FORMAT:**

ALWAYS use the `store_memory` tool for ANY work-related content:
- **content**: VERY detailed, project-specific description. Include:
  - Exact file names and paths
  - Function/class names visible
  - What code sections user is viewing/editing
  - Technologies/libraries spotted
  - User's apparent goal or focus
  - Any errors, outputs, or interesting patterns
- **summary**: One-sentence summary (e.g., "Reading video analysis implementation in ghost-widget backend")
- **importance**: "low", "medium", or "high" based on activity type
- **tags**: Comprehensive list of tags (project name, file names, technologies, concepts)

Example for PASSIVE work (reading code):
store_memory(
    content="ghost-widget project: User reading and analyzing backend.py implementation. Focused on _analyze_video_with_gemini method (lines 1030-1280) which handles video upload to Gemini API, processes tool calls for memory storage, and supports multi-turn conversations. User appears to be understanding how video analysis and memory storage integration works. Project uses google-generativeai SDK, ChromaDB for vector storage, and implements temporal-aware memory retrieval.",
    summary="Reading video analysis and memory storage implementation in ghost-widget backend.py",
    importance="high",
    tags=["python", "ghost-widget", "backend", "video-analysis", "gemini-api", "chromadb", "code-reading"]
)

Example for ACTIVE work (editing code):
store_memory(
    content="ghost-widget project: User modifying _store_context method in backend.py to store exclusively in ChromaDB, removing SQLite dependency. Editing lines around 1385-1435, removing conn.execute() calls and replacing with local_memory.add_memory(). Testing temporal-aware memory storage with metadata including timestamp, context_id, and screenshot_path.",
    summary="Removing SQLite dependency from ghost-widget backend, switching to ChromaDB-only storage",
    importance="high",
    tags=["python", "ghost-widget", "backend", "chromadb", "database-migration", "code-editing", "refactoring"]
)

**NOW ANALYZE AND STORE:**

1. Analyze what the user is viewing/doing in the video
2. If you see code files, IDE, or development tools: You MUST call store_memory!
3. Use read_file_as_text or list_directory ONLY ONCE if needed for context
4. After getting context (or if not needed), IMMEDIATELY call store_memory with importance="high"

**CRITICAL**: If this video shows ANY development work (code visible, IDE open, terminal, etc.), you MUST call store_memory before finishing. Do NOT just explore files and then stop - you must STORE what you learned!"""

            # Analyze video with Gemini - support multi-turn tool calling
            print(f"   🤖 Sending video to Gemini for analysis...")

            # Start a chat for multi-turn tool calling
            chat = model_with_tools.start_chat()
            response = chat.send_message([video_file, prompt])

            print(f"\n   📋 VIDEO ANALYSIS RESULTS:")
            print(f"   " + "="*60)

            # Handle multi-turn tool calling (AI can call tools, see results, then decide to store)
            memory_stored = False
            max_turns = 5  # Prevent infinite loops
            turn_count = 0

            while turn_count < max_turns:
                turn_count += 1
                tool_calls_made = False
                text_responses = []
                tool_results = []

                if response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            tool_calls_made = True
                            function_name = part.function_call.name
                            function_args = dict(part.function_call.args)

                            print(f"   🔧 AI calling tool: {function_name}")
                            # Convert function_args to dict safely (handle protobuf types)
                            try:
                                safe_args = {}
                                for key, value in function_args.items():
                                    if isinstance(value, (list, tuple)):
                                        safe_args[key] = list(value)
                                    else:
                                        safe_args[key] = value
                                print(f"   📝 Tool arguments: {json.dumps(safe_args, indent=2)[:200]}...")
                            except Exception:
                                # Fallback to str representation
                                print(f"   📝 Tool arguments: {str(function_args)[:200]}...")

                            # Execute the tool call
                            if function_name == "store_memory":
                                memory_stored = True
                                # Call store_memory function
                                try:
                                    # Convert tags from RepeatedComposite to list if needed
                                    clean_args = dict(function_args)
                                    if 'tags' in clean_args and not isinstance(clean_args['tags'], list):
                                        clean_args['tags'] = list(clean_args['tags'])

                                    result = self.store_memory(**clean_args)
                                    content_preview = clean_args.get('content', '')[:100]
                                    print(f"   ✅ Memory stored: {content_preview}...")
                                    print(f"   Result: {result}")
                                    tool_results.append({
                                        "function_call": part.function_call,
                                        "function_response": {"result": result}
                                    })
                                except Exception as store_error:
                                    print(f"   ❌ Error storing memory: {store_error}")
                                    import traceback
                                    traceback.print_exc()
                                    tool_results.append({
                                        "function_call": part.function_call,
                                        "function_response": {"error": str(store_error)}
                                    })
                            else:
                                # Handle other tool calls using _execute_tool
                                try:
                                    result = self._execute_tool(function_name, function_args)
                                    result_preview = str(result)[:300] if result else "None"
                                    print(f"   ✅ Tool executed: {function_name}")
                                    print(f"   📤 Tool result: {result_preview}...")
                                    tool_results.append({
                                        "function_call": part.function_call,
                                        "function_response": {"result": str(result)[:500]}
                                    })
                                except Exception as e:
                                    print(f"   ❌ Tool error ({function_name}): {e}")
                                    import traceback
                                    traceback.print_exc()
                                    tool_results.append({
                                        "function_call": part.function_call,
                                        "function_response": {"error": str(e)}
                                    })
                        elif hasattr(part, 'text') and part.text:
                            text_responses.append(part.text)
                            print(f"   💭 AI Response: {part.text[:200]}...")

                # If no tools were called, we're done
                if not tool_calls_made:
                    if not memory_stored:
                        print(f"   ⚠️ AI decided not to store memory for this video")
                        if text_responses:
                            full_response = "\n".join(text_responses)
                            print(f"   📝 Reasoning: {full_response[:300]}...")
                    break

                # If store_memory was called, we're done
                if memory_stored:
                    break

                # Send tool results back to the model for next turn
                if tool_results:
                    print(f"   🔄 Sending tool results back to AI for next decision...")
                    try:
                        # Create function response parts
                        from google.ai.generativelanguage_v1beta.types import content as glm_content
                        response_parts = []
                        for tr in tool_results:
                            response_parts.append(glm_content.Part(
                                function_response=glm_content.FunctionResponse(
                                    name=tr["function_call"].name,
                                    response=tr["function_response"]
                                )
                            ))
                        response = chat.send_message(response_parts)
                    except Exception as e:
                        print(f"   ⚠️ Error in multi-turn conversation: {e}")
                        break

            print(f"   " + "="*60)
            if memory_stored:
                print(f"   ✅ Memory successfully stored after {turn_count} turn(s)")
            else:
                print(f"   ℹ️ No memory stored after {turn_count} turn(s)")

            # Track analytics for this video analysis
            if self.analytics:
                # Calculate approximate cost (Gemini Flash Lite pricing)
                # Video: 258 tokens/second = 10,320 tokens for 40 seconds
                # Input: $0.10 per 1M tokens, Output: $0.40 per 1M tokens
                video_tokens = self.analysis_interval * 258
                output_tokens = 500  # Approximate context summary
                cost = (video_tokens * 0.10 / 1_000_000) + (output_tokens * 0.40 / 1_000_000)

                # Get frame counts from recording
                frames_total = int(self.analysis_interval * self.recording_fps)
                frames_captured = frames_total - self.frames_skipped

                self.analytics.track_video_analysis(
                    duration_seconds=self.analysis_interval,
                    frames_captured=frames_captured,
                    frames_skipped=self.frames_skipped,
                    cost=cost
                )

            # Clean up - delete video file from Gemini Files API
            try:
                genai.delete_file(video_file.name)
            except Exception as e:
                print(f"   ⚠️ Could not delete video file from Gemini: {e}")

            # Clean up temporary video file if it was created for analysis only
            if is_temp_file:
                try:
                    video_file_path = Path(video_path)
                    if video_file_path.exists():
                        video_file_path.unlink()
                        print(f"   🗑️ Temporary analysis video deleted")
                except Exception as e:
                    print(f"   ⚠️ Could not delete temporary video: {e}")
            else:
                # Keep permanent videos for review
                print(f"   📁 Video saved for review: {video_path}")

        except Exception as e:
            print(f"   ❌ Error analyzing video: {e}")
            import traceback
            traceback.print_exc()

            # Track failed analysis in analytics
            if self.analytics:
                frames_total = int(self.analysis_interval * self.recording_fps) if hasattr(self, 'analysis_interval') else 0
                self.analytics.track_video_analysis(
                    duration_seconds=self.analysis_interval if hasattr(self, 'analysis_interval') else 40,
                    frames_captured=frames_total,
                    frames_skipped=0,
                    cost=0.0
                )

    def _video_analysis_worker(self):
        """Background worker thread that processes videos from the queue"""
        print("🔄 Video analysis worker thread started")

        while self.analysis_running:
            try:
                # Get video from queue with timeout to allow checking analysis_running flag
                try:
                    queue_item = self.analysis_queue.get(timeout=1.0)
                except Empty:
                    continue

                # Unpack queue item (video_path, active_context, is_temp)
                if len(queue_item) == 3:
                    video_path, active_context, is_temp = queue_item
                else:
                    # Backward compatibility
                    video_path, active_context = queue_item
                    is_temp = False

                if video_path is None:  # Sentinel value to stop the worker
                    break

                # Process the video
                print(f"\n{'='*70}")
                print(f"🧠 [ANALYSIS WORKER] Processing video: {Path(video_path).name if video_path else 'None'}")
                print(f"{'='*70}")
                self._analyze_video_with_gemini(video_path, active_context, is_temp_file=is_temp)

                # Mark task as done
                self.analysis_queue.task_done()
                print(f"✅ Video analysis complete")
                print(f"{'='*70}\n")

            except Exception as e:
                print(f"\n❌❌❌ ERROR IN ANALYSIS WORKER ❌❌❌")
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()
                print(f"{'='*70}\n")
                # Still mark as done to prevent queue from blocking
                self.analysis_queue.task_done()

        print("🛑 Video analysis worker thread stopped")

    def _get_active_context(self):
        """Get active applications and open files"""
        context = {
            "applications": [],
            "files": []
        }
        
        try:
            # Get active processes (more selective)
            seen_names = set()
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    pinfo = proc.info
                    name = pinfo.get('name', '')
                    if name and name not in seen_names:
                        # Filter out system processes
                        if not name.lower().startswith(('system', 'svchost', 'conhost')):
                            context["applications"].append(name)
                            seen_names.add(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Get recently accessed files with full paths
            context["files"] = self._get_recent_files_internal(hours=1)
            
        except Exception as e:
            print(f"Error getting active context: {e}")
        
        return context
    
    def _get_recent_files_internal(self, hours=1):
        """Internal method to get recently modified files with full paths"""
        recent_files = []
        cutoff_time = time.time() - (hours * 3600)
        
        for watch_dir in self.watch_dirs:
            try:
                watch_path = Path(watch_dir)
                if not watch_path.exists():
                    continue
                
                for file_path in watch_path.rglob("*"):
                    if file_path.is_file():
                        try:
                            # Skip hidden files and common ignore patterns
                            if any(part.startswith('.') for part in file_path.parts):
                                continue
                            if any(ignore in str(file_path) for ignore in ['node_modules', '__pycache__', '.git', 'venv']):
                                continue
                            
                            mtime = file_path.stat().st_mtime
                            if mtime > cutoff_time:
                                # Store absolute path
                                recent_files.append({
                                    'path': str(file_path.absolute()),
                                    'name': file_path.name,
                                    'modified': mtime
                                })
                        except Exception:
                            pass
            except Exception as e:
                print(f"Error scanning {watch_dir}: {e}")
        
        # Sort by modification time (newest first)
        recent_files.sort(key=lambda x: x['modified'], reverse=True)
        
        # Return just the paths for storage, limited to 30
        return [f['path'] for f in recent_files[:30]]
    
    def _analyze_screenshot(self, screenshot_path, active_context):
        """Analyze screenshot using Gemini"""
        try:
            with open(screenshot_path, 'rb') as f:
                image_data = f.read()
            
            # Format file paths nicely
            file_list = active_context['files'][:10] if active_context['files'] else []
            file_info = '\n'.join([f"  - {f}" for f in file_list]) if file_list else "  None"
            
            context_info = f"""
Active Applications: {', '.join(active_context['applications'][:10]) if active_context['applications'] else 'None'}

Recently Accessed Files:
{file_info}
"""
            
            prompt = f"""Analyze this screenshot with EXTREME DETAIL. Extract EVERY piece of information visible on screen.

Additional Context:
{context_info}

**COMPREHENSIVE ANALYSIS REQUIREMENTS:**

1. **APPLICATIONS & WINDOWS:**
   - Name every visible application/window
   - Note window titles EXACTLY as shown (including full file paths in title bars)
   - Identify browser tabs with full URLs
   - Note any system notifications or popups

2. **FILE PATHS - CRITICAL PRIORITY:**
   Extract EVERY file path visible anywhere on screen:
   - **Window titles** (e.g., "main.py - Visual Studio Code", "C:\\Projects\\app\\config.json - Notepad++")
   - **File explorers** (address bar, folder tree, file names with full paths)
   - **IDE/Editor tabs** (file names, breadcrumbs, project structures)
   - **Terminal/Command prompt** (pwd output, cd commands, file operations, ls/dir output)
   - **Browser URLs** (full URLs including protocols, paths, query parameters)
   - **Error messages** (stack traces with file paths and line numbers)
   - **File dialogs** (save/open dialogs with visible paths)
   - **Status bars** (often show current file path)
   - **Breadcrumbs** (navigation paths in apps)
   - **Recent files lists** (in menus or sidebars)
   - **Git/version control** (repo paths, branch names, file diffs)

   Format paths EXACTLY as shown, preserving:
   - Full absolute paths (C:\\Users\\..., /home/user/..., etc.)
   - Relative paths (./src/..., ../config/...)
   - File extensions
   - Line numbers if visible (file.py:125)

3. **VISIBLE TEXT CONTENT:**
   - Code snippets (include language, function names, key logic)
   - Document text (headings, paragraphs, key points)
   - Chat messages (sender, message content)
   - Form fields (labels, entered values if visible)
   - Button labels and menu items
   - Search queries
   - Error messages and warnings (full text)
   - Console/terminal output (commands and results)

4. **USER ACTIVITY ANALYSIS:**
   - What is the user actively doing? (coding, writing, debugging, browsing, etc.)
   - What stage of work are they in? (planning, implementing, reviewing, etc.)
   - What problem are they solving or task are they completing?
   - Are they learning something new or working on familiar content?

5. **UI ELEMENTS & STRUCTURE:**
   - Sidebar content (project structure, file tree, outline)
   - Panels/panes (code editor, preview, console, debug)
   - Toolbar buttons and their state (enabled/disabled)
   - Selected items or focused elements
   - Scroll position indicators
   - Minimap or overview pane contents

6. **TECHNICAL CONTEXT:**
   - Programming language(s) visible
   - Framework or library names
   - Version numbers or git commit hashes
   - Dependencies or imports
   - Configuration settings
   - Environment variables
   - Database names or table structures

7. **METADATA & TIMESTAMPS:**
   - File modification times if visible
   - Message timestamps in chat apps
   - Commit times in version control
   - Last saved indicators

8. **CONNECTIONS & RELATIONSHIPS:**
   - How do visible files relate to context files?
   - Are multiple related files open?
   - Is there a project structure visible?
   - Are there references between files?

9. **SUGGESTED TAGS:**
   Provide 5-10 specific tags based on:
   - Languages/technologies
   - Activity type
   - Project names
   - File types
   - Topics or domains

**OUTPUT FORMAT:**
Structure your analysis clearly with sections. Start with file paths section listing EVERY discovered path. Be exhaustive and specific. This analysis is used for precise context retrieval - missing details means lost context."""
            
            response = self.model.generate_content([
                prompt,
                {"mime_type": "image/png", "data": image_data}
            ])
            
            return response.text
        except Exception as e:
            print(f"Error analyzing screenshot: {e}")
            return f"Error analyzing: {str(e)}"
    
    def _store_context(self, screenshot_path, description, active_context):
        """Store context in ChromaDB local memory system"""
        if not self.use_local_memory or not self.local_memory:
            print(f"⚠️ ChromaDB not available, skipping context storage")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # Format content for local memory (vision-based description only)
            files_info = "\n".join([f"  - {f}" for f in active_context['files'][:10]]) if active_context['files'] else "None"
            apps_info = ", ".join(active_context['applications'][:10]) if active_context['applications'] else "None"

            # Generate a unique context ID
            context_id = f"ctx_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

            memory_content = f"""Timestamp: {timestamp}

Description (from Vision Analysis):
{description}

Active Applications: {apps_info}

Recently Accessed Files:
{files_info}

Screenshot: {screenshot_path}
"""

            # Add memory with metadata for rich retrieval
            memory_metadata = {
                "timestamp": timestamp,
                "context_id": context_id,
                "screenshot_path": screenshot_path,
                "applications": json.dumps(active_context['applications'][:10]),
                "files": json.dumps(active_context['files'][:10]),
                "type": "screen_capture"
            }

            self.local_memory.add_memory(
                content=memory_content,
                metadata=memory_metadata,
                memory_id=context_id
            )
            print(f"[{timestamp}] ✓ Context stored to ChromaDB for user '{self.user_id}'")

        except Exception as e:
            print(f"❌ Failed to store context in ChromaDB: {e}")
            import traceback
            traceback.print_exc()
    
    def _retrieve_relevant_contexts(self, query: str, top_k: int = 10):
        """
        Retrieve most relevant contexts using ChromaDB local memory system with temporal awareness

        Args:
            query: The user's question or current screen content
            top_k: Total number of contexts to retrieve

        Returns:
            List of (id, timestamp, description, active_files, open_applications, screen_text, similarity_score) tuples
        """
        # Use ChromaDB local memory system for fast temporal-aware retrieval
        if self.use_local_memory and self.local_memory:
            return self._retrieve_from_local_memory(query, top_k)

        # No fallback - ChromaDB is required
        print("⚠️ ChromaDB not available, cannot retrieve contexts")
        return []

    def _retrieve_from_local_memory(self, query: str, top_k: int = 10):
        """
        Retrieve contexts from Local Memory System (fast, privacy-focused retrieval with temporal awareness)

        Args:
            query: The user's question or current screen content
            top_k: Total number of contexts to retrieve

        Returns:
            List of tuples with context information
        """
        try:
            print(f"\n🔍 Searching local memory for user '{self.user_id}' with query: '{query[:100]}...'")

            # Search using LocalMemorySystem with temporal awareness
            memories = self.local_memory.search_memories(query=query, top_k=top_k)

            if not memories:
                print("⚠️ No memories found in ChromaDB")
                return []

            # Convert LocalMemorySystem format to backend format
            results = []
            for idx, memory in enumerate(memories):
                content = memory['content']
                metadata = memory['metadata']
                temporal_score = memory['temporal_score']

                # Parse structured content
                timestamp = metadata.get('timestamp', 'Unknown')
                context_id = metadata.get('context_id', f"local_{idx}")
                active_files = metadata.get('files', "[]")
                open_apps = metadata.get('applications', "[]")
                screen_text = ""

                # Extract description from content
                description = content
                if "Description (from Vision Analysis):" in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if line.startswith("Description (from Vision Analysis):"):
                            desc_start = i + 1
                            desc_lines = []
                            for j in range(desc_start, len(lines)):
                                if lines[j].startswith("Active Applications:") or lines[j].startswith("Recently Accessed"):
                                    break
                                if lines[j].strip():
                                    desc_lines.append(lines[j])
                            description = "\n".join(desc_lines).strip()
                            break

                # Add to results in expected format
                results.append((
                    context_id,
                    timestamp,
                    description,
                    active_files,
                    open_apps,
                    screen_text,
                    temporal_score
                ))

                # Show what we extracted
                print(f"  Memory {idx+1}: {description[:100]}... (temporal score: {temporal_score:.3f})")

            print(f"✓ Retrieved {len(results)} results from local memory with temporal awareness")
            return results

        except Exception as e:
            print(f"❌ Error retrieving from ChromaDB: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _generate_autonomous_content(self):
        """Generate proactive content based on current screen activity (vision only)"""
        try:
            # Capture current screenshot for analysis
            screenshot_path = self._capture_screenshot()
            if not screenshot_path:
                print("Could not capture screenshot for content generation")
                return

            with open(screenshot_path, 'rb') as f:
                image_data = f.read()

            # Note: We're skipping similarity check since we're not extracting text anymore
            # The vision model will handle the analysis directly

            # Retrieve recent contexts for additional context
            relevant_contexts = self._retrieve_relevant_contexts("recent screen activity", top_k=5)
            
            # Build context string
            context_parts = []
            all_files = set()
            
            for ctx_id, timestamp, desc, files_json, apps_json, screen_text, similarity in relevant_contexts:
                context_parts.append(f"[Past Context - {timestamp}]\n{desc}")
                if screen_text:
                    context_parts.append(f"Previous Screen Text:\n{screen_text[:500]}")
                
                if files_json:
                    try:
                        files = json.loads(files_json)
                        all_files.update(files)
                    except:
                        pass
            
            context_str = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant past context"
            
            # Create content generation prompt
            prompt = f"""You are an AI companion that generates useful content based on what the user is currently doing on screen.

RELEVANT PAST CONTEXT:
{context_str}

RELEVANT FILES:
{', '.join(list(all_files)[:10]) if all_files else 'None'}

YOUR TASK:
Analyze the current screen image using vision and generate appropriate content:

1. IF on an AI chatbot/assistant website (ChatGPT, Claude, Gemini, etc.):
   - Generate a well-crafted prompt for the AI based on what you see
   - Make it specific and contextual to their apparent goal

2. IF writing a document with just a heading/title:
   - Generate the full content for that section
   - Match the tone and style of existing content
   - Use relevant information from past contexts

3. IF coding with comments/function stubs:
   - Generate the complete implementation
   - Follow best practices and existing code style

4. IF on a blank document/editor:
   - Suggest relevant content based on recent activity
   - Provide a starter template or outline

5. IF researching/reading:
   - Summarize key points
   - Generate related questions or next steps

6. OTHERWISE:
   - Generate contextually relevant content that would be helpful
   - Could be: draft text, code snippet, outline, summary, etc.

IMPORTANT:
- Be specific and actionable
- Generate COMPLETE, READY-TO-USE content
- Match the context and style
- Keep it focused (200-400 words or equivalent)
- Format appropriately (markdown, code blocks, etc.)

Generate the content now:"""

            # Generate content with vision
            response = self.model.generate_content([
                prompt,
                {"mime_type": "image/png", "data": image_data}
            ])
            
            generated_content = response.text

            # Detect content type based on generated content only
            content_type = self._detect_content_type("", generated_content)
            
            # Write to file with timestamp and metadata
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.autonomous_output, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"🤖 AUTONOMOUS CONTENT - {timestamp}\n")
                f.write(f"📋 Type: {content_type}\n")
                f.write(f"{'='*80}\n")
                f.write(f"{generated_content}\n")
                f.write(f"\n{'='*80}\n")
            
            # Also copy to clipboard for immediate use
            try:
                pyperclip.copy(generated_content)
                clipboard_status = "✅ Copied to clipboard"
            except:
                clipboard_status = "❌ Could not copy to clipboard"
            
            print(f"\n{'='*80}")
            print(f"🤖 AUTONOMOUS CONTENT GENERATED - {timestamp}")
            print(f"📋 Type: {content_type}")
            print(f"{'='*80}")
            print(generated_content[:300] + "..." if len(generated_content) > 300 else generated_content)
            print(f"{'='*80}\n")
            print(f"💾 Saved to: {self.autonomous_output}")
            print(f"📋 {clipboard_status}")
            
        except Exception as e:
            import traceback
            print(f"Error generating autonomous content: {e}")
            print(traceback.format_exc())
    
    def _detect_content_type(self, screen_text: str, generated_content: str) -> str:
        """Detect what type of content was generated"""
        screen_lower = screen_text.lower()
        content_lower = generated_content.lower()
        
        if any(keyword in screen_lower for keyword in ['chatgpt', 'claude', 'gemini', 'copilot', 'chat']):
            return "AI Prompt"
        elif '```' in generated_content or 'def ' in content_lower or 'function' in content_lower:
            return "Code"
        elif any(keyword in screen_lower for keyword in ['document', 'word', 'docs', 'write']):
            return "Document Content"
        elif '#' in generated_content[:100] or any(heading in content_lower[:200] for heading in ['introduction', 'overview', 'summary']):
            return "Article/Blog"
        else:
            return "General Content"
    
    # Tool execution methods
    def read_file(self, file_path: str) -> str:
        """Read file contents as text - supports text, PDFs, Word docs, Excel, CSV"""
        try:
            path = Path(file_path).resolve()
            if not path.exists():
                return f"File not found: {file_path}"
            
            # Check if file is in watched directories or current directory
            is_allowed = True
            if self.watch_dirs:
                # If watch_dirs is specified, check if file is in one of them
                is_allowed = any(
                    str(path).startswith(str(Path(d).resolve())) 
                    for d in self.watch_dirs
                )
            else:
                # If no watch_dirs specified, allow access to current directory and subdirectories
                current_dir = Path.cwd().resolve()
                is_allowed = str(path).startswith(str(current_dir))
            
            if not is_allowed:
                return f"Access denied: {file_path} is not in watched directories or current project directory"
            
            file_extension = path.suffix.lower()
            
            # PDF files
            if file_extension == '.pdf':
                return self._read_pdf(path)
            
            # Word documents (.docx, .doc)
            elif file_extension in ['.docx', '.doc']:
                return self._read_word(path)
            
            # Excel files (.xlsx, .xls)
            elif file_extension in ['.xlsx', '.xls']:
                return self._read_excel(path)
            
            # PowerPoint files (.pptx)
            elif file_extension == '.pptx':
                return self._read_powerpoint(path)
            
            # CSV files
            elif file_extension == '.csv':
                return self._read_csv(path)
            
            # Text files
            else:
                text_extensions = {
                    '.txt', '.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.md', '.markdown',
                    '.log', '.xml', '.html', '.htm', '.css', '.scss', '.sass',
                    '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.sh', '.bash',
                    '.c', '.cpp', '.h', '.hpp', '.java', '.go', '.rs', '.php', '.rb',
                    '.sql', '.r', '.m', '.swift', '.kt', '.cs', '.vb', '.ps1', '.bat'
                }
                
                if file_extension in text_extensions or file_extension == '':
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(100000)  # Limit to 100KB
                        return content
                else:
                    # Try to read as text anyway
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(100000)
                            return content
                    except:
                        return f"File type not supported for text reading: {file_extension}. Try using read_file_with_vision instead."
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    def _read_csv(self, path: Path) -> str:
        """Read CSV file"""
        try:
            import csv
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                rows = list(reader)[:100]  # Limit to 100 rows
                return f"CSV File ({len(rows)} rows):\n" + "\n".join([" | ".join(row) for row in rows])
        except Exception as e:
            return f"Error reading CSV: {str(e)}"
    
    def read_file_with_vision(self, file_path: str) -> str:
        """Read and analyze any file using Gemini's vision capabilities"""
        try:
            path = Path(file_path).resolve()
            if not path.exists():
                return f"File not found: {file_path}"
            
            # Check permissions
            is_allowed = True
            if self.watch_dirs:
                # If watch_dirs is specified, check if file is in one of them
                is_allowed = any(
                    str(path).startswith(str(Path(d).resolve())) 
                    for d in self.watch_dirs
                )
            else:
                # If no watch_dirs specified, allow access to current directory and subdirectories
                current_dir = Path.cwd().resolve()
                is_allowed = str(path).startswith(str(current_dir))
            
            if not is_allowed:
                return f"Access denied: {file_path} is not in watched directories or current project directory"
            
            file_extension = path.suffix.lower()
            
            # Read file as bytes
            with open(path, 'rb') as f:
                file_data = f.read()
            
            # Determine mime type and prepare for Gemini
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp',
                '.pdf': 'application/pdf',
            }
            
            mime_type = mime_types.get(file_extension)
            
            if not mime_type:
                return f"File type {file_extension} not supported for vision analysis. Supported: images (.png, .jpg, etc.) and PDFs."
            
            # Create appropriate prompt based on file type
            if file_extension == '.pdf':
                prompt = """Analyze this PDF document thoroughly. Extract and provide:
1. All text content from the document
2. Document structure (sections, headings, etc.)
3. Any tables, charts, or figures with their content
4. Key information and main points
5. Full content of all sections including introduction, methodology, results, discussion, conclusion, etc.

Be comprehensive and extract all readable text."""
            else:
                prompt = """Analyze this image thoroughly. Provide:
1. Detailed description of what's visible
2. Extract ALL text visible in the image (OCR)
3. Any diagrams, charts, or visual elements
4. Context and purpose of the image
5. Any important information or data shown

Be comprehensive and extract all text and information."""
            
            # Send to Gemini with vision
            response = self.model.generate_content([
                prompt,
                {"mime_type": mime_type, "data": file_data}
            ])
            
            return f"Vision Analysis of {path.name}:\n\n{response.text}"
            
        except Exception as e:
            return f"Error analyzing file with vision: {str(e)}"
    
    def _read_pdf(self, path: Path) -> str:
        """Read PDF file using PyPDF2"""
        try:
            import PyPDF2
            with open(path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                text_content = []
                page_count = len(pdf_reader.pages)
                
                # Limit to first 50 pages
                for i in range(min(page_count, 50)):
                    page = pdf_reader.pages[i]
                    text_content.append(f"--- Page {i+1} ---\n{page.extract_text()}")
                
                return f"PDF Document ({page_count} pages):\n\n" + "\n\n".join(text_content)
        except ImportError:
            return "PyPDF2 not installed. Install with: pip install PyPDF2"
        except Exception as e:
            return f"Error reading PDF: {str(e)}"
    
    def _read_word(self, path: Path) -> str:
        """Read Word document using python-docx"""
        try:
            from docx import Document
            doc = Document(path)
            
            text_content = []
            
            # Extract paragraphs
            for para in doc.paragraphs:
                if para.text.strip():
                    text_content.append(para.text)
            
            # Extract tables
            if doc.tables:
                text_content.append("\n--- Tables ---")
                for table_idx, table in enumerate(doc.tables):
                    text_content.append(f"\nTable {table_idx + 1}:")
                    for row in table.rows:
                        row_text = " | ".join(cell.text.strip() for cell in row.cells)
                        text_content.append(row_text)
            
            return f"Word Document:\n\n" + "\n\n".join(text_content)
        except ImportError:
            return "python-docx not installed. Install with: pip install python-docx"
        except Exception as e:
            return f"Error reading Word document: {str(e)}"
    
    def _read_excel(self, path: Path) -> str:
        """Read Excel file using openpyxl"""
        try:
            import openpyxl
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
            
            text_content = [f"Excel Workbook with {len(workbook.sheetnames)} sheets"]
            
            for sheet_name in workbook.sheetnames[:10]:  # Limit to 10 sheets
                sheet = workbook[sheet_name]
                text_content.append(f"\n--- Sheet: {sheet_name} ---")
                
                row_count = 0
                for row in sheet.iter_rows(max_row=100, values_only=True):  # Limit to 100 rows
                    if any(cell is not None for cell in row):
                        row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
                        text_content.append(row_text)
                        row_count += 1
                
                text_content.append(f"({row_count} rows shown)")
            
            return "\n".join(text_content)
        except ImportError:
            return "openpyxl not installed. Install with: pip install openpyxl"
        except Exception as e:
            return f"Error reading Excel file: {str(e)}"
    
    def _read_powerpoint(self, path: Path) -> str:
        """Read PowerPoint file using python-pptx"""
        try:
            from pptx import Presentation
            prs = Presentation(path)
            
            text_content = [f"PowerPoint Presentation with {len(prs.slides)} slides"]
            
            for slide_idx, slide in enumerate(prs.slides[:50]):  # Limit to 50 slides
                text_content.append(f"\n--- Slide {slide_idx + 1} ---")
                
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        text_content.append(shape.text)
            
            return "\n\n".join(text_content)
        except ImportError:
            return "python-pptx not installed. Install with: pip install python-pptx"
        except Exception as e:
            return f"Error reading PowerPoint: {str(e)}"
    
    def list_directory(self, directory_path: str) -> str:
        """List directory contents"""
        try:
            path = Path(directory_path)
            if not path.exists():
                return f"Directory not found: {directory_path}"
            
            items = []
            for item in path.iterdir():
                items.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0
                })
            
            return json.dumps(items[:100], indent=2)  # Limit to 100 items
        except Exception as e:
            return f"Error listing directory: {str(e)}"
    
    def get_file_info(self, file_path: str) -> str:
        """Get file metadata"""
        try:
            path = Path(file_path)
            if not path.exists():
                return f"File not found: {file_path}"
            
            stat = path.stat()
            info = {
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "extension": path.suffix
            }
            return json.dumps(info, indent=2)
        except Exception as e:
            return f"Error getting file info: {str(e)}"
    
    def search_files(self, pattern: str, search_scope: str = "watched", max_results: int = 20) -> str:
        """Search for files by pattern with limited scope (watched/home/desktop only)"""
        try:
            # Rate limiting: Track recent search calls
            if not hasattr(self, '_search_calls'):
                self._search_calls = []

            # Clean up old calls (older than 60 seconds)
            current_time = time.time()
            self._search_calls = [t for t in self._search_calls if current_time - t < 60]

            # Limit to 3 searches per minute
            if len(self._search_calls) >= 3:
                return json.dumps({
                    "error": "Search limit reached (3 per minute). Please ask the user for the file path instead of searching.",
                    "message": "Too many search attempts. Ask user for file location.",
                    "results": []
                }, indent=2)

            self._search_calls.append(current_time)

            results = []

            # Determine search directories based on scope
            if search_scope == "home":
                search_dirs = [str(Path.home())]
            elif search_scope == "desktop":
                search_dirs = [str(Path.home() / "Desktop")]
            else:  # "watched" or default
                # If no watch dirs specified, search current directory
                search_dirs = self.watch_dirs if self.watch_dirs else [str(Path.cwd())]

            print(f"🔍 Searching for '{pattern}' in scope '{search_scope}' ({len(search_dirs)} directories)...")

            for watch_dir in search_dirs:
                watch_path = Path(watch_dir).resolve()
                if not watch_path.exists():
                    continue

                try:
                    # Use rglob for recursive search
                    for file_path in watch_path.rglob(pattern):
                        if len(results) >= max_results:
                            break

                        if file_path.is_file():
                            # Skip common ignore patterns and system directories
                            path_str = str(file_path)
                            skip_patterns = [
                                'node_modules', '__pycache__', '.git', 'venv', '.venv',
                                'AppData\\Local\\Temp', 'Windows\\System32', '$Recycle.Bin',
                                '.cache', '.tmp', 'Library/Caches'
                            ]
                            if any(ignore in path_str for ignore in skip_patterns):
                                continue

                            try:
                                results.append({
                                    'path': str(file_path.absolute()),
                                    'name': file_path.name,
                                    'size': file_path.stat().st_size,
                                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                                })
                            except Exception:
                                # Skip files we can't access
                                pass

                    if len(results) >= max_results:
                        break

                except Exception as e:
                    print(f"Error searching in {watch_dir}: {e}")

            if not results:
                return json.dumps({
                    "message": f"No files found matching pattern '{pattern}' in scope '{search_scope}'",
                    "results": []
                }, indent=2)

            return json.dumps({
                "message": f"Found {len(results)} files matching '{pattern}' (scope: {search_scope})",
                "results": results
            }, indent=2)

        except Exception as e:
            return f"Error searching files: {str(e)}"
    
    def get_recent_files(self, hours: float) -> str:
        """Get recently modified files"""
        try:
            recent_files = self._get_recent_files_internal(hours)
            return json.dumps(recent_files, indent=2)
        except Exception as e:
            return f"Error getting recent files: {str(e)}"

    def store_memory(self, content: str, summary: str, importance: str = "medium", tags: List[str] = None) -> str:
        """
        Store important information to local memory with temporal awareness

        Args:
            content: The detailed content to store
            summary: Brief one-sentence summary
            importance: Importance level (low/medium/high)
            tags: List of tags for categorization

        Returns:
            Success or error message
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tags_str = ", ".join(tags) if tags else "general"

            # Track storage locations
            storage_locations = []
            memory_id = None

            # Try to store in ChromaDB (LocalMemorySystem) first
            if self.use_local_memory and self.local_memory:
                try:
                    # Format content with metadata
                    formatted_content = f"""[AI-Stored Memory - {importance.upper()} priority]
Timestamp: {timestamp}
Summary: {summary}
Tags: {tags_str}

{content}
"""

                    # Store to Local Memory System with metadata
                    memory_metadata = {
                        "summary": summary,
                        "importance": importance,
                        "tags": json.dumps(tags) if tags else "[]",
                        "timestamp": timestamp,
                        "type": "ai_stored"
                    }

                    memory_id = self.local_memory.add_memory(
                        content=formatted_content,
                        metadata=memory_metadata
                    )
                    storage_locations.append("ChromaDB")
                    print(f"✓ Stored to ChromaDB: {memory_id}")

                except Exception as chromadb_error:
                    print(f"⚠️ Failed to store in ChromaDB: {chromadb_error}")
                    import traceback
                    traceback.print_exc()
            else:
                print("⚠️ ChromaDB not available, cannot store memory")

            # Check if we stored anywhere
            if not storage_locations:
                raise Exception("Failed to store memory - ChromaDB not available")

            print(f"\n💾 [AI Decision] Stored memory for user '{self.user_id}': {summary}")
            print(f"   Importance: {importance} | Tags: {tags_str}")
            print(f"   Storage: {' + '.join(storage_locations)}")

            # Emit progress if callback available
            self._emit_progress("MEMORY_STORED", {
                "summary": summary,
                "importance": importance,
                "tags": tags or [],
                "timestamp": timestamp,
                "user_id": self.user_id,
                "storage_locations": storage_locations
            })

            return json.dumps({
                "success": True,
                "message": f"Memory stored successfully: {summary}",
                "timestamp": timestamp,
                "user_id": self.user_id,
                "memory_id": memory_id,
                "storage_locations": storage_locations
            })

        except Exception as e:
            error_msg = f"Error storing memory: {str(e)}"
            import traceback
            traceback.print_exc()
            print(f"❌ {error_msg}")
            return json.dumps({
                "success": False,
                "error": error_msg
            })

    def github_get_commits(self, repo_name: str, count: int = 10) -> str:
        """
        Get recent commits from a GitHub repository

        Args:
            repo_name: Repository name in format "owner/repo"
            count: Number of commits to retrieve (max 50)

        Returns:
            JSON string with commits data or error
        """
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({
                    "success": False,
                    "error": "GitHub integration not available. Install PyGithub: pip install PyGithub"
                })

            github_auth = get_github_auth()

            if not github_auth.is_authenticated():
                return json.dumps({
                    "success": False,
                    "error": "Not authenticated with GitHub. Please sign in with GitHub first."
                })

            # Limit count to reasonable max
            count = min(count, 50)

            commits = github_auth.get_latest_commits(repo_name, count)

            if commits is None:
                return json.dumps({
                    "success": False,
                    "error": f"Could not fetch commits from repository: {repo_name}. Repository may not exist or you may not have access."
                })

            return json.dumps({
                "success": True,
                "repo_name": repo_name,
                "commit_count": len(commits),
                "commits": commits
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error fetching commits: {str(e)}"
            })

    def github_get_repo_info(self, repo_name: str) -> str:
        """
        Get information about a GitHub repository

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            JSON string with repository data or error
        """
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({
                    "success": False,
                    "error": "GitHub integration not available. Install PyGithub: pip install PyGithub"
                })

            github_auth = get_github_auth()

            if not github_auth.is_authenticated():
                return json.dumps({
                    "success": False,
                    "error": "Not authenticated with GitHub. Please sign in with GitHub first."
                })

            repo_info = github_auth.get_repository_info(repo_name)

            if repo_info is None:
                return json.dumps({
                    "success": False,
                    "error": f"Could not fetch repository info: {repo_name}. Repository may not exist or you may not have access."
                })

            return json.dumps({
                "success": True,
                "repository": repo_info
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error fetching repository info: {str(e)}"
            })

    def github_search_repos(self, query: str, max_results: int = 10) -> str:
        """
        Search for GitHub repositories

        Args:
            query: Search query
            max_results: Maximum number of results (default 10)

        Returns:
            JSON string with search results or error
        """
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({
                    "success": False,
                    "error": "GitHub integration not available. Install PyGithub: pip install PyGithub"
                })

            github_auth = get_github_auth()

            if not github_auth.is_authenticated():
                return json.dumps({
                    "success": False,
                    "error": "Not authenticated with GitHub. Please sign in with GitHub first."
                })

            results = github_auth.search_repositories(query, max_results)

            if results is None:
                return json.dumps({
                    "success": False,
                    "error": f"Could not search repositories with query: {query}"
                })

            return json.dumps({
                "success": True,
                "query": query,
                "result_count": len(results),
                "repositories": results
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error searching repositories: {str(e)}"
            })

    def github_get_user_repos(self, max_results: int = 100) -> str:
        """
        Get all repositories for the authenticated user

        Args:
            max_results: Maximum number of repositories to return (default 100)

        Returns:
            JSON string with user's repositories or error
        """
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({
                    "success": False,
                    "error": "GitHub integration not available. Install PyGithub: pip install PyGithub"
                })

            github_auth = get_github_auth()

            if not github_auth.is_authenticated():
                return json.dumps({
                    "success": False,
                    "error": "Not authenticated with GitHub. Please sign in with GitHub first."
                })

            repositories = github_auth.get_user_repositories(max_results)

            if repositories is None:
                return json.dumps({
                    "success": False,
                    "error": "Could not fetch user repositories"
                })

            return json.dumps({
                "success": True,
                "repo_count": len(repositories),
                "repositories": repositories
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error fetching user repositories: {str(e)}"
            })

    def github_get_readme(self, repo_name: str) -> str:
        """
        Get README content from a repository

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            JSON string with README content or error
        """
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({
                    "success": False,
                    "error": "GitHub integration not available. Install PyGithub: pip install PyGithub"
                })

            github_auth = get_github_auth()

            if not github_auth.is_authenticated():
                return json.dumps({
                    "success": False,
                    "error": "Not authenticated with GitHub. Please sign in with GitHub first."
                })

            readme_info = github_auth.get_repository_readme(repo_name)

            if readme_info is None:
                return json.dumps({
                    "success": False,
                    "error": f"Could not fetch README from repository: {repo_name}"
                })

            if 'error' in readme_info:
                return json.dumps({
                    "success": False,
                    "error": readme_info['error']
                })

            return json.dumps({
                "success": True,
                "repo_name": repo_name,
                "readme": readme_info
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error fetching README: {str(e)}"
            })

    def github_get_pull_requests(self, repo_name: str, state: str = 'all', max_results: int = 30) -> str:
        """Get pull requests from a repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            prs = github_auth.get_pull_requests(repo_name, state, max_results)
            if prs is None:
                return json.dumps({"success": False, "error": f"Could not fetch PRs from {repo_name}"})

            return json.dumps({"success": True, "repo_name": repo_name, "pr_count": len(prs), "pull_requests": prs}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_get_issues(self, repo_name: str, state: str = 'all', max_results: int = 30) -> str:
        """Get issues from a repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            issues = github_auth.get_issues(repo_name, state, max_results)
            if issues is None:
                return json.dumps({"success": False, "error": f"Could not fetch issues from {repo_name}"})

            return json.dumps({"success": True, "repo_name": repo_name, "issue_count": len(issues), "issues": issues}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_get_branches(self, repo_name: str, max_results: int = 30) -> str:
        """Get branches from a repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            branches = github_auth.get_branches(repo_name, max_results)
            if branches is None:
                return json.dumps({"success": False, "error": f"Could not fetch branches from {repo_name}"})

            return json.dumps({"success": True, "repo_name": repo_name, "branch_count": len(branches), "branches": branches}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_get_commit_details(self, repo_name: str, commit_sha: str) -> str:
        """Get detailed information about a specific commit"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            commit = github_auth.get_commit_details(repo_name, commit_sha)
            if commit is None:
                return json.dumps({"success": False, "error": f"Could not fetch commit {commit_sha} from {repo_name}"})

            return json.dumps({"success": True, "repo_name": repo_name, "commit": commit}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_get_contributors(self, repo_name: str, max_results: int = 30) -> str:
        """Get contributors to a repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            contributors = github_auth.get_contributors(repo_name, max_results)
            if contributors is None:
                return json.dumps({"success": False, "error": f"Could not fetch contributors from {repo_name}"})

            return json.dumps({"success": True, "repo_name": repo_name, "contributor_count": len(contributors), "contributors": contributors}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_get_releases(self, repo_name: str, max_results: int = 10) -> str:
        """Get releases from a repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            releases = github_auth.get_releases(repo_name, max_results)
            if releases is None:
                return json.dumps({"success": False, "error": f"Could not fetch releases from {repo_name}"})

            return json.dumps({"success": True, "repo_name": repo_name, "release_count": len(releases), "releases": releases}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_list_directory(self, repo_name: str, path: str = "", ref: str = None) -> str:
        """List contents of a directory in a GitHub repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            contents = github_auth.get_repository_contents(repo_name, path, ref)
            if contents is None:
                return json.dumps({"success": False, "error": f"Could not list directory {path} in {repo_name}"})

            if isinstance(contents, dict) and 'error' in contents:
                return json.dumps({"success": False, "error": contents['error']})

            return json.dumps({"success": True, "repo_name": repo_name, "path": path, "item_count": len(contents), "contents": contents}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_read_file(self, repo_name: str, file_path: str, ref: str = None) -> str:
        """Read the content of a file from a GitHub repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            file_content = github_auth.get_file_content(repo_name, file_path, ref)
            if file_content is None:
                return json.dumps({"success": False, "error": f"Could not read file {file_path} from {repo_name}"})

            if isinstance(file_content, dict) and 'error' in file_content:
                return json.dumps({"success": False, "error": file_content['error']})

            return json.dumps({"success": True, "repo_name": repo_name, "file": file_content}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def github_get_tree(self, repo_name: str, ref: str = None, recursive: bool = True) -> str:
        """Get the complete file tree of a GitHub repository"""
        try:
            if not GITHUB_AVAILABLE:
                return json.dumps({"success": False, "error": "GitHub integration not available"})

            github_auth = get_github_auth()
            if not github_auth.is_authenticated():
                return json.dumps({"success": False, "error": "Not authenticated with GitHub"})

            tree = github_auth.get_repository_tree(repo_name, ref, recursive)
            if tree is None:
                return json.dumps({"success": False, "error": f"Could not get tree from {repo_name}"})

            return json.dumps({"success": True, "repo_name": repo_name, "file_count": len(tree), "tree": tree}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def search_web(self, query: str) -> str:
        """
        Search the web using Google's grounding feature via a separate Gemini instance

        Args:
            query: The search query

        Returns:
            JSON string with search results
        """
        try:
            if not GROUNDING_AVAILABLE:
                return json.dumps({
                    "error": "Web search not available - Google genai grounding not supported",
                    "query": query
                })

            # Import Google genai client for grounding
            from google import genai as google_genai

            # Create a separate client with grounding tool
            client = google_genai.Client(api_key=self.api_key)

            grounding_tool = types.Tool(
                google_search=types.GoogleSearch()
            )

            config = types.GenerateContentConfig(
                tools=[grounding_tool]
            )

            # Create a search prompt
            search_prompt = f"""Search the web for: {query}

Provide a comprehensive summary of the search results including:
1. Key facts and information found
2. Relevant dates, numbers, or statistics
3. Multiple perspectives if applicable
4. Sources of information

Be detailed and informative."""

            # Generate content with grounding
            response = client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=search_prompt,
                config=config
            )

            # Extract text response
            result_text = ""
            if response and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            result_text += part.text

            # Check for grounding metadata
            grounding_metadata = None
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                grounding_metadata = str(candidate.grounding_metadata)

            return json.dumps({
                "query": query,
                "results": result_text,
                "grounding_metadata": grounding_metadata,
                "success": True
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Web search failed: {str(e)}",
                "query": query,
                "success": False
            })

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool and return the result"""
        tools = {
            "read_file_as_text": lambda: self.read_file(args.get("file_path", "")),
            "read_file_with_vision": lambda: self.read_file_with_vision(args.get("file_path", "")),
            "list_directory": lambda: self.list_directory(args.get("directory_path", "")),
            "get_file_info": lambda: self.get_file_info(args.get("file_path", "")),
            "search_files": lambda: self.search_files(
                pattern=args.get("pattern", ""),
                search_scope=args.get("search_scope", "watched"),
                max_results=args.get("max_results", 50)
            ),
            "get_recent_files": lambda: self.get_recent_files(args.get("hours", 1)),
            "search_web": lambda: self.search_web(args.get("query", "")),
            "store_memory": lambda: self.store_memory(
                content=args.get("content", ""),
                summary=args.get("summary", ""),
                importance=args.get("importance", "medium"),
                tags=args.get("tags", None)
            ),
            "github_get_commits": lambda: self.github_get_commits(
                repo_name=args.get("repo_name", ""),
                count=int(args.get("count", 10))
            ),
            "github_get_repo_info": lambda: self.github_get_repo_info(
                repo_name=args.get("repo_name", "")
            ),
            "github_search_repos": lambda: self.github_search_repos(
                query=args.get("query", ""),
                max_results=int(args.get("max_results", 10))
            ),
            "github_get_user_repos": lambda: self.github_get_user_repos(
                max_results=int(args.get("max_results", 100))
            ),
            "github_get_readme": lambda: self.github_get_readme(
                repo_name=args.get("repo_name", "")
            ),
            "github_get_pull_requests": lambda: self.github_get_pull_requests(
                repo_name=args.get("repo_name", ""),
                state=args.get("state", "all"),
                max_results=int(args.get("max_results", 30))
            ),
            "github_get_issues": lambda: self.github_get_issues(
                repo_name=args.get("repo_name", ""),
                state=args.get("state", "all"),
                max_results=int(args.get("max_results", 30))
            ),
            "github_get_branches": lambda: self.github_get_branches(
                repo_name=args.get("repo_name", ""),
                max_results=int(args.get("max_results", 30))
            ),
            "github_get_commit_details": lambda: self.github_get_commit_details(
                repo_name=args.get("repo_name", ""),
                commit_sha=args.get("commit_sha", "")
            ),
            "github_get_contributors": lambda: self.github_get_contributors(
                repo_name=args.get("repo_name", ""),
                max_results=int(args.get("max_results", 30))
            ),
            "github_get_releases": lambda: self.github_get_releases(
                repo_name=args.get("repo_name", ""),
                max_results=int(args.get("max_results", 10))
            ),
            "github_list_directory": lambda: self.github_list_directory(
                repo_name=args.get("repo_name", ""),
                path=args.get("path", ""),
                ref=args.get("ref", None)
            ),
            "github_read_file": lambda: self.github_read_file(
                repo_name=args.get("repo_name", ""),
                file_path=args.get("file_path", ""),
                ref=args.get("ref", None)
            ),
            "github_get_tree": lambda: self.github_get_tree(
                repo_name=args.get("repo_name", ""),
                ref=args.get("ref", None),
                recursive=args.get("recursive", True)
            )
        }

        if tool_name in tools:
            return tools[tool_name]()
        else:
            return f"Unknown tool: {tool_name}"
    
    def _get_related_memories_for_context(self, active_context, limit=5):
        """Get existing memories related to current context for knowledge building"""
        if not self.use_local_memory or not self.local_memory:
            return []

        try:
            # Create a search query from active context
            file_list = active_context['files'][:5] if active_context['files'] else []
            apps = active_context['applications'][:3] if active_context['applications'] else []

            # Extract project names from file paths
            project_names = set()
            for file_path in file_list:
                # Extract meaningful project directory names
                parts = file_path.replace('\\', '/').split('/')
                for part in parts:
                    if part and not part.startswith('.') and len(part) > 2:
                        project_names.add(part)

            # Build search query
            search_terms = list(project_names)[:3] + apps[:2]
            if search_terms:
                query = ' '.join(search_terms)

                # Search existing memories
                results = self.local_memory.search_memories(query=query, top_k=limit)

                # Convert to expected format
                memories = []
                for result in results:
                    memories.append({
                        'content': result['content'],
                        'metadata': result['metadata'],
                        'score': result['temporal_score']
                    })

                return memories

            return []
        except Exception as e:
            print(f"   ⚠️ Could not retrieve related memories: {e}")
            return []

    def _ai_analyze_and_store(self, screenshot_path, active_context):
        """
        AI-driven analysis that decides whether to store information
        The AI model analyzes the screen using vision and calls store_memory tool if deemed important
        Now includes: file reading capabilities, access to related memories, project-specific analysis
        """
        try:
            with open(screenshot_path, 'rb') as f:
                image_data = f.read()

            # Format context information
            file_list = active_context['files'][:10] if active_context['files'] else []
            file_info = '\n'.join([f"  - {f}" for f in file_list]) if file_list else "  None"
            apps_info = ', '.join(active_context['applications'][:10]) if active_context['applications'] else 'None'

            # Get existing related memories to build upon
            print("   🔍 Searching for related memories...")
            related_memories = self._get_related_memories_for_context(active_context, limit=5)

            existing_memories_str = ""
            if related_memories:
                print(f"   📚 Found {len(related_memories)} related memories")
                existing_memories_str = "\n**EXISTING RELATED MEMORIES (Build upon this knowledge):**\n"
                for idx, mem in enumerate(related_memories[:5], 1):
                    memory_text = mem.get('memory', '')
                    created_at = mem.get('created_at', '')
                    existing_memories_str += f"\n{idx}. [{created_at}] {memory_text[:200]}...\n"
            else:
                print("   📚 No related memories found - creating fresh context")

            # Create model with ALL tools (including file reading)
            model_with_tools = genai.GenerativeModel(
                'gemini-flash-lite-latest',
                tools=self.tools  # This includes file reading, store_memory, and all other tools
            )

            prompt = f"""You are an advanced AI memory system analyzing the user's screen activity using vision. Your job is to perform a COMPREHENSIVE analysis and determine if the current screen contains information worth storing as a long-term memory.

**Active Applications:** {apps_info}

**Recently Accessed Files:**
{file_info}
{existing_memories_str}

**CRITICAL: PROJECT-SPECIFIC ANALYSIS**

The user works on MULTIPLE DIFFERENT PROJECTS. Your memories must be PROJECT-SPECIFIC, not generic!

❌ BAD: "User project path is C:\\Projects\\app"
❌ BAD: "Working on Python code"
❌ BAD: "User is coding"

✅ GOOD: "ghost-widget project: PyQt6 desktop app for AI screen capture with local memory storage. Main file: C:\\projects\\ghost-widget\\main.py. Currently implementing memory card UI with QScrollArea and custom QFrame cards."

✅ GOOD: "api-server project (C:\\work\\api-server): FastAPI backend with PostgreSQL. Working on authentication endpoints in auth.py:125. Implementing JWT token refresh logic with Redis caching."

**PROJECT IDENTIFICATION REQUIREMENTS:**
1. Extract project name from paths (e.g., "ghost-widget" from "C:\\projects\\ghost-widget\\main.py")
2. Identify project type (web app, desktop app, API, library, etc.)
3. Note key technologies/frameworks used
4. Describe SPECIFIC work being done (which file, which function, what problem)
5. Include relevant context (error being fixed, feature being added, etc.)

**YOU HAVE TOOLS - USE THEM BEFORE STORING!**

Available tools:
- `read_file_as_text`: Read code files to understand project structure and content
- `list_directory`: Explore project directories
- `get_file_info`: Get file metadata
- All other file system tools

**EXPLORATION WORKFLOW:**
1. See files on screen? → Read them with `read_file_as_text` to understand what user is actually working on
2. See project directory? → Use `list_directory` to understand project structure
3. See code? → Read the actual file to get function names, logic, imports
4. See error? → Read the file to understand the context around that line

**DO NOT STORE VAGUE INFORMATION!**
- Reading files gives you specific function names, class names, logic details
- This makes memories searchable and useful
- Generic descriptions are useless later

**COMPREHENSIVE ANALYSIS INSTRUCTIONS:**

Before deciding whether to store, perform a THOROUGH analysis of the screen extracting:

1. **FILE PATHS - HIGHEST PRIORITY:**
   Scan EVERY visible location for file paths:
   - Window titles (full paths in title bars)
   - File explorer address bars and navigation
   - IDE/Editor tabs, breadcrumbs, and file trees
   - Terminal/Console (pwd, cd, ls/dir output, file operations)
   - Browser URLs (full URLs with protocols and paths)
   - Status bars (current file indicators)
   - Error messages and stack traces (file:line numbers)
   - Git panels (repository paths, file diffs)
   - Recent files/open files lists
   - Project structure panels

   Extract COMPLETE paths including:
   - Full absolute paths (C:\\Projects\\app\\main.py)
   - Relative paths (./src/utils/helper.js)
   - File extensions
   - Line numbers if shown (main.py:125)

2. **DETAILED CONTENT EXTRACTION:**
   - All visible text (code, documents, messages, commands)
   - Function/class/variable names in code
   - Document headings and key points
   - Terminal commands and output
   - Error messages (complete text)
   - UI labels and menu items
   - Search queries or form inputs

3. **TECHNICAL CONTEXT:**
   - Programming languages/frameworks
   - Library names and versions
   - Configuration settings
   - Git branches/commits
   - Database/API names
   - Dependencies and imports

4. **USER ACTIVITY:**
   - What specific task is being performed?
   - What problem is being solved?
   - What stage of work? (planning, coding, debugging, reviewing)
   - Learning new concepts or working on familiar topics?

**STORAGE DECISION CRITERIA:**

**STORE AS MEMORY if:**
- User is actively working on code, writing, or research
- New concepts, insights, or learning is visible
- Important project work or problem-solving in progress
- ANY file paths are visible (crucial for context)
- Significant content is being created or modified
- Technical discussions or documentation visible
- Configuration or setup work
- Debugging or error resolution
- Novel or educational content

**DO NOT STORE if:**
- Idle screen or screensaver
- Just browsing social media casually
- Routine navigation (no substantive content)
- Repetitive content already seen
- Just reading news/entertainment with no work context

**MEMORY STORAGE PROCESS:**

**STEP 1: READ FILES FIRST (if file paths visible)**
- Use `read_file_as_text` to read visible files
- This gives you actual code content, function names, class definitions
- Understand what the user is ACTUALLY working on
- Get imports, dependencies, configurations

**STEP 2: BUILD UPON EXISTING MEMORIES**
- Review "EXISTING RELATED MEMORIES" above
- How does current work connect to previous memories?
- Is this continuing previous work?
- Is this a new feature for known project?
- Update/extend knowledge rather than duplicate

**STEP 3: CREATE PROJECT-SPECIFIC MEMORY**

Use `store_memory` with:

- **content**: COMPREHENSIVE project-specific description:

  **Required format:**
  ```
  PROJECT: [project-name] ([project-type])
  LOCATION: [full absolute path to project root]
  TECHNOLOGIES: [frameworks, languages, databases]

  CURRENT WORK:
  - File: [specific file with full path]
  - Function/Class: [specific function or class being modified]
  - Activity: [what specifically is being done]
  - Context: [why - bug fix, new feature, refactoring, etc.]

  DETAILS:
  [Extracted information from reading files]
  - Function signatures
  - Key variables/classes
  - Logic being implemented
  - Dependencies/imports relevant to current work
  - Error messages if debugging
  - Code snippets if relevant

  FILES INVOLVED:
  [List ALL file paths]

  CONNECTION TO EXISTING WORK:
  [How this relates to previous memories if any]
  ```

- **summary**: PROJECT-SPECIFIC one-sentence summary
  Format: "[project-name]: [specific action] in [specific file/component]"
  Example: "ghost-widget: Implementing memory card UI with QScrollArea in main.py"

- **importance**:
  * "high" - Critical features, major bugs, architecture decisions
  * "medium" - Regular features, bug fixes, improvements
  * "low" - Minor tweaks, documentation, simple changes

- **tags**: 8-12 SPECIFIC tags including:
  * PROJECT NAME (e.g., "ghost-widget", "api-server")
  * Specific technologies (e.g., "pyqt6", "fastapi", "postgresql")
  * Activity type (e.g., "implementing-feature", "fixing-bug", "refactoring")
  * Component names (e.g., "memory-ui", "auth-endpoint", "database-migration")
  * File names without extension (e.g., "main", "auth", "config")
  * Specific topics (e.g., "qscrollarea", "jwt-tokens", "card-layout")

**CRITICAL REQUIREMENTS:**
1. ✅ USE TOOLS to read files and get details BEFORE storing
2. ✅ PROJECT NAME must be in content and tags
3. ✅ Specific file paths with full absolute paths
4. ✅ Specific functions/classes/variables being worked on
5. ✅ Build upon existing memories (reference them if related)
6. ✅ Include code details from file reading
7. ❌ NO generic descriptions like "working on code" or "user project"

**DECISION:**
- If worth storing: READ FILES FIRST, then call `store_memory` with project-specific details
- If not worth storing: Respond "No storage needed - routine activity"
- If unsure about project: READ FILES to understand before deciding

Analyze the screen NOW and make your decision:"""

            # Start chat and get AI decision
            chat = model_with_tools.start_chat()
            response = chat.send_message([
                prompt,
                {"mime_type": "image/png", "data": image_data}
            ])

            # Handle tool calls (AI can read files, then store)
            max_iterations = 10  # Increased to allow file reading + storing
            iteration = 0
            memory_stored = False

            while iteration < max_iterations:
                if not response or not hasattr(response, 'candidates') or not response.candidates:
                    break

                candidate = response.candidates[0]
                if not hasattr(candidate, 'content') or not candidate.content:
                    break

                parts = candidate.content.parts
                if not parts:
                    break

                # Check for function calls
                function_calls = [part for part in parts if hasattr(part, 'function_call') and part.function_call]

                if not function_calls:
                    # No function calls - AI decided not to store or finished
                    # Extract text response
                    for part in parts:
                        if hasattr(part, 'text') and part.text:
                            if "no storage needed" in part.text.lower():
                                print(f"   🤖 AI Decision: Not significant enough to store")
                            else:
                                print(f"   🤖 AI says: {part.text[:100]}")
                    break

                # Execute ALL tool calls (file reading, store_memory, etc.)
                function_responses = []
                for fc in function_calls:
                    tool_name = fc.function_call.name
                    tool_args = dict(fc.function_call.args)

                    # Log tool usage
                    if tool_name == "store_memory":
                        memory_stored = True
                        print(f"   💾 AI is storing memory...")
                    elif tool_name == "read_file_as_text":
                        file_path = tool_args.get('file_path', 'unknown')
                        print(f"   📖 AI is reading: {file_path}")
                    elif tool_name in ["list_directory", "get_file_info"]:
                        print(f"   🔍 AI is exploring: {tool_name}")

                    # Execute the tool
                    result = self._execute_tool(tool_name, tool_args)
                    function_responses.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={"result": result}
                            )
                        )
                    )

                if function_responses:
                    response = chat.send_message(function_responses)

                iteration += 1

            return memory_stored

        except Exception as e:
            print(f"   ❌ Error in AI analysis: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _capture_loop(self):
        """Main capture loop with video recording and AI-driven storage decisions"""
        print(f"🧠 AI-Driven Memory System Started (Video Recording Mode)")
        print(f"   Recording at {self.recording_fps} FPS")
        print(f"   Analyzing video every {self.analysis_interval} seconds")
        print(f"   🎯 CONDENSED VIDEO OPTIMIZATION enabled:")
        print(f"      - Frame similarity detection: {self.frame_similarity_threshold*100:.0f}%")
        print(f"      - Creates condensed video with ONLY changed frames")
        print(f"      - Full videos saved for review, condensed sent to Gemini")
        print(f"      - Average cost savings: 50-70% per analysis!")
        print(f"   AI will decide what's worth storing")
        print(f"   Parallel processing: Recording continues while AI analyzes")
        print(f"   📁 Videos saved to: {self.video_dir}")
        print(f"   Watching directories: {self.watch_dirs}")
        if self.analytics:
            print(f"   📊 Analytics tracking enabled for user: {self.user_id}")
        if self.autonomous_mode:
            print(f"🤖 AUTONOMOUS MODE ENABLED - Generating content every {self.autonomous_interval} seconds")
            print(f"📝 Content will be written to: {self.autonomous_output}")
            print(f"📋 Content will be automatically copied to clipboard")
        print("Press Ctrl+C to stop.\n")

        # Start the background analysis worker thread
        self.analysis_running = True
        self.analysis_thread = threading.Thread(target=self._video_analysis_worker, daemon=True)
        self.analysis_thread.start()

        iteration_count = 0

        while self.running:
            try:
                iteration_count += 1
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{timestamp}] 🎥 Recording #{iteration_count}")

                # Get active context (apps, files)
                active_context = self._get_active_context()

                # Start video recording
                if self._start_video_recording():
                    print(f"   📹 Recording started at {self.recording_fps} FPS for {self.analysis_interval} seconds...")

                    # Calculate frame interval based on FPS
                    frame_interval = 1.0 / self.recording_fps
                    recording_duration = self.analysis_interval

                    # Record frames for the specified duration
                    start_time = time.time()
                    frame_count = 0

                    while time.time() - start_time < recording_duration and self.running:
                        frame_start = time.time()

                        # Capture and write frame
                        if self._capture_frame():
                            frame_count += 1

                        # Sleep to maintain desired FPS
                        elapsed = time.time() - frame_start
                        sleep_time = max(0, frame_interval - elapsed)
                        time.sleep(sleep_time)

                    # Calculate skip rate for this recording
                    skip_rate = (self.frames_skipped / frame_count * 100) if frame_count > 0 else 0
                    print(f"   ✅ Recording complete: {frame_count} frames captured ({self.frames_skipped} skipped, {skip_rate:.1f}% skip rate)")

                    # Stop recording and get both full and condensed video paths
                    video_result = self._stop_video_recording()

                    if video_result:
                        full_video_path = video_result['full_video_path']
                        condensed_video_path = video_result['condensed_video_path']
                        compression_ratio = video_result['compression_ratio']
                        frames_kept = video_result['frames_kept']

                        # Calculate cost savings
                        full_duration = frame_count / self.recording_fps
                        condensed_duration = frames_kept / self.recording_fps
                        full_cost = (full_duration * 258 / 1_000_000) * 0.10  # Gemini Flash Lite pricing
                        condensed_cost = (condensed_duration * 258 / 1_000_000) * 0.10
                        savings = full_cost - condensed_cost
                        savings_percent = (savings / full_cost * 100) if full_cost > 0 else 0

                        print(f"   💰 Cost optimization: Condensed video = {compression_ratio*100:.1f}% of original")
                        print(f"   💰 Savings: ${savings:.6f} ({savings_percent:.1f}%) per analysis")

                        # CONDENSED VIDEO APPROACH: Always analyze, prefer condensed if available
                        # Determine which video to analyze
                        video_to_analyze = condensed_video_path if (condensed_video_path and frames_kept > 0) else full_video_path
                        analysis_duration = condensed_duration if (condensed_video_path and frames_kept > 0) else full_duration
                        analysis_cost = condensed_cost if (condensed_video_path and frames_kept > 0) else full_cost

                        if not condensed_video_path or frames_kept == 0:
                            # No interesting frames - analyze full video instead
                            print(f"   ⚠️ No interesting frames detected - analyzing full video instead")
                            if full_video_path:
                                print(f"   💾 Full video saved for review: {Path(full_video_path).name}")
                        else:
                            # Use condensed video for analysis
                            print(f"   🧠 Using condensed video for Gemini analysis...")
                            if full_video_path:
                                print(f"   💾 Full video saved for review: {Path(full_video_path).name}")

                        # Always queue video for analysis (condensed if available, full otherwise)
                        print(f"   🧠 Queuing video for Gemini analysis...")
                        try:
                            # Check queue size
                            queue_size = self.analysis_queue.qsize()
                            if queue_size > 0:
                                print(f"   📊 Analysis queue: {queue_size} video(s) waiting")

                            # Check if this is a temporary video (for cleanup after analysis)
                            is_temp = video_result.get('is_temp', False)

                            # Add video to queue (condensed if available, full video as fallback)
                            self.analysis_queue.put((video_to_analyze, active_context, is_temp), timeout=2.0)
                            print(f"   ✅ Video queued for analysis (continuing recording...)")

                            # Track analysis in analytics with cost savings
                            if self.analytics:
                                self.analytics.track_video_analysis(
                                    duration_seconds=analysis_duration,
                                    frames_captured=frame_count,
                                    frames_skipped=self.frames_skipped,
                                    cost=analysis_cost
                                )

                        except Exception as e:
                            print(f"   ⚠️ Failed to queue video for analysis: {e}")
                            # If queue is full or error, analyze synchronously as fallback
                            print(f"   🧠 Falling back to synchronous analysis...")
                            is_temp = video_result.get('is_temp', False)
                            self._analyze_video_with_gemini(video_to_analyze, active_context, is_temp_file=is_temp)

                        # Autonomous content generation (if enabled)
                        if self.autonomous_mode:
                            current_time = time.time()
                            if current_time - self.last_autonomous_check >= self.autonomous_interval:
                                print("\n🤖 Generating autonomous content...")
                                self._generate_autonomous_content()
                                self.last_autonomous_check = current_time
                    else:
                        print(f"   ❌ Failed to save video recording")
                else:
                    print(f"   ❌ Failed to start video recording")
                    time.sleep(5)  # Wait before retrying

            except Exception as e:
                print(f"Error in capture loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)
    
    def start(self):
        """Start background capturing"""
        if self.running:
            print("Already running!")
            return

        # Track session start
        if self.analytics:
            self.analytics.track_session_start()

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping background companion...")
            self.stop()
    
    def stop(self):
        """Stop background capturing and cleanup resources"""
        self.running = False

        # Stop the analysis worker thread
        if self.analysis_running:
            print("Stopping analysis worker thread...")
            self.analysis_running = False

            # Send sentinel value to unblock the worker if it's waiting
            try:
                self.analysis_queue.put((None, None), timeout=1.0)
            except:
                pass

            # Wait for analysis thread to finish
            if self.analysis_thread and self.analysis_thread.is_alive():
                print("Waiting for pending video analysis to complete...")
                self.analysis_thread.join(timeout=10)

                if self.analysis_thread.is_alive():
                    print("⚠️ Analysis thread did not stop gracefully")

        # Clean up video recording resources
        if self.video_writer:
            try:
                self.video_writer.release()
                self.video_writer = None
                print("Video writer released.")
            except Exception as e:
                print(f"Error releasing video writer: {e}")

        if hasattr(self, 'thread'):
            self.thread.join(timeout=5)

        # Track session end and print daily summary
        if self.analytics:
            self.analytics.track_session_end()
            self.analytics.print_daily_summary()

        print("Stopped.")
    
    def query(self, question, guidance_mode=False):
        """Query stored context using RAG-based retrieval with Claude or Gemini

        Args:
            question: The user's question
            guidance_mode: If True, use fast model with live screenshot for real-time guidance
        """
        # In guidance mode, use fast lightweight approach with live screen capture
        if guidance_mode:
            return self._query_with_guidance(question)

        # Use the model specified by qa_model preference
        if self.qa_model == "claude" and self.claude_client:
            return self._query_with_claude(question)
        elif self.qa_model == "claude" and not self.claude_client:
            print("⚠️ Claude selected but not available. Falling back to Gemini.")
            return self._query_with_gemini(question)
        else:
            return self._query_with_gemini(question)

    def _query_with_guidance(self, question):
        """Fast guidance mode with live screenshot and full tool access

        Uses gemini-flash-latest for speed while maintaining all tool calling capabilities.
        Includes live screen capture for instant help.
        """
        print(f"\n{'='*60}")
        print("🚀 GUIDANCE MODE - INSTANT HELP WITH FULL TOOLS")
        print(f"{'='*60}")
        print("\n📸 Capturing live screenshot...")

        # Emit progress
        self._emit_progress("GUIDANCE_MODE", {
            "status": "Capturing screen"
        })

        # Capture current screenshot
        screenshot_path = None
        screenshot_image = None
        try:
            screenshot = ImageGrab.grab()
            screenshot_image = screenshot  # Keep in memory

            # Only save to disk if save_recordings is enabled
            if self.save_recordings:
                screenshot_path = self.screenshot_dir / f"guidance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                screenshot.save(screenshot_path, 'PNG')
                print(f"✓ Screenshot captured and saved: {screenshot_path}")
            else:
                print(f"✓ Screenshot captured (not saved to disk)")
        except Exception as e:
            print(f"⚠️ Warning: Could not capture screenshot: {e}")

        # Get active context (files, apps, etc.)
        active_context = self._get_active_context()

        # Get recent stored context from ChromaDB
        recent_contexts = []
        if self.use_local_memory and self.local_memory:
            try:
                recent_memories = self.local_memory.get_recent_memories(limit=5)
                for mem in recent_memories:
                    metadata = mem.get('metadata', {})
                    content = mem.get('content', '')
                    # Parse content to extract description
                    description = ""
                    if "Description (from Vision Analysis):" in content:
                        lines = content.split('\n')
                        for i, line in enumerate(lines):
                            if line.startswith("Description (from Vision Analysis):"):
                                desc_lines = []
                                for j in range(i+1, len(lines)):
                                    if lines[j].startswith("Active Applications:"):
                                        break
                                    if lines[j].strip():
                                        desc_lines.append(lines[j])
                                description = "\n".join(desc_lines).strip()
                                break

                    recent_contexts.append((
                        metadata.get('timestamp', ''),
                        description,
                        '',  # screen_text (not used)
                        metadata.get('files', '[]'),
                        metadata.get('applications', '[]')
                    ))
            except Exception as e:
                print(f"⚠️ Could not retrieve recent contexts from ChromaDB: {e}")

        # Build context string with file information
        context_parts = []
        all_files = set()

        if active_context.get('active_files'):
            all_files.update(active_context['active_files'][:10])
            context_parts.append("Current Files:\n" + "\n".join([f"  - {f}" for f in active_context['active_files'][:10]]))
        if active_context.get('active_apps'):
            context_parts.append("Active Apps:\n" + "\n".join([f"  - {app}" for app in active_context['active_apps'][:5]]))

        if recent_contexts:
            context_parts.append("\nRecent Activity:")
            for timestamp, desc, screen_text, files_json, apps_json in recent_contexts:
                context_parts.append(f"[{timestamp}] {desc[:300]}")

                if files_json:
                    try:
                        files = json.loads(files_json)
                        if files:
                            all_files.update(files)
                    except:
                        pass

        context_str = "\n\n".join(context_parts) if context_parts else "No recent context available."

        # Add file summary
        if all_files:
            files_summary = "\n\nAll Recently Accessed Files:\n" + "\n".join([f"  - {f}" for f in list(all_files)[:20]])
            context_str += files_summary

        # Emit progress
        self._emit_progress("GUIDANCE_MODE", {
            "status": "Analyzing with AI (with tools)"
        })

        # Use fast model with tools - gemini-flash-latest
        try:
            flash_model = genai.GenerativeModel(
                'gemini-flash-latest',
                tools=self.tools
            )

            # Build initial prompt
            prompt = f"""You are an AI assistant in GUIDANCE MODE - providing instant, helpful guidance with FULL TOOL ACCESS.

CURRENT SCREEN CONTEXT:
{context_str}

You have access to ALL tools including:
- FILE SYSTEM TOOLS: read_file_as_text, read_file_with_vision, list_directory, get_file_info, search_files, get_recent_files
- GITHUB TOOLS: github_get_user_repos, github_get_commits, github_get_repo_info, github_get_readme, github_get_pull_requests, github_get_issues, github_get_branches, github_read_file, github_list_directory, and more
- WEB SEARCH: search_web

CRITICAL INSTRUCTIONS:
- BE PROACTIVE with your tools - use them to gather information the user needs
- For code/file questions: Use file reading tools or GitHub tools to explore
- For GitHub questions: Use github_get_user_repos and other GitHub tools
- Use FULL ABSOLUTE PATHS from the "All Recently Accessed Files" section above
- Provide INSTANT, ACTIONABLE guidance based on what you can access

User Question: {question}

Provide clear, concise, step-by-step guidance. Use your tools to access real information rather than saying "I don't have access"."""

            print("\n🤖 Generating instant response with Gemini Flash + Tools...")

            # Start chat with tools
            chat = flash_model.start_chat()

            # If we have a screenshot, include it (use in-memory image)
            if screenshot_image:
                response = chat.send_message([prompt, screenshot_image])
            else:
                response = chat.send_message(prompt)

            # Handle function calls (same as normal mode but with iteration limit for speed)
            max_iterations = 8  # Reduced from 10 for faster guidance
            iteration = 0
            tool_execution_count = 0

            while iteration < max_iterations:
                if not response or not hasattr(response, 'candidates') or not response.candidates:
                    break

                candidate = response.candidates[0]
                if not hasattr(candidate, 'content') or not candidate.content:
                    break

                parts = candidate.content.parts
                if not parts:
                    break

                # Check if there are function calls
                has_function_call = any(hasattr(part, 'function_call') and part.function_call for part in parts)

                if not has_function_call:
                    break

                # Execute all function calls
                function_responses = []
                for part in parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        func_name = fc.name
                        func_args = dict(fc.args) if fc.args else {}

                        # Emit progress
                        self._emit_progress("TOOL_EXECUTE", {
                            "tool_name": func_name,
                            "args": func_args
                        })

                        print(f"  🔧 Tool: {func_name}({func_args})")

                        # Call the function
                        try:
                            result = self._execute_tool(func_name, func_args)
                            tool_execution_count += 1

                            self._emit_progress("TOOL_COMPLETE", {
                                "tool_name": func_name,
                                "status": "success"
                            })

                            print(f"  ✓ Result: {str(result)[:200]}...")
                        except Exception as e:
                            result = f"Error executing {func_name}: {str(e)}"
                            print(f"  ✗ Error: {result}")

                            self._emit_progress("TOOL_COMPLETE", {
                                "tool_name": func_name,
                                "status": "error",
                                "error": str(e)
                            })

                        # Add function response
                        function_responses.append(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=func_name,
                                    response={'result': result}
                                )
                            )
                        )

                # Send function results back to model
                if function_responses:
                    response = chat.send_message(function_responses)
                    iteration += 1
                else:
                    break

            # Clean up screenshot
            if screenshot_path and screenshot_path.exists():
                try:
                    screenshot_path.unlink()
                except:
                    pass

            # Extract final response
            final_text = ""
            if response and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            final_text += part.text

            # Emit completion
            self._emit_progress("GUIDANCE_MODE", {
                "status": "Complete",
                "tools_used": tool_execution_count
            })

            print(f"\n✓ Guidance complete! (Used {tool_execution_count} tools)")

            return {
                "display": final_text if final_text else "No response generated.",
                "gemini_raw": final_text if final_text else "No response generated."
            }

        except Exception as e:
            import traceback
            print(f"Error in guidance mode: {e}")
            traceback.print_exc()
            return f"Error generating guidance: {str(e)}"

    def _query_with_gemini(self, question):
        """Query stored context using RAG-based retrieval with Gemini (fallback)"""
        # Check if ChromaDB is available and has contexts
        count = 0
        if self.use_local_memory and self.local_memory:
            try:
                stats = self.local_memory.get_stats()
                count = stats.get('total_memories', 0)
            except Exception as e:
                print(f"⚠️ Error checking ChromaDB: {e}")

        if count == 0:
            return "No memories stored yet in ChromaDB. Start capturing first!"

        print(f"\n{'='*60}")
        print("🤖 PROCESSING YOUR QUESTION")
        print(f"{'='*60}")
        print(f"\n🔍 Step 1: Searching through {count} stored contexts...")

        # Emit progress: Memory search started
        self._emit_progress("MEMORY_SEARCH", {
            "status": "Searching",
            "count": count
        })

        # Use RAG to retrieve relevant contexts
        relevant_contexts = self._retrieve_relevant_contexts(question, top_k=10)

        if not relevant_contexts:
            return "No relevant context found. Try capturing more activity!"

        # Build context string with file information
        context_parts = []
        all_files = set()

        print(f"\n📊 Step 2: Retrieved {len(relevant_contexts)} relevant contexts:")
        print(f"{'─'*60}")

        # Emit progress: Memory retrieved
        self._emit_progress("MEMORY_RETRIEVED", {
            "status": "Retrieved",
            "count": len(relevant_contexts),
            "contexts": [(timestamp, similarity) for _, timestamp, _, _, _, _, similarity in relevant_contexts]
        })

        for idx, (ctx_id, timestamp, desc, files_json, apps_json, screen_text, similarity) in enumerate(relevant_contexts, 1):
            # Indicate if this is a recent context (always included)
            marker = "📌 RECENT" if similarity == 1.0 else f"🎯 {similarity:.3f}"
            print(f"  {idx}. [{marker}] {timestamp}")
            
            context_parts.append(f"[Context {idx} - {timestamp} - Relevance: {marker}]\n{desc}")
            
            if screen_text:
                context_parts.append(f"Screen Text:\n{screen_text[:500]}")
            
            if files_json:
                try:
                    files = json.loads(files_json)
                    if files:
                        # Add to all_files set
                        all_files.update(files)
                        # Show files in context
                        file_list = '\n'.join([f"  - {f}" for f in files[:5]])
                        context_parts.append(f"Active Files:\n{file_list}")
                except Exception as e:
                    print(f"Error parsing files JSON: {e}")
        
        context_str = "\n\n---\n\n".join(context_parts)
        
        # Add summary of all files
        if all_files:
            files_summary = "\n\nAll Files Accessed During Retrieved Contexts:\n" + "\n".join([f"  - {f}" for f in list(all_files)[:30]])
            context_str += files_summary
        
        # Create model with tools
        # Note: Google's grounding tools cannot be combined with custom function calling
        # We'll use the traditional model with function calling for file operations
        try:
            model_with_tools = genai.GenerativeModel(
                'gemini-2.5-pro',
                tools=self.tools
            )
        except Exception as e:
            print(f"Error creating model with tools: {e}")
            return f"Error creating model: {str(e)}"

        # Initial prompt
        prompt = f"""Based on the following context captured from screen activity (retrieved using semantic search):

{context_str}

---

IMPORTANT CONTEXT RETRIEVAL INFO:
- Contexts marked "📌 RECENT" are the {self.always_recent} most recent captures (always included)
- Contexts with "🎯 [score]" were retrieved based on semantic similarity to your question
- Higher similarity scores (closer to 1.0) indicate more relevance

You have access to the following tools:

FILE SYSTEM TOOLS:
- read_file_as_text: Read text-based files (code, documents, PDFs, Word docs, Excel, etc.) and get extracted text
- read_file_with_vision: Use AI vision to analyze any file including images, PDFs, and complex documents
- list_directory: List directory contents
- get_file_info: Get file metadata
- search_files: Search for SPECIFIC files by name/pattern (ONLY when you have a concrete file name from context)
- get_recent_files: Get recently modified files from watched directories

GITHUB TOOLS (Full Access to User's Repositories):
- github_get_user_repos: List all user's repositories (public and private)
- github_get_commits: Get commit history from a repository
- github_get_commit_details: Get detailed info about a specific commit (file changes, diffs, stats)
- github_get_repo_info: Get repository metadata (description, stars, language, etc.)
- github_get_readme: Read README files from repositories
- github_get_pull_requests: Get PRs with state, author, changes, merge status
- github_get_issues: Get issues with labels, assignees, comments
- github_get_branches: List repository branches
- github_get_contributors: Get contributor information
- github_get_releases: Get release history with notes and downloads
- github_search_repos: Search for repositories by keyword

WEB SEARCH TOOL:
- search_web: Search the web for current information, facts, news, or real-time data

CRITICAL: BE PROACTIVE AND USE YOUR TOOLS!

**DON'T SAY "I don't have enough context" WHEN YOU HAVE TOOLS TO GET IT!**

If the user asks about:
- **Code/files**: Use file reading tools or GitHub tools to explore and find the answer
- **GitHub repositories**: Use github_get_user_repos to discover repositories, then use other GitHub tools
- **Commits**: Use github_get_commits and github_get_commit_details to analyze commits
- **Codebase structure**: Use list_directory and read_file_as_text to explore
- **Project capabilities**: Read the README, source code files, and configuration files

**EXPLORATION STRATEGY:**

1. **For questions about codebases/projects:**
   - FIRST: Look at the "All Files Accessed During Retrieved Contexts" section above - these are FULL ABSOLUTE PATHS
   - Use github_get_user_repos to find the repository
   - Read README files with github_get_readme
   - Use list_directory with FULL ABSOLUTE PATHS from the context (e.g., C:\\projects\\ghost-widget)
   - Read relevant source files with read_file_as_text using FULL ABSOLUTE PATHS from context
   - Check commits with github_get_commits

2. **For questions about specific features/functionality:**
   - Find and read the relevant source code files using FULL ABSOLUTE PATHS from the context above
   - Check recent commits for changes
   - Look at file structure and dependencies

3. **For questions about GitHub activity:**
   - Use github_get_commits for commit history
   - Use github_get_commit_details for specific commit analysis
   - Use github_get_pull_requests and github_get_issues for project activity

**CRITICAL: ALWAYS USE FULL ABSOLUTE PATHS FROM MEMORY CONTEXT!**

**When using file/directory tools:**
- ✅ CORRECT: Use full absolute paths from "All Files Accessed During Retrieved Contexts" section (e.g., C:\\projects\\ghost-widget\\backend.py)
- ✅ CORRECT: Use full absolute paths from "Active Files" in context entries (e.g., C:\\Users\\Name\\Documents\\file.txt)
- ❌ WRONG: Using relative paths (e.g., "ghost-widget" or "backend.py")
- ❌ WRONG: Using partial paths (e.g., "Documents\\file.txt")
- ❌ WRONG: Guessing paths or using project names as paths

**Path Extraction Examples:**
- If context shows: "C:\\projects\\ghost-widget\\backend.py" → Use exactly this path
- If you see "ghost-widget" mentioned → Look in the file lists above for paths containing "ghost-widget"
- If no path available → Use get_recent_files to discover paths, or ASK the user

**SMART FILE HANDLING:**
1. ALWAYS check the "All Files Accessed During Retrieved Contexts" section FIRST
2. Use those EXACT FULL PATHS - don't modify or shorten them
3. If you need to list a directory, extract the directory path from file paths (e.g., C:\\projects\\ghost-widget\\backend.py → C:\\projects\\ghost-widget)
4. Use get_recent_files to discover more file paths if needed
5. Only use search_files with specific file names as a last resort
6. ASK the user for paths only when you've exhausted all other options

**NEVER SAY:**
- ❌ "I don't have enough context to answer"
- ❌ "The retrieved contexts don't contain information about..."
- ❌ "I would need access to..."

**INSTEAD:**
- ✅ Use your tools proactively to gather the information
- ✅ "Let me check the codebase..." then use file/GitHub tools
- ✅ "Let me look at the repository..." then use GitHub tools
- ✅ "Let me explore the project structure..." then use directory/file tools

User Question: {question}"""
        
        try:
            # Start chat with tools
            print(f"\n{'─'*60}")
            print("💬 Step 3: Processing with Gemini AI...")
            print(f"{'─'*60}")

            # Emit progress: AI processing
            self._emit_progress("AI_PROCESSING", {
                "status": "Processing"
            })

            # Use traditional model with function calling
            chat = model_with_tools.start_chat()
            response = chat.send_message(prompt)

            # Handle function calls
            max_iterations = 10
            iteration = 0
            tool_execution_count = 0

            while iteration < max_iterations:
                # Check if response is None or has no candidates
                if not response or not hasattr(response, 'candidates') or not response.candidates:
                    print("⚠️ Warning: Empty response from model")
                    break

                # Get the first candidate
                candidate = response.candidates[0]
                if not hasattr(candidate, 'content') or not candidate.content:
                    break

                parts = candidate.content.parts
                if not parts:
                    break

                # Check for function calls
                function_calls = [part for part in parts if hasattr(part, 'function_call') and part.function_call]

                if not function_calls:
                    # No more function calls, we're done
                    break

                # Execute all function calls
                if tool_execution_count == 0:
                    print(f"\n{'─'*60}")
                    print("🔧 Step 4: Executing tools to gather information...")
                    print(f"{'─'*60}")

                function_responses = []
                for fc in function_calls:
                    tool_name = fc.function_call.name
                    tool_args = dict(fc.function_call.args)

                    tool_execution_count += 1

                    # Emit progress: Tool execution started
                    self._emit_progress("TOOL_EXECUTE", {
                        "tool_name": tool_name,
                        "args": tool_args,
                        "status": "executing"
                    })

                    # Visual indicator based on tool type
                    if tool_name == "read_file_as_text" or tool_name == "read_file_with_vision":
                        file_path = tool_args.get("file_path", "")
                        file_name = Path(file_path).name if file_path else "unknown"
                        print(f"\n  📄 [{tool_execution_count}] Reading file: {file_name}")
                        print(f"      Path: {file_path}")
                    elif tool_name == "search_web":
                        query = tool_args.get("query", "")
                        print(f"\n  🌐 [{tool_execution_count}] Searching web: '{query}'")
                        # Emit special progress event for grounding search
                        self._emit_progress("GROUNDING_SEARCH", {
                            "query": query,
                            "status": "searching"
                        })
                    elif tool_name == "list_directory":
                        dir_path = tool_args.get("directory_path", "")
                        print(f"\n  📁 [{tool_execution_count}] Listing directory: {dir_path}")
                    elif tool_name == "search_files":
                        pattern = tool_args.get("pattern", "")
                        print(f"\n  🔎 [{tool_execution_count}] Searching files: {pattern}")
                    elif tool_name == "get_recent_files":
                        hours = tool_args.get("hours", 1)
                        print(f"\n  🕐 [{tool_execution_count}] Getting files from last {hours} hours")
                    elif tool_name == "get_file_info":
                        file_path = tool_args.get("file_path", "")
                        file_name = Path(file_path).name if file_path else "unknown"
                        print(f"\n  ℹ️  [{tool_execution_count}] Getting info for: {file_name}")
                    else:
                        print(f"\n  🔧 [{tool_execution_count}] Executing: {tool_name}")

                    result = self._execute_tool(tool_name, tool_args)

                    # Show completion indicator
                    # Check for specific error patterns, not just the word "Error"
                    is_error = (
                        result.startswith("Error reading file") or
                        result.startswith("Error analyzing file") or
                        result.startswith("Error getting file info") or
                        result.startswith("Error searching files") or
                        result.startswith("Error listing directory") or
                        result.startswith("Error getting recent files") or
                        result.startswith("Access denied") or
                        result.startswith("File not found") or
                        result.startswith("Directory not found") or
                        "not installed" in result.lower() or
                        "not supported" in result.lower()
                    )
                    if is_error:
                        print(f"      ❌ Failed")
                    else:
                        print(f"      ✅ Complete")

                    # Emit progress: Tool execution complete
                    self._emit_progress("TOOL_COMPLETE", {
                        "tool_name": tool_name,
                        "status": "error" if is_error else "success",
                        "result_preview": result[:100] if result else ""
                    })

                    function_responses.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={"result": result}
                            )
                        )
                    )

                # Send function responses back
                try:
                    if function_responses:
                        print(f"\n  🔄 Sending results back to AI for processing...")
                    response = chat.send_message(function_responses)
                except Exception as e:
                    print(f"  ❌ Error sending function responses: {e}")
                    break

                iteration += 1

            if tool_execution_count > 0:
                print(f"\n{'─'*60}")
                print(f"✅ Completed {tool_execution_count} tool execution(s)")
                print(f"{'─'*60}")

            # Extract final text response
            print(f"\n{'─'*60}")
            print("✨ Step 5: Generating final answer...")
            print(f"{'─'*60}\n")

            final_text = ""
            if response and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            final_text += part.text

            if final_text:
                print(f"{'='*60}")
                print("✅ ANSWER READY")
                print(f"{'='*60}\n")

                # Emit progress: Answer ready
                self._emit_progress("ANSWER_READY", {
                    "status": "complete"
                })

            return final_text if final_text else "No response generated. The model may need more context or there may be an issue with the query."
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Full error traceback:\n{error_details}")
            return f"Error querying: {str(e)}\n\nPlease check that:\n1. Your API key is valid\n2. You have internet connection\n3. The Gemini API is accessible"

    def _query_with_claude(self, question):
        """Query stored context using RAG-based retrieval with Claude 4.5 Sonnet"""
        # Check if ChromaDB is available and has contexts
        count = 0
        if self.use_local_memory and self.local_memory:
            try:
                stats = self.local_memory.get_stats()
                count = stats.get('total_memories', 0)
            except Exception as e:
                print(f"⚠️ Error checking ChromaDB: {e}")

        if count == 0:
            return "No memories stored yet in ChromaDB. Start capturing first!"

        print(f"\n{'='*60}")
        print("🤖 PROCESSING YOUR QUESTION WITH CLAUDE 4.5 SONNET")
        print(f"{'='*60}")
        print(f"\n🔍 Step 1: Searching through {count} stored contexts...")

        # Emit progress: Memory search started
        self._emit_progress("MEMORY_SEARCH", {
            "status": "Searching",
            "count": count
        })

        # Use RAG to retrieve relevant contexts
        relevant_contexts = self._retrieve_relevant_contexts(question, top_k=10)

        if not relevant_contexts:
            return "No relevant context found. Try capturing more activity!"

        # Build context string with file information
        context_parts = []
        all_files = set()

        print(f"\n📊 Step 2: Retrieved {len(relevant_contexts)} relevant contexts:")
        print(f"{'─'*60}")

        # Emit progress: Memory retrieved
        self._emit_progress("MEMORY_RETRIEVED", {
            "status": "Retrieved",
            "count": len(relevant_contexts),
            "contexts": [(timestamp, similarity) for _, timestamp, _, _, _, _, similarity in relevant_contexts]
        })

        for idx, (ctx_id, timestamp, desc, files_json, apps_json, screen_text, similarity) in enumerate(relevant_contexts, 1):
            # Indicate if this is a recent context (always included)
            marker = "📌 RECENT" if similarity == 1.0 else f"🎯 {similarity:.3f}"
            print(f"  {idx}. [{marker}] {timestamp}")

            context_parts.append(f"[Context {idx} - {timestamp} - Relevance: {marker}]\n{desc}")

            if screen_text:
                context_parts.append(f"Screen Text:\n{screen_text[:500]}")

            if files_json:
                try:
                    files = json.loads(files_json)
                    if files:
                        # Add to all_files set
                        all_files.update(files)
                        # Show files in context
                        file_list = '\n'.join([f"  - {f}" for f in files[:5]])
                        context_parts.append(f"Active Files:\n{file_list}")
                except Exception as e:
                    print(f"Error parsing files JSON: {e}")

        context_str = "\n\n---\n\n".join(context_parts)

        # Add summary of all files
        if all_files:
            files_summary = "\n\nAll Files Accessed During Retrieved Contexts:\n" + "\n".join([f"  - {f}" for f in list(all_files)[:30]])
            context_str += files_summary

        # Define Claude-compatible tools
        claude_tools = self._get_claude_tools()

        # Build the system prompt with tool descriptions
        system_prompt = f"""You are a helpful AI assistant with access to the user's screen activity context, file system tools, and GitHub integration.

Based on the following context captured from screen activity (retrieved using semantic search):

{context_str}

---

IMPORTANT CONTEXT RETRIEVAL INFO:
- Contexts marked "📌 RECENT" are the {self.always_recent} most recent captures (always included)
- Contexts with "🎯 [score]" were retrieved based on semantic similarity to your question
- Higher similarity scores (closer to 1.0) indicate more relevance

You have access to the following tools:

FILE SYSTEM TOOLS:
- read_file_as_text: Read text-based files (code, documents, PDFs, Word docs, Excel, etc.)
- read_file_with_vision: Use AI vision to analyze any file including images, PDFs, and complex documents
- list_directory: List directory contents
- get_file_info: Get file metadata
- search_files: Search for SPECIFIC files by name/pattern
- get_recent_files: Get recently modified files from watched directories

GITHUB TOOLS (Full Access to User's Repositories):
- github_get_user_repos: List all user's repositories (public and private)
- github_get_commits: Get commit history from a repository
- github_get_commit_details: Get detailed info about a specific commit (file changes, diffs, stats)
- github_get_repo_info: Get repository metadata (description, stars, language, etc.)
- github_get_readme: Read README files from repositories
- github_get_pull_requests: Get PRs with state, author, changes, merge status
- github_get_issues: Get issues with labels, assignees, comments
- github_get_branches: List repository branches
- github_get_contributors: Get contributor information
- github_get_releases: Get release history with notes and downloads
- github_search_repos: Search for repositories by keyword

WEB SEARCH TOOL:
- search_web: Search the web for current information, facts, news, or real-time data

CRITICAL: BE PROACTIVE AND USE YOUR TOOLS!

**DON'T SAY "I don't have enough context" WHEN YOU HAVE TOOLS TO GET IT!**

If the user asks about:
- **Code/files**: Use file reading tools or GitHub tools to explore and find the answer
- **GitHub repositories**: Use github_get_user_repos to discover repositories, then use other GitHub tools
- **Commits**: Use github_get_commits and github_get_commit_details to analyze commits
- **Codebase structure**: Use list_directory and read_file_as_text to explore
- **Project capabilities**: Read the README, source code files, and configuration files

**EXPLORATION STRATEGY:**

1. **For questions about codebases/projects:**
   - FIRST: Look at the "All Files Accessed During Retrieved Contexts" section above - these are FULL ABSOLUTE PATHS
   - Use github_get_user_repos to find the repository
   - Read README files with github_get_readme
   - Use list_directory with FULL ABSOLUTE PATHS from the context (e.g., C:\\projects\\ghost-widget)
   - Read relevant source files with read_file_as_text using FULL ABSOLUTE PATHS from context
   - Check commits with github_get_commits

2. **For questions about specific features/functionality:**
   - Find and read the relevant source code files using FULL ABSOLUTE PATHS from the context above
   - Check recent commits for changes
   - Look at file structure and dependencies

3. **For questions about GitHub activity:**
   - Use github_get_commits for commit history
   - Use github_get_commit_details for specific commit analysis
   - Use github_get_pull_requests and github_get_issues for project activity

**CRITICAL: ALWAYS USE FULL ABSOLUTE PATHS FROM MEMORY CONTEXT!**

**When using file/directory tools:**
- ✅ CORRECT: Use full absolute paths from "All Files Accessed During Retrieved Contexts" section (e.g., C:\\projects\\ghost-widget\\backend.py)
- ✅ CORRECT: Use full absolute paths from "Active Files" in context entries (e.g., C:\\Users\\Name\\Documents\\file.txt)
- ❌ WRONG: Using relative paths (e.g., "ghost-widget" or "backend.py")
- ❌ WRONG: Using partial paths (e.g., "Documents\\file.txt")
- ❌ WRONG: Guessing paths or using project names as paths

**Path Extraction Examples:**
- If context shows: "C:\\projects\\ghost-widget\\backend.py" → Use exactly this path
- If you see "ghost-widget" mentioned → Look in the file lists above for paths containing "ghost-widget"
- If no path available → Use get_recent_files to discover paths, or ASK the user

**SMART FILE HANDLING:**
1. ALWAYS check the "All Files Accessed During Retrieved Contexts" section FIRST
2. Use those EXACT FULL PATHS - don't modify or shorten them
3. If you need to list a directory, extract the directory path from file paths (e.g., C:\\projects\\ghost-widget\\backend.py → C:\\projects\\ghost-widget)
4. Use get_recent_files to discover more file paths if needed
5. Only use search_files with specific file names as a last resort
6. ASK the user for paths only when you've exhausted all other options

**NEVER SAY:**
- ❌ "I don't have enough context to answer"
- ❌ "The retrieved contexts don't contain information about..."
- ❌ "I would need access to..."

**INSTEAD:**
- ✅ Use your tools proactively to gather the information
- ✅ "Let me check the codebase..." then use file/GitHub tools
- ✅ "Let me look at the repository..." then use GitHub tools
- ✅ "Let me explore the project structure..." then use directory/file tools"""

        try:
            # Start conversation with Claude
            print(f"\n{'─'*60}")
            print("💬 Step 3: Processing with Claude 4.5 Sonnet...")
            print(f"{'─'*60}")

            # Emit progress: AI processing
            self._emit_progress("AI_PROCESSING", {
                "status": "Processing"
            })

            # Claude conversation loop
            messages = [{"role": "user", "content": question}]
            max_iterations = 10
            iteration = 0
            tool_execution_count = 0

            for iteration in range(max_iterations):
                # Send message to Claude
                response = self.claude_client.messages.create(
                    model="claude-sonnet-4-5@20250929",
                    max_tokens=4096,
                    system=system_prompt,
                    tools=claude_tools,
                    messages=messages
                )

                # Check if Claude wants to use tools
                if response.stop_reason == "tool_use":
                    # Execute tools
                    if tool_execution_count == 0:
                        print(f"\n{'─'*60}")
                        print("🔧 Step 4: Executing tools to gather information...")
                        print(f"{'─'*60}")

                    # Add assistant response to messages
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    # Execute each tool call
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_args = block.input
                            tool_execution_count += 1

                            # Emit progress: Tool execution started
                            self._emit_progress("TOOL_EXECUTE", {
                                "tool_name": tool_name,
                                "args": tool_args,
                                "status": "executing"
                            })

                            # Visual indicator based on tool type
                            if tool_name == "read_file_as_text" or tool_name == "read_file_with_vision":
                                file_path = tool_args.get("file_path", "")
                                file_name = Path(file_path).name if file_path else "unknown"
                                print(f"\n  📄 [{tool_execution_count}] Reading file: {file_name}")
                                print(f"      Path: {file_path}")
                            elif tool_name == "search_web":
                                query = tool_args.get("query", "")
                                print(f"\n  🌐 [{tool_execution_count}] Searching web: '{query}'")
                                self._emit_progress("GROUNDING_SEARCH", {
                                    "query": query,
                                    "status": "searching"
                                })
                            elif tool_name == "list_directory":
                                dir_path = tool_args.get("directory_path", "")
                                print(f"\n  📁 [{tool_execution_count}] Listing directory: {dir_path}")
                            elif tool_name == "search_files":
                                pattern = tool_args.get("pattern", "")
                                print(f"\n  🔎 [{tool_execution_count}] Searching files: {pattern}")
                            elif tool_name == "get_recent_files":
                                hours = tool_args.get("hours", 1)
                                print(f"\n  🕐 [{tool_execution_count}] Getting files from last {hours} hours")
                            elif tool_name == "get_file_info":
                                file_path = tool_args.get("file_path", "")
                                file_name = Path(file_path).name if file_path else "unknown"
                                print(f"\n  ℹ️  [{tool_execution_count}] Getting info for: {file_name}")
                            else:
                                print(f"\n  🔧 [{tool_execution_count}] Executing: {tool_name}")

                            # Execute the tool
                            result = self._execute_tool(tool_name, tool_args)

                            # Show completion indicator
                            is_error = (
                                result.startswith("Error reading file") or
                                result.startswith("Error analyzing file") or
                                result.startswith("Error getting file info") or
                                result.startswith("Error searching files") or
                                result.startswith("Error listing directory") or
                                result.startswith("Error getting recent files") or
                                result.startswith("Access denied") or
                                result.startswith("File not found") or
                                result.startswith("Directory not found") or
                                "not installed" in result.lower() or
                                "not supported" in result.lower()
                            )
                            if is_error:
                                print(f"      ❌ Failed")
                            else:
                                print(f"      ✅ Complete")

                            # Emit progress: Tool execution complete
                            self._emit_progress("TOOL_COMPLETE", {
                                "tool_name": tool_name,
                                "status": "error" if is_error else "success",
                                "result_preview": result[:100] if result else ""
                            })

                            # Add tool result
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result
                            })

                    # Add tool results to messages
                    if tool_results:
                        print(f"\n  🔄 Sending results back to AI for processing...")
                        messages.append({
                            "role": "user",
                            "content": tool_results
                        })
                else:
                    # No more tool calls, extract final answer
                    break

            if tool_execution_count > 0:
                print(f"\n{'─'*60}")
                print(f"✅ Completed {tool_execution_count} tool execution(s)")
                print(f"{'─'*60}")

            # Extract final text response
            print(f"\n{'─'*60}")
            print("✨ Step 5: Generating final answer...")
            print(f"{'─'*60}\n")

            final_text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    final_text += block.text

            if final_text:
                print(f"{'='*60}")
                print("✅ ANSWER READY")
                print(f"{'='*60}\n")

                # Emit progress: Answer ready
                self._emit_progress("ANSWER_READY", {
                    "status": "complete"
                })

            return final_text if final_text else "No response generated. The model may need more context or there may be an issue with the query."

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Full error traceback:\n{error_details}")
            return f"Error querying with Claude: {str(e)}\n\nPlease check that:\n1. Your Google Cloud project is configured correctly\n2. You have the GOOGLE_CLOUD_PROJECT environment variable set\n3. You have authenticated with Google Cloud (gcloud auth application-default login)\n4. Claude is enabled in your Vertex AI project"

    def _get_claude_tools(self):
        """Get tool definitions in Claude's format"""
        return [
            {
                "name": "read_file_as_text",
                "description": "Read and extract text content from various file types including code files, PDFs, Word documents, Excel spreadsheets, PowerPoint presentations, and plain text files. Returns the extracted text content.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the file to read"
                        }
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "read_file_with_vision",
                "description": "Use AI vision to analyze any file including images, PDFs, diagrams, charts, screenshots, or complex documents. Provides comprehensive visual analysis and content extraction.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the file to analyze"
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Optional analysis prompt to guide the vision model (e.g., 'Describe this chart', 'Extract the table data')"
                        }
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "list_directory",
                "description": "List all files and subdirectories in a directory with their metadata (size, modification time, type).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "directory_path": {
                            "type": "string",
                            "description": "Absolute path to the directory to list"
                        }
                    },
                    "required": ["directory_path"]
                }
            },
            {
                "name": "get_file_info",
                "description": "Get detailed metadata about a specific file (size, creation time, modification time, file type).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the file"
                        }
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "search_files",
                "description": "Search for files by name pattern in watched directories, home directory, or desktop. WARNING: This is slow. Only use when you have a specific file name from the captured context. If you don't know the file name or location, ask the user instead.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "File name or pattern to search for (e.g., 'report.pdf', '*.txt')"
                        },
                        "search_scope": {
                            "type": "string",
                            "description": "Where to search: 'watched' (default, searches watched directories only), 'home' (searches entire home directory), or 'desktop' (searches desktop only)",
                            "enum": ["watched", "home", "desktop"]
                        }
                    },
                    "required": ["pattern"]
                }
            },
            {
                "name": "get_recent_files",
                "description": "Get list of recently modified files from watched directories, sorted by modification time.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Number of hours to look back (default: 1)"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "search_web",
                "description": "Search the web using Google for current information, facts, news, real-time data, or to verify information. Use this when you need up-to-date information not available in the captured contexts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "github_get_commits",
                "description": "Get recent commits from a GitHub repository. Requires GitHub authentication. Use this to get commit history, messages, authors, and code changes for blog posts or analysis.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo' (e.g., 'facebook/react', 'torvalds/linux')"
                        },
                        "count": {
                            "type": "integer",
                            "description": "Number of commits to retrieve (default: 10, max: 50)"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_get_repo_info",
                "description": "Get detailed information about a GitHub repository including description, stars, forks, language, etc. Requires GitHub authentication.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo' (e.g., 'facebook/react', 'anthropics/anthropic-sdk-python')"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_search_repos",
                "description": "Search for GitHub repositories by keyword. Requires GitHub authentication. Useful for finding repositories related to a topic.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'machine learning python', 'react hooks', 'rust game engine')"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "github_get_user_repos",
                "description": "Get all repositories for the authenticated GitHub user, sorted by most recently updated. Use this to discover and search through the user's repositories when they mention a project name without specifying the full repository path. IMPORTANT: The results include a 'full_name' field (e.g., 'ekalabya/ghost-widget') which is the complete 'owner/repo' format you MUST use with other GitHub tools like github_get_commits.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of repositories to return (default: 100)"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "github_get_readme",
                "description": "Get the README content from a GitHub repository. Useful for understanding what a repository is about and finding the right repository based on its description and documentation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo' (e.g., 'facebook/react')"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_get_pull_requests",
                "description": "Get pull requests from a GitHub repository. Returns comprehensive PR information including state, author, changes, reviews, and merge status.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "state": {
                            "type": "string",
                            "description": "PR state: 'open', 'closed', or 'all' (default: 'all')",
                            "enum": ["open", "closed", "all"]
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of PRs to return (default: 30)"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_get_issues",
                "description": "Get issues from a GitHub repository. Returns issue information including state, labels, assignees, and comments.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "state": {
                            "type": "string",
                            "description": "Issue state: 'open', 'closed', or 'all' (default: 'all')",
                            "enum": ["open", "closed", "all"]
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of issues to return (default: 30)"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_get_branches",
                "description": "Get branches from a GitHub repository. Returns branch names, protection status, and latest commit information.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of branches to return (default: 30)"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_get_commit_details",
                "description": "Get detailed information about a specific commit including file changes, diffs, and statistics. Use this to analyze what changed in a particular commit.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "commit_sha": {
                            "type": "string",
                            "description": "The commit SHA or hash to retrieve details for"
                        }
                    },
                    "required": ["repo_name", "commit_sha"]
                }
            },
            {
                "name": "github_get_contributors",
                "description": "Get contributors to a GitHub repository. Returns contributor usernames, contribution counts, and profile information.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of contributors to return (default: 30)"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_get_releases",
                "description": "Get releases from a GitHub repository. Returns release tags, names, dates, release notes, and download URLs.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of releases to return (default: 10)"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_list_directory",
                "description": "List contents of a directory in a GitHub repository. Returns files and subdirectories with their metadata. Use empty string for root directory.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "path": {
                            "type": "string",
                            "description": "Path within the repository (empty string for root directory, e.g., 'src' or 'docs/api')"
                        },
                        "ref": {
                            "type": "string",
                            "description": "Optional branch/tag/commit to read from (default: default branch)"
                        }
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "github_read_file",
                "description": "Read the complete content of a file from a GitHub repository. Returns the full file content as text.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file within the repository (e.g., 'README.md', 'src/main.py')"
                        },
                        "ref": {
                            "type": "string",
                            "description": "Optional branch/tag/commit to read from (default: default branch)"
                        }
                    },
                    "required": ["repo_name", "file_path"]
                }
            },
            {
                "name": "github_get_tree",
                "description": "Get the complete file tree structure of a GitHub repository. Returns all files and directories recursively. Useful for understanding the full project structure.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name in format 'owner/repo'"
                        },
                        "ref": {
                            "type": "string",
                            "description": "Optional branch/tag/commit to read from (default: default branch)"
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Get full tree recursively (default: true)"
                        }
                    },
                    "required": ["repo_name"]
                }
            }
        ]

    def list_recent(self, limit=10):
        """List recent captures from ChromaDB"""
        if not self.use_local_memory or not self.local_memory:
            print("ChromaDB not available.")
            return

        try:
            memories = self.local_memory.get_recent_memories(limit=limit)

            if not memories:
                print("No captures yet.")
                return

            for mem in memories:
                metadata = mem.get('metadata', {})
                content = mem.get('content', '')
                timestamp = metadata.get('timestamp', 'Unknown')
                context_id = metadata.get('context_id', 'Unknown')

                # Extract description from content
                description = content[:200] + "..." if len(content) > 200 else content

                print(f"\n[ID: {context_id}] {timestamp}")
                print(description)
                print("-" * 80)
        except Exception as e:
            print(f"Error listing recent captures: {e}")

    def reindex_embeddings(self):
        """ChromaDB handles embeddings automatically - this method is deprecated"""
        print("Embeddings are automatically generated by ChromaDB when memories are stored.")
        print("No reindexing needed!")


def main():
    parser = argparse.ArgumentParser(description='AI Background Companion with Content Generation and RAG-based Context Retrieval using Local Memory Storage')
    parser.add_argument('mode', choices=['capture', 'query', 'list', 'reindex', 'autonomous'],
                       help='Mode: capture, query, list, reindex, or autonomous')
    parser.add_argument('--api-key', required=True, help='Google Gemini API key')
    parser.add_argument('--user-id', type=str, default='default_user',
                       help='User ID for per-user memory separation (default: default_user)')
    parser.add_argument('--interval', type=int, default=10,
                       help='DEPRECATED: Use --analysis-interval instead. Capture interval in seconds (default: 10)')
    parser.add_argument('--fps', type=int, default=1,
                       help='Video recording frames per second (default: 1)')
    parser.add_argument('--analysis-interval', type=int, default=10,
                       help='Video analysis interval in seconds (default: 10)')
    parser.add_argument('--watch-dirs', nargs='+',
                       help='Directories to watch for file context (e.g., ~/Documents ~/Projects)')
    parser.add_argument('--question', help='Question to ask (for query mode)')
    parser.add_argument('--limit', type=int, default=10,
                       help='Number of recent items to show (for list mode)')
    parser.add_argument('--always-recent', type=int, default=3,
                       help='Number of most recent contexts to always include in retrieval (default: 3)')
    parser.add_argument('--autonomous-interval', type=int, default=180,
                       help='Interval in seconds for autonomous content generation (default: 180 = 3 minutes)')
    parser.add_argument('--autonomous-output', type=str, default='autonomous_content.txt',
                       help='File to write autonomous content to (default: autonomous_content.txt)')

    args = parser.parse_args()

    # Expand paths
    watch_dirs = []
    if args.watch_dirs:
        watch_dirs = [str(Path(d).expanduser().resolve()) for d in args.watch_dirs]

    companion = BackgroundCompanion(
        api_key=args.api_key,
        capture_interval=args.interval,  # Kept for backward compatibility
        recording_fps=args.fps,
        analysis_interval=args.analysis_interval,
        watch_dirs=watch_dirs,
        always_recent=args.always_recent,
        autonomous_mode=(args.mode == 'autonomous'),
        autonomous_interval=args.autonomous_interval,
        autonomous_output=args.autonomous_output,
        user_id=args.user_id
    )
    
    if args.mode == 'capture':
        companion.start()
    elif args.mode == 'autonomous':
        print("\n" + "="*80)
        print("🤖 AUTONOMOUS CONTENT GENERATION MODE")
        print("="*80)
        print("The AI will:")
        print("  • Extract and analyze text from your screen")
        print("  • Generate contextual content based on what you're doing")
        print("  • Auto-copy generated content to clipboard")
        print("  • Save all content to file with timestamps")
        print("\nContent Types:")
        print("  • AI Prompts (when on ChatGPT, Claude, etc.)")
        print("  • Document content (when writing with headings)")
        print("  • Code implementations (when coding)")
        print("  • Summaries and outlines (when researching)")
        print("="*80 + "\n")
        companion.start()
    elif args.mode == 'query':
        if not args.question:
            print("Please provide a --question for query mode")
            return
        print("\n" + "="*80)
        print("PROCESSING QUERY WITH RAG RETRIEVAL...")
        print("="*80)
        answer = companion.query(args.question)
        print("\n" + "="*80)
        print("ANSWER:")
        print("="*80)
        print(answer)
    elif args.mode == 'list':
        companion.list_recent(args.limit)
    elif args.mode == 'reindex':
        print("Reindexing all contexts with embeddings...")
        companion.reindex_embeddings()


if __name__ == "__main__":
    main()