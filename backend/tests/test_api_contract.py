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


def test_admin_user_activity_filter_and_page_response_are_explicit() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    operation = schema["paths"]["/api/v1/admin/users"]["get"]
    parameters = {
        parameter["name"]: parameter
        for parameter in operation["parameters"]
        if parameter["in"] == "query"
    }

    assert {"page", "page_size", "activity"} <= set(parameters)
    assert "inactive" in str(parameters["activity"]["schema"])
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/UserPage"}

    user_page = schema["components"]["schemas"]["UserPage"]
    assert {"items", "page", "page_size", "total"} <= set(user_page["required"])
    admin_user = schema["components"]["schemas"]["AdminUserResponse"]
    assert {"last_active_at", "is_inactive", "inactive_days"} <= set(admin_user["required"])
    assert admin_user["properties"]["inactive_days"]["minimum"] == 0


def test_admin_user_delete_requires_reason_and_returns_empty_204() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    operation = schema["paths"]["/api/v1/admin/users/{user_id}"]["delete"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]

    assert request_schema == {"$ref": "#/components/schemas/UserDeleteRequest"}
    delete_request = schema["components"]["schemas"]["UserDeleteRequest"]
    assert delete_request["required"] == ["reason"]
    assert delete_request["properties"]["reason"]["minLength"] == 3
    assert delete_request["properties"]["reason"]["maxLength"] == 500
    assert set(operation["responses"]) >= {"204", "422"}
    assert "content" not in operation["responses"]["204"]


def test_admin_user_mutations_return_activity_aware_user_schema() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]
    response_ref = {"$ref": "#/components/schemas/AdminUserResponse"}

    operations = [
        paths["/api/v1/admin/users/{user_id}"]["patch"],
        paths["/api/v1/admin/users/{user_id}/disable"]["post"],
        paths["/api/v1/admin/users/{user_id}/restore"]["post"],
        paths["/api/v1/admin/users/{user_id}/role"]["post"],
    ]
    for operation in operations:
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"] == response_ref
        )


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


def test_questionnaire_openapi_exposes_questions_limits_stats_and_admin_roster() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]

    detail_path = paths["/api/v1/admin/intentions/{survey_id}"]
    assert detail_path["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AdminIntentionSurveyDetail"
    }
    assert detail_path["patch"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AdminIntentionSurveyDetail"
    }

    assert "/api/v1/admin/intentions/{survey_id}/responses" in paths
    roster_operation = paths["/api/v1/admin/intentions/{survey_id}/responses"]["get"]
    assert roster_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/IntentionRosterResponse"
    }

    create_request = schema["components"]["schemas"]["IntentionSurveyCreateRequest"]
    assert {"title", "questions"} <= set(create_request["required"])
    assert "max_submissions" in create_request["properties"]
    question = schema["components"]["schemas"]["IntentionQuestionInput"]
    assert {"prompt", "options"} <= set(question["required"])

    response_request = schema["components"]["schemas"]["IntentionResponseRequest"]
    assert "answers" in response_request["required"]
    stats = schema["components"]["schemas"]["IntentionStatsResponse"]
    assert "questions" in stats["required"]


def test_help_request_openapi_exposes_private_public_and_admin_contracts() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]
    expected_paths = {
        "/api/v1/help-requests",
        "/api/v1/help-requests/public",
        "/api/v1/help-requests/public/{request_id}",
        "/api/v1/help-requests/{request_id}",
        "/api/v1/admin/help-requests",
        "/api/v1/admin/help-requests/{request_id}",
        "/api/v1/admin/help-requests/{request_id}/resolution",
    }

    assert expected_paths <= set(paths)
    operation_count = sum(
        method in {"get", "post", "put"}
        for path, operations in paths.items()
        if "help-requests" in path
        for method in operations
    )
    assert operation_count == 8

    assert paths["/api/v1/help-requests"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/HelpRequestDetail"}

    student_parameters = {
        parameter["name"] for parameter in paths["/api/v1/help-requests"]["get"]["parameters"]
    }
    public_parameters = {
        parameter["name"]
        for parameter in paths["/api/v1/help-requests/public"]["get"]["parameters"]
    }
    admin_parameters = {
        parameter["name"] for parameter in paths["/api/v1/admin/help-requests"]["get"]["parameters"]
    }
    assert {"type", "status", "page", "page_size"} <= student_parameters
    assert public_parameters == {"page", "page_size"}
    assert {"type", "status", "query", "page", "page_size"} <= admin_parameters

    assert paths["/api/v1/help-requests/public/{request_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicHelpRequestDetail"}
    public_detail = schema["components"]["schemas"]["PublicHelpRequestDetail"]
    assert {
        "created_by",
        "resolved_by",
        "notification_ids",
        "content_markdown",
        "resolution_markdown",
    }.isdisjoint(public_detail["properties"])

    create_request = schema["components"]["schemas"]["HelpRequestCreateRequest"]
    assert set(create_request["required"]) == {
        "request_type",
        "title",
        "content_markdown",
    }
    resolution_request = schema["components"]["schemas"]["HelpRequestResolutionRequest"]
    assert set(resolution_request["required"]) == {
        "resolution_markdown",
        "revision",
    }
    assert resolution_request["properties"]["revision"]["minimum"] == 1


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
