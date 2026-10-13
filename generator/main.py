"""从 GitHub 真实数据生成个人主页和四张 SVG。"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import tomllib
import urllib.parse
from pathlib import Path

from . import data as data_mod
from . import ctf, environment, seasons, svg
from .panels import boot, house, integrations, soc

ROOT = Path(__file__).resolve().parent.parent
PANELS = {"boot": boot, "house": house, "soc": soc, "integrations": integrations}


def featured_table(cfg: dict, data: dict) -> str:
    by_name = {r["name"]: r for r in data["repos"]}
    # 用本人的公开仓库生成项目列表，并转义表格分隔符和换行。
    rows = ["| | 项目 | 简介 | ★ |", "|:-:|---|---|:-:|"]
    for f in cfg["featured"]:
        r = by_name.get(f["repo"])
        if not r:  # private, renamed or deleted: never leak it
            continue
        desc = (r["description"] or "—").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        tag = " `archived`" if r.get("archived") else ""
        rows.append(f"| {f['icon']} | [**{r['name']}**]({r['url']}){tag} | {desc} | {r['stars']} |")
    return "\n".join(rows)


def badges(cfg: dict) -> str:
    out = []
    for link in cfg["links"]:
        label = urllib.parse.quote(link["label"])
        out.append(f'<a href="{link["url"]}"><img alt="{link["label"]}" '
                   f'src="https://img.shields.io/badge/{label}-0c1320?style=for-the-badge&logo={link["logo"]}&logoColor=00e5ff"></a>')
    return "\n".join(out)


def readme(cfg: dict, data: dict, generated: str) -> str:
    ctf_hint = ("<!-- 🏁 psst: a flag is split in 3 encoded fragments across assets/*.svg. "
                "Found it? Open an issue with it… and watch my alarm go off. -->\n") if ctf.flag() else ""
    return f"""<div align="center">

<img src="assets/boot.svg" width="100%" alt="ssh {data['login'].lower()}@{cfg['hostname']} — boot console">

**{cfg['tagline_en']}**<br>
<sub>{cfg['tagline_zh']}</sub>

</div>

### 🏠 我的 GitHub 贡献小屋
<sub>把过去一年的 GitHub 活动建成一座 3D 小屋：庭院里的每根柱子代表一天贡献，窗户亮度对应每月活动。天空随杭州的昼夜与天气变化；待处理 PR 打开车库，新发布版本带来一辆车，新 Issue 点亮提醒，还有随季节变化的装饰。</sub>

<img src="assets/house.svg" width="100%" alt="Isometric smart home made from contributions">

### 🛡️ GitHub 活动控制中心
<img src="assets/soc.svg" width="100%" alt="SOC dashboard: radar, streaks, alerts, 30-day activity">

### 🔌 技术栈 · 正在学习
<img src="assets/integrations.svg" width="100%" alt="Home-lab integrations and languages">

### 📦 我的项目
{featured_table(cfg, data)}

### 📡 联系我
{badges(cfg)}

**QQ**：{cfg['qq']} · **Email**：{cfg['email']}

{ctf_hint}<div align="center"><sub>⚙️ GitHub Actions 每两小时自动更新 · 最近同步 {generated}<br>
视觉与生成器改编自 <a href="https://github.com/JigSawFr/JigSawFr">JigSawFr 的贡献小屋</a> · 数据来自 @{cfg['login']} 的公开 GitHub 活动</sub></div>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="读取已抓取的真实公开活动数据")
    ap.add_argument("--out", type=Path, default=ROOT)
    ap.add_argument("--season", default=os.environ.get("PROFILE_SEASON") or None,
                    help=f"force a theme: {', '.join(seasons.THEMES)} (default: from today's date)")
    ap.add_argument("--phase", choices=environment.PHASES, help="force the time of day")
    ap.add_argument("--weather", choices=environment.WEATHERS, help="force the weather")
    ap.add_argument("--demo-intrusion", action="store_true", help="pretend someone just opened an issue")
    ap.add_argument("--demo-outage", action="store_true", help="pretend I haven't contributed for 10 days")
    ap.add_argument("--demo-birthday", action="store_true", help="pretend it's my birthday")
    ap.add_argument("--demo-milestone", action="store_true", help="pretend a repo just passed 100 stars")
    args = ap.parse_args()

    cfg = tomllib.loads((ROOT / "generator" / "config.toml").read_text(encoding="utf-8"))
    data = data_mod.load(cfg["login"], args.data)
    st = data_mod.stats(data)
    st["env"] = environment.load(False, args.phase, args.weather)
    # 日期、生日和季节统一采用上海时区，避免午夜附近显示前一天。
    now = dt.datetime.now(environment.LOCAL_TZ)
    # MM-DD, kept in the PROFILE_BIRTHDAY repository secret so it never sits in the code
    st["birthday"] = args.demo_birthday or now.strftime("%m-%d") == os.environ.get("PROFILE_BIRTHDAY")
    if args.demo_outage:
        st["idle_days"] = 10
    st["outage"] = st["idle_days"] >= 7
    if args.demo_milestone:
        st["milestone"] = {"repo": cfg["featured"][0]["repo"], "stars": 100}
    if args.demo_intrusion:
        st["intrusions"] = [{"repo": cfg["featured"][0]["repo"], "number": 12, "created_at": st["today"].isoformat()}]
    svg.use_theme(seasons.theme(args.season or seasons.season_key(now.date())))

    assets = args.out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name, mod in PANELS.items():
        (assets / f"{name}.svg").write_text(mod.render(cfg, data, st), encoding="utf-8")
    generated = now.strftime("%Y-%m-%d %H:%M CST")
    (args.out / "README.md").write_text(readme(cfg, data, generated), encoding="utf-8")
    print(f"已生成 {len(PANELS)} 张主页图片，账号 {data['login']}，贡献 {data['total']}，主题 {svg.THEME['key']}，昼夜/天气 {st['env']['phase']}/{st['env']['weather']}")


if __name__ == "__main__":
    main()
