# GitHub Integration Setup Guide

## Quick Start (TL;DR)

1. **Create GitHub OAuth App:** https://github.com/settings/developers → New OAuth App
   - Name: `Ghost Widget`
   - Homepage: `https://github.com/yourusername/ghost-widget`
   - Callback: `http://localhost`

2. **Copy Client ID** and set it:
   ```bash
   # Windows
   set GITHUB_CLIENT_ID=your_client_id_here

   # OR edit github_auth.py line 28
   GITHUB_CLIENT_ID = "your_client_id_here"
   ```

3. **Install & Run:**
   ```bash
   pip install -r requirements.txt
   python main.py
   ```

4. **Sign In:** Click "🔗 Sign in with GitHub" in Auth tab → Authorize in browser → Done!

---

## Overview

Ghost Widget now supports **GitHub integration with browser-based OAuth authentication** (just like GitHub Desktop!). You can query repository information directly from the AI and ask questions like:

- "Write me a blog post about the latest commit to repository facebook/react"
- "What are the most recent changes in anthropics/anthropic-sdk-python?"
- "Search for popular machine learning repositories and summarize them"
- "Get information about the torvalds/linux repository"

## Features

✅ **Browser-Based Authentication** - No manual token creation needed!
✅ **Get Recent Commits** - Fetch commit history with messages, authors, and stats
✅ **Repository Information** - Get stars, forks, description, language, and more
✅ **Search Repositories** - Find repositories by keyword
✅ **AI-Powered Analysis** - Use Claude or Gemini to analyze and write about repository data
✅ **Blog Post Generation** - Automatically generate blog posts from commit history
✅ **Persistent Sessions** - Stay logged in across app restarts

## Prerequisites

1. **GitHub Account** (free or paid)
2. **PyGithub** installed (included in requirements.txt)
3. **Web browser** (for authentication)

## Setup Instructions

### Step 1: Create a GitHub OAuth App

Before you can use GitHub authentication, you need to create a GitHub OAuth App:

1. **Go to GitHub Developer Settings:**
   - Navigate to: https://github.com/settings/developers
   - Or: GitHub Settings → Developer settings → OAuth Apps

2. **Click "New OAuth App"**

3. **Fill in the application details:**
   ```
   Application name: Ghost Widget (or any name you prefer)
   Homepage URL: https://github.com/yourusername/ghost-widget
   Application description: AI-powered screen context companion with GitHub integration
   Authorization callback URL: http://localhost
   ```

   **Note:** The callback URL doesn't matter for Device Flow, but GitHub requires it. Use `http://localhost`

4. **Click "Register application"**

5. **Copy your Client ID:**
   - You'll see your new OAuth App's details
   - Copy the **Client ID** (it looks like: `Ov23liXXXXXXXXXX`)
   - **Important:** You don't need the Client Secret for Device Flow!

6. **Enable Device Flow (if required):**
   - Some GitHub accounts require you to enable Device Flow
   - Check the OAuth App settings page
   - Look for "Enable Device Flow" checkbox and enable it if present

### Step 2: Configure Ghost Widget

**Option A: Environment Variable (Recommended)**

Set the `GITHUB_CLIENT_ID` environment variable:

```bash
# Windows (Command Prompt)
set GITHUB_CLIENT_ID=your_client_id_here

# Windows (PowerShell)
$env:GITHUB_CLIENT_ID="your_client_id_here"

# Linux/Mac
export GITHUB_CLIENT_ID=your_client_id_here
```

**Option B: Edit github_auth.py**

Open `github_auth.py` and replace the placeholder:

```python
GITHUB_CLIENT_ID = "your_actual_client_id_here"
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs PyGithub, requests, and all other required packages.

### Step 4: Run Ghost Widget

```bash
python main.py
```

### Step 5: Authenticate with GitHub

1. **Click the Auth Tab** in Ghost Widget
2. **Click "🔗 Sign in with GitHub"** button
3. **Your browser will open** automatically to GitHub's authorization page
4. **You'll see a device code** displayed in the Ghost Widget console
5. **In your browser**, GitHub will ask you to:
   - Enter the device code (if not auto-filled)
   - Review the permissions requested
   - Click "Authorize Ghost Widget"
6. **Return to Ghost Widget** - authentication completes automatically!
7. **Done!** You're now connected to GitHub

### Step 6: Verification

After successful authentication:
- Button changes to: "✓ Connected to GitHub"
- You'll see: "Connected as: your-github-username"
- Authentication persists across app restarts (no need to sign in again)

**Important Notes:**
- Make sure you created the GitHub OAuth App first and configured the Client ID
- The OAuth flow handles token generation automatically - no manual tokens needed!
- Your token is stored locally in `github_config.json` for persistent sessions

## Usage Examples

### Example 1: Get Latest Commits

**You ask:**
```
Get the latest 5 commits from facebook/react
```

**Ghost Widget will:**
1. Call the `github_get_commits` tool
2. Fetch commit data including messages, authors, dates, and code changes
3. Return structured information about each commit

### Example 2: Write a Blog Post

**You ask:**
```
Write me a blog post about the latest commits to anthropics/anthropic-sdk-python.
Focus on new features and improvements.
```

**Ghost Widget will:**
1. Fetch recent commits from the repository
2. Analyze the commit messages and code changes
3. Use Claude/Gemini to generate a well-structured blog post
4. Include relevant details about features, bug fixes, and improvements

### Example 3: Repository Analysis

**You ask:**
```
Give me information about the repository microsoft/vscode.
What's it about, how popular is it, and what language is it written in?
```

**Ghost Widget will:**
1. Call `github_get_repo_info` tool
2. Fetch repository metadata
3. Provide a summary including:
   - Description
   - Stars and forks count
   - Primary language
   - Last update date
   - Open issues count

### Example 4: Search for Repositories

**You ask:**
```
Search for popular Python machine learning libraries on GitHub and summarize the top 5
```

**Ghost Widget will:**
1. Call `github_search_repos` with query "machine learning python"
2. Retrieve top results
3. Summarize each repository with name, description, and stats

## Available GitHub Tools

Ghost Widget has access to these GitHub tools:

### 1. `github_get_commits`
- **Purpose**: Get recent commits from a repository
- **Parameters**:
  - `repo_name`: Repository in format "owner/repo" (e.g., "facebook/react")
  - `count`: Number of commits (default: 10, max: 50)
- **Returns**: Commit history with messages, authors, dates, and code statistics

### 2. `github_get_repo_info`
- **Purpose**: Get detailed repository information
- **Parameters**:
  - `repo_name`: Repository in format "owner/repo"
- **Returns**: Name, description, stars, forks, language, creation date, etc.

### 3. `github_search_repos`
- **Purpose**: Search for repositories by keyword
- **Parameters**:
  - `query`: Search query (e.g., "machine learning", "react hooks")
  - `max_results`: Maximum results to return (default: 10)
- **Returns**: List of matching repositories with basic info

## How It Works

```
┌─────────────────────────────────────────────────────┐
│               Your Question/Request                  │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│            Claude/Gemini processes request           │
│        Decides which GitHub tools to call            │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│               GitHub Auth Module                     │
│         (Authenticates with your token)              │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│              PyGithub Library                        │
│         (Fetches data from GitHub API)               │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│            Data returned to AI                       │
│      (Commits, repo info, search results)            │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│      AI analyzes and formats response                │
│   (Blog post, summary, analysis, etc.)               │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│            Response displayed to you                 │
└─────────────────────────────────────────────────────┘
```

## Troubleshooting

### Error: "GitHub OAuth App not configured"

**Full Error:** "Failed to initiate GitHub auth: 404" or "GitHub OAuth App not configured"

**Reason**: You haven't created a GitHub OAuth App or haven't set the Client ID

**Solution:**
1. Follow Step 1 to create a GitHub OAuth App: https://github.com/settings/developers
2. Copy your Client ID from the OAuth App page
3. Set it via environment variable:
   ```bash
   set GITHUB_CLIENT_ID=your_client_id_here
   ```
   OR edit `github_auth.py` and replace `YOUR_GITHUB_CLIENT_ID_HERE` with your actual Client ID
4. Restart Ghost Widget
5. Try signing in again

### Error: "Not authenticated with GitHub"

**Solution**: Click the "🔗 Sign in with GitHub" button in the Auth tab and complete the browser authentication flow.

### Browser doesn't open automatically

**Solution**:
1. Check the console output for the verification URL
2. Manually navigate to: `https://github.com/login/device`
3. Enter the device code shown in Ghost Widget
4. Complete the authorization

### Error: "Authentication timed out"

**Reasons**:
- Took too long to complete authorization (15 minutes limit)
- Network connection issues

**Solution**:
- Click "🔗 Sign in with GitHub" again to restart the flow
- Complete the authorization quickly (within 15 minutes)
- Check your internet connection

### Error: "Access denied"

**Reason**: You cancelled the authorization in your browser

**Solution**: Click "🔗 Sign in with GitHub" again and approve the authorization

### Error: "Repository not found" or "No access"

**Reasons**:
- Repository name is incorrect (should be "owner/repo")
- Repository is private (OAuth gives access to public repos by default)
- Repository doesn't exist

**Solution**:
- Check repository name format: "facebook/react" ✓ not "facebook-react" ✗
- For private repos, the OAuth flow should request additional permissions

### GitHub tools not being called

**Check**:
1. Is PyGithub installed? Run: `pip list | grep PyGithub`
2. Did you complete the sign-in process? Check for "✓ Connected to GitHub"
3. Check the console for "✅ GitHub: Auto-restored session"
4. Try signing out and signing in again

### Button stuck on "Signing in..."

**Reason**: Authentication process may have stalled

**Solution**:
1. Close and restart Ghost Widget
2. Try the sign-in process again
3. Check console for error messages

## Security & Privacy

🔐 **OAuth Security:**
- Ghost Widget uses GitHub's official OAuth Device Flow
- **No client secrets are stored** - uses public OAuth app credentials
- Your access token is **stored locally** in `github_config.json`
- Token is **never transmitted** to any third-party servers (only to GitHub)
- Authentication expires and can be revoked at any time

⚠️ **Permissions Granted:**
- `public_repo`: Access to public repositories
- `user:email`: Read your email address
- **No write access** to any repositories
- **No organization access**

🛡️ **Revoking Access:**
To revoke Ghost Widget's access to your GitHub account:
1. Go to [GitHub Settings > Applications](https://github.com/settings/applications)
2. Find "Ghost Widget" under "Authorized OAuth Apps"
3. Click "Revoke"
4. Delete `github_config.json` from your Ghost Widget directory

## Rate Limits

GitHub API has rate limits:
- **Authenticated requests**: 5,000 requests per hour
- **Unauthenticated**: 60 requests per hour

Ghost Widget uses authenticated requests (with your token), so you have plenty of API quota for normal usage.

## Example Use Cases

### 1. Technical Blog Writer
"Write a blog post about the latest 10 commits to vercel/next.js, highlighting new features and improvements"

### 2. Repository Researcher
"Compare the repositories tensorflow/tensorflow and pytorch/pytorch. Which one is more popular and actively maintained?"

### 3. Code Change Tracker
"What changes were made in the last 5 commits to the openai/gpt-4 repository? Summarize the key updates."

### 4. Technology Scout
"Search for the top 5 Rust web frameworks on GitHub and give me a brief overview of each"

### 5. Open Source Monitor
"Get information about the microsoft/TypeScript repository. When was the last commit? How many contributors does it have?"

## Additional Resources

- [GitHub Personal Access Tokens Documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
- [PyGithub Documentation](https://pygithub.readthedocs.io/)
- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [Ghost Widget Documentation](./README.md)
- [Claude Setup Guide](./CLAUDE_SETUP.md)

## Future Enhancements

Planned features for future releases:
- OAuth-based authentication (no manual token needed)
- Pull request information and analysis
- Issue tracking integration
- Repository comparison tools
- Contribution statistics
- Code review summaries
- Branch and tag information
