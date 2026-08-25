from app.core.config import Settings
from app.main import create_app


def test_stage_five_openapi_contains_competitions_teams_and_team_submissions() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]

    expected_paths = {
        "/api/v1/competitions",
        "/api/v1/competitions/{competition_id}",
        "/api/v1/competitions/{competition_id}/registration",
        "/api/v1/competitions/{competition_id}/my-team",
        "/api/v1/competitions/{competition_id}/teams",
        "/api/v1/competitions/{competition_id}/teams/join",
        "/api/v1/teams/{team_id}/invite-code/rotate",
        "/api/v1/teams/{team_id}/members/{user_id}",
        "/api/v1/teams/{team_id}/captain-transfer",
        "/api/v1/teams/{team_id}/dissolve",
        "/api/v1/competitions/{competition_id}/tasks/{task_id}",
        "/api/v1/competitions/{competition_id}/tasks/{task_id}/submission-versions",
        "/api/v1/competitions/{competition_id}/tasks/{task_id}/submission",
        "/api/v1/admin/competitions",
        "/api/v1/admin/competitions/{competition_id}",
        "/api/v1/admin/competitions/{competition_id}/publish",
        "/api/v1/admin/competitions/{competition_id}/close-registration",
        "/api/v1/admin/competitions/{competition_id}/close-submissions",
        "/api/v1/admin/competitions/{competition_id}/archive",
        "/api/v1/admin/competitions/{competition_id}/tasks",
        "/api/v1/admin/competition-tasks/{task_id}",
        "/api/v1/admin/competitions/{competition_id}/teams",
        "/api/v1/admin/teams/{team_id}/members",
        "/api/v1/admin/teams/{team_id}/captain-transfer",
        "/api/v1/admin/teams/{team_id}/waive-min-size",
        "/api/v1/admin/teams/{team_id}/disqualify",
    }
    assert expected_paths <= set(paths)

    create_parameters = paths[
        "/api/v1/competitions/{competition_id}/tasks/{task_id}/submission-versions"
    ]["post"]["parameters"]
    header = next(
        parameter for parameter in create_parameters if parameter["name"] == "Idempotency-Key"
    )
    assert header["in"] == "header"
    assert header["required"] is True

    purpose_schema = schema["components"]["schemas"]["UploadInitRequest"]["properties"]["purpose"]
    assert set(purpose_schema["enum"]) == {
        "announcement_attachment",
        "assignment_submission",
        "competition_submission",
    }

    serialized = str(schema).lower()
    assert "'score'" not in serialized
    assert "'ranking'" not in serialized
