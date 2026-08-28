import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_COMPOSE = ROOT / "infra/compose/compose.production.yml"
DEVELOPMENT_NGINX = ROOT / "infra/nginx/nginx.conf"
PRODUCTION_NGINX = ROOT / "infra/nginx/nginx.production.conf"
PRODUCTION_ENV = ROOT / ".env.production.example"

BACKEND_DOCKERFILE = ROOT / "backend/Dockerfile"
SECURITY_SCAN = ROOT / "infra/security/scan.sh"


def _service_block(compose: str, service: str, next_service: str | None) -> str:
    start = compose.index(f"  {service}:\n")
    end = (
        compose.index(f"  {next_service}:\n", start)
        if next_service
        else compose.index("\nnetworks:")
    )
    return compose[start:end]


def test_production_compose_uses_fixed_images_and_only_nginx_ports() -> None:
    compose = PRODUCTION_COMPOSE.read_text(encoding="utf-8")

    assert "\n    build:" not in compose
    assert compose.count("${BACKEND_IMAGE:?BACKEND_IMAGE must be fixed}") == 3
    assert compose.count("${FRONTEND_IMAGE:?FRONTEND_IMAGE must be fixed}") == 1
    assert ":latest" not in compose

    service_order = ["postgres", "minio", "migrate", "backend", "worker", "frontend", "nginx"]
    for index, service in enumerate(service_order):
        next_service = service_order[index + 1] if index + 1 < len(service_order) else None
        block = _service_block(compose, service, next_service)
        if service == "nginx":
            assert "\n    ports:" in block
            assert ":8080" in block
            assert ":8443" in block
        else:
            assert "\n    ports:" not in block


def test_production_compose_injects_secrets_and_limits_privileges() -> None:
    compose = PRODUCTION_COMPOSE.read_text(encoding="utf-8")

    for variable in (
        "SESSION_CURRENT_SECRET_FILE",
        "CSRF_SECRET_FILE",
        "TEAM_INVITE_CODE_PEPPER_FILE",
        "OUTBOX_ENCRYPTION_KEY_FILE",
        "DATABASE_PASSWORD_FILE",
        "MINIO_ACCESS_KEY_FILE",
        "MINIO_SECRET_KEY_FILE",
        "SMTP_PASSWORD_FILE",
    ):
        assert f"  {variable}: /run/secrets/" in compose

    assert compose.count("<<: *app-security") == 3
    app_security = compose[compose.index("x-app-security:") : compose.index("x-default-logging:")]
    assert "read_only: true" in app_security
    assert "no-new-privileges:true" in app_security
    for service, next_service in (
        ("postgres", "minio"),
        ("minio", "migrate"),
        ("frontend", "nginx"),
        ("nginx", None),
    ):
        block = _service_block(compose, service, next_service)
        assert "read_only: true" in block
        assert "no-new-privileges:true" in block
    assert compose.count("resources:") == 7
    assert "data_net:\n    driver: bridge\n    internal: true" in compose


def test_production_nginx_enforces_https_and_security_headers() -> None:
    nginx = PRODUCTION_NGINX.read_text(encoding="utf-8")

    assert "return 308 https://$host$request_uri;" in nginx
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in nginx
    assert "Strict-Transport-Security" in nginx
    assert "X-Content-Type-Options nosniff" in nginx
    assert "X-Frame-Options DENY" in nginx
    assert "proxy_request_buffering off;" in nginx
    assert "server_tokens off;" in nginx


def test_nginx_auth_rate_limit_uses_429_and_ignores_forwarded_ip_spoofing() -> None:
    for path in (DEVELOPMENT_NGINX, PRODUCTION_NGINX):
        nginx = path.read_text(encoding="utf-8")

        assert "limit_req_status 429;" in nginx
        assert "limit_req zone=auth_limit burst=20 nodelay;" in nginx
        assert "proxy_set_header X-Real-IP $remote_addr;" in nginx
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx


def test_production_template_contains_paths_not_secret_values() -> None:
    template = PRODUCTION_ENV.read_text(encoding="utf-8")

    assert "SESSION_PREVIOUS_SECRET_SOURCE" not in template
    assert "replace-with-digest" in template

    secret_lines = [
        line
        for line in template.splitlines()
        if re.match(r"^[A-Z0-9_]+_(?:SECRET|PASSWORD|KEY)_SOURCE=", line)
    ]
    assert secret_lines
    assert all("=/srv/pnx-training-hub/" in line for line in secret_lines)


def test_backend_process_and_pool_defaults_fit_postgresql_connection_budget() -> None:
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    development = (ROOT / ".env.example").read_text(encoding="utf-8")
    production = PRODUCTION_ENV.read_text(encoding="utf-8")

    assert '"--workers", "4"' in dockerfile
    assert "DATABASE_POOL_SIZE=8\nDATABASE_MAX_OVERFLOW=4" in development
    assert "DATABASE_POOL_SIZE=8\nDATABASE_MAX_OVERFLOW=4" in production


def test_alembic_escapes_config_parser_interpolation_in_database_url() -> None:
    migration_env = (ROOT / "backend/migrations/env.py").read_text(encoding="utf-8")

    assert (
        'config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))' in migration_env
    )


def test_security_scan_covers_git_history_and_current_candidate_tree() -> None:
    source = SECURITY_SCAN.read_text(encoding="utf-8")

    assert '"$GITLEAKS_IMAGE" detect' in source
    assert '"$GITLEAKS_IMAGE" dir /worktree' in source
    assert 'git -C "$REPOSITORY_ROOT" ls-files --cached --others --exclude-standard -z' in source
    assert "--env HOME=" not in source
