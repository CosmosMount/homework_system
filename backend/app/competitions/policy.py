from datetime import datetime

from app.competitions.models import Competition, CompetitionTask, Team

_STATUS_RANK = {
    "draft": 0,
    "registration_open": 1,
    "registration_closed": 2,
    "submission_open": 3,
    "submission_closed": 4,
    "archived": 5,
}


def timed_competition_status(competition: Competition, now: datetime) -> str:
    if competition.status == "archived":
        return "archived"
    if competition.published_at is None:
        return "draft"
    if now >= competition.submission_end:
        candidate = "submission_closed"
    elif now >= competition.submission_start:
        candidate = "submission_open"
    elif now >= competition.registration_end:
        candidate = "registration_closed"
    else:
        candidate = "registration_open"
    if _STATUS_RANK[competition.status] > _STATUS_RANK[candidate]:
        return competition.status
    return candidate


def registration_is_open(competition: Competition, now: datetime) -> bool:
    return (
        competition.status == "registration_open"
        and competition.registration_start <= now < competition.registration_end
    )


def team_can_change(competition: Competition, team: Team, now: datetime) -> bool:
    return team.status == "forming" and registration_is_open(competition, now)


def task_submission_is_open(
    competition: Competition,
    task: CompetitionTask,
    team: Team,
    now: datetime,
) -> bool:
    return (
        competition.status == "submission_open"
        and team.status == "locked"
        and competition.submission_start <= now < competition.submission_end
        and now < task.deadline
    )


def team_is_valid_for_lock(
    competition: Competition,
    team: Team,
    member_count: int,
) -> bool:
    return (
        team.min_size_waived_at is not None
        or competition.min_team_size <= member_count <= competition.max_team_size
    )
