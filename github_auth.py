"""
GitHub Authentication Module for Ghost Widget

Handles GitHub authentication using OAuth Device Flow
and provides methods to access GitHub API data.
"""

import json
import time
import webbrowser
import requests
import os
from pathlib import Path

try:
    from github import Github, Auth
    from github.GithubException import GithubException, BadCredentialsException
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    Github = None
    Auth = None
    GithubException = Exception
    BadCredentialsException = Exception

# GitHub OAuth App credentials
# You need to create your own GitHub OAuth App and add the client ID here
# See docs/GITHUB_SETUP.md for instructions
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
if not GITHUB_CLIENT_ID:
    print("[WARNING] GITHUB_CLIENT_ID not set in environment. GitHub integration will not work.")


class GitHubAuth:
    """Manages GitHub authentication and API access"""

    def __init__(self, config_path="github_config.json"):
        """
        Initialize GitHub authentication

        Args:
            config_path: Path to JSON file storing GitHub token
        """
        self.config_path = Path(config_path)
        self.github_client = None
        self.authenticated_user = None
        self.token = None

        if not GITHUB_AVAILABLE:
            print("Warning: PyGithub not installed. GitHub integration disabled.")
            return

        # Try to load existing token
        self._load_token()

    def _load_token(self):
        """Load GitHub token from config file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    token = config.get('github_token')
                    if token:
                        self.authenticate(token)
            except Exception as e:
                print(f"Error loading GitHub token: {e}")

    def _save_token(self, token):
        """Save GitHub token to config file"""
        try:
            config = {'github_token': token}
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving GitHub token: {e}")

    def sign_in_with_browser(self, progress_callback=None):
        """
        Authenticate with GitHub using OAuth Device Flow (browser-based)
        Similar to GitHub Desktop authentication

        Args:
            progress_callback: Optional callback function(message: str, user_code=None, verification_url=None) for progress updates

        Returns:
            dict: {'success': bool, 'message': str, 'user': str or None}
        """
        if not GITHUB_AVAILABLE:
            return {
                'success': False,
                'message': 'PyGithub not installed',
                'user': None
            }

        # Check if GitHub OAuth App is configured
        if GITHUB_CLIENT_ID == "YOUR_GITHUB_CLIENT_ID_HERE":
            return {
                'success': False,
                'message': 'GitHub OAuth App not configured. Please create a GitHub OAuth App and set GITHUB_CLIENT_ID. See docs/GITHUB_SETUP.md for instructions.',
                'user': None
            }

        try:
            # Step 1: Request device and user codes
            if progress_callback:
                progress_callback("🔄 Initiating GitHub authentication...")

            device_response = requests.post(
                'https://github.com/login/device/code',
                headers={'Accept': 'application/json'},
                data={
                    'client_id': GITHUB_CLIENT_ID,
                    'scope': 'repo user:email'
                }
            )

            if device_response.status_code != 200:
                return {
                    'success': False,
                    'message': f'Failed to initiate GitHub auth: {device_response.status_code}',
                    'user': None
                }

            device_data = device_response.json()
            device_code = device_data['device_code']
            user_code = device_data['user_code']
            verification_uri = device_data['verification_uri']
            expires_in = device_data['expires_in']
            interval = device_data.get('interval', 5)

            # Step 2: Show user code and open browser
            print(f"\n{'='*60}")
            print(f"🔐 GitHub Authentication")
            print(f"{'='*60}")
            print(f"User Code: {user_code}")
            print(f"Opening browser to: {verification_uri}")
            print(f"{'='*60}\n")

            if progress_callback:
                # Send structured user code data to the callback
                print(f"[GITHUB_AUTH] Calling progress_callback with user_code={user_code}")
                try:
                    # Try calling with keyword arguments (for GUI)
                    progress_callback("Opening browser...", user_code=user_code, verification_url=verification_uri)
                    print(f"[GITHUB_AUTH] Successfully called progress_callback with keyword args")
                except TypeError as e:
                    print(f"[GITHUB_AUTH] TypeError calling progress_callback: {e}")
                    # Fallback to simple string message (for console/older callers)
                    progress_callback(f"🔐 User Code: {user_code}")
                    progress_callback(f"Opening browser to {verification_uri}...")

            # Open browser
            webbrowser.open(verification_uri)

            # Step 3: Poll for authorization
            if progress_callback:
                progress_callback("⏳ Waiting for you to authorize in the browser...")

            start_time = time.time()
            while time.time() - start_time < expires_in:
                time.sleep(interval)

                # Poll the token endpoint
                token_response = requests.post(
                    'https://github.com/login/oauth/access_token',
                    headers={'Accept': 'application/json'},
                    data={
                        'client_id': GITHUB_CLIENT_ID,
                        'device_code': device_code,
                        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
                    }
                )

                if token_response.status_code != 200:
                    continue

                token_data = token_response.json()

                # Check for errors
                if 'error' in token_data:
                    error = token_data['error']
                    if error == 'authorization_pending':
                        # Still waiting for user
                        continue
                    elif error == 'slow_down':
                        # Rate limit - increase interval
                        interval += 5
                        continue
                    elif error == 'expired_token':
                        return {
                            'success': False,
                            'message': 'Authentication expired. Please try again.',
                            'user': None
                        }
                    elif error == 'access_denied':
                        return {
                            'success': False,
                            'message': 'Access denied. You cancelled the authorization.',
                            'user': None
                        }
                    else:
                        return {
                            'success': False,
                            'message': f'GitHub auth error: {error}',
                            'user': None
                        }

                # Success! We have an access token
                if 'access_token' in token_data:
                    access_token = token_data['access_token']

                    if progress_callback:
                        progress_callback("✅ Authorization successful! Setting up GitHub access...")

                    # Use the token to authenticate
                    return self.authenticate(access_token)

            # Timeout
            return {
                'success': False,
                'message': 'Authentication timed out. Please try again.',
                'user': None
            }

        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error during authentication: {str(e)}',
                'user': None
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Authentication error: {str(e)}',
                'user': None
            }

    def authenticate(self, token):
        """
        Authenticate with GitHub using a Personal Access Token

        Args:
            token: GitHub Personal Access Token

        Returns:
            dict: {'success': bool, 'message': str, 'user': str or None}
        """
        if not GITHUB_AVAILABLE:
            return {
                'success': False,
                'message': 'PyGithub not installed',
                'user': None
            }

        try:
            # Create authentication
            auth = Auth.Token(token)

            # Create GitHub instance
            self.github_client = Github(auth=auth)

            # Test authentication by getting user info
            self.authenticated_user = self.github_client.get_user()
            username = self.authenticated_user.login

            # Save token
            self.token = token
            self._save_token(token)

            return {
                'success': True,
                'message': f'Successfully authenticated as {username}',
                'user': username
            }

        except BadCredentialsException:
            self.github_client = None
            self.authenticated_user = None
            return {
                'success': False,
                'message': 'Invalid GitHub token',
                'user': None
            }
        except GithubException as e:
            self.github_client = None
            self.authenticated_user = None
            return {
                'success': False,
                'message': f'GitHub API error: {str(e)}',
                'user': None
            }
        except Exception as e:
            self.github_client = None
            self.authenticated_user = None
            return {
                'success': False,
                'message': f'Authentication error: {str(e)}',
                'user': None
            }

    def logout(self):
        """Logout and clear stored token"""
        if self.github_client:
            self.github_client.close()

        self.github_client = None
        self.authenticated_user = None
        self.token = None

        # Remove token file
        if self.config_path.exists():
            self.config_path.unlink()

        return {'success': True, 'message': 'Logged out successfully'}

    def is_authenticated(self):
        """Check if user is authenticated"""
        return self.github_client is not None and self.authenticated_user is not None

    def get_user_info(self):
        """
        Get authenticated user information

        Returns:
            dict: User information or None if not authenticated
        """
        if not self.is_authenticated():
            return None

        try:
            user = self.authenticated_user
            return {
                'login': user.login,
                'name': user.name,
                'email': user.email,
                'bio': user.bio,
                'public_repos': user.public_repos,
                'followers': user.followers,
                'following': user.following,
                'avatar_url': user.avatar_url,
                'html_url': user.html_url
            }
        except Exception as e:
            print(f"Error getting user info: {e}")
            return None

    def get_repository(self, repo_name):
        """
        Get a repository by name (format: owner/repo)

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            Repository object or None
        """
        if not self.is_authenticated():
            return None

        try:
            return self.github_client.get_repo(repo_name)
        except Exception as e:
            print(f"Error getting repository {repo_name}: {e}")
            return None

    def get_latest_commits(self, repo_name, count=10):
        """
        Get latest commits from a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            count: Number of commits to retrieve

        Returns:
            list: List of commit dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            commits = []
            for commit in repo.get_commits()[:count]:
                commits.append({
                    'sha': commit.sha,
                    'message': commit.commit.message,
                    'author': commit.commit.author.name,
                    'author_email': commit.commit.author.email,
                    'date': commit.commit.author.date.isoformat(),
                    'url': commit.html_url,
                    'stats': {
                        'additions': commit.stats.additions if commit.stats else 0,
                        'deletions': commit.stats.deletions if commit.stats else 0,
                        'total': commit.stats.total if commit.stats else 0
                    }
                })

            return commits
        except Exception as e:
            print(f"Error getting commits from {repo_name}: {e}")
            return None

    def get_repository_info(self, repo_name):
        """
        Get repository information

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            dict: Repository information or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            return {
                'name': repo.name,
                'full_name': repo.full_name,
                'description': repo.description,
                'url': repo.html_url,
                'stars': repo.stargazers_count,
                'forks': repo.forks_count,
                'watchers': repo.watchers_count,
                'language': repo.language,
                'created_at': repo.created_at.isoformat() if repo.created_at else None,
                'updated_at': repo.updated_at.isoformat() if repo.updated_at else None,
                'pushed_at': repo.pushed_at.isoformat() if repo.pushed_at else None,
                'default_branch': repo.default_branch,
                'open_issues': repo.open_issues_count,
                'license': repo.license.name if repo.license else None
            }
        except Exception as e:
            print(f"Error getting repository info for {repo_name}: {e}")
            return None

    def search_repositories(self, query, max_results=10):
        """
        Search for repositories

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            list: List of repository dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            results = []
            repositories = self.github_client.search_repositories(query)

            for repo in repositories[:max_results]:
                results.append({
                    'name': repo.name,
                    'full_name': repo.full_name,
                    'description': repo.description,
                    'url': repo.html_url,
                    'stars': repo.stargazers_count,
                    'language': repo.language
                })

            return results
        except Exception as e:
            print(f"Error searching repositories: {e}")
            return None

    def get_user_repositories(self, max_results=100):
        """
        Get all repositories for the authenticated user

        Args:
            max_results: Maximum number of repositories to retrieve

        Returns:
            list: List of repository dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            results = []
            repos = self.authenticated_user.get_repos(sort='updated', direction='desc')

            for repo in repos[:max_results]:
                results.append({
                    'name': repo.name,
                    'full_name': repo.full_name,
                    'description': repo.description,
                    'url': repo.html_url,
                    'stars': repo.stargazers_count,
                    'forks': repo.forks_count,
                    'language': repo.language,
                    'updated_at': repo.updated_at.isoformat() if repo.updated_at else None,
                    'is_private': repo.private,
                    'is_fork': repo.fork
                })

            return results
        except Exception as e:
            print(f"Error getting user repositories: {e}")
            return None

    def get_repository_readme(self, repo_name):
        """
        Get README content from a repository

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            dict: README information including content or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            try:
                readme = repo.get_readme()
                content = readme.decoded_content.decode('utf-8')

                return {
                    'content': content,
                    'name': readme.name,
                    'path': readme.path,
                    'size': readme.size,
                    'url': readme.html_url
                }
            except GithubException as e:
                if e.status == 404:
                    return {
                        'content': None,
                        'error': 'README not found'
                    }
                raise

        except Exception as e:
            print(f"Error getting README from {repo_name}: {e}")
            return None

    def get_pull_requests(self, repo_name, state='all', max_results=30):
        """
        Get pull requests from a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            state: PR state - 'open', 'closed', or 'all' (default: 'all')
            max_results: Maximum number of PRs to retrieve (default: 30)

        Returns:
            list: List of pull request dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            prs = []
            for pr in repo.get_pulls(state=state, sort='updated', direction='desc')[:max_results]:
                prs.append({
                    'number': pr.number,
                    'title': pr.title,
                    'state': pr.state,
                    'author': pr.user.login if pr.user else None,
                    'created_at': pr.created_at.isoformat() if pr.created_at else None,
                    'updated_at': pr.updated_at.isoformat() if pr.updated_at else None,
                    'merged': pr.merged,
                    'merged_at': pr.merged_at.isoformat() if pr.merged_at else None,
                    'body': pr.body,
                    'url': pr.html_url,
                    'head_branch': pr.head.ref if pr.head else None,
                    'base_branch': pr.base.ref if pr.base else None,
                    'additions': pr.additions,
                    'deletions': pr.deletions,
                    'changed_files': pr.changed_files,
                    'comments': pr.comments,
                    'review_comments': pr.review_comments,
                    'commits': pr.commits
                })

            return prs
        except Exception as e:
            print(f"Error getting pull requests from {repo_name}: {e}")
            return None

    def get_issues(self, repo_name, state='all', max_results=30):
        """
        Get issues from a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            state: Issue state - 'open', 'closed', or 'all' (default: 'all')
            max_results: Maximum number of issues to retrieve (default: 30)

        Returns:
            list: List of issue dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            issues = []
            for issue in repo.get_issues(state=state, sort='updated', direction='desc')[:max_results]:
                # Skip pull requests (they show up in issues API)
                if issue.pull_request:
                    continue

                issues.append({
                    'number': issue.number,
                    'title': issue.title,
                    'state': issue.state,
                    'author': issue.user.login if issue.user else None,
                    'created_at': issue.created_at.isoformat() if issue.created_at else None,
                    'updated_at': issue.updated_at.isoformat() if issue.updated_at else None,
                    'closed_at': issue.closed_at.isoformat() if issue.closed_at else None,
                    'body': issue.body,
                    'url': issue.html_url,
                    'labels': [label.name for label in issue.labels],
                    'comments': issue.comments,
                    'assignees': [assignee.login for assignee in issue.assignees] if issue.assignees else []
                })

            return issues
        except Exception as e:
            print(f"Error getting issues from {repo_name}: {e}")
            return None

    def get_branches(self, repo_name, max_results=30):
        """
        Get branches from a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            max_results: Maximum number of branches to retrieve (default: 30)

        Returns:
            list: List of branch dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            branches = []
            for branch in repo.get_branches()[:max_results]:
                branches.append({
                    'name': branch.name,
                    'protected': branch.protected,
                    'commit_sha': branch.commit.sha if branch.commit else None,
                    'commit_url': branch.commit.html_url if branch.commit else None
                })

            return branches
        except Exception as e:
            print(f"Error getting branches from {repo_name}: {e}")
            return None

    def get_commit_details(self, repo_name, commit_sha):
        """
        Get detailed information about a specific commit

        Args:
            repo_name: Repository name in format "owner/repo"
            commit_sha: The commit SHA to retrieve

        Returns:
            dict: Detailed commit information or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            commit = repo.get_commit(commit_sha)

            files = []
            for file in commit.files:
                files.append({
                    'filename': file.filename,
                    'status': file.status,
                    'additions': file.additions,
                    'deletions': file.deletions,
                    'changes': file.changes,
                    'patch': file.patch if hasattr(file, 'patch') else None
                })

            return {
                'sha': commit.sha,
                'message': commit.commit.message,
                'author': commit.commit.author.name,
                'author_email': commit.commit.author.email,
                'date': commit.commit.author.date.isoformat(),
                'url': commit.html_url,
                'stats': {
                    'additions': commit.stats.additions if commit.stats else 0,
                    'deletions': commit.stats.deletions if commit.stats else 0,
                    'total': commit.stats.total if commit.stats else 0
                },
                'files': files,
                'parents': [p.sha for p in commit.parents] if commit.parents else []
            }
        except Exception as e:
            print(f"Error getting commit details {commit_sha} from {repo_name}: {e}")
            return None

    def get_contributors(self, repo_name, max_results=30):
        """
        Get contributors to a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            max_results: Maximum number of contributors to retrieve (default: 30)

        Returns:
            list: List of contributor dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            contributors = []
            for contributor in repo.get_contributors()[:max_results]:
                contributors.append({
                    'login': contributor.login,
                    'name': contributor.name,
                    'contributions': contributor.contributions,
                    'avatar_url': contributor.avatar_url,
                    'profile_url': contributor.html_url
                })

            return contributors
        except Exception as e:
            print(f"Error getting contributors from {repo_name}: {e}")
            return None

    def get_releases(self, repo_name, max_results=10):
        """
        Get releases from a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            max_results: Maximum number of releases to retrieve (default: 10)

        Returns:
            list: List of release dictionaries or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            releases = []
            for release in repo.get_releases()[:max_results]:
                releases.append({
                    'tag_name': release.tag_name,
                    'name': release.title,
                    'published_at': release.published_at.isoformat() if release.published_at else None,
                    'author': release.author.login if release.author else None,
                    'body': release.body,
                    'url': release.html_url,
                    'prerelease': release.prerelease,
                    'draft': release.draft,
                    'tarball_url': release.tarball_url,
                    'zipball_url': release.zipball_url
                })

            return releases
        except Exception as e:
            print(f"Error getting releases from {repo_name}: {e}")
            return None

    def get_repository_contents(self, repo_name, path="", ref=None):
        """
        Get contents of a directory or file from a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            path: Path within the repository (empty string for root)
            ref: Branch/tag/commit to read from (default: default branch)

        Returns:
            list: List of file/directory information or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            contents = repo.get_contents(path, ref=ref) if ref else repo.get_contents(path)

            # Handle single file
            if not isinstance(contents, list):
                contents = [contents]

            result = []
            for content in contents:
                item = {
                    'name': content.name,
                    'path': content.path,
                    'type': content.type,  # 'file' or 'dir'
                    'size': content.size,
                    'sha': content.sha,
                    'url': content.html_url,
                    'download_url': content.download_url if content.type == 'file' else None
                }
                result.append(item)

            return result
        except GithubException as e:
            if e.status == 404:
                return {'error': 'Path not found'}
            print(f"Error getting contents from {repo_name}:{path}: {e}")
            return None
        except Exception as e:
            print(f"Error getting contents from {repo_name}:{path}: {e}")
            return None

    def get_file_content(self, repo_name, file_path, ref=None):
        """
        Get the content of a specific file from a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            file_path: Path to the file within the repository
            ref: Branch/tag/commit to read from (default: default branch)

        Returns:
            dict: File content and metadata or None
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            file_content = repo.get_contents(file_path, ref=ref) if ref else repo.get_contents(file_path)

            # Decode content
            try:
                content = file_content.decoded_content.decode('utf-8')
            except UnicodeDecodeError:
                # Binary file
                content = None
                content_base64 = file_content.content

            return {
                'name': file_content.name,
                'path': file_content.path,
                'size': file_content.size,
                'content': content,
                'encoding': file_content.encoding,
                'sha': file_content.sha,
                'url': file_content.html_url,
                'download_url': file_content.download_url,
                'is_binary': content is None
            }
        except GithubException as e:
            if e.status == 404:
                return {'error': 'File not found'}
            print(f"Error getting file content from {repo_name}:{file_path}: {e}")
            return None
        except Exception as e:
            print(f"Error getting file content from {repo_name}:{file_path}: {e}")
            return None

    def get_repository_tree(self, repo_name, ref=None, recursive=True):
        """
        Get the complete file tree of a repository

        Args:
            repo_name: Repository name in format "owner/repo"
            ref: Branch/tag/commit to read from (default: default branch)
            recursive: Get full tree recursively (default: True)

        Returns:
            list: List of all files and directories with paths
        """
        if not self.is_authenticated():
            return None

        try:
            repo = self.get_repository(repo_name)
            if not repo:
                return None

            # Get the branch
            if ref:
                branch = repo.get_branch(ref)
            else:
                branch = repo.get_branch(repo.default_branch)

            # Get the tree
            tree = repo.get_git_tree(branch.commit.sha, recursive=recursive)

            result = []
            for item in tree.tree:
                result.append({
                    'path': item.path,
                    'type': item.type,  # 'blob' (file) or 'tree' (directory)
                    'size': item.size,
                    'sha': item.sha,
                    'url': item.url
                })

            return result
        except Exception as e:
            print(f"Error getting repository tree from {repo_name}: {e}")
            return None


# Singleton instance
_github_auth_instance = None

def get_github_auth():
    """Get or create the singleton GitHub auth instance"""
    global _github_auth_instance
    if _github_auth_instance is None:
        _github_auth_instance = GitHubAuth()
    return _github_auth_instance
