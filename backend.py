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

class BackgroundCompanion:
    def __init__(self, api_key, capture_interval=60, db_path="companion_memory.db", watch_dirs=None, always_recent=3):
        """
        Initialize the background companion with RAG support
        
        Args:
            api_key: Google Gemini API key
            capture_interval: Seconds between screenshots (default: 60)
            db_path: Path to SQLite database
            watch_dirs: List of directories to watch for file context
            always_recent: Number of most recent contexts to always include (default: 3)
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        self.capture_interval = capture_interval
        self.db_path = db_path
        self.running = False
        self.screenshot_dir = Path("screenshots")
        self.screenshot_dir.mkdir(exist_ok=True)
        self.watch_dirs = watch_dirs or []
        self.always_recent = always_recent
        
        # Initialize database
        self._init_database()
        
        # Define available tools for Gemini
        self.tools = self._define_tools()
    
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
                created_at TEXT NOT NULL
            )
        ''')
        
        # Migrate existing database: add embedding column if it doesn't exist
        try:
            cursor.execute("SELECT embedding FROM context_snapshots LIMIT 1")
        except sqlite3.OperationalError:
            print("Migrating database: adding embedding column...")
            cursor.execute("ALTER TABLE context_snapshots ADD COLUMN embedding BLOB")
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
                        "description": "Search for files by name pattern in watched directories",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "pattern": {
                                    "type": "string",
                                    "description": "The pattern to search for (e.g., '*.py', 'report*')"
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
                    }
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
5. Connection to recently accessed files (if relevant) - mention full file paths
6. Suggested tags for categorization

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
        """Store context in database with embedding"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Generate embedding for the description
        print("Generating embedding...")
        embedding = self._generate_embedding(description)
        embedding_blob = None
        if embedding:
            embedding_blob = json.dumps(embedding).encode('utf-8')
        
        cursor.execute('''
            INSERT INTO context_snapshots 
            (timestamp, screenshot_path, description, active_files, open_applications, embedding, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp, 
            screenshot_path, 
            description, 
            json.dumps(active_context['files']),
            json.dumps(active_context['applications']),
            embedding_blob,
            timestamp
        ))
        
        conn.commit()
        conn.close()
        
        print(f"[{timestamp}] Context stored with embedding")
    
    def _retrieve_relevant_contexts(self, query: str, top_k: int = 10):
        """
        Retrieve most relevant contexts using RAG
        Always includes the last N recent contexts plus semantically similar ones
        
        Args:
            query: The user's question
            top_k: Total number of contexts to retrieve (including always_recent)
        
        Returns:
            List of (id, timestamp, description, active_files, open_applications, similarity_score) tuples
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the most recent N contexts (always included)
        cursor.execute('''
            SELECT id, timestamp, description, active_files, open_applications, embedding
            FROM context_snapshots 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (self.always_recent,))
        
        recent_contexts = cursor.fetchall()
        recent_ids = {ctx[0] for ctx in recent_contexts}
        
        # Get all contexts with embeddings for similarity search
        cursor.execute('''
            SELECT id, timestamp, description, active_files, open_applications, embedding
            FROM context_snapshots 
            WHERE embedding IS NOT NULL
            ORDER BY created_at DESC
        ''')
        
        all_contexts = cursor.fetchall()
        conn.close()
        
        if not all_contexts:
            return []
        
        # Generate embedding for the query
        print("Generating query embedding...")
        query_embedding = self._generate_embedding(query)
        
        if not query_embedding:
            print("Warning: Could not generate query embedding, using only recent contexts")
            return [(ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], 1.0) for ctx in recent_contexts]
        
        # Calculate similarity scores for all contexts
        scored_contexts = []
        for ctx in all_contexts:
            ctx_id, timestamp, description, active_files, open_applications, embedding_blob = ctx
            
            if embedding_blob:
                try:
                    embedding = json.loads(embedding_blob.decode('utf-8'))
                    similarity = self._cosine_similarity(query_embedding, embedding)
                    scored_contexts.append((ctx_id, timestamp, description, active_files, open_applications, similarity))
                except Exception as e:
                    print(f"Error processing embedding for context {ctx_id}: {e}")
        
        # Sort by similarity (descending)
        scored_contexts.sort(key=lambda x: x[5], reverse=True)
        
        # Combine: always include recent contexts, then add most similar ones
        result = []
        
        # Add recent contexts first (with score 1.0 to indicate they're always included)
        for ctx in recent_contexts:
            result.append((ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], 1.0))
        
        # Add most similar contexts (excluding those already in recent)
        remaining_slots = top_k - len(recent_contexts)
        for ctx in scored_contexts:
            if ctx[0] not in recent_ids and len(result) < top_k:
                result.append(ctx)
        
        print(f"\nRetrieved {len(result)} contexts:")
        print(f"  - {len(recent_contexts)} most recent (always included)")
        print(f"  - {len(result) - len(recent_contexts)} semantically similar")
        
        return result
    
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
                is_allowed = any(
                    str(path).startswith(str(Path(d).resolve())) 
                    for d in self.watch_dirs
                )
            
            if not is_allowed:
                return f"Access denied: {file_path} is not in watched directories"
            
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
                is_allowed = any(
                    str(path).startswith(str(Path(d).resolve())) 
                    for d in self.watch_dirs
                )
            
            if not is_allowed:
                return f"Access denied: {file_path} is not in watched directories"
            
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
    
    def search_files(self, pattern: str) -> str:
        """Search for files by pattern"""
        try:
            results = []
            
            # If no watch dirs specified, search current directory
            search_dirs = self.watch_dirs if self.watch_dirs else [str(Path.cwd())]
            
            for watch_dir in search_dirs:
                watch_path = Path(watch_dir).resolve()
                if not watch_path.exists():
                    continue
                
                try:
                    for file_path in watch_path.rglob(pattern):
                        if file_path.is_file():
                            # Skip common ignore patterns
                            if any(ignore in str(file_path) for ignore in ['node_modules', '__pycache__', '.git', 'venv', '.venv']):
                                continue
                            results.append({
                                'path': str(file_path.absolute()),
                                'name': file_path.name,
                                'size': file_path.stat().st_size
                            })
                except Exception as e:
                    print(f"Error searching in {watch_dir}: {e}")
            
            return json.dumps(results[:50], indent=2)  # Limit to 50 results
        except Exception as e:
            return f"Error searching files: {str(e)}"
    
    def get_recent_files(self, hours: float) -> str:
        """Get recently modified files"""
        try:
            recent_files = self._get_recent_files_internal(hours)
            return json.dumps(recent_files, indent=2)
        except Exception as e:
            return f"Error getting recent files: {str(e)}"
    
    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool and return the result"""
        tools = {
            "read_file_as_text": lambda: self.read_file(args.get("file_path", "")),
            "read_file_with_vision": lambda: self.read_file_with_vision(args.get("file_path", "")),
            "list_directory": lambda: self.list_directory(args.get("directory_path", "")),
            "get_file_info": lambda: self.get_file_info(args.get("file_path", "")),
            "search_files": lambda: self.search_files(args.get("pattern", "")),
            "get_recent_files": lambda: self.get_recent_files(args.get("hours", 1))
        }
        
        if tool_name in tools:
            return tools[tool_name]()
        else:
            return f"Unknown tool: {tool_name}"
    
    def _capture_loop(self):
        """Main capture loop"""
        print(f"Background companion started. Capturing every {self.capture_interval} seconds.")
        print(f"Watching directories: {self.watch_dirs}")
        print("Press Ctrl+C to stop.")
        
        while self.running:
            try:
                # Get active context (apps, files)
                active_context = self._get_active_context()
                
                # Capture screenshot
                screenshot_path = self._capture_screenshot()
                
                if screenshot_path:
                    # Analyze with Gemini
                    print(f"Analyzing screenshot: {screenshot_path}")
                    description = self._analyze_screenshot(screenshot_path, active_context)
                    
                    # Store in database
                    self._store_context(screenshot_path, description, active_context)
                
                # Wait for next capture
                time.sleep(self.capture_interval)
                
            except Exception as e:
                print(f"Error in capture loop: {e}")
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
        
        print(f"\n🔍 Searching through {count} stored contexts...")
        
        # Use RAG to retrieve relevant contexts
        relevant_contexts = self._retrieve_relevant_contexts(question, top_k=10)
        
        if not relevant_contexts:
            return "No relevant context found. Try capturing more activity!"
        
        # Build context string with file information
        context_parts = []
        all_files = set()
        
        print("\n📊 Retrieved contexts:")
        for idx, (ctx_id, timestamp, desc, files_json, apps_json, similarity) in enumerate(relevant_contexts, 1):
            # Indicate if this is a recent context (always included)
            marker = "📌 RECENT" if similarity == 1.0 else f"🎯 {similarity:.3f}"
            print(f"  {idx}. [{marker}] {timestamp}")
            
            context_parts.append(f"[Context {idx} - {timestamp} - Relevance: {marker}]\n{desc}")
            
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
        try:
            model_with_tools = genai.GenerativeModel(
                'gemini-2.5-flash',
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

You have access to file system tools. You can:
- read_file_as_text: Read text-based files (code, documents, PDFs, Word docs, Excel, etc.) and get extracted text
- read_file_with_vision: Use AI vision to analyze any file including images, PDFs, and complex documents
- list_directory: List directory contents  
- get_file_info: Get file metadata
- search_files: Search for files by pattern (e.g., "*.py", "config.*")
- get_recent_files: Get recently modified files

IMPORTANT: For Word documents (.docx), PDFs, and other complex documents, you can use EITHER:
1. read_file_as_text - to get extracted text content
2. read_file_with_vision - to send the file directly to Gemini for comprehensive analysis

Both methods will give you the full content. Use read_file_with_vision for PDFs and documents where you want the most comprehensive extraction.

User Question: {question}

Provide a detailed answer. If you need to access files to answer better, use the available tools with full file paths."""
        
        try:
            # Start chat with tools
            print("\n💬 Processing with Gemini...")
            chat = model_with_tools.start_chat()
            response = chat.send_message(prompt)
            
            # Handle function calls
            max_iterations = 10
            iteration = 0
            
            while iteration < max_iterations:
                # Check if response is None or has no candidates
                if not response or not hasattr(response, 'candidates') or not response.candidates:
                    print("Warning: Empty response from model")
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
                function_responses = []
                for fc in function_calls:
                    tool_name = fc.function_call.name
                    tool_args = dict(fc.function_call.args)
                    
                    print(f"🔧 Executing tool: {tool_name} with args: {tool_args}")
                    result = self._execute_tool(tool_name, tool_args)
                    
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
                    response = chat.send_message(function_responses)
                except Exception as e:
                    print(f"Error sending function responses: {e}")
                    break
                    
                iteration += 1
            
            # Extract final text response
            final_text = ""
            if response and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            final_text += part.text
            
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
            SELECT id, description
            FROM context_snapshots 
            WHERE embedding IS NULL
        ''')
        
        contexts_to_index = cursor.fetchall()
        
        if not contexts_to_index:
            print("All contexts already have embeddings!")
            conn.close()
            return
        
        print(f"Generating embeddings for {len(contexts_to_index)} contexts...")
        
        for idx, (ctx_id, description) in enumerate(contexts_to_index, 1):
            print(f"Processing {idx}/{len(contexts_to_index)}...", end='\r')
            
            embedding = self._generate_embedding(description)
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
    parser = argparse.ArgumentParser(description='AI Background Companion with RAG-based Context Retrieval')
    parser.add_argument('mode', choices=['capture', 'query', 'list', 'reindex'], 
                       help='Mode: capture, query, list, or reindex')
    parser.add_argument('--api-key', required=True, help='Google Gemini API key')
    parser.add_argument('--interval', type=int, default=60, 
                       help='Capture interval in seconds (default: 60)')
    parser.add_argument('--watch-dirs', nargs='+', 
                       help='Directories to watch for file context (e.g., ~/Documents ~/Projects)')
    parser.add_argument('--question', help='Question to ask (for query mode)')
    parser.add_argument('--limit', type=int, default=10, 
                       help='Number of recent items to show (for list mode)')
    parser.add_argument('--always-recent', type=int, default=3,
                       help='Number of most recent contexts to always include in retrieval (default: 3)')
    
    args = parser.parse_args()
    
    # Expand paths
    watch_dirs = []
    if args.watch_dirs:
        watch_dirs = [str(Path(d).expanduser().resolve()) for d in args.watch_dirs]
    
    companion = BackgroundCompanion(
        api_key=args.api_key,
        capture_interval=args.interval,
        watch_dirs=watch_dirs,
        always_recent=args.always_recent
    )
    
    if args.mode == 'capture':
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