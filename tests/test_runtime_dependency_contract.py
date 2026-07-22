from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scikit_learn_matches_persisted_model_version() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert '"scikit-learn==1.7.2"' in pyproject
    package = lockfile[lockfile.index('name = "scikit-learn"') :]
    assert 'version = "1.7.2"' in package[:100]
