# Ghost Widget: Privacy-First Local Memory Manager for ADHD

## Overview
Ghost Widget is a privacy-first, local-first memory management tool designed specifically for people with ADHD and anyone who needs help organizing, recalling, and managing information. Unlike cloud-based solutions, Ghost Widget keeps your data on your device, ensuring your privacy and giving you full control over your information.

## Key Features
- **Local-First Storage:** All your data is stored locally. No information is sent to the cloud unless you explicitly enable integrations.
- **Privacy by Design:** No tracking, no analytics, and no hidden data collection. Your information stays yours.
- **Memory Tools:** Capture notes, tasks, and reminders quickly. Organize them with tags and search efficiently.
- **Smart Recording:** Record and transcribe important conversations or thoughts for later review.
- **Contextual Recall:** Retrieve information based on context, time, or topic, helping you remember what matters when you need it.
- **Integration Options:** Optional integrations with services like Firebase and GitHub for advanced users, but always opt-in and transparent.
- **Open Source:** Fully auditable codebase. Contribute or customize to fit your needs.

## Why Ghost Widget?
People with ADHD often struggle with memory, organization, and information overload. Ghost Widget is built to:
- Reduce cognitive load by making information easy to capture and retrieve
- Minimize distractions with a simple, focused interface
- Protect your privacy by keeping your data local
- Support flexible workflows for notes, tasks, and recordings

## Getting Started
### Prerequisites
- Python 3.8+
- (Optional) [FAISS](https://github.com/facebookresearch/faiss) for advanced memory search
- (Optional) Firebase or GitHub accounts for integrations

### Installation
1. **Clone the repository:**
   ```sh
   git clone https://github.com/yourusername/ghost-widget.git
   cd ghost-widget
   ```
2. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
3. **Configure Environment:**
   Copy the example environment file and fill in your details:
   ```sh
   cp .env.example .env
   # Edit .env with your favorite text editor
   ```
   At minimum, you need to set your `GOOGLE_API_KEY` or `GEMINI_API_KEY` for the AI features to work.
   
4. **Run the application:**
   ```sh
   python main.py
   ```

### Optional: Enable Integrations
- **Firebase:** See `docs/FIREBASE_SETUP.md` for setup instructions.
- **GitHub:** See `docs/GITHUB_SETUP.md` for connecting your GitHub account.

## Usage
- **Notes & Tasks:** Use the main interface to add, tag, and search notes or tasks.
- **Recordings:** Start a recording session to capture audio and transcribe it for later review.
- **Memory Search:** Use the search bar to find information by keyword, tag, or context.
- **Onboarding:** The onboarding flow will guide you through initial setup and privacy options.

## Privacy & Security
- **Local Storage:** By default, all data is stored on your device in secure, accessible formats.
- **No Analytics:** Ghost Widget does not collect or transmit usage data.
- **Open Source:** Review the code to verify privacy claims.
- **Data Portability:** Export your data at any time.

## Project Structure
- `main.py` — Application entry point
- `faiss_memory.py` — Local memory search engine
- `local_memory.py` — Local storage management
- `firebase_auth.py`, `firestore_chat.py` — Optional Firebase integration
- `github_auth.py` — Optional GitHub integration
- `recordings/` — Stores audio recordings
- `docs/` — Documentation and setup guides
- `tests/` — Automated tests

## Contributing
We welcome contributions! Please see `docs/README_BUILD.md` for build instructions and `CONTRIBUTING.md` (to be created) for guidelines.

## License
This project is licensed under the MIT License.

## Support & Contact
For questions, suggestions, or support, please open an issue on GitHub or contact the maintainer at [your.email@example.com].

---
Ghost Widget: Helping you remember, your way — with privacy and control.