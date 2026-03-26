from src.services.prompt_patterns import get_prompt_pattern_db


def test_pattern_db_loaded():
    db = get_prompt_pattern_db()
    patterns = db.get_patterns()
    assert len(patterns) >= 5
    names = [name for name, _, _ in patterns]
    assert "ignore_directives" in names
    assert db.version()


