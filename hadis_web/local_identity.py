"""Dependency-free identity for the installed project, not authentication."""
import hashlib
from pathlib import Path


def installation_id(project_root):
    return hashlib.sha256(str(Path(project_root).resolve()).casefold().encode('utf-8')).hexdigest()
