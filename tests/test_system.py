from django.core.management import call_command


def test_manage_check() -> None:
    """Django system check passes without errors."""
    call_command("check", "--fail-level", "ERROR")
