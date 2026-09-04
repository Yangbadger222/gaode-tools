# Cross-platform audit

| Location | Previous assumption | Windows risk | Resolution |
|---|---|---|---|
| `.env.example` | macOS Chrome absolute path example | Invalid path | Documented as optional override; automatic discovery added |
| `capture.py` | Relied on one configured browser or Playwright download | Edge was not discovered | Centralized browser discovery for Chrome/Edge/Chromium |
| `region.json` and plan | Stored invocation-dependent paths | Dataset movement could fail | New region files store portable filenames using `/` semantics |
| Annotator/check/preview loaders | Inconsistent relative-path resolution | Mac data might not open after copying | Absolute, manifest-relative, then project-relative legacy resolution |
| Annotation atomic save | `Path.replace` with an open `mkstemp` descriptor | Windows file locking risk | Close descriptor, validate JSON, then `os.replace` |
| README commands | Primarily POSIX shell and user-specific path | Not usable in PowerShell | Added separate macOS and Windows instructions |

Remaining: Windows 10/11 x64 real-machine collector and GUI validation must still be run.
