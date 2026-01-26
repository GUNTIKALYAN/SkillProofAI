import os
import requests
from datetime import datetime, timezone
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()

GITHUB_API_BASE = "https://api.github.com"


def fetch_github_evidence(username: str) -> Dict[str, dict]:
    """
    Fetches GitHub repositories and raw evidence per skill.
    Output contract (LOCKED):

    {
      "python": {
        "repos": [],
        "languages": [],
        "recent_activity": bool,
        "last_commit_days": int | None
      },
      ...
    }
    """

    if not username or not username.strip():
        raise ValueError("GitHub username is required")

    token = os.getenv("GITHUB_TOKEN")

    headers = {
        "Accept": "application/vnd.github+json"
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos = _fetch_repositories(username, headers)

    # Import vocabulary here to avoid circular imports
    from app.utils.constants import SKILL_VOCABULARY

    evidence = {}

    for skill in SKILL_VOCABULARY:
        evidence[skill] = {
            "repos": [],
            "languages": [],
            "recent_activity": False,
            "last_commit_days": None
        }

    for repo in repos:
        repo_name = repo["name"]
        updated_at = repo["updated_at"]

        last_commit_days = _days_since(updated_at)

        languages = _fetch_repo_languages(username, repo_name, headers)

        readme_text = _fetch_readme_text(username, repo_name, headers)

        combined_text = (
            repo_name.lower() + " " +
            " ".join(languages).lower() + " " +
            readme_text.lower()
        )

        for skill in evidence.keys():
            if skill in combined_text:
                evidence[skill]["repos"].append(repo_name)
                evidence[skill]["languages"].extend(languages)

                if last_commit_days is not None:
                    evidence[skill]["last_commit_days"] = (
                        min(
                            evidence[skill]["last_commit_days"],
                            last_commit_days
                        )
                        if evidence[skill]["last_commit_days"] is not None
                        else last_commit_days
                    )

                    if last_commit_days <= 180:
                        evidence[skill]["recent_activity"] = True

    # Deduplicate language lists
    for skill in evidence:
        evidence[skill]["languages"] = list(
            set(evidence[skill]["languages"])
        )

    return evidence


# Internal Helpers

def _fetch_repositories(username: str, headers: dict) -> List[dict]:
    url = f"{GITHUB_API_BASE}/users/{username}/repos?per_page=100"

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub API error {response.status_code}: {response.text}"
        )

    return response.json()


def _fetch_repo_languages(username: str, repo_name: str, headers: dict) -> List[str]:
    url = f"{GITHUB_API_BASE}/repos/{username}/{repo_name}/languages"

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return []

    return list(response.json().keys())


def _fetch_readme_text(username: str, repo_name: str, headers: dict) -> str:
    url = f"{GITHUB_API_BASE}/repos/{username}/{repo_name}/readme"

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return ""

    data = response.json()
    content = data.get("content")

    if not content:
        return ""

    try:
        import base64
        decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
        return decoded
    except Exception:
        return ""


def _days_since(date_str: str) -> int | None:
    try:
        last_update = datetime.fromisoformat(
            date_str.replace("Z", "+00:00")
        )
        now = datetime.now(timezone.utc)
        return (now - last_update).days
    except Exception:
        return None
