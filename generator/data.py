"""读取和归一化真实 GitHub 活动；缺少数据来源时停止生成。"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from collections import OrderedDict
from pathlib import Path

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    name
    createdAt
    followers(first: 6) {
      totalCount
      nodes { login contributionsCollection { contributionCalendar { totalContributions } } }
    }
    pullRequests(states: OPEN) { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        description
        url
        stargazerCount
        isArchived
        pushedAt
        primaryLanguage { name }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
        releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { tagName publishedAt }
        }
        issues(states: OPEN, first: 3, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { number createdAt author { login } }
        }
        stargazers(last: 10, orderBy: {field: STARRED_AT, direction: ASC}) { edges { starredAt } }
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 5) { nodes { messageHeadline committedDate author { user { login } } } }
            }
          }
        }
      }
    }
  }
}
"""


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "homelab-os-profile"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    # Actions 令牌可能无法读取其他公开仓库的星标用户；该装饰字段缺失不影响主要贡献数据。
    errors = payload.get("errors", [])
    blocking = [error for error in errors
                if error.get("type") != "FORBIDDEN" or (error.get("path") or [None])[-1] != "stargazers"]
    if blocking:
        raise RuntimeError(f"GitHub 数据读取失败：{blocking}")
    if errors:
        print("星标用户列表权限不足，跳过新星小鸟与星标里程碑装饰")
    return normalise(payload["data"]["user"])


def normalise(user: dict) -> dict:
    cc = user["contributionsCollection"]
    days = [
        {"date": d["date"], "count": d["contributionCount"]}
        for w in cc["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    ]
    repos = []
    langs: dict[str, int] = {}
    for r in user["repositories"]["nodes"]:
        if r["name"].lower() == user["login"].lower():  # the profile repo itself is noise
            continue
        repos.append({
            "name": r["name"],
            "description": r.get("description") or "",
            "url": r["url"],
            "stars": r["stargazerCount"],
            "archived": r["isArchived"],
            "pushed_at": r["pushedAt"],
            "language": (r.get("primaryLanguage") or {}).get("name"),
            "release": next(({"tag": n["tagName"], "published_at": n["publishedAt"]}
                             for n in r["releases"]["nodes"] if n.get("publishedAt")), None),
            "issues": [{"number": i["number"], "created_at": i["createdAt"],
                        "author": (i.get("author") or {}).get("login") or "ghost"}
                       for i in r["issues"]["nodes"]],
            # 权限不足时 GraphQL 保留仓库数据，但将 stargazers 返回为 null。
            "recent_stars": [e["starredAt"] for e in (r.get("stargazers") or {}).get("edges", [])],
            "last_commit": _my_commit(r, user["login"]),
        })
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    return {
        "login": user["login"],
        "name": user.get("name") or user["login"],
        "created_at": user["createdAt"],
        "followers": user["followers"]["totalCount"],
        "neighbours": [{"login": f["login"],
                        "total": f["contributionsCollection"]["contributionCalendar"]["totalContributions"]}
                       for f in user["followers"]["nodes"]],
        "open_prs": user["pullRequests"]["totalCount"],
        "days": sorted(days, key=lambda d: d["date"]),
        "total": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "repo_count": user["repositories"]["totalCount"],
        "repos": repos,
        "languages": sorted(langs.items(), key=lambda kv: -kv[1]),
    }


def _my_commit(repo: dict, login: str) -> dict | None:
    target = (repo.get("defaultBranchRef") or {}).get("target") or {}
    for c in (target.get("history") or {}).get("nodes", []):
        if ((c.get("author") or {}).get("user") or {}).get("login", "").lower() == login.lower():
            return {"headline": c["messageHeadline"], "date": c["committedDate"]}
    return None


def load(login: str, path: str | None = None) -> dict:
    # 本地首次生成可读取已抓取的真实公开数据；定时任务使用 GitHub 令牌。
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("login", "").lower() != login.lower():
            raise ValueError("数据账号与主页配置不一致")
        return payload
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("需要 GITHUB_TOKEN 或通过 --data 指定真实公开数据文件")
    return fetch(login, token)


# ---------------------------------------------------------------- derived stats

def stats(data: dict, today: dt.date | None = None) -> dict:
    days = data["days"]
    counts = [d["count"] for d in days]
    today = today or dt.date.fromisoformat(days[-1]["date"])

    # current streak tolerates "nothing yet today"
    i = len(days) - 1
    if counts and counts[i] == 0 and days[i]["date"] == today.isoformat():
        i -= 1
    current = 0
    while i >= 0 and counts[i] > 0:
        current += 1
        i -= 1
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)

    best = max(days, key=lambda d: d["count"]) if days else {"date": today.isoformat(), "count": 0}
    months: "OrderedDict[str, list[dict]]" = OrderedDict()
    for d in days:
        months.setdefault(d["date"][:7], []).append(d)
    last12 = list(months.items())[-12:]
    return {
        "today": today,
        "current_streak": current,
        "longest_streak": longest,
        "best_day": best,
        "last7": sum(counts[-7:]),
        "last30": counts[-30:],
        "active_days": sum(1 for c in counts if c),
        "months": last12,
        "max_day": max(counts or [0]),
        "stars": sum(r["stars"] for r in data["repos"]),
        "release": recent_release(data, today),
        "intrusions": intrusions(data, today),
        "last_commit": last_commit(data),
        "today_count": counts[-1] if counts else 0,
        "idle_days": next((k for k, c in enumerate(reversed(counts)) if c), len(counts)),
        "stars_week": sum(1 for r in data["repos"] for s in r.get("recent_stars", []) if _age(s, today) <= 7),
        "milestone": star_milestone(data, today),
    }


def last_commit(data: dict) -> dict | None:
    found = [(r["last_commit"]["date"], r["name"], r["last_commit"]["headline"])
             for r in data["repos"] if r.get("last_commit")]
    if not found:
        return None
    date, repo, headline = max(found)
    return {"repo": repo, "headline": headline, "date": date}


def star_milestone(data: dict, today: dt.date, step: int = 100) -> dict | None:
    """A repo that crossed a multiple of `step` stars during the last week → fireworks."""
    for r in data["repos"]:
        recent = sum(1 for s in r.get("recent_stars", []) if _age(s, today) <= 7)
        if r["stars"] >= step and (r["stars"] - recent) // step < r["stars"] // step:
            return {"repo": r["name"], "stars": r["stars"] // step * step}
    return None


def _age(ts: str, today: dt.date) -> int:
    return (today - dt.date.fromisoformat(ts[:10])).days


def recent_release(data: dict, today: dt.date, days: int = 7) -> dict | None:
    """Newest release published in the last week → the car is parked in the driveway."""
    found = [(r["release"]["published_at"], r["name"], r["release"]["tag"])
             for r in data["repos"] if r.get("release") and _age(r["release"]["published_at"], today) <= days]
    if not found:
        return None
    ts, repo, tag = max(found)
    return {"repo": repo, "tag": tag, "published_at": ts}


def intrusions(data: dict, today: dt.date, days: int = 7) -> list[dict]:
    """Open issues filed by someone else (not a bot) on my public repos during the last week."""
    me = data.get("login", "").lower()
    hits = [
        {"repo": r["name"], "number": i["number"], "created_at": i["created_at"]}
        for r in data["repos"] for i in r.get("issues", [])
        if i["author"].lower() != me and not i["author"].endswith("[bot]") and _age(i["created_at"], today) <= days
    ]
    return sorted(hits, key=lambda h: h["created_at"], reverse=True)
