from app.auth.schemas import LoginRequest
from app.core.config import Settings
from app.main import create_app


def test_admin_user_status_filter_uses_public_status_parameter() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    operation = schema["paths"]["/api/v1/admin/users"]["get"]
    parameter_names = {
        parameter["name"] for parameter in operation["parameters"] if parameter["in"] == "query"
    }

    assert "status" in parameter_names
    assert "account_status" not in parameter_names


def test_login_request_accepts_identifier_and_legacy_email_alias() -> None:
    primary = LoginRequest.model_validate({"identifier": "student", "password": "test-password"})
    legacy = LoginRequest.model_validate(
        {"email": "student@connect.hkust-gz.edu.cn", "password": "test-password"}
    )

    assert primary.identifier == "student"
    assert legacy.identifier == "student@connect.hkust-gz.edu.cn"


def test_login_openapi_exposes_identifier_instead_of_legacy_email() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    login_request = schema["components"]["schemas"]["LoginRequest"]

    assert set(login_request["required"]) == {"identifier", "password"}
    assert "identifier" in login_request["properties"]
    assert "email" not in login_request["properties"]


def test_stage_three_openapi_contains_dashboard_announcements_notifications_and_uploads() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]

    expected_paths = {
        "/api/v1/dashboard",
        "/api/v1/notifications",
        "/api/v1/notifications/{notification_id}/read",
        "/api/v1/notifications/read-all",
        "/api/v1/announcements",
        "/api/v1/announcements/{announcement_id}",
        "/api/v1/admin/announcements",
        "/api/v1/admin/announcements/{announcement_id}",
        "/api/v1/admin/announcements/{announcement_id}/publish",
        "/api/v1/admin/announcements/{announcement_id}/archive",
        "/api/v1/admin/announcements/{announcement_id}/send-update",
        "/api/v1/uploads/init",
        "/api/v1/uploads/{upload_id}",
        "/api/v1/uploads/{upload_id}/parts/presign",
        "/api/v1/uploads/{upload_id}/complete",
        "/api/v1/files/{file_id}/download-url",
        "/api/v1/knowledge",
        "/api/v1/knowledge/documents/{document_id}",
        "/api/v1/knowledge/assets/{asset_id}/content",
        "/api/v1/admin/knowledge",
        "/api/v1/admin/knowledge/sync",
    }

    assert expected_paths <= set(paths)
    publish_parameters = paths["/api/v1/admin/announcements/{announcement_id}/publish"]["post"][
        "parameters"
    ]
    idempotency_parameter = next(
        parameter for parameter in publish_parameters if parameter["name"] == "Idempotency-Key"
    )
    assert idempotency_parameter["in"] == "header"
    assert idempotency_parameter["required"] is True
