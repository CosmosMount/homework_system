from app.core.config import Settings
from app.main import create_app


def test_stage_four_openapi_contains_assignments_submissions_and_upload_purpose() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]

    expected_paths = {
        "/api/v1/assignments",
        "/api/v1/assignments/{assignment_id}",
        "/api/v1/assignments/{assignment_id}/excellent-submissions",
        "/api/v1/assignments/{assignment_id}/excellent-submissions/{version_id}",
        "/api/v1/admin/assignments",
        "/api/v1/admin/assignments/{assignment_id}",
        "/api/v1/admin/assignments/{assignment_id}/publish",
        "/api/v1/admin/assignments/{assignment_id}/close",
        "/api/v1/admin/assignments/{assignment_id}/archive",
        "/api/v1/admin/assignments/{assignment_id}/extensions/{user_id}",
        "/api/v1/admin/assignments/{assignment_id}/submissions",
        "/api/v1/admin/assignments/{assignment_id}/excellent-submissions/{version_id}",
        "/api/v1/assignments/{assignment_id}/submission-versions",
        "/api/v1/assignments/{assignment_id}/submission",
        "/api/v1/submissions/{submission_id}",
        "/api/v1/submissions/{submission_id}/versions/{version_id}",
        "/api/v1/admin/submissions/{submission_id}/versions/{version_id}/feedback",
    }

    assert expected_paths <= set(paths)
    create_parameters = paths["/api/v1/assignments/{assignment_id}/submission-versions"]["post"][
        "parameters"
    ]
    header = next(
        parameter for parameter in create_parameters if parameter["name"] == "Idempotency-Key"
    )
    assert header["in"] == "header"
    assert header["required"] is True

    purpose_schema = schema["components"]["schemas"]["UploadInitRequest"]["properties"]["purpose"]
    assert {
        "announcement_attachment",
        "assignment_submission",
    } <= set(purpose_schema["enum"])
