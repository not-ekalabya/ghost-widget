"""
Test script to verify GitHub repository and releases are accessible
"""
import requests


GITHUB_REPO = "not-ekalabya/ghost-widget"
import os
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("[WARNING] GITHUB_TOKEN not set in environment. GitHub API tests may fail.")

def test_repo():
    """Test if repository exists"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    print(f"Testing repository access...")
    print(f"URL: {url}\n")

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        print("✅ Repository EXISTS!")
        print(f"   Name: {data['full_name']}")
        print(f"   Private: {data['private']}")
        print(f"   Default branch: {data['default_branch']}")
        return True
    else:
        print(f"❌ Repository NOT FOUND (HTTP {response.status_code})")
        print(f"   Message: {response.json().get('message', 'Unknown error')}")
        print(f"\n📝 Create it at: https://github.com/new")
        return False

def test_releases():
    """Test if releases exist"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    print(f"\nTesting releases access...")
    print(f"URL: {url}\n")

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        print("✅ Latest release FOUND!")
        print(f"   Version: {data['tag_name']}")
        print(f"   Published: {data['published_at']}")
        print(f"   Assets: {len(data.get('assets', []))}")

        for asset in data.get('assets', []):
            print(f"      - {asset['name']} ({asset['size'] / 1024 / 1024:.2f} MB)")

        return True
    else:
        print(f"❌ No releases found (HTTP {response.status_code})")
        print(f"   Message: {response.json().get('message', 'Unknown error')}")
        print(f"\n📝 Create one at: https://github.com/{GITHUB_REPO}/releases/new")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("GitHub Auto-Update Connection Test")
    print("=" * 60)

    repo_ok = test_repo()

    if repo_ok:
        releases_ok = test_releases()

        if releases_ok:
            print("\n" + "=" * 60)
            print("🎉 AUTO-UPDATES READY!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("⚠️  Repository exists but no releases yet")
            print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ Repository doesn't exist - create it first")
        print("=" * 60)
