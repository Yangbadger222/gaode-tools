from pathlib import Path
def portable_name(path): return Path(path).name.replace('\\','/')
def resolve_data_path(value,manifest,project_root=None):
    p=Path(value)
    if p.is_absolute() and p.exists():return p
    for candidate in (Path(manifest).parent/p, p, (Path(project_root)/p if project_root else p)):
        if candidate.exists():return candidate
    return Path(manifest).parent/p
