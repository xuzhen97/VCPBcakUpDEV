import base64
import datetime
import hashlib
import json
import os
import secrets
import webbrowser
from urllib.parse import parse_qs, quote, urlparse


DEFAULT_OPENAPI_BASE = "https://openapi.alipan.com"
DEFAULT_SCOPE = "user:base,file:all:read,file:all:write"
DEFAULT_REDIRECT_URI = "oob"
TOKEN_EXPIRY_SAFETY_SECONDS = 300
SINGLE_PART_LIMIT = 5 * 1024 * 1024 * 1024


class AliyunAuthError(RuntimeError):
    pass


def import_requests():
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("缺少 requests 依赖，请先执行: pip install requests") from exc
    return requests


def build_code_verifier(length=64):
    # PKCE verifier must be 43-128 chars.
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    target_length = min(128, max(43, length))
    return "".join(secrets.choice(alphabet) for _ in range(target_length))


def build_code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def extract_authorization_code(text):
    value = text.strip()
    if not value:
        raise ValueError("授权结果不能为空")

    if "code=" in value:
        parsed = urlparse(value)
        code = parse_qs(parsed.query).get("code", [""])[0]
        if code:
            return code

    return value


def load_cached_token(token_path):
    if not os.path.exists(token_path):
        return None

    try:
        with open(token_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    access_token = data.get("access_token")
    expires_at = data.get("expires_at")
    if not access_token or not expires_at:
        return None

    try:
        expires_time = datetime.datetime.fromisoformat(expires_at)
    except ValueError:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_time.tzinfo is None:
        expires_time = expires_time.replace(tzinfo=datetime.timezone.utc)

    if expires_time <= now + datetime.timedelta(seconds=TOKEN_EXPIRY_SAFETY_SECONDS):
        return None

    return data


def save_cached_token(token_path, token_data):
    os.makedirs(os.path.dirname(os.path.abspath(token_path)), exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)


def clear_cached_token(token_path):
    try:
        if os.path.exists(token_path):
            os.remove(token_path)
    except OSError:
        pass


def split_folder_path(folder_path):
    return [segment for segment in folder_path.replace("\\", "/").split("/") if segment]


def get_openapi_base(config):
    return config.get("AliyunDriveOpenApiBase", DEFAULT_OPENAPI_BASE).rstrip("/")


def get_token_file(config, current_dir=None):
    token_file = config.get("AliyunDriveTokenFile", "./aliyundrive_token.json")
    if os.path.isabs(token_file):
        return token_file
    base_dir = current_dir or os.getcwd()
    return os.path.abspath(os.path.join(base_dir, token_file))


def build_authorization_url(config, verifier, state=None):
    client_id = config.get("AliyunDriveClientId")
    if not client_id:
        raise ValueError("未配置 AliyunDriveClientId")

    redirect_uri = config.get("AliyunDriveRedirectUri", DEFAULT_REDIRECT_URI)
    scope = config.get("AliyunDriveScope", DEFAULT_SCOPE)
    pkce_method = config.get("AliyunDrivePkceMethod", "plain").strip() or "plain"
    openapi_base = get_openapi_base(config)

    if pkce_method == "S256":
        code_challenge = build_code_challenge(verifier)
    else:
        code_challenge = verifier
        pkce_method = "plain"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": pkce_method,
    }
    if state:
        params["state"] = state

    query = "&".join(f"{key}={quote(str(value), safe='')}" for key, value in params.items())
    return f"{openapi_base}/oauth/authorize?{query}"


def exchange_code_for_token(config, code, verifier):
    requests = import_requests()
    openapi_base = get_openapi_base(config)
    client_id = config.get("AliyunDriveClientId")
    client_secret = config.get("AliyunDriveClientSecret", "").strip()

    payload = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    response = requests.post(
        f"{openapi_base}/oauth/access_token",
        json=payload,
        timeout=30,
    )
    if not response.ok:
        message = response.text.strip()
        raise RuntimeError(
            f"换取 access_token 失败: HTTP {response.status_code} {message or response.reason}"
        )
    data = response.json()

    expires_in = int(data.get("expires_in", 0))
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)

    return {
        "access_token": data["access_token"],
        "token_type": data.get("token_type", "Bearer"),
        "expires_at": expires_at.isoformat(),
        "scope": config.get("AliyunDriveScope", DEFAULT_SCOPE),
    }


def authorize_interactively(config, token_path):
    verifier = build_code_verifier()
    authorization_url = build_authorization_url(config, verifier)

    print("\n首次使用阿里云盘上传，需要先完成一次 OAuth 授权。")
    print("请在浏览器完成授权，然后把回调地址中的 code，或直接把 code 粘贴回来。")
    print(f"授权地址:\n{authorization_url}\n")

    try:
        webbrowser.open(authorization_url)
    except Exception:
        pass

    user_input = input("请输入授权完成后的回调地址或 code: ").strip()
    code = extract_authorization_code(user_input)
    token_data = exchange_code_for_token(config, code, verifier)
    save_cached_token(token_path, token_data)
    return token_data


def auth_headers(access_token):
    return {"Authorization": f"Bearer {access_token}"}


def api_post(config, access_token, path, payload):
    requests = import_requests()
    openapi_base = get_openapi_base(config)
    response = requests.post(
        f"{openapi_base}{path}",
        headers=auth_headers(access_token),
        json=payload,
        timeout=60,
    )
    if response.status_code in (401, 403):
        message = response.text.strip()
        raise AliyunAuthError(message or response.reason)
    response.raise_for_status()
    return response.json()


def get_access_token(config, current_dir=None, force_reauth=False):
    token_path = get_token_file(config, current_dir)
    if not force_reauth:
        cached = load_cached_token(token_path)
        if cached:
            return cached["access_token"], token_path, cached

    if force_reauth:
        clear_cached_token(token_path)

    token_data = authorize_interactively(config, token_path)
    return token_data["access_token"], token_path, token_data


def run_with_access_token(config, current_dir, operation):
    access_token, _, _ = get_access_token(config, current_dir=current_dir)
    try:
        return operation(access_token)
    except AliyunAuthError:
        access_token, _, _ = get_access_token(config, current_dir=current_dir, force_reauth=True)
        return operation(access_token)


def get_drive_info(config, access_token):
    data = api_post(config, access_token, "/adrive/v1.0/user/getDriveInfo", {})
    drive_id = (
        data.get("default_drive_id")
        or data.get("defaultDriveId")
        or data.get("resource_drive_id")
        or data.get("resourceDriveId")
        or data.get("backup_drive_id")
        or data.get("backupDriveId")
    )
    if not drive_id:
        raise RuntimeError("无法从 getDriveInfo 返回中获取 drive_id")
    return drive_id, data


def list_child_folders(config, access_token, drive_id, parent_file_id):
    items = []
    marker = ""

    while True:
        payload = {
            "drive_id": drive_id,
            "parent_file_id": parent_file_id,
            "type": "folder",
            "limit": 100,
            "order_by": "name",
            "order_direction": "ASC",
        }
        if marker:
            payload["marker"] = marker

        data = api_post(config, access_token, "/adrive/v1.0/openFile/list", payload)
        items.extend(data.get("items", []))
        marker = data.get("next_marker") or ""
        if not marker:
            break

    return items


def create_folder(config, access_token, drive_id, parent_file_id, name):
    payload = {
        "drive_id": drive_id,
        "parent_file_id": parent_file_id,
        "name": name,
        "type": "folder",
        "check_name_mode": "refuse",
    }
    return api_post(config, access_token, "/adrive/v1.0/openFile/create", payload)


def ensure_folder_path(config, access_token, drive_id, folder_path):
    parent_file_id = "root"
    for segment in split_folder_path(folder_path):
        children = list_child_folders(config, access_token, drive_id, parent_file_id)
        matched = next((item for item in children if item.get("name") == segment), None)
        if matched:
            parent_file_id = matched["file_id"]
            continue

        created = create_folder(config, access_token, drive_id, parent_file_id, segment)
        parent_file_id = created["file_id"]

    return parent_file_id


def build_part_info_list(file_size):
    if file_size > SINGLE_PART_LIMIT:
        raise RuntimeError("当前脚本暂不支持大于 5GB 的单文件上传，请先缩小备份包或扩展分片上传逻辑")
    return [{"part_number": 1}]


def resolve_drive_id(config, access_token):
    drive_id = config.get("AliyunDriveId")
    if drive_id:
        return drive_id
    drive_id, _ = get_drive_info(config, access_token)
    return drive_id


def list_files(config, access_token, drive_id, parent_file_id, file_type="all", order_by="updated_at", order_direction="DESC"):
    items = []
    marker = ""

    while True:
        payload = {
            "drive_id": drive_id,
            "parent_file_id": parent_file_id,
            "type": file_type,
            "limit": 100,
            "order_by": order_by,
            "order_direction": order_direction,
        }
        if marker:
            payload["marker"] = marker

        data = api_post(config, access_token, "/adrive/v1.0/openFile/list", payload)
        items.extend(data.get("items", []))
        marker = data.get("next_marker") or ""
        if not marker:
            break

    return items


def get_aliyundrive_context(config, current_dir=None):
    def operation(access_token):
        drive_id = resolve_drive_id(config, access_token)
        folder_path = config.get("AliyunDriveFolder", "VCPToolBox备份")
        parent_file_id = ensure_folder_path(config, access_token, drive_id, folder_path)
        return access_token, drive_id, parent_file_id

    access_token, drive_id, parent_file_id = run_with_access_token(config, current_dir, operation)
    token_path = get_token_file(config, current_dir)
    cached = load_cached_token(token_path)
    return access_token, token_path, cached, drive_id, parent_file_id


def list_backup_files(config, current_dir=None, prefix="VCPToolBox_Backup_", suffix=".zip"):
    def operation(access_token):
        drive_id = resolve_drive_id(config, access_token)
        folder_path = config.get("AliyunDriveFolder", "VCPToolBox备份")
        parent_file_id = ensure_folder_path(config, access_token, drive_id, folder_path)
        files = []
        for item in list_files(config, access_token, drive_id, parent_file_id, file_type="file"):
            name = item.get("name", "")
            if name.startswith(prefix) and name.endswith(suffix):
                files.append(item)
        return sorted(files, key=lambda item: item.get("name", ""), reverse=True)

    return run_with_access_token(config, current_dir, operation)


def get_download_url(config, access_token, drive_id, file_id):
    data = api_post(
        config,
        access_token,
        "/adrive/v1.0/openFile/getDownloadUrl",
        {
            "drive_id": drive_id,
            "file_id": file_id,
        },
    )
    download_url = data.get("download_url") or data.get("url")
    if not download_url:
        raise RuntimeError("获取阿里云盘下载地址失败，接口未返回 download_url")
    return download_url, data


def download_file_from_aliyundrive(file_item, local_path, config, current_dir=None):
    requests = import_requests()
    file_id = file_item.get("file_id")
    if not file_id:
        raise RuntimeError("阿里云盘文件信息缺少 file_id")

    def operation(access_token):
        drive_id = resolve_drive_id(config, access_token)
        download_url, _ = get_download_url(config, access_token, drive_id, file_id)
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)

        with requests.get(download_url, stream=True, timeout=600) as response:
            response.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        return local_path

    return run_with_access_token(config, current_dir, operation)


def create_file_upload(config, access_token, drive_id, parent_file_id, file_name, file_size):
    payload = {
        "drive_id": drive_id,
        "parent_file_id": parent_file_id,
        "name": file_name,
        "type": "file",
        "check_name_mode": config.get("AliyunDriveCheckNameMode", "auto_rename"),
        "size": file_size,
        "part_info_list": build_part_info_list(file_size),
    }
    return api_post(config, access_token, "/adrive/v1.0/openFile/create", payload)


def upload_single_part(upload_url, file_path):
    requests = import_requests()
    with open(file_path, "rb") as f:
        response = requests.put(
            upload_url,
            data=f,
            headers={"Content-Type": ""},
            timeout=600,
        )
    response.raise_for_status()
    return response.headers.get("ETag") or response.headers.get("Etag")


def complete_upload(config, access_token, drive_id, file_id, upload_id):
    payload = {
        "drive_id": drive_id,
        "file_id": file_id,
        "upload_id": upload_id,
    }
    return api_post(config, access_token, "/adrive/v1.0/openFile/complete", payload)


def upload_file_to_aliyundrive(file_path, config, current_dir=None):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"本地文件不存在: {file_path}")

    def operation(access_token):
        drive_id = resolve_drive_id(config, access_token)
        folder_path = config.get("AliyunDriveFolder", "VCPToolBox备份")
        parent_file_id = ensure_folder_path(config, access_token, drive_id, folder_path)

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        create_result = create_file_upload(config, access_token, drive_id, parent_file_id, file_name, file_size)

        if create_result.get("rapid_upload"):
            return create_result

        part_info_list = create_result.get("part_info_list", [])
        if not part_info_list:
            raise RuntimeError("创建上传任务成功，但未返回 upload_url")

        upload_url = part_info_list[0].get("upload_url")
        if not upload_url:
            raise RuntimeError("上传地址为空")

        upload_single_part(upload_url, file_path)
        return complete_upload(
            config,
            access_token,
            drive_id,
            create_result["file_id"],
            create_result["upload_id"],
        )

    return run_with_access_token(config, current_dir, operation)
