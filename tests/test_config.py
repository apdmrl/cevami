from hadis_web.config import Settings


def test_settings_repr_does_not_disclose_database_connection():
    connection='postgresql://example:private-connection-sentinel@localhost/test'
    rendered=repr(Settings(postgres_dsn=connection))
    assert 'private-connection-sentinel' not in rendered
    assert connection not in rendered
