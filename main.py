import os
import re
import requests
import base64
import json
import urllib.parse
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ================= 配置 =================
# 注意：Token 现在从环境变量读取，不要在这里写死
GITHUB_TOKEN = os.environ.get("MY_GIT_TOKEN") 
GITHUB_REPO = os.environ.get("MY_REPO")  # 格式: 用户名/仓库名
GITHUB_FILE_PATH = "sub.txt"
TARGET_URL = "https://v2raya.net/free-nodes/free-v2ray-node-subscriptions.html"
# =======================================

class V2RayScraperAction:
    def __init__(self):
        self.final_node_list = []

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    # ... (辅助函数保持不变: safe_base64_decode, get_node_name, is_target_country) ...
    def safe_base64_decode(self, s):
        if not s: return ""
        s = s.strip()
        missing_padding = 4 - len(s) % 4
        if missing_padding: s += '=' * missing_padding
        try:
            return base64.urlsafe_b64decode(s).decode('utf-8', errors='ignore')
        except:
            return ""

    def get_node_name(self, link):
        name = ""
        try:
            if link.startswith("vmess://"):
                b64_str = link.replace("vmess://", "")
                json_str = self.safe_base64_decode(b64_str)
                if json_str:
                    data = json.loads(json_str)
                    name = data.get("ps", "")
            elif "://" in link:
                parsed = urllib.parse.urlparse(link)
                name = urllib.parse.unquote(parsed.fragment)
        except:
            pass
        return name

    def is_target_country(self, name):
        keywords = ["美国", "United States", " US ", "(US)", "[US]", "🇺🇸", 
                    "英国", "United Kingdom", " UK ", "(UK)", "[UK]", "🇬🇧",
                    "日本", "Japan", "🇯🇵", "新加坡", "Singapore", "🇸🇬"]
        if not name: return False
        for kw in keywords:
            if kw.lower() in name.lower():
                return True
        return False

    def run_scraping(self):
        self.log(f"🚀 开始访问: {TARGET_URL}")

        chrome_options = Options()
        # 服务器环境必备参数
        chrome_options.add_argument("--headless") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        driver = None
        try:
            # 使用 webdriver_manager 自动安装匹配的驱动
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(TARGET_URL)
            time.sleep(10)
            page_text = driver.page_source
        except Exception as e:
            self.log(f"❌ Selenium Error: {e}")
            if driver: driver.quit()
            return None
        finally:
            if driver: driver.quit()

        pattern = re.compile(r"https://fn10[^\s\"'<]+")
        sub_links = list(set(pattern.findall(page_text)))

        if not sub_links:
            self.log("❌ 未找到链接")
            return None

        self.log(f"✅ 找到 {len(sub_links)} 个订阅源")

        headers = {"User-Agent": "Mozilla/5.0"}
        for sub_url in sub_links:
            try:
                resp = requests.get(sub_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    content = resp.text.strip()
                    decoded = self.safe_base64_decode(content) or content
                    lines = decoded.splitlines()
                    for node in lines:
                        if self.is_target_country(self.get_node_name(node)):
                            self.final_node_list.append(node)
            except:
                pass

        self.final_node_list = list(set(self.final_node_list))
        self.log(f"🎉 筛选出 {len(self.final_node_list)} 个节点")
        return "\n".join(self.final_node_list) if self.final_node_list else None

    def upload_to_github(self, content):
        if not GITHUB_TOKEN or not GITHUB_REPO:
            self.log("❌ 未配置 Token 或 Repo 信息")
            return

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

        sha = None
        try:
            resp = requests.get(api_url, headers=headers)
            if resp.status_code == 200:
                sha = resp.json().get("sha")
        except: pass

        b64_content = base64.b64encode(base64.b64encode(content.encode("utf-8"))).decode("utf-8")
        data = {
            "message": f"Auto update {time.strftime('%m-%d %H:%M')}",
            "content": b64_content,
            "branch": "main"
        }
        if sha: data["sha"] = sha

        resp = requests.put(api_url, headers=headers, data=json.dumps(data))
        if resp.status_code in [200, 201]:
            self.log("✅ GitHub 更新成功")
        else:
            self.log(f"❌ 更新失败: {resp.text}")

if __name__ == "__main__":
    app = V2RayScraperAction()
    nodes = app.run_scraping()
    if nodes:
        app.upload_to_github(nodes)