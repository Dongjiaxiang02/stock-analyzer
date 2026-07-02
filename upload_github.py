"""
GitHub 上传脚本 —— 创建仓库并推送
在你的终端里运行:  python upload_github.py
前提：先 export GH_TOKEN=你的token
"""
import os, sys, requests, subprocess

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    print("❌ 请先设置 token:  export GH_TOKEN=ghp_xxx")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
}

# 1. 获取用户名
r = requests.get("https://api.github.com/user", headers=headers)
if r.status_code != 200:
    print(f"❌ Token 无效: {r.status_code}")
    sys.exit(1)
user = r.json()["login"]
print(f"✅ 已认证: {user}")

# 2. 创建仓库
repo_name = "stock-analyzer"
r = requests.post(
    "https://api.github.com/user/repos",
    headers=headers,
    json={
        "name": repo_name,
        "description": "A股自动分析工具 | 自选股跟踪+热门板块筛选+K线均线MACD+HTML日报",
        "private": False,
    },
)

if r.status_code == 422:
    print(f"⚠️  仓库已存在，直接推送")
elif r.status_code == 201:
    print(f"✅ 仓库已创建: {r.json()['html_url']}")
else:
    print(f"❌ 创建失败: {r.status_code} {r.text[:200]}")
    sys.exit(1)

# 3. 配置 remote 并推送
repo_url = f"https://{user}:{TOKEN}@github.com/{user}/{repo_name}.git"

# 确保已初始化 git
if not os.path.exists(".git"):
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-m", "feat: 股票自动分析程序 v1.0"], check=True)

# 添加 remote（如果已存在则更新 URL）
result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True)
if result.returncode == 0:
    subprocess.run(["git", "remote", "set-url", "origin", repo_url], check=True)
else:
    subprocess.run(["git", "remote", "add", "origin", repo_url], check=True)

# 推送
print("📤 正在推送到 GitHub...")
subprocess.run(["git", "push", "-u", "origin", "master"], check=True)

print(f"\n✅ 完成！仓库地址: https://github.com/{user}/{repo_name}")
