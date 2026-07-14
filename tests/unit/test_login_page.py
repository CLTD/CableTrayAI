from pathlib import Path


LOGIN = Path("apps/web/login.html")


def test_login_uses_selected_real_model_animation_and_live_auth_form() -> None:
    text = LOGIN.read_text(encoding="utf-8")

    assert 'id="ct-login-hero-v3"' in text
    assert 'id="ct-v3-model-source"' in text
    assert "ctV3Flow" in text
    assert "ctV3Scan" in text
    assert 'id="loginForm"' in text
    assert 'id="username"' in text
    assert 'id="password"' in text
    assert 'id="loginButton"' in text
    assert 'fetch("/auth/login"' in text
    assert "cabletray_login_username" in text


def test_login_animation_has_accessible_reduced_motion_and_mobile_layout() -> None:
    text = LOGIN.read_text(encoding="utf-8")

    assert "prefers-reduced-motion: reduce" in text
    assert "@media (max-width: 760px)" in text
    assert 'aria-live="polite"' in text
    assert "width: 28.5%;" in text
    assert "min-height: clamp(36px, 3vw, 50px);" in text
    assert ".form-control,\n      #ct-login-hero-v3 .btn { min-height: 48px; }" in text
