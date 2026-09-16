import re
import io
import base64
import uuid
import zipfile
from github import Github, GithubException, InputGitTreeElement
from config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, GITHUB_PATH, USE_CDN

_gh = Github(GITHUB_TOKEN)
_repo = _gh.get_repo(GITHUB_REPO)

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
    ".tiff", ".tif", ".svg", ".heic", ".avif",
}
MAX_FILES = 100
MAX_TOTAL_SIZE = 300 * 1024 * 1024
FOLDER_FILE_LIMIT = 500

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
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
    filename = _translit(filename)
    filename = re.sub(r"[^\w.\-]+", "_", filename)
    filename = filename.strip("._")
    if not filename:
        filename = uuid.uuid4().hex[:12] + ".jpg"
    return filename


def _unique_name(name: str, used: set) -> str:
    if name not in used:
        used.add(name)
        return name
    base, dot, ext = name.rpartition(".")
    if not dot:
        base, ext = name, ""
    counter = 1
    while True:
        candidate = f"{base}_{counter}.{ext}" if ext else f"{base}_{counter}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def _build_urls(full_path: str) -> dict:
    raw_url = (
        f"https://raw.githubusercontent.com/{GITHUB_REPO}/"
        f"{GITHUB_BRANCH}/{full_path}"
    )
    cdn_url = (
        f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GITHUB_BRANCH}/{full_path}"
        if USE_CDN else None
    )
    return {"path": full_path, "raw_url": raw_url, "cdn_url": cdn_url}


def _upload_single(content: bytes, full_path: str) -> dict:
    try:
        existing = _repo.get_contents(full_path, ref=GITHUB_BRANCH)
        _repo.update_file(
            path=full_path,
            message=f"Update via bot: {full_path}",
            content=content,
            sha=existing.sha,
            branch=GITHUB_BRANCH,
        )
    except GithubException as e:
        if e.status == 404:
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
    return _build_urls(full_path)


def _commit_many(files: dict, message: str) -> None:
    ref = _repo.get_git_ref(f"heads/{GITHUB_BRANCH}")
    base_commit = _repo.get_git_commit(ref.object.sha)

    elements = []
    for path, content in files.items():
        b64 = base64.b64encode(content).decode("ascii")
        blob = _repo.create_git_blob(b64, "base64")
        elements.append(
            InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha)
        )

    new_tree = _repo.create_git_tree(elements, base_commit.tree)
    new_commit = _repo.create_git_commit(message, new_tree, [base_commit])
    ref.edit(new_commit.sha)


def _first_letter_key(source: str) -> str:
    """Берёт первую букву из строки (транслит, lower). Если не буква — 'x'."""
    s = (source or "").strip()
    if not s:
        return "x"
    first = _translit(s[0]).lower()
    if not first.isalpha():
        return "x"
    return first


def _folder_for_game(game_name: str) -> str:
    """Возвращает имя подпапки: 'a1', 'a2', ... по первой букве."""
    first = _first_letter_key(game_name)
    base = GITHUB_PATH.strip("/")
    base_for_api = base if base else "."

    try:
        items = _repo.get_contents(base_for_api, ref=GITHUB_BRANCH)
    except GithubException as e:
        if e.status == 404:
            items = []
        else:
            raise

    if not isinstance(items, list):
        items = [items]

    pattern = re.compile(rf"^{re.escape(first)}(\d+)$")
    max_n = 0
    for it in items:
        if it.type == "dir":
            m = pattern.match(it.name)
            if m:
                max_n = max(max_n, int(m.group(1)))

    if max_n == 0:
        return f"{first}1"

    candidate_path = f"{base}/{first}{max_n}" if base else f"{first}{max_n}"
    try:
        contents = _repo.get_contents(candidate_path, ref=GITHUB_BRANCH)
        if not isinstance(contents, list):
            contents = [contents]
    except GithubException:
        contents = []

    if len(contents) < FOLDER_FILE_LIMIT:
        return f"{first}{max_n}"
    return f"{first}{max_n + 1}"


def _pick_subfolder(game_name: str, filename: str) -> str:
    """
    Определяет подпапку (a1/a2/...).
    Если подпись (game_name) есть — по ней.
    Иначе — по имени файла, но не для технических имён (photo_, file_, uuid).
    """
    name = (game_name or "").strip()
    if name:
        return _folder_for_game(name)

    base = (filename or "").rsplit("/", 1)[-1]
    low = base.lower()
    if low.startswith("photo_") or low.startswith("file_"):
        return ""
    if re.fullmatch(r"[0-9a-f]{8,}\.[a-z0-9]+", low):
        return ""
    if not base:
        return ""
    return _folder_for_game(base)


def upload_image(content: bytes, filename: str, game_name: str = "") -> dict:
    safe = _safe_filename(filename)
    sub = _pick_subfolder(game_name, filename)

    if sub:
        full_path = f"{GITHUB_PATH.strip('/')}/{sub}/{safe}" if GITHUB_PATH else f"{sub}/{safe}"
    else:
        full_path = f"{GITHUB_PATH.strip('/')}/{safe}" if GITHUB_PATH else safe

    return _upload_single(content, full_path)


def _is_skippable(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    if base.startswith(".") or base.startswith("__"):
        return True
    if "__MACOSX" in name:
        return True
    return False


def upload_zip(content: bytes, archive_name: str = "archive.zip", game_name: str = "") -> dict:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise RuntimeError("Файл не является корректным ZIP-архивом")

    files = {}
    used_names = set()
    uploaded_paths = []
    skipped = []
    total_size = 0
    base = GITHUB_PATH.strip("/")

    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if _is_skippable(name):
                skipped.append(name)
                continue
            ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
            if ext not in IMAGE_EXTENSIONS:
                skipped.append(name)
                continue
            if len(files) >= MAX_FILES:
                skipped.append(name)
                continue
            total_size += info.file_size
            if total_size > MAX_TOTAL_SIZE:
                raise RuntimeError(
                    f"Распакованный размер превышает {MAX_TOTAL_SIZE // 1024 // 1024} МБ"
                )

            base_name = name.rsplit("/", 1)[-1]
            safe = _safe_filename(base_name)
            sub = _pick_subfolder(game_name, safe)

            if sub:
                full_path = f"{base}/{sub}/{safe}" if base else f"{sub}/{safe}"
            else:
                full_path = f"{base}/{safe}" if base else safe

            full_path = _unique_path(full_path, used_names)
            files[full_path] = zf.read(info)
            uploaded_paths.append(full_path)

    if not files:
        return {"uploaded": [], "skipped": skipped, "failed": [],
                "note": "В архиве нет поддерживаемых изображений"}

    try:
        _commit_many(files, message=f"Upload {len(files)} files via bot ({archive_name})")
    except Exception as e:
        return {
            "uploaded": [],
            "skipped": skipped,
            "failed": [{"name": p, "error": str(e)} for p in files.keys()],
        }

    return {"uploaded": uploaded_paths, "skipped": skipped, "failed": []}


def _unique_path(full_path: str, used: set) -> str:
    if full_path not in used:
        used.add(full_path)
        return full_path
    folder, _, filename = full_path.rpartition("/")
    base, dot, ext = filename.rpartition(".")
    if not dot:
        base, ext = filename, ""
    counter = 1
    while True:
        candidate_name = f"{base}_{counter}.{ext}" if ext else f"{base}_{counter}"
        candidate = f"{folder}/{candidate_name}" if folder else candidate_name
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1
