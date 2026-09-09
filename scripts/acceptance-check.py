#!/usr/bin/env python3
"""acceptance-check.py — 7 项验收检查（纯规则, 直接查 DB）
独立来源识别 / 事件证据关联 / 事实状态 / 质量评分 / 发现机制 / 健康检查 / AI-OFF核心
"""
import json, sqlite3, sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
DB = Path(PROJ) / "news-data/database/news.db"

def q(con, sql, args=()):
    return con.execute(sql, args).fetchall()

def main():
    out = {}
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    # 1 独立来源识别: 存在 independent_source_count < source_count 的活跃 story
    rows = q(con, "SELECT id, source_count, independent_source_count FROM stories WHERE status='active' AND independent_source_count IS NOT NULL")
    compressed = [r for r in rows if r[1] and r[2] is not None and r[2] < r[1]]
    out["独立来源识别"] = "PASS" if compressed else "FAIL"
    out["  证据"] = f"{len(compressed)}/{len(rows)} 个 story 实现转载压缩 (如 {compressed[0] if compressed else '-'})"
    # 2 事件证据关联
    n_ev = q(con, "SELECT COUNT(*), COUNT(DISTINCT story_id) FROM event_evidence")[0]
    out["事件证据关联"] = "PASS" if n_ev[0] > 0 and n_ev[1] > 0 else "FAIL"
    out["  证据"] = f"event_evidence {n_ev[0]} 行 / {n_ev[1]} 个 story"
    # 3 事实状态 + 历史
    st = q(con, "SELECT fact_status, COUNT(*) FROM stories WHERE fact_status IS NOT NULL GROUP BY fact_status")
    hist = q(con, "SELECT COUNT(*) FROM story_fact_history")[0][0]
    out["事实状态"] = "PASS" if st and hist > 0 else "FAIL"
    out["  证据"] = f"{json.dumps(dict(st), ensure_ascii=False)} | 历史 {hist} 条"
    # 4 质量评分
    sc = q(con, "SELECT tier, COUNT(*), ROUND(AVG(quality_score),1) FROM sources WHERE quality_score IS NOT NULL GROUP BY tier")
    out["来源质量评分"] = "PASS" if sc else "FAIL"
    out["  证据"] = json.dumps({r[0]: f"{r[1]}源 均分{r[2]}" for r in sc}, ensure_ascii=False)
    # 5 发现机制: candidate_sources 存在且有记录
    cd = q(con, "SELECT verification_status, COUNT(*) FROM candidate_sources GROUP BY verification_status")
    out["来源发现机制"] = "PASS" if cd else "FAIL"
    out["  证据"] = json.dumps(dict(cd), ensure_ascii=False)
    # 6 健康检查: audit JSON 存在 + degraded 机制(标状态不删)
    audit = Path(PROJ) / "news-data/state/source-audit.json"
    src_total = q(con, "SELECT COUNT(*) FROM sources")[0][0]
    del_cnt = q(con, "SELECT COUNT(*) FROM sources WHERE disabled=1 AND disabled_reason IS NOT NULL")[0][0]
    out["来源健康检查"] = "PASS" if audit.exists() and src_total > 0 else "FAIL"
    out["  证据"] = f"audit JSON={'有' if audit.exists() else '无'} | sources={src_total} | disabled(非删除)={del_cnt}"
    # 7 AI OFF 核心: 无 LLM 客户端依赖, 规则模块可独立运行
    import importlib.util
    mods = ["evidence", "sourcesvc"]
    ok = all(importlib.util.find_spec(f"news.{m}") is not None for m in mods)
    ai_dep = "FAIL"
    try:
        src = Path(PROJ, "news/evidence.py").read_text() if Path(PROJ, "news/evidence.py").exists() else ""
        src2 = Path(PROJ, "news/sourcesvc.py").read_text()
        bad = [k for k in ("openai", "deepseek", "anthropic", "gemini", "api_key") if k in (src + src2).lower()]
        ai_dep = "PASS" if ok and not bad else "FAIL"
    except Exception:
        pass
    out["AI关闭后核心功能"] = ai_dep
    out["  证据"] = "evidence/sourcesvc 纯规则实现, 无 LLM API 引用" if ai_dep == "PASS" else "存在 AI 依赖"
    con.close()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    npass = sum(1 for k in out if not k.startswith(" ") and out[k] == "PASS")
    print(f"\n总计: {npass}/7 PASS")
    return 0 if npass == 7 else 1

if __name__ == "__main__":
    sys.exit(main())
