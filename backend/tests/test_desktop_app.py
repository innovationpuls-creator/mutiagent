from pathlib import Path

from fastapi.testclient import TestClient

from app.desktop import create_desktop_app
from tests.postgres import postgresql_test_url


def _write_frontend(frontend_dist: Path) -> None:
    assets_dir = frontend_dist / "assets"
    assets_dir.mkdir(parents=True)
    (frontend_dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root">OneTree</div></body></html>',
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('onetree')", encoding="utf-8")


def test_desktop_app_serves_api_assets_and_spa_routes(tmp_path: Path) -> None:
    frontend_dist = tmp_path / "frontend"
    _write_frontend(frontend_dist)
    app = create_desktop_app(
        database_url=postgresql_test_url(tmp_path, "desktop-static"),
        frontend_dist=frontend_dist,
    )

    with TestClient(app) as client:
        assert client.get("/api/health/live").json() == {"status": "ok"}
        assert client.get("/assets/app.js").text == "console.log('onetree')"
        branch_response = client.get("/branch")

    assert branch_response.status_code == 200
    assert "OneTree" in branch_response.text


def test_desktop_app_rejects_missing_frontend_index(tmp_path: Path) -> None:
    frontend_dist = tmp_path / "frontend"
    frontend_dist.mkdir()

    try:
        create_desktop_app(
            database_url=postgresql_test_url(tmp_path, "desktop-missing-frontend"),
            frontend_dist=frontend_dist,
        )
    except RuntimeError as error:
        assert str(error) == "桌面版前端入口不存在"
    else:
        raise AssertionError("missing desktop frontend index was accepted")
