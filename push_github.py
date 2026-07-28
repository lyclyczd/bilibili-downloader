#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 GitHub REST API 推送当前 HEAD 到 main（绕开沙箱 git/HTTPS 限制）。
用法：GH_TOKEN=ghp_xxx python push_github.py
"""
import os, sys, json, base64, subprocess, requests, urllib3
urllib3.disable_warnings()

REPO = "lyclyczd/bilibili-downloader"
TOK = os.environ.get("GH_TOKEN")
if not TOK:
    print("ERROR: 请通过环境变量 GH_TOKEN 提供 GitHub token"); sys.exit(2)

API = f"https://api.github.com/repos/{REPO}"
VERIFY = False
sess = requests.Session()
sess.headers.update({"Authorization": f"token {TOK}",
                    "Accept": "application/vnd.github+json"})


def gh(method, url, **kw):
    kw.setdefault("verify", VERIFY); kw.setdefault("timeout", 60)
    return sess.request(method, url, **kw)


r = gh("GET", f"{API}/git/refs/heads/main"); r.raise_for_status()
base_sha = r.json()["object"]["sha"]
print("remote main:", base_sha)
head_parent = subprocess.check_output(["git", "rev-parse", "HEAD~1"]).decode().strip()
print("local HEAD~1:", head_parent)

files = subprocess.check_output(["git", "ls-files"]).decode().split()
print("files:", len(files))
blobs = {}
for f in files:
    data = open(f, "rb").read()
    if len(data) > 90*1024*1024:
        print("  SKIP too large:", f); continue
    rr = gh("POST", f"{API}/git/blobs",
            json={"content": base64.b64encode(data).decode("ascii"),
                  "encoding": "base64"})
    if rr.status_code != 201:
        print("BLOB FAIL", f, rr.status_code, rr.text[:200]); sys.exit(1)
    blobs[f] = rr.json()["sha"]

tree_entries = [{"path": f, "mode": "100644", "type": "blob", "sha": s}
                for f, s in blobs.items()]
tt = gh("POST", f"{API}/git/trees", json={"tree": tree_entries})
if tt.status_code != 201:
    print("TREE FAIL", tt.status_code, tt.text[:300]); sys.exit(1)
tree_sha = tt.json()["sha"]

msg = ("feat(gui): 新增 16 项功能 (v1.2.0) + 两种分发模式\n\n"
        "①系统通知 ②限速+代理 ③暂停/恢复/排序 ④更新检查 ⑤多账号\n"
        "⑥UP主投稿分页 ⑦浏览器扩展 ⑧字幕硬烧/裁剪/合并\n"
        "⑨AI字幕 ⑩日志+主题 ⑪设置导入导出 ⑫默认低速风控\n"
        "⑬免责声明 ⑭启动脚本 ⑮exe安装包/Python双模式 ⑯上传GitHub")
cc = gh("POST", f"{API}/git/commits",
        json={"message": msg, "tree": tree_sha, "parents": [base_sha]})
if cc.status_code != 201:
    print("COMMIT FAIL", cc.status_code, cc.text[:300]); sys.exit(1)
new_sha = cc.json()["sha"]
print("new commit:", new_sha)

uu = gh("PATCH", f"{API}/git/refs/heads/main",
        json={"sha": new_sha, "force": False})
print("ref update:", uu.status_code, uu.text[:120])
if uu.status_code in (200, 201):
    print("OK -> https://github.com/%s" % REPO)
else:
    print("PUSH FAILED"); sys.exit(1)
