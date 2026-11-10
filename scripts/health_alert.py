"""Open (or close) a GitHub issue that tells the editor when the daily
edition needs attention. GitHub emails the repository owner about new
issues, so problems don't go unnoticed.

An alert is raised when the run failed, or when 3 or more sources failed.
When a later run is healthy again, the alert issue is closed.
Uses the GitHub CLI (gh), which is preinstalled on GitHub's runners.
"""

import json
import os
import subprocess
from pathlib import Path

TITLE = "Daily edition needs attention"
STATUS = Path(__file__).resolve().parent.parent / "docs" / "data" / "status.json"
FAILED_SOURCES_LIMIT = 3


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> None:
    job_ok = os.environ.get("JOB_STATUS", "success") == "success"
    failed = []
    if STATUS.exists():
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        failed = [s for s in status.get("sources", []) if not s.get("ok")]

    problem = (not job_ok) or len(failed) >= FAILED_SOURCES_LIMIT
    open_issues = json.loads(gh("issue", "list", "--state", "open", "--search",
                                f'"{TITLE}" in:title', "--json", "number"))

    if problem:
        lines = [f"Run: {os.environ.get('RUN_URL', '')}", ""]
        if not job_ok:
            lines.append("**The daily run failed.** Open the run link above to see which step.")
        if failed:
            lines.append(f"**{len(failed)} sources failed:**")
            lines += [f"- {s['name']}: {(s.get('error') or '')[:200]}" for s in failed]
        body = "\n".join(lines)
        if open_issues:
            gh("issue", "comment", str(open_issues[0]["number"]), "--body", body)
        else:
            gh("issue", "create", "--title", TITLE, "--body", body)
        print("Alert raised.")
    elif open_issues:
        for issue in open_issues:
            gh("issue", "close", str(issue["number"]), "--comment",
               "Resolved: the latest run was healthy.")
        print("Alert closed.")
    else:
        print("All good.")


if __name__ == "__main__":
    main()
