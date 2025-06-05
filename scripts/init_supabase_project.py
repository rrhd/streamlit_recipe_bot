import logging
import os
import time
from pathlib import Path

import requests
import toml
from pydantic import BaseModel, Field

from config import CONFIG
from constants import SupabaseEnv


class ApiEndpoint(str):
    BASE = "https://api.supabase.com"
    ORGS = "/v1/organizations"
    PROJECTS = "/v1/projects"
    PROJECT = "/v1/projects/{ref}"
    API_KEYS = "/v1/projects/{ref}/api-keys"

class SecretDefaults(str):
    DOWNLOAD_DEST_DIR = "."
    BOOK_DIR_RELATIVE = "books"
    PROFILE_DB_PATH = "data/profiles_db.sqlite"
    RECIPE_DB_FILENAME = "recipe_links.db"
    SECRETS_PATH = ".streamlit/secrets.toml"
    PROJECT_NAME = "streamlit-recipe-bot"
    REGION = "us-east-1"
    DB_PASSWORD = "postgres"


class SetupConfig(BaseModel):
    supabase_access_token: str = Field(default_factory=lambda: os.getenv(SupabaseEnv.ACCESS_TOKEN, ""))
    supabase_org_id: str | None = Field(default_factory=lambda: os.getenv(SupabaseEnv.ORG_ID))
    supabase_project_name: str = Field(default=SecretDefaults.PROJECT_NAME)
    region: str = Field(default=SecretDefaults.REGION)
    db_password: str = Field(default=SecretDefaults.DB_PASSWORD)
    secrets_path: Path = Field(default_factory=lambda: Path(SecretDefaults.SECRETS_PATH))


class ProjectInfo(BaseModel):
    supabase_url: str
    supabase_api_key: str
    supabase_db_url: str


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "apikey": token, "Content-Type": "application/json"}


def _get_org_id(cfg: SetupConfig) -> str:
    if cfg.supabase_org_id:
        return cfg.supabase_org_id
    resp = requests.get(ApiEndpoint.BASE + ApiEndpoint.ORGS, headers=_headers(cfg.supabase_access_token), timeout=30)
    resp.raise_for_status()
    orgs = resp.json()
    return orgs[0]["id"]


def _create_project(cfg: SetupConfig, org_id: str) -> dict:
    payload = {
        "organization_id": org_id,
        "name": cfg.supabase_project_name,
        "db_pass": cfg.db_password,
        "region": cfg.region,
        "plan": "free",
    }
    resp = requests.post(ApiEndpoint.BASE + ApiEndpoint.PROJECTS, headers=_headers(cfg.supabase_access_token), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_project_details(cfg: SetupConfig, ref: str) -> dict:
    url = ApiEndpoint.BASE + ApiEndpoint.PROJECT.format(ref=ref)
    resp = requests.get(url, headers=_headers(cfg.supabase_access_token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_service_role_key(cfg: SetupConfig, ref: str) -> str:
    url = ApiEndpoint.BASE + ApiEndpoint.API_KEYS.format(ref=ref)
    resp = requests.get(url, headers=_headers(cfg.supabase_access_token), timeout=30)
    resp.raise_for_status()
    keys = resp.json()
    for item in keys:
        if item.get("name") == "service_role":
            return item["api_key"]  # Changed from 'secret' to 'api_key'
    raise RuntimeError("service_role key not found")


def _write_secrets(info: ProjectInfo, cfg: SetupConfig) -> None:
    if cfg.secrets_path.exists():
        data = toml.loads(cfg.secrets_path.read_text())
    else:
        data = {}
    data.update(
        {
            "supabase_url": info.supabase_url,
            "supabase_api_key": info.supabase_api_key,
            "supabase_db_url": info.supabase_db_url,
            "download_dest_dir": Path(SecretDefaults.DOWNLOAD_DEST_DIR).resolve().absolute().as_posix(),
            "book_dir_relative": SecretDefaults.BOOK_DIR_RELATIVE,
            "profile_db_path": SecretDefaults.PROFILE_DB_PATH,
            "recipe_db_filename": SecretDefaults.RECIPE_DB_FILENAME,
        }
    )
    cfg.secrets_path.write_text(toml.dumps(data))

def _find_project_by_name(cfg: SetupConfig, org_id: str, project_name: str) -> dict | None:
    url = f"{ApiEndpoint.BASE}{ApiEndpoint.PROJECTS}?organization_id={org_id}"
    resp = requests.get(url, headers=_headers(cfg.supabase_access_token), timeout=30)
    resp.raise_for_status()
    projects = resp.json()
    for proj in projects:
        if proj.get("name") == project_name:
            return proj
    return None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = SetupConfig(**CONFIG.model_dump())
    org_id = _get_org_id(cfg)
    logging.info("Using organization %s", org_id)

    # Check if project exists
    existing_proj = _find_project_by_name(cfg, org_id, cfg.supabase_project_name)
    if existing_proj:
        ref = existing_proj["id"]
        logging.info("Using existing project %s", ref)
    else:
        proj = _create_project(cfg, org_id)
        ref = proj["id"]
        logging.info("Created project %s", ref)

    # Wait until project is ready
    for _ in range(20):
        details = _get_project_details(cfg, ref)
        if details.get("status", "").startswith("ACTIVE"):
            break
        time.sleep(15)
    else:
        raise RuntimeError("Project did not become active")

    key = _get_service_role_key(cfg, ref)

    # Build database connection string from components
    db_host = details["database"]["host"]
    db_user = "postgres"  # Default username
    db_password = cfg.db_password
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:5432/postgres"

    info = ProjectInfo(
        supabase_url=f"https://{ref}.supabase.co",
        supabase_api_key=key,
        supabase_db_url=db_url,
    )
    _write_secrets(info, cfg)
    logging.info("Secrets written to %s", cfg.secrets_path)


if __name__ == "__main__":
    main()
