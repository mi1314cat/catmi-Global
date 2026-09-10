#!/usr/bin/env python3
"""secret_scan.py — 凭据入库扫描 (P0-S11 复发防护, CI/pre-commit 用)
扫描已跟踪文件中的密钥模式; 命中即退出码 1。"""
import os, re, subprocess, sys
PATTERNS = [
    (r"github_pat_[A-Za-z0-9_]{20,}", "GitHub PAT"),
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub token"),
    (r"AKIA[0-9A-Z]{16}", "AWS key"),
    (r"sk-[A-Za-z0-9]{20,}", "API key (sk-)"),
    (r"Bearer [A-Fa-f0-9]{40,}", "Bearer hex token"),
    (r'"password"\s*:\s*"[^"\s]{8,}"', "hardcoded password in JSON"),
    (r"(?i)mcp_token\s*=\s*['\"][A-Fa-f0-9]{32,}", "MCP token literal"),
]
files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
hits = 0
for f in files:
    if f.endswith((".png", ".jpg", ".gz", ".db")): continue
    try: text = open(f, encoding="utf-8", errors="ignore").read()
    except Exception: continue
    for pat, label in PATTERNS:
        for m in re.finditer(pat, text):
            line = text[:m.start()].count("\n") + 1
            print(f"HIT {label}: {f}:{line} (掩码: {m.group(0)[:8]}...)")
            hits += 1
print(f"\n== secret_scan: {hits} 命中 ==")
sys.exit(1 if hits else 0)
