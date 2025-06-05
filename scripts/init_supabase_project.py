import logging
import time
from pathlib import Path

import os
import requests
import toml
from pydantic import BaseModel, Field

from enum import StrEnum

from constants import ConfigKeys, SupabaseEnv, PROJECT_DIR


class ApiEndpoint(StrEnum):
    BASE = "https://api.supabase.com"
    ORGS = "/v1/organizations"
    PROJECTS = "/v1/projects"
    PROJECT = "/v1/projects/{ref}"
    API_KEYS = "/v1/projects/{ref}/api-keys"


class SecretDefaults(StrEnum):
    DOWNLOAD_DEST_DIR = "data"
    BOOK_DIR_RELATIVE = "data/books"
    PROFILE_DB_PATH = ConfigKeys.PROFILE_DB_PATH
    RECIPE_DB_FILENAME = ConfigKeys.RECIPE_DB_FILENAME
    SECRETS_PATH = ".streamlit/secrets.toml"
    PROJECT_NAME = "streamlit_recipe_bot"
    REGION = "us-east-1"
    DB_PASSWORD = "postgres"


class SetupConfig(BaseModel):
    access_token: str = ""
    org_id: str | None = None
    project_name: str = Field(default=SecretDefaults.PROJECT_NAME)
    region: str = Field(default=SecretDefaults.REGION)
    db_password: str = Field(default=SecretDefaults.DB_PASSWORD)
    secrets_path: Path = Field(default_factory=lambda: Path(SecretDefaults.SECRETS_PATH))

    @classmethod
    def load(cls) -> "SetupConfig":
        path = PROJECT_DIR / SecretDefaults.SECRETS_PATH
        data = toml.loads(path.read_text()) if path.exists() else {}
        token = (
            os.getenv(SupabaseEnv.ACCESS_TOKEN.value)
            or os.getenv(SupabaseEnv.API_KEY.value)
            or data.get("supabase_access_token")
            or data.get("supabase_api_key", "")
        )
        org_id = os.getenv(SupabaseEnv.ORG_ID.value) or data.get("supabase_org_id")
        return cls(access_token=token, org_id=org_id, secrets_path=path)


class ProjectInfo(BaseModel):
    supabase_url: str
    supabase_api_key: str
    supabase_db_url: str


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "apikey": token,
        "Content-Type": "application/json",
    }


def _get_org_id(cfg: SetupConfig) -> str:
    if cfg.org_id:
        return cfg.org_id
    resp = requests.get(ApiEndpoint.BASE + ApiEndpoint.ORGS, headers=_headers(cfg.access_token), timeout=30)
    resp.raise_for_status()
    orgs = resp.json()
    return orgs[0]["id"]


def _create_project(cfg: SetupConfig, org_id: str) -> dict:
    payload = {
        "organization_id": org_id,
        "name": cfg.project_name,
        "db_pass": cfg.db_password,
        "region": cfg.region,
        "plan": "free",
    }
    resp = requests.post(ApiEndpoint.BASE + ApiEndpoint.PROJECTS, headers=_headers(cfg.access_token), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_project_details(cfg: SetupConfig, ref: str) -> dict:
    url = ApiEndpoint.BASE + ApiEndpoint.PROJECT.format(ref=ref)
    resp = requests.get(url, headers=_headers(cfg.access_token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_service_role_key(cfg: SetupConfig, ref: str) -> str:
    url = ApiEndpoint.BASE + ApiEndpoint.API_KEYS.format(ref=ref)
    resp = requests.get(url, headers=_headers(cfg.access_token), timeout=30)
    resp.raise_for_status()
    keys = resp.json()
    for item in keys:
        if item.get("name") == "service_role":
            return item["secret"]
    raise RuntimeError("service_role key not found")


def _write_secrets(info: ProjectInfo, cfg: SetupConfig) -> None:
    cfg.secrets_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.secrets_path.exists():
        data = toml.loads(cfg.secrets_path.read_text())
    else:
        data = {}
    data.update(
        {
            "supabase_url": info.supabase_url,
            "supabase_api_key": info.supabase_api_key,
            "supabase_db_url": info.supabase_db_url,
            "download_dest_dir": SecretDefaults.DOWNLOAD_DEST_DIR,
            "book_dir_relative": SecretDefaults.BOOK_DIR_RELATIVE,
            "profile_db_path": SecretDefaults.PROFILE_DB_PATH,
            "recipe_db_filename": SecretDefaults.RECIPE_DB_FILENAME,
        }
    )
    cfg.secrets_path.write_text(toml.dumps(data))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = SetupConfig.load()

    if not cfg.access_token:
        raise RuntimeError(
            "Personal access token missing. "
            "Add 'supabase_access_token' to the secrets file."
        )
    org_id = _get_org_id(cfg)
    logging.info("Using organization %s", org_id)
    proj = _create_project(cfg, org_id)
    ref = proj.get("ref") or proj["id"]
    logging.info("Created project %s", ref)

    # Wait until project is ready (~10 min max)
    for _ in range(40):
        details = _get_project_details(cfg, ref)
        if details.get("status") == "ACTIVE":
            break
        time.sleep(15)
    else:
        raise RuntimeError("Project did not become active")

    key = _get_service_role_key(cfg, ref)
    db_url = _get_project_details(cfg, ref)["db_url"]
    info = ProjectInfo(
        supabase_url=f"https://{ref}.supabase.co",
        supabase_api_key=key,
        supabase_db_url=db_url,
    )
    _write_secrets(info, cfg)
    logging.info("Secrets written to %s", cfg.secrets_path)


if __name__ == "__main__":
    main()
