"""Load and lightly validate config.yaml."""
from __future__ import annotations

import pathlib
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"
DATA_DIR = REPO_ROOT / "data"


def load_config(path: pathlib.Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("profile", {})
    cfg.setdefault("tracks", [])
    cfg.setdefault("exclude_titles", [])
    cfg.setdefault("experience", {"max_years_required": 3})
    cfg.setdefault("companies", [])
    cfg.setdefault("feeds", [])
    cfg.setdefault("alerts", {"min_score_high_priority": 7, "min_score_digest": 5})
    return cfg
