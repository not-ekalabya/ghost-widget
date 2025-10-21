import os
import time
import json
import sqlite3
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

# Mem0 integration
try:
    from mem0 import MemoryClient
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    print("Warning: mem0 package not installed. Install with: pip install mem0ai")

# Google grounding for web search
try:
    from google.genai import types
    GROUNDING_AVAILABLE = True
except ImportError:
    GROUNDING_AVAILABLE = False
    print("Warning: Google genai library doesn't support grounding. Using fallback search.")

class BackgroundCompanion:
    def __init__(self, api_key, capture_interval=60, db_path="companion_memory.db", watch_dirs=None, always_recent=3, autonomous_mode=False, autonomous_interval=180, autonomous_output="autonomous_content.txt", user_id="default_user", progress_callback=None):
        """
        Initialize the background companion with RAG support and autonomous content generation

        Args:
            api_key: Google Gemini API key
            capture_interval: Seconds between screenshots (default: 60)
            db_path: Path to SQLite database
            watch_dirs: List of directories to watch for file context
            always_recent: Number of most recent contexts to always include (default: 3)
            autonomous_mode: Whether to run in autonomous mode
            autonomous_interval: Seconds between autonomous content generation
            autonomous_output: File path for autonomous content
            user_id: User identifier for per-user memory separation (default: "default_user")
            progress_callback: Callback function for progress updates (for GUI)
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        self.api_key = api_key
        self.capture_interval = capture_interval
        self.db_path = db_path
        self.running = False
        self.screenshot_dir = Path("screenshots")
        self.screenshot_dir.mkdir(exist_ok=True)
        self.watch_dirs = watch_dirs or []
        self.always_recent = always_recent
        self.autonomous_mode = autonomous_mode
        self.autonomous_interval = autonomous_interval
        self.autonomous_output = Path(autonomous_output)
        self.last_autonomous_check = 0
        self.progress_callback = progress_callback  # For GUI progress updates
        self.user_id = user_id  # Store user_id for per-user memory separation

        # Initialize Mem0 Platform with API key
        self.use_mem0 = MEM0_AVAILABLE
        self.mem0_client = None
        if self.use_mem0:
            try:
                # Hard-coded Mem0 API key
                mem0_api_key = "m0-GQo1C1BLFecWLInbI5Cb3R3MAum0cwxwbIOJcKnk"

                # Initialize MemoryClient for managed Mem0 platform
                # The platform handles graph memory and all storage automatically
                self.mem0_client = MemoryClient(api_key=mem0_api_key)
                print(f"OK Mem0 platform initialized for user: {self.user_id}")
            except Exception as e:
                print(f"WARNING Failed to initialize Mem0: {e}")
                print("   Falling back to local database only")
                self.use_mem0 = False

        # Initialize database (fallback for local storage)
        self._init_database()

        # Define available tools for Gemini
        self.tools = self._define_tools()

    def _emit_progress(self, event_type: str, data: dict):
        """Emit progress update to GUI if callback is set"""
        if self.progress_callback:
            try:
                self.progress_callback(event_type, data)
            except Exception as e:
                print(f"Error in progress callback: {e}")

    def _init_database(self):
        """Create database schema with embeddings support"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS context_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                screenshot_path TEXT,
                description TEXT NOT NULL,
                active_window TEXT,
                active_files TEXT,
                open_applications TEXT,
                tags TEXT,
                embedding BLOB,
                created_at TEXT NOT NULL,
                screen_text TEXT
            )
        ''')
        
        # Migrate existing database: add embedding and screen_text columns if they don't exist
        try:
            cursor.execute("SELECT embedding FROM context_snapshots LIMIT 1")
        except sqlite3.OperationalError:
            print("Migrating database: adding embedding column...")
            cursor.execute("ALTER TABLE context_snapshots ADD COLUMN embedding BLOB")
            print("✅ Database migration complete!")
        
        try:
            cursor.execute("SELECT screen_text FROM context_snapshots LIMIT 1")
        except sqlite3.OperationalError:
            print("Migrating database: adding screen_text column...")
            cursor.execute("ALTER TABLE context_snapshots ADD COLUMN screen_text TEXT")
            print("✅ Database migration complete!")
        
        conn.commit()
        conn.close()
    
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
                        "description": "Store important information to long-term graph memory (Mem0). Use this when you observe something significant, novel, or worth remembering about the user's screen activity. Memories are stored per-user and as graph relationships. Only call this for truly important information, not routine/repetitive activity.",
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
        """Capture current screenshot"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = self.screenshot_dir / f"screen_{timestamp}.png"
        
        try:
            screenshot = ImageGrab.grab()
            screenshot.save(screenshot_path)
            return str(screenshot_path)
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return None
    
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
            
            prompt = f"""Analyze this screenshot in detail.

Additional Context:
{context_info}

Provide:
1. What application(s) or websites are visible
2. What the user appears to be doing
3. Key content visible (text, images, UI elements)
4. Any important context or information
5. **IMPORTANT: Extract and mention ANY file paths visible on screen** (from file explorers, title bars, terminal windows, IDE tabs, browser URLs, etc.)
6. Connection to recently accessed files (if relevant) - mention full file paths from the context
7. Suggested tags for categorization

**FILE PATH EXTRACTION IS CRITICAL:**
- Look carefully for file paths in window titles, terminal outputs, file explorers, IDEs, and browser address bars
- Record complete absolute paths whenever visible (e.g., C:\\Users\\Documents\\report.pdf, /home/user/project/main.py)
- Include file extensions

Be thorough and specific. This will be used for context retrieval later."""
            
            response = self.model.generate_content([
                prompt,
                {"mime_type": "image/png", "data": image_data}
            ])
            
            return response.text
        except Exception as e:
            print(f"Error analyzing screenshot: {e}")
            return f"Error analyzing: {str(e)}"
    
    def _store_context(self, screenshot_path, description, active_context):
        """Store context in database with embedding and Mem0 graph memory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Generate embedding for the description only (vision-based)
        print("Generating embedding...")
        embedding = self._generate_embedding(description)
        embedding_blob = None
        if embedding:
            embedding_blob = json.dumps(embedding).encode('utf-8')

        # Store in local database
        cursor.execute('''
            INSERT INTO context_snapshots
            (timestamp, screenshot_path, description, active_files, open_applications, embedding, created_at, screen_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp,
            screenshot_path,
            description,
            json.dumps(active_context['files']),
            json.dumps(active_context['applications']),
            embedding_blob,
            timestamp,
            ""  # Empty screen_text since we're using vision only
        ))

        context_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Store in Mem0 if available
        if self.use_mem0 and self.mem0_client:
            try:
                # Format content for Mem0 (vision-based description only)
                files_info = "\n".join([f"  - {f}" for f in active_context['files'][:10]]) if active_context['files'] else "None"
                apps_info = ", ".join(active_context['applications'][:10]) if active_context['applications'] else "None"

                mem0_content = f"""Timestamp: {timestamp}
Context ID: {context_id}

Description (from Vision Analysis):
{description}

Active Applications: {apps_info}

Recently Accessed Files:
{files_info}

Screenshot: {screenshot_path}
"""

                # Add memory with user_id for per-user separation
                # MemoryClient.add() expects messages format
                self.mem0_client.add(mem0_content, user_id=self.user_id)
                print(f"[{timestamp}] Context stored in local DB and Mem0 platform for user '{self.user_id}'")
            except Exception as e:
                print(f"⚠️ Failed to store in Mem0 (stored locally): {e}")
        else:
            print(f"[{timestamp}] Context stored with embedding (local only, vision-based)")
    
    def _retrieve_relevant_contexts(self, query: str, top_k: int = 10):
        """
        Retrieve most relevant contexts using RAG with Mem0 graph memory or local embeddings
        Always includes the last N recent contexts plus semantically similar ones

        Args:
            query: The user's question or current screen content
            top_k: Total number of contexts to retrieve (including always_recent)

        Returns:
            List of (id, timestamp, description, active_files, open_applications, screen_text, similarity_score) tuples
        """
        # If Mem0 is available, use it for faster retrieval with graph memory
        if self.use_mem0 and self.mem0_client:
            return self._retrieve_from_mem0(query, top_k)

        # Fallback to local SQLite + embeddings
        return self._retrieve_from_local_db(query, top_k)

    def _retrieve_from_mem0(self, query: str, top_k: int = 10):
        """
        Retrieve contexts from Mem0 Platform (fast, cloud-based retrieval with graph memory)

        Args:
            query: The user's question or current screen content
            top_k: Total number of contexts to retrieve

        Returns:
            List of tuples with context information
        """
        try:
            print(f"\nSearching Mem0 platform for user '{self.user_id}' with query: '{query[:100]}...'")

            # Search using MemoryClient with user_id filter (required by v2 API)
            # The v2 API requires filters to be provided and cannot be empty
            filters = {"user_id": self.user_id}
            response = self.mem0_client.search(query=query, filters=filters, limit=top_k)

            # Debug: Check response structure
            if not response:
                print("WARNING Empty response from Mem0, falling back to local DB")
                return self._retrieve_from_local_db(query, top_k)

            # Debug: Print actual response structure
            print(f"DEBUG: Mem0 response type: {type(response)}")
            print(f"DEBUG: Mem0 response: {response}")
            
            # Handle different response formats
            if isinstance(response, dict):
                # If response is a dictionary, check for common keys
                if 'results' in response:
                    response = response['results']
                elif 'data' in response:
                    response = response['data']
                elif 'memories' in response:
                    response = response['memories']
                else:
                    print("WARNING Unexpected dictionary format from Mem0, falling back to local DB")
                    return self._retrieve_from_local_db(query, top_k)
            
            # Ensure response is a list
            if not isinstance(response, list):
                print(f"WARNING Expected list from Mem0, got {type(response)}, falling back to local DB")
                return self._retrieve_from_local_db(query, top_k)
            
            if len(response) > 0:
                print(f"DEBUG: First item type: {type(response[0])}")
                print(f"DEBUG: First item keys: {response[0].keys() if isinstance(response[0], dict) else 'N/A'}")
                print(f"DEBUG: First item sample: {str(response[0])[:200]}")

            # Response format from MemoryClient.search() is a list of memory dictionaries
            results = []
            for idx, memory in enumerate(response):
                # Ensure memory is a dictionary
                if not isinstance(memory, dict):
                    print(f"WARNING Skipping non-dict memory item {idx}: {type(memory)}")
                    continue
                # Extract memory content
                # MemoryClient returns: {'id': '...', 'memory': 'content', 'user_id': '...', ...}
                content = memory.get('memory', '') if isinstance(memory, dict) else str(memory)

                # Ensure content is not None
                if content is None:
                    content = ""

                # Extract timestamp and description from content
                timestamp = memory.get('created_at', 'Unknown') if isinstance(memory, dict) else "Unknown"
                context_id = memory.get('id', f"mem0_{idx}") if isinstance(memory, dict) else f"mem0_{idx}"
                active_files = "[]"
                open_apps = "[]"
                screen_text = ""

                # Initialize description with the full content
                description = content if content else "No content available"

                # Try to parse structured content (if stored in our format)
                if content and "Timestamp:" in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if line.startswith("Timestamp:"):
                            timestamp = line.replace("Timestamp:", "").strip()
                        elif line.startswith("Context ID:"):
                            context_id = line.replace("Context ID:", "").strip()
                        elif line.startswith("Description:") or line.startswith("Description (from Vision Analysis):"):
                            # Get description until next section
                            desc_start = i + 1
                            desc_lines = []
                            for j in range(desc_start, len(lines)):
                                if lines[j].startswith("Screen Text:") or lines[j].startswith("Active Applications:") or lines[j].startswith("Recently Accessed"):
                                    break
                                desc_lines.append(lines[j])
                            description = "\n".join(desc_lines).strip()
                        elif line.startswith("Screen Text:"):
                            # Get screen text until next section
                            st_start = i + 1
                            st_lines = []
                            for j in range(st_start, len(lines)):
                                if lines[j].startswith("Active Applications:") or lines[j].startswith("Recently Accessed"):
                                    break
                                st_lines.append(lines[j])
                            screen_text = "\n".join(st_lines).strip()
                        elif line.startswith("Active Applications:"):
                            # Extract apps info
                            apps_line = line.replace("Active Applications:", "").strip()
                            if apps_line and apps_line != "None":
                                open_apps = json.dumps(apps_line.split(", "))
                        elif line.startswith("Recently Accessed Files:"):
                            # Extract files from following lines
                            files_start = i + 1
                            file_paths = []
                            for j in range(files_start, len(lines)):
                                if lines[j].strip().startswith("-"):
                                    file_paths.append(lines[j].strip()[1:].strip())
                                elif lines[j].startswith("Screenshot:") or not lines[j].strip():
                                    break
                            if file_paths:
                                active_files = json.dumps(file_paths)

                # Score from Mem0 (use actual score if available)
                score = memory.get('score', 0.9 - (idx * 0.05)) if isinstance(memory, dict) else (0.9 - (idx * 0.05))

                # Add to results
                results.append((
                    context_id,
                    timestamp,
                    description,
                    active_files,
                    open_apps,
                    screen_text,
                    score
                ))

                # Debug: Show what we extracted
                print(f"  Memory {idx+1}: {description[:100]}... (score: {score:.3f})")

            print(f"OK Retrieved {len(results)} results from Mem0 platform")
            return results

        except Exception as e:
            print(f"WARNING Error retrieving from Mem0: {e}")
            import traceback
            traceback.print_exc()
            print("Falling back to local database...")
            return self._retrieve_from_local_db(query, top_k)

    def _retrieve_from_local_db(self, query: str, top_k: int = 10):
        """
        Retrieve contexts from local SQLite database (fallback method)

        Args:
            query: The user's question or current screen content
            top_k: Total number of contexts to retrieve

        Returns:
            List of tuples with context information
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get the most recent N contexts (always included)
        cursor.execute('''
            SELECT id, timestamp, description, active_files, open_applications, embedding, screen_text
            FROM context_snapshots
            ORDER BY created_at DESC
            LIMIT ?
        ''', (self.always_recent,))

        recent_contexts = cursor.fetchall()
        recent_ids = {ctx[0] for ctx in recent_contexts}

        # Get all contexts with embeddings for similarity search
        cursor.execute('''
            SELECT id, timestamp, description, active_files, open_applications, embedding, screen_text
            FROM context_snapshots
            WHERE embedding IS NOT NULL
            ORDER BY created_at DESC
        ''')

        all_contexts = cursor.fetchall()
        conn.close()

        if not all_contexts:
            return []

        # Generate embedding for the query
        query_embedding = self._generate_embedding(query)

        if not query_embedding:
            print("Warning: Could not generate query embedding, using only recent contexts")
            return [(ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[6], 1.0) for ctx in recent_contexts]

        # Calculate similarity scores for all contexts
        scored_contexts = []
        for ctx in all_contexts:
            ctx_id, timestamp, description, active_files, open_applications, embedding_blob, screen_text = ctx

            if embedding_blob:
                try:
                    embedding = json.loads(embedding_blob.decode('utf-8'))
                    similarity = self._cosine_similarity(query_embedding, embedding)
                    scored_contexts.append((ctx_id, timestamp, description, active_files, open_applications, screen_text or "", similarity))
                except Exception as e:
                    print(f"Error processing embedding for context {ctx_id}: {e}")

        # Sort by similarity (descending)
        scored_contexts.sort(key=lambda x: x[6], reverse=True)

        # Combine: always include recent contexts, then add most similar ones
        result = []

        # Add recent contexts first (with score 1.0 to indicate they're always included)
        for ctx in recent_contexts:
            result.append((ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[6] or "", 1.0))

        # Add most similar contexts (excluding those already in recent)
        remaining_slots = top_k - len(recent_contexts)
        for ctx in scored_contexts:
            if ctx[0] not in recent_ids and len(result) < top_k:
                result.append(ctx)

        return result
    
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
        Store important information to Mem0 graph memory

        Args:
            content: The detailed content to store
            summary: Brief one-sentence summary
            importance: Importance level (low/medium/high)
            tags: List of tags for categorization

        Returns:
            Success or error message
        """
        try:
            if not self.use_mem0 or not self.mem0_client:
                return json.dumps({
                    "success": False,
                    "error": "Mem0 not available. Using local storage only."
                })

            # Format content with metadata
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tags_str = ", ".join(tags) if tags else "general"

            formatted_content = f"""[AI-Stored Memory - {importance.upper()} priority]
Timestamp: {timestamp}
Summary: {summary}
Tags: {tags_str}

{content}
"""

            # Store to Mem0 Platform with user_id for per-user separation
            self.mem0_client.add(formatted_content, user_id=self.user_id)

            # Also store in local database for backup
            self._store_context_simple(content, summary, importance, tags)

            print(f"\n💾 [AI Decision] Stored memory for user '{self.user_id}': {summary}")
            print(f"   Importance: {importance} | Tags: {tags_str}")

            # Emit progress if callback available
            self._emit_progress("MEMORY_STORED", {
                "summary": summary,
                "importance": importance,
                "tags": tags or [],
                "timestamp": timestamp,
                "user_id": self.user_id
            })

            return json.dumps({
                "success": True,
                "message": f"Memory stored successfully in graph memory: {summary}",
                "timestamp": timestamp,
                "user_id": self.user_id
            })

        except Exception as e:
            error_msg = f"Error storing memory: {str(e)}"
            print(f"❌ {error_msg}")
            return json.dumps({
                "success": False,
                "error": error_msg
            })

    def _store_context_simple(self, content: str, summary: str, importance: str, tags: List[str] = None):
        """Store a simple memory entry in local database (backup)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tags_str = json.dumps(tags) if tags else "[]"

            # Generate embedding
            embedding_content = f"{summary}\n\n{content}"
            embedding = self._generate_embedding(embedding_content)
            embedding_blob = json.dumps(embedding).encode('utf-8') if embedding else None

            cursor.execute('''
                INSERT INTO context_snapshots
                (timestamp, screenshot_path, description, active_files, open_applications, embedding, created_at, screen_text, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                None,  # No screenshot for AI-stored memories
                f"[AI-Stored - {importance}] {summary}",
                "[]",
                "[]",
                embedding_blob,
                timestamp,
                content,
                tags_str
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not store to local database: {e}")

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
            )
        }

        if tool_name in tools:
            return tools[tool_name]()
        else:
            return f"Unknown tool: {tool_name}"
    
    def _ai_analyze_and_store(self, screenshot_path, active_context):
        """
        AI-driven analysis that decides whether to store information
        The AI model analyzes the screen using vision and calls store_memory tool if deemed important
        """
        try:
            with open(screenshot_path, 'rb') as f:
                image_data = f.read()

            # Format context information
            file_list = active_context['files'][:10] if active_context['files'] else []
            file_info = '\n'.join([f"  - {f}" for f in file_list]) if file_list else "  None"
            apps_info = ', '.join(active_context['applications'][:10]) if active_context['applications'] else 'None'

            # Create model with store_memory tool
            model_with_tools = genai.GenerativeModel(
                'gemini-2.0-flash-exp',
                tools=self.tools
            )

            prompt = f"""You are an AI memory system analyzing the user's screen activity using vision. Your job is to determine if the current screen content contains information worth storing as a long-term memory.

**Active Applications:** {apps_info}

**Recently Accessed Files:**
{file_info}

**Your Task:**
Analyze this screen content and decide if it contains information worth remembering. Consider:

1. **STORE AS MEMORY if:**
   - User is working on something important (coding, writing, research)
   - New insights, ideas, or discoveries are visible
   - Important information is being viewed (documents, articles, data)
   - A significant task or project is in progress
   - Novel or unique content (not just browsing social media)
   - User appears to be learning something new
   - Important communications or decisions
   - **Any file paths are visible on screen** (file explorers, terminal, IDE, browser)

2. **DO NOT STORE if:**
   - Routine browsing or scrolling
   - Repetitive or already-seen content
   - Just navigating menus or settings
   - Idle screen or screensaver
   - Entertainment/casual content with no learning value
   - Similar to recently stored memories

**Available Tool:**
- `store_memory`: Call this function to store important information
  - content: Detailed description of what's happening and why it's important. **MUST include any file paths visible on screen!**
  - summary: One-sentence summary
  - importance: "high" for critical info, "medium" for useful info, "low" for minor info
  - tags: Array of relevant tags (e.g., ["coding", "python", "bug-fix"])

**Instructions:**
1. Analyze the screen content carefully
2. **CRITICAL: Extract ALL visible file paths** from window titles, file explorers, terminal output, IDE tabs, browser URLs, etc.
3. If worth storing, call `store_memory` with comprehensive details including:
   - Complete file paths with extensions (e.g., C:\\Users\\Documents\\report.pdf)
   - What the user was doing with those files
   - Application context
4. If not worth storing, simply respond with "No storage needed - routine activity"
5. Only store truly important or novel information

Make your decision now:"""

            # Start chat and get AI decision
            chat = model_with_tools.start_chat()
            response = chat.send_message([
                prompt,
                {"mime_type": "image/png", "data": image_data}
            ])

            # Handle tool calls (if AI decides to store)
            max_iterations = 3
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
                    # No function calls - AI decided not to store
                    # Extract text response
                    for part in parts:
                        if hasattr(part, 'text') and part.text:
                            if "no storage needed" in part.text.lower():
                                print(f"   🤖 AI Decision: Not significant enough to store")
                            else:
                                print(f"   🤖 AI says: {part.text[:100]}")
                    break

                # Execute store_memory tool calls
                function_responses = []
                for fc in function_calls:
                    tool_name = fc.function_call.name
                    tool_args = dict(fc.function_call.args)

                    if tool_name == "store_memory":
                        memory_stored = True
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
        """Main capture loop with AI-driven storage decisions"""
        print(f"🧠 AI-Driven Memory System Started")
        print(f"   Analyzing screen every {self.capture_interval} seconds")
        print(f"   AI will decide what's worth storing")
        print(f"   Watching directories: {self.watch_dirs}")
        if self.autonomous_mode:
            print(f"🤖 AUTONOMOUS MODE ENABLED - Generating content every {self.autonomous_interval} seconds")
            print(f"📝 Content will be written to: {self.autonomous_output}")
            print(f"📋 Content will be automatically copied to clipboard")
        print("Press Ctrl+C to stop.\n")

        iteration_count = 0

        while self.running:
            try:
                iteration_count += 1
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{timestamp}] 📸 Capture #{iteration_count}")

                # Get active context (apps, files)
                active_context = self._get_active_context()

                # Capture screenshot
                screenshot_path = self._capture_screenshot()

                if screenshot_path:
                    # AI-driven analysis and storage decision (vision only)
                    print(f"   🧠 AI analyzing content with vision...")
                    self._ai_analyze_and_store(screenshot_path, active_context)

                    # Autonomous content generation (if enabled)
                    if self.autonomous_mode:
                        current_time = time.time()
                        if current_time - self.last_autonomous_check >= self.autonomous_interval:
                            print("\n🤖 Generating autonomous content...")
                            self._generate_autonomous_content()
                            self.last_autonomous_check = current_time

                # Wait for next capture
                print(f"   ⏳ Waiting {self.capture_interval} seconds until next check...")
                time.sleep(self.capture_interval)

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
        """Stop background capturing"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=5)
        print("Stopped.")
    
    def query(self, question):
        """Query stored context using RAG-based retrieval with Gemini"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if we have any contexts
        cursor.execute('SELECT COUNT(*) FROM context_snapshots')
        count = cursor.fetchone()[0]
        conn.close()

        if count == 0:
            return "No context stored yet. Start capturing first!"

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
                'gemini-flash-latest',
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
- search_files: Search for SPECIFIC files by name/pattern (ONLY when you have a concrete file name from context):
  * pattern: Specific file name (e.g., "report.pdf", "main.py")
  * search_scope: "watched" (default), "home", or "desktop" only
  * **WARNING: This is slow. ONLY use when you have a specific file name from the captured context!**
  * **If you don't know the file name or location, ASK THE USER instead of searching!**
- get_recent_files: Get recently modified files from watched directories

WEB SEARCH TOOL:
- search_web: Search the web for current information, facts, news, or real-time data
  Use this when you need:
  * Current/recent information not in the captured contexts
  * Up-to-date facts, statistics, or news
  * Real-time data (weather, stock prices, etc.)
  * Verification of information

IMPORTANT GUIDELINES:

1. **SMART FILE HANDLING STRATEGY (behave like a sane human):**

   **WHEN YOU SEE FILE PATHS IN THE CONTEXT:**
   - Use those exact paths directly with read_file_as_text or read_file_with_vision
   - Don't search - you already have the path!

   **WHEN USER ASKS ABOUT A FILE YOU DON'T HAVE THE PATH FOR:**
   - First check: Is there a similar file name in the recent files list?
   - If YES and it seems related: Use that path
   - If NO or UNSURE: **ASK THE USER** for the file path
   - DO NOT blindly search through directories hoping to find it

   **ONLY USE search_files WHEN:**
   - You saw the exact file name in a recent context (e.g., "report.pdf")
   - You're 90% sure it's in watched/home/desktop directories
   - It's a common file in a predictable location (e.g., "config.json" on desktop)

   **NEVER DO THIS:**
   - ❌ "Let me search the entire computer for you..." (NO!)
   - ❌ Searching with vague patterns like "*.txt" or "*report*"
   - ❌ Multiple search attempts with different patterns
   - ❌ Searching when you have zero clues about the file

   **INSTEAD DO THIS:**
   - ✅ "I can see you were working on C:\\Users\\John\\Documents\\report.pdf. Let me read that file."
   - ✅ "I don't have the path to that file. Could you please provide the full file path?"
   - ✅ "I see you mentioned 'config.json' - let me check your desktop for it."

2. For Word documents (.docx), PDFs, and other complex documents:
   - read_file_as_text: to get extracted text content
   - read_file_with_vision: for comprehensive AI analysis

3. Always read relevant files first to gather information before answering
4. Use search_web when you need current information beyond the stored contexts
5. Provide detailed, well-structured answers
6. **When in doubt, ASK THE USER - don't waste time searching randomly!**

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
    
    def list_recent(self, limit=10):
        """List recent captures"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, timestamp, description 
            FROM context_snapshots 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            print("No captures yet.")
            return
        
        for id, timestamp, desc in results:
            print(f"\n[ID: {id}] {timestamp}")
            print(desc)
            print("-" * 80)
    
    def reindex_embeddings(self):
        """Generate embeddings for all contexts that don't have them"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get contexts without embeddings
        cursor.execute('''
            SELECT id, description, screen_text
            FROM context_snapshots 
            WHERE embedding IS NULL
        ''')
        
        contexts_to_index = cursor.fetchall()
        
        if not contexts_to_index:
            print("All contexts already have embeddings!")
            conn.close()
            return
        
        print(f"Generating embeddings for {len(contexts_to_index)} contexts...")
        
        for idx, (ctx_id, description, screen_text) in enumerate(contexts_to_index, 1):
            print(f"Processing {idx}/{len(contexts_to_index)}...", end='\r')
            
            embedding_content = description + "\n\nScreen Text:\n" + (screen_text or "")
            embedding = self._generate_embedding(embedding_content)
            if embedding:
                embedding_blob = json.dumps(embedding).encode('utf-8')
                cursor.execute('''
                    UPDATE context_snapshots 
                    SET embedding = ?
                    WHERE id = ?
                ''', (embedding_blob, ctx_id))
                conn.commit()
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
        
        conn.close()
        print(f"\n✅ Successfully generated embeddings for {len(contexts_to_index)} contexts!")


def main():
    parser = argparse.ArgumentParser(description='AI Background Companion with Content Generation and RAG-based Context Retrieval using Mem0 Graph Memory')
    parser.add_argument('mode', choices=['capture', 'query', 'list', 'reindex', 'autonomous'],
                       help='Mode: capture, query, list, reindex, or autonomous')
    parser.add_argument('--api-key', required=True, help='Google Gemini API key')
    parser.add_argument('--user-id', type=str, default='default_user',
                       help='User ID for per-user memory separation (default: default_user)')
    parser.add_argument('--interval', type=int, default=60,
                       help='Capture interval in seconds (default: 60)')
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
        capture_interval=args.interval,
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