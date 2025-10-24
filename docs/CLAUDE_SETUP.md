# Claude 4.5 Sonnet Setup Guide

## Overview

Ghost Widget supports **Claude 4.5 Sonnet via Google Cloud Vertex AI** as an optional model for question answering, while **always using Gemini 2.5 Flash** for screenshot evaluation. You can choose which model to use for Q&A in the settings:

- **Gemini 2.5 Flash**: Fast, free/low-cost, excellent for most use cases (default)
- **Claude 4.5 Sonnet**: Superior reasoning and complex problem-solving (requires Vertex AI setup)

**Screenshot analysis always uses Gemini** regardless of your Q&A model choice, ensuring cost-effective visual processing.

## Prerequisites

1. **Google Cloud Project** with Vertex AI enabled
2. **Anthropic Claude access** on Vertex AI (enable from Model Garden)
3. **Google Cloud SDK** installed and configured
4. **Python packages** from requirements.txt

## Setup Instructions

### 1. Enable Claude on Vertex AI

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **Vertex AI** > **Model Garden**
3. Search for **"Claude Sonnet 4.5"**
4. Click **Enable** to activate the model in your project
5. Note your **Project ID** (you'll need this later)

### 2. Install Required Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `anthropic[vertex]>=0.18.0` - Claude SDK with Vertex AI support
- `google-generativeai>=0.3.0` - Gemini SDK (for screenshots)
- All other required packages

### 3. Configure Google Cloud Authentication

You need to authenticate with Google Cloud to use Vertex AI:

```bash
# Install Google Cloud SDK if not already installed
# Download from: https://cloud.google.com/sdk/docs/install

# Authenticate with your Google Cloud account
gcloud auth application-default login

# Set your project ID
gcloud config set project YOUR_PROJECT_ID
```

### 4. Set Environment Variables

Set the following environment variables before running Ghost Widget:

```bash
# Windows (Command Prompt)
set GOOGLE_CLOUD_PROJECT=your-gcp-project-id
set GOOGLE_CLOUD_REGION=us-east5

# Windows (PowerShell)
$env:GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
$env:GOOGLE_CLOUD_REGION="us-east5"

# Linux/Mac
export GOOGLE_CLOUD_PROJECT=your-gcp-project-id
export GOOGLE_CLOUD_REGION=us-east5
```

**Available Regions for Claude:**
- `us-east5` (US - recommended)
- `europe-west1` (Europe)
- `asia-southeast1` (Asia Pacific)

### 5. Select Model in Ghost Widget

1. Run Ghost Widget:
   ```bash
   python main.py
   ```

2. Go to the **Settings** tab

3. Find the **QA Model** dropdown

4. Select **"Claude 4.5 Sonnet"** from the dropdown

5. Click **Save Config**

6. **Restart** Ghost Widget for the changes to take effect

When you ask questions after restart, Ghost Widget will use Claude 4.5 Sonnet for processing!

## Verification

### During Startup

When Ghost Widget starts with Claude enabled, you should see:

```
OK Mem0 platform initialized for user: your-user-id
OK Claude 4.5 Sonnet initialized via Vertex AI (project: your-project-id, region: us-east5)
```

If Claude is not configured or fails to initialize, you'll see a warning but the app will continue with Gemini:

```
WARNING Failed to initialize Claude on Vertex AI: [error details]
   Falling back to Gemini for question answering
```

### When Asking Questions

If you selected **Claude** in settings and it's available:
```
🤖 PROCESSING YOUR QUESTION WITH CLAUDE 4.5 SONNET
```

If you selected **Gemini** in settings (or Claude unavailable):
```
🤖 PROCESSING YOUR QUESTION
💬 Step 3: Processing with Gemini AI...
```

## Model Selection Behavior

### How It Works

1. **You choose** which model to use via the **Settings** tab
2. **Gemini is always used** for screenshot analysis (cost-effective)
3. **Your selected model** is used for question answering

### Automatic Fallback

If you select **Claude** but it's not available:
- Ghost Widget will show a warning: `⚠️ Claude selected but not available. Falling back to Gemini.`
- Questions will be processed with Gemini instead
- You can continue using the app normally

Common reasons Claude may be unavailable:
- Claude not enabled in Vertex AI Model Garden
- Missing `GOOGLE_CLOUD_PROJECT` environment variable
- Authentication not configured (`gcloud auth application-default login`)
- Invalid project ID or region
- `anthropic[vertex]` package not installed

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Ghost Widget                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Screenshot Capture → Gemini 2.5 Flash             │
│  (Visual Analysis)    (Fast, vision-optimized)     │
│                                                     │
│  Question Answering → Claude 4.5 Sonnet            │
│  (RAG + Tools)        (Superior reasoning)         │
│                                                     │
│  Memory Storage    → Mem0 Platform                 │
│  (Context DB)         (Graph memory)               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Features Supported by Claude

✅ **Tool Calling**: All file system tools and web search
✅ **RAG Retrieval**: Semantic search through captured contexts
✅ **Multi-turn Conversations**: Complex reasoning with multiple tool calls
✅ **Large Context**: Up to 200,000 tokens input (1M in preview)
✅ **File Analysis**: Read text, PDFs, Word docs, Excel, images, etc.

## Quick Start (Without Claude)

If you don't have Vertex AI quotas approved yet, **you can still use Ghost Widget with Gemini**:

1. Install dependencies: `pip install -r requirements.txt`
2. Run: `python main.py`
3. In Settings, ensure **QA Model** is set to **"Gemini (Default)"**
4. All features work normally with Gemini

When your Vertex AI quotas are approved, follow the setup steps above to enable Claude.

## Pricing

### Claude 4.5 Sonnet on Vertex AI:
- **Input**: $3 per million tokens
- **Output**: $15 per million tokens
- **Note**: Requires quota approval from Google Cloud

### Gemini 2.5 Flash (Default):
- **Free tier available** for development
- **Screenshots**: Always free/low-cost (used for all visual analysis)
- **Q&A**: Free for moderate use
- Check [Google AI Pricing](https://ai.google.dev/pricing) for details

## Troubleshooting

### Error: "No project ID provided"

**Solution**: Set the `GOOGLE_CLOUD_PROJECT` environment variable:
```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
```

### Error: "Could not load credentials"

**Solution**: Run authentication command:
```bash
gcloud auth application-default login
```

### Error: "Claude model not found"

**Solution**: Enable Claude in Vertex AI Model Garden:
1. Go to Vertex AI > Model Garden
2. Search for "Claude Sonnet 4.5"
3. Click "Enable"

### Claude not being used (falls back to Gemini)

**Check**:
1. Did you select Claude in Settings > QA Model dropdown?
2. Did you save the config and restart Ghost Widget?
3. Is `anthropic[vertex]` installed? Run: `pip list | grep anthropic`
4. Are environment variables set? Echo them to verify
5. Is authentication configured? Run: `gcloud auth application-default print-access-token`
6. Do you have Vertex AI quotas approved for Claude?

## Development Notes

- Screenshot analysis continues to use Gemini (optimized for vision)
- Claude is used only for question answering (optimized for reasoning)
- All existing tools work seamlessly with both models
- Fallback to Gemini ensures reliability even if Claude unavailable

## Additional Resources

- [Claude on Vertex AI Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude)
- [Anthropic SDK Documentation](https://docs.anthropic.com/en/api/claude-on-vertex-ai)
- [Google Cloud Vertex AI](https://cloud.google.com/vertex-ai)
- [Ghost Widget Mem0 Setup](./MEM0_SETUP.md)
- [Ghost Widget Firebase Setup](./FIREBASE_SETUP.md)
