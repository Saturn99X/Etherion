from sqlalchemy.orm import configure_mappers


def test_sqlalchemy_mappers_configure_without_errors():
    import src.database.ts_models  # noqa: F401
    import src.database.models  # noqa: F401

    configure_mappers()
