from tests.conftest import TEST_DB_PATH


def test_placeholder_auth_and_admin_suite_exists():
    assert TEST_DB_PATH.name == 'test_app.db'
