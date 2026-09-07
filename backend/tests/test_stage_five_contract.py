from app.core.config import Settings
from app.main import create_app


def test_openapi_exposes_independent_teams_without_competition_domain() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]

    expected_team_paths = {
        "/api/v1/team-profiles",
        "/api/v1/team-profiles/me",
        "/api/v1/team-invitations",
        "/api/v1/team-invitations/{invitation_id}/accept",
        "/api/v1/team-invitations/{invitation_id}/decline",
        "/api/v1/teams",
        "/api/v1/teams/me",
        "/api/v1/teams/join",
        "/api/v1/teams/auto-assign",
        "/api/v1/teams/{team_id}/invite-code/rotate",
        "/api/v1/teams/{team_id}/members/{user_id}",
        "/api/v1/teams/{team_id}/captain-transfer",
        "/api/v1/teams/{team_id}/dissolve",
        "/api/v1/admin/teams",
        "/api/v1/admin/teams/{team_id}",
        "/api/v1/admin/teams/{team_id}/members",
        "/api/v1/admin/teams/{team_id}/members/{user_id}",
        "/api/v1/admin/teams/{team_id}/captain-transfer",
    }
    assert expected_team_paths <= set(paths)
    assert not any("competition" in path for path in paths)

    delete_operation = paths["/api/v1/admin/teams/{team_id}"]["delete"]
    assert set(delete_operation["responses"]) == {"204", "422"}
    assert delete_operation["requestBody"]["required"] is True
    assert "AdminReasonRequest" in str(delete_operation["requestBody"])

    team_directory_schema = paths["/api/v1/teams"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    profile_directory_schema = paths["/api/v1/team-profiles"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert team_directory_schema == {"$ref": "#/components/schemas/TeamDirectoryResponse"}
    assert profile_directory_schema == {"$ref": "#/components/schemas/TeamProfilePage"}

    directory = schema["components"]["schemas"]["TeamDirectoryItem"]["properties"]
    assert "invite_code" not in directory
    assert "members" not in directory
    profile = schema["components"]["schemas"]["TeamProfileResponse"]["properties"]
    assert "email" not in profile
    assert "student_number" not in profile
    assert "introduction" in profile

    invitation = schema["components"]["schemas"]["TeamInvitationResponse"]["properties"]
    assert "invite_code" not in invitation
    assert "team_name" in invitation

    purpose_schema = schema["components"]["schemas"]["UploadInitRequest"]["properties"]["purpose"]
    assert set(purpose_schema["enum"]) == {
        "announcement_attachment",
        "assignment_submission",
    }

    serialized = str(schema).lower()
    assert "'score'" not in serialized
    assert "'ranking'" not in serialized


def test_openapi_keeps_intention_surveys_after_team_decoupling() -> None:
    paths = create_app(Settings(app_env="test")).openapi()["paths"]
    expected_paths = {
        "/api/v1/intentions",
        "/api/v1/intentions/{survey_id}",
        "/api/v1/intentions/{survey_id}/response",
        "/api/v1/admin/intentions",
        "/api/v1/admin/intentions/{survey_id}",
        "/api/v1/admin/intentions/{survey_id}/stats",
        "/api/v1/admin/intentions/{survey_id}/qr-token",
        "/api/v1/admin/intentions/{survey_id}/{action}",
    }
    assert expected_paths <= set(paths)
