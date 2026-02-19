from main import create_app


def test_favicon_route_registered():
    app = create_app()
    paths = [getattr(r, "path", None) for r in getattr(app, "router", None).routes]
    assert "/favicon.ico" in paths
