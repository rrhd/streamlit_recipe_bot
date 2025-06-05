import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location(
    "init_supabase_project", ROOT / "scripts" / "init_supabase_project.py"
)
init_supabase_project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init_supabase_project)
_headers = init_supabase_project._headers


def test_headers_includes_authorization_and_apikey():
    token = "abc"
    headers = _headers(token)
    assert headers["Authorization"] == f"Bearer {token}"
    assert headers["apikey"] == token
