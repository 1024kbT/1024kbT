"""Panel 1 — SSH into the homelab: banner + systemd-style boot log built from real stats."""

from __future__ import annotations

from .. import ctf, environment
from ..svg import AMBER, CYAN, DIM, GREEN, MAGENTA, RED, THEME, document, esc, text, titlebar

# 用等宽点阵绘制本人的 FTWEST 标题，保留终端霓虹效果。
GLYPHS = {
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
}
BANNER = [" ".join(GLYPHS[c][row] for c in "FTWEST").replace("1", "█").replace("0", " ") for row in range(7)]

CSS = """
.glitch { animation: glitch 6s infinite; }
@keyframes glitch {
  0%, 91%, 100% { transform: translate(0,0); }
  92% { transform: translate(-3px,1px); } 93% { transform: translate(3px,-1px); }
  94% { transform: translate(-1px,0); }
}
.ghost { animation: ghost 6s infinite; opacity: 0; }
@keyframes ghost { 0%,91%,95%,100% { opacity: 0; } 92%,94% { opacity: .6; } }
"""



def typed(x, y, s, begin, cls="green", size=12.5):
    """A command line that types itself (SMIL clip width animation)."""
    w = len(s) * 7.9 + 10  # generous: any monospace font at 12.5px fits
    cid = f"t{int(y)}"
    return (
        f'<clipPath id="{cid}"><rect x="{x}" y="{y - 14}" width="0" height="20">'
        f'<animate attributeName="width" from="0" to="{w}" begin="{begin}s" dur="{len(s) * 0.035:.2f}s" fill="freeze"/>'
        f"</rect></clipPath>"
        f'<g clip-path="url(#{cid})">{text(x, y, s, cls, size)}</g>'
    )


def render(cfg: dict, data: dict, st: dict) -> str:
    years = st["today"].year - int(data["created_at"][:4])
    integ = len(cfg["integrations"])
    body = [titlebar(f"{data['login'].lower()}@{cfg['hostname']} — ssh — 120×32", "● CONNECTED")]

    # banner (top-left) with glitch + magenta ghost copy
    bx, by = 34, 68
    def banner(fill):
        return "".join(
            f'<text x="{bx}" y="{by + i * 15}" font-size="13" textLength="{len(line) * 8.4:.1f}" '
            f'lengthAdjust="spacingAndGlyphs" xml:space="preserve" style="fill:{fill}">{esc(line)}</text>'
            for i, line in enumerate(BANNER)
        )

    body.append(f'<g class="ghost" transform="translate(4,0)">{banner(MAGENTA)}</g>')
    body.append(f'<g class="glitch" filter="url(#glow)">{banner("url(#neon)")}</g>')

    # whoami card (top-right)
    cx = 470
    card = [
        (f"{cfg['display_name']}", "b cyan", 15),
        (cfg["role"], "mag", 11.5),
        (f"loc     {cfg['location']}", "", 11),
        (f"uptime  {years} yrs on GitHub", "", 11),
        (f"repos   {data['repo_count']} public · {st['stars']} ★", "", 11),
        (f"motto   {cfg['motto']}", "dim", 11),
    ]
    body.append(f'<rect x="{cx - 14}" y="50" width="{840 - cx - 10}" height="114" rx="8" fill="none" stroke="{CYAN}" stroke-opacity=".35"/>')
    for i, (s, cls, size) in enumerate(card):
        body.append(text(cx, 70 + i * 16, s, f"fade {cls}", size,
                         extra=f'style="animation-delay:{0.2 + i * 0.12:.2f}s"'))

    # boot log
    y0 = 186
    t = 0.6
    body.append(typed(30, y0, f"$ ssh {data['login'].lower()}@{cfg['hostname']}", t))
    t += 1.3
    log = [
        ("OK", f"加载 dev-stack.service — {integ} 项技术栈就绪"),
        ("OK", "启动 vue.service + nestjs.service — 持续学习中"),
        ("OK", f"挂载 /dev/github — {data['repo_count']} 个公开仓库，{st['stars']} 颗星"),
        ("OK", f"贡献日历已同步 — {len(data['days'])} 天内 {data['total']} 次贡献"),
        ("OK", f"连续贡献 — 当前 {st['current_streak']} 天，最长 {st['longest_streak']} 天"),
        ("OK", f"启用季节主题 — {THEME['label']} {THEME['icon']}"),
        ("OK", f"杭州天气 — {environment.describe(st['env'])[1]}"),
    ]
    if st["birthday"]:
        log.append(("OK", "birthday.target — 生日快乐！🎂"))
    if st["outage"]:
        log.append(("WARN", f"ups.service — 已休息 {st['idle_days']} 天，小屋使用备用电源"))
    if ctf.flag():
        log.append(("OK", "honeypot.service — SVG 中藏着挑战线索 🏁"))
    if st["intrusions"]:
        hit = st["intrusions"][0]
        log.append(("WARN", f"issue.service — 新问题 {hit['repo']}#{hit['number']}"))
    else:
        log.append(("WARN", "coffee.service — 咖啡不足，请续杯 ☕"))
    for i, (lvl, msg) in enumerate(log):
        y = y0 + 22 + i * 19
        color = {"OK": GREEN, "WARN": AMBER, "FAIL": RED}[lvl]
        delay = f"animation-delay:{t + i * 0.28:.2f}s"
        body.append(
            f'<g class="fade" style="{delay}">'
            f'<text x="30" y="{y}" font-size="12" xml:space="preserve"><tspan fill="{DIM}">[</tspan>'
            f'<tspan fill="{color}" font-weight="700">{lvl:^6}</tspan><tspan fill="{DIM}">]</tspan> {esc(msg)}</text></g>'
        )
    t += len(log) * 0.28 + 0.3
    y = y0 + 22 + len(log) * 19 + 8
    body.append(typed(30, y, "$ echo $WELCOME", t))
    t += 0.8
    msg = "Welcome to FTWest's dev home."
    body.append(f'<g class="fade" style="animation-delay:{t:.2f}s">{text(30, y + 20, msg, "cyan b", 12.5)}</g>')
    cur_x = 30 + len(msg) * 7.55 + 6
    body.append(f'<rect class="blink" x="{cur_x:.0f}" y="{y + 9}" width="8" height="14" fill="{CYAN}"/>')
    return document(y + 42, "\n".join(body), f"{cfg['display_name']} — homelab boot console", CSS, head=ctf.desc())
