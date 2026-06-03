from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from data_forge.lab.state import LabRunStore
from data_forge.lab.supabase_store import SupabaseLabRunStore


def build_lab_store(*, root: Path, store_path: str) -> Any:
    backend = os.environ.get("DATA_FORGE_LAB_STORE", "local").strip().lower()
    if backend == "supabase":
        artifact_root = root / "generation/lab/supabase_artifacts"
        return SupabaseLabRunStore.from_env(artifact_root=artifact_root)
    if backend != "local":
        raise ValueError("DATA_FORGE_LAB_STORE must be 'local' or 'supabase'")
    path = Path(store_path)
    if not path.is_absolute():
        path = root / path
    return LabRunStore(path)
