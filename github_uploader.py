import re
import uuid
from github import Github, GithubException
from config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, GITHUB_PATH, USE_CDN

_gh = Github(GITHUB_TOKEN)
_repo = _gh.get_repo(GITHUB_REPO)

# Транслитерация кириллицы (чтобы ссылки были "читаемыми" и безопасными)
_CYRILLIC = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def _translit(text: str) -> str:
    result = []
    for ch in text:
        low = ch.lower()
        if low in _CYRILLIC:
            tr = _CYRILLIC[low]
            result.append(tr.upper() if ch.isupper() and tr else tr)
        else:
            result.append(ch)
    return "".join(result)


def _safe_filename(filename: str) -> str:
    """Чистит имя: транслит, убирает запрещённые символы, оставляет расширение."""
    filename = _translit(filename)
    # оставляем буквы/цифры/точку/дефис/подчёркивание, остальное — в _
    filename = re.sub(r"[^\w.\-]+", "_", filename)
    # убираем ведущие/замыкающие точки и подчёркивания
    filename = filename.strip("._")
    if not filename:
        filename = uuid.uuid4().hex[:12] + ".jpg"
    return filename


def upload_image(content: bytes, filename: str) -> dict:
    """
    Загружает файл в GITHUB_PATH/<filename>.
    Если файл с таким именем уже есть — обновляет его.
    """
    safe = _safe_filename(filename)
    full_path = f"{GITHUB_PATH}/{safe}" if GITHUB_PATH else safe

    try:
        # Пробуем получить существующий файл
        existing = _repo.get_contents(full_path, ref=GITHUB_BRANCH)
        # Файл есть — обновляем
        _repo.update_file(
            path=full_path,
            message=f"Update via bot: {full_path}",
            content=content,
            sha=existing.sha,
            branch=GITHUB_BRANCH,
        )
    except GithubException as e:
        if e.status == 404:
            # Файла нет — создаём
            try:
                _repo.create_file(
                    path=full_path,
                    message=f"Upload via bot: {full_path}",
                    content=content,
                    branch=GITHUB_BRANCH,
                )
            except GithubException as e2:
                raise RuntimeError(f"GitHub API error: {e2.data.get('message', e2)}") from e2
        else:
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
