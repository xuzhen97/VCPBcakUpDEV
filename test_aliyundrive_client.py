import importlib.util
import os
import string
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    "aliyundrive_client.py",
)


def load_module():
    spec = importlib.util.spec_from_file_location("aliyundrive_client", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", reason="OK"):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.reason = reason

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


class AliyunDriveClientTests(unittest.TestCase):
    def test_build_code_verifier_uses_alphanumeric_ascii(self):
        module = load_module()

        verifier = module.build_code_verifier()

        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)
        self.assertTrue(all(ch in string.ascii_letters + string.digits for ch in verifier))

    def test_build_code_challenge_matches_rfc_example(self):
        module = load_module()

        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        result = module.build_code_challenge(verifier)

        self.assertEqual(result, "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_extract_authorization_code_supports_redirect_url(self):
        module = load_module()

        result = module.extract_authorization_code(
            "http://localhost/callback?code=test-code-123&state=abc"
        )

        self.assertEqual(result, "test-code-123")

    def test_load_cached_token_rejects_expired_token(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = os.path.join(temp_dir, "token.json")
            with open(token_path, "w", encoding="utf-8") as f:
                f.write('{"access_token": "abc", "expires_at": "2000-01-01T00:00:00"}')

            result = module.load_cached_token(token_path)

        self.assertIsNone(result)

    def test_split_folder_path_ignores_blank_segments(self):
        module = load_module()

        result = module.split_folder_path("/foo//bar/baz/")

        self.assertEqual(result, ["foo", "bar", "baz"])

    def test_build_authorization_url_defaults_to_plain_pkce(self):
        module = load_module()

        url = module.build_authorization_url(
            {
                "AliyunDriveClientId": "app-id",
                "AliyunDriveOpenApiBase": "https://openapi.alipan.com",
            },
            "verifier123",
        )

        self.assertIn("code_challenge=verifier123", url)
        self.assertIn("code_challenge_method=plain", url)

    def test_build_authorization_url_supports_s256_pkce(self):
        module = load_module()

        url = module.build_authorization_url(
            {
                "AliyunDriveClientId": "app-id",
                "AliyunDriveOpenApiBase": "https://openapi.alipan.com",
                "AliyunDrivePkceMethod": "S256",
            },
            "verifier123",
        )

        self.assertIn("code_challenge_method=S256", url)
        self.assertNotIn("code_challenge=verifier123", url)

    def test_get_access_token_reuses_valid_cache(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = os.path.join(temp_dir, "token.json")
            module.save_cached_token(
                token_path,
                {
                    "access_token": "cached-token",
                    "expires_at": "2999-01-01T00:00:00+00:00",
                },
            )

            token, returned_path, cached = module.get_access_token(
                {"AliyunDriveTokenFile": token_path},
                current_dir=temp_dir,
            )

        self.assertEqual(token, "cached-token")
        self.assertEqual(returned_path, token_path)
        self.assertEqual(cached["access_token"], "cached-token")

    def test_run_with_access_token_reauths_once_on_auth_error(self):
        module = load_module()
        calls = []

        def fake_get_access_token(config, current_dir=None, force_reauth=False):
            calls.append(force_reauth)
            token = "new-token" if force_reauth else "old-token"
            return token, "token.json", {"access_token": token}

        def operation(token):
            if token == "old-token":
                raise module.AliyunAuthError("expired")
            return token

        with patch.object(module, "get_access_token", side_effect=fake_get_access_token):
            result = module.run_with_access_token({}, ".", operation)

        self.assertEqual(result, "new-token")
        self.assertEqual(calls, [False, True])

    def test_list_files_reads_all_pages(self):
        module = load_module()
        responses = [
            {"items": [{"name": "one.zip"}], "next_marker": "next-page"},
            {"items": [{"name": "two.zip"}], "next_marker": ""},
        ]

        def fake_api_post(config, access_token, path, payload):
            self.assertEqual(path, "/adrive/v1.0/openFile/list")
            if len(responses) == 1:
                self.assertEqual(payload["marker"], "next-page")
            return responses.pop(0)

        with patch.object(module, "api_post", side_effect=fake_api_post):
            result = module.list_files({}, "token", "drive", "parent")

        self.assertEqual([item["name"] for item in result], ["one.zip", "two.zip"])

    def test_list_backup_files_filters_and_sorts_zip_backups(self):
        module = load_module()
        items = [
            {"name": "notes.txt", "file_id": "1"},
            {"name": "VCPToolBox_Backup_20240101_010101.zip", "file_id": "2"},
            {"name": "VCPToolBox_Backup_20240102_010101.zip", "file_id": "3"},
        ]

        with patch.object(module, "run_with_access_token") as mocked_run:
            def invoke_operation(config, current_dir, operation):
                return operation("token")

            mocked_run.side_effect = invoke_operation
            with patch.object(module, "resolve_drive_id", return_value="drive"):
                with patch.object(module, "ensure_folder_path", return_value="parent"):
                    with patch.object(module, "list_files", return_value=items):
                        result = module.list_backup_files({}, current_dir=".")

        self.assertEqual(
            [item["name"] for item in result],
            [
                "VCPToolBox_Backup_20240102_010101.zip",
                "VCPToolBox_Backup_20240101_010101.zip",
            ],
        )

    def test_exchange_code_for_token_uses_pkce_payload_without_redirect_uri(self):
        module = load_module()
        captured = {}

        class FakeRequests:
            @staticmethod
            def post(url, json, timeout):
                captured["url"] = url
                captured["json"] = json
                captured["timeout"] = timeout
                return FakeResponse(
                    json_data={
                        "access_token": "token-123",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    }
                )

        with patch.object(module, "import_requests", return_value=FakeRequests):
            result = module.exchange_code_for_token(
                {"AliyunDriveClientId": "app-id", "AliyunDriveOpenApiBase": "https://openapi.alipan.com"},
                "auth-code",
                "verifier-123",
            )

        self.assertEqual(captured["url"], "https://openapi.alipan.com/oauth/access_token")
        self.assertEqual(
            captured["json"],
            {
                "client_id": "app-id",
                "grant_type": "authorization_code",
                "code": "auth-code",
                "code_verifier": "verifier-123",
            },
        )
        self.assertNotIn("redirect_uri", captured["json"])
        self.assertEqual(result["access_token"], "token-123")

    def test_exchange_code_for_token_includes_optional_client_secret(self):
        module = load_module()
        captured = {}

        class FakeRequests:
            @staticmethod
            def post(url, json, timeout):
                captured["json"] = json
                return FakeResponse(
                    json_data={
                        "access_token": "token-123",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    }
                )

        with patch.object(module, "import_requests", return_value=FakeRequests):
            module.exchange_code_for_token(
                {
                    "AliyunDriveClientId": "app-id",
                    "AliyunDriveClientSecret": "secret-123",
                    "AliyunDriveOpenApiBase": "https://openapi.alipan.com",
                },
                "auth-code",
                "verifier-123",
            )

        self.assertEqual(captured["json"]["client_secret"], "secret-123")


if __name__ == "__main__":
    unittest.main()
