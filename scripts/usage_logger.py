"""
usage_logger.py
---------------
Fail-soft usage tracker for Growisto Claude Code plugins.
POSTs login/tool_open (start) and tool_close (end) events to the
Apps Script webhook, tagging rows as source=Plugin so the Activity
Logs sheet shows both online-tool and plugin usage in one place.

Usage:
  python3 scripts/usage_logger.py start --name "Priya" --project "Nivia Sports" --tool "Keyword Classifier"
  python3 scripts/usage_logger.py end

Always exits 0 — logging must never break or interrupt a plugin run.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_WEBHOOK_URL = os.environ.get(
    "GROWISTO_USAGE_WEBHOOK_URL",
    "https://script.google.com/macros/s/AKfycbwBSxQ6cyCWjiKhWSkh8sz9KGP_IvE6bGwiik8Ho2Y0blSEnKgdCStji9t0rpZletMU/exec",
)

# State file lives in .work/ (gitignored) one level above scripts/
_SESSION_FILE = Path(__file__).parent.parent / ".work" / ".usage_session.json"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _post(events):
    try:
        import requests
        requests.post(_WEBHOOK_URL, json=events, timeout=5)
    except Exception:
        pass


def _start(name, project, tool):
    try:
        session_id = str(uuid.uuid4())
        session_start = _now_iso()
        ts = _now_iso()

        _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_FILE.write_text(json.dumps({
            "session_id": session_id,
            "session_start": session_start,
            "team_member": name,
            "project": project,
            "tool_name": tool,
        }))

        base = {
            "team_member": name,
            "project": project,
            "tool_name": tool,
            "session_id": session_id,
            "session_start": session_start,
            "session_end": "",
            "active_inactive": "active",
            "active_time": 0,
            "idle_time": 0,
            "browser": "Claude Code",
            "device": "desktop",
            "source": "Plugin",
        }

        _post([
            {**base, "event_type": "login",    "timestamp": ts},
            {**base, "event_type": "tool_open", "timestamp": ts},
        ])

        print(session_id)
    except Exception:
        pass


def _end():
    try:
        if not _SESSION_FILE.exists():
            return

        state = json.loads(_SESSION_FILE.read_text())
        ts = _now_iso()

        try:
            start_dt = datetime.fromisoformat(state["session_start"])
            active_time = int((datetime.now(timezone.utc) - start_dt).total_seconds())
        except Exception:
            active_time = 0

        _post([{
            "event_type": "tool_close",
            "team_member": state["team_member"],
            "project": state["project"],
            "tool_name": state["tool_name"],
            "session_id": state["session_id"],
            "session_start": state["session_start"],
            "session_end": ts,
            "active_inactive": "inactive",
            "active_time": active_time,
            "idle_time": 0,
            "browser": "Claude Code",
            "device": "desktop",
            "source": "Plugin",
            "timestamp": ts,
        }])

        _SESSION_FILE.unlink()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(add_help=False)
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start")
    p_start.add_argument("--name", required=True)
    p_start.add_argument("--project", required=True)
    p_start.add_argument("--tool", required=True)

    sub.add_parser("end")

    args, _ = parser.parse_known_args()

    if args.cmd == "start":
        _start(args.name, args.project, args.tool)
    elif args.cmd == "end":
        _end()

    sys.exit(0)


if __name__ == "__main__":
    main()
