import uuid
from datetime import datetime
from github import Github, GithubException
from config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, GITHUB_PATH, USE_CDN

_gh = Github(GITHUB_TOKEN)
_repo = _gh.get_repo(GITHUB_REPO)


def _build_filename(ext: str) -> str:
    today = datetime.utcnow().strftime("%Y/%m/%d")
    return f"{today}/{uuid.uuid4().hex[:12]}.{ext}"


def upload_image(content: bytes, ext: str = "jpg") -> dict:
    rel_path = _build_filename(ext)
    full_path = f"{GITHUB_PATH}/{rel_path}" if GITHUB_PATH else rel_path

    try:
        _repo.create_file(
            path=full_path,
            message=f"Upload image via bot: {full_path}",
            content=content,
            branch=GITHUB_BRANCH,
        )
    except GithubException as e:
        raise RuntimeError(f"GitHub API error: {e.data.get('message', e)}") from e

    raw_url = (
        f"https://raw.githubusercontent.com/{GITHUB_REPO}/"
        f"{GITHUB_BRANCH}/{full_path}"
    )
    cdn_url = (
        f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GITHUB_BRANCH}/{full_path}"
        if USE_CDN else None
    )

    return {"path": full_path, "raw_url": raw_url, "cdn_url": cdn_url}
