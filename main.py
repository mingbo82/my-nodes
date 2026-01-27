import os
import re
import base64
import json
import urllib.parse
import time
from curl_cffi import requests # 引入伪装库

# ================= 配置 =================
GITHUB_TOKEN = os.environ.get("MY_GIT_TOKEN") 
GITHUB_REPO = os.environ.get("MY_REPO")
GITHUB_FILE_PATH = "sub.txt"
# 你的目标地址
TARGET_URL = "https://v2raya.net/free-nodes/free-v2ray-node-subscriptions.html"
# =======================================

class V2RayScraperStealth:
    def __init__(self):
        self.final_node_list = []
        # 使用 curl_cffi 的 Session，模拟 Chrome 110
        self.session = requests.Session()

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

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
                    "英国", "United Kingdom", " UK ", "(UK)", "[UK]", "🇬🇧"]
        if not name: return False
        for kw in keywords:
            if kw.lower() in name.lower():
                return True
        return False

    def fetch_url_content(self, url):
        """使用伪装指纹下载内容"""
        try:
            # impersonate="chrome110" 是核心，它模拟了真实浏览器的握手
            response = self.session.get(url, impersonate="chrome110", timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                self.log(f"⚠️ 访问失败 [{response.status_code}]: {url}")
                return None
        except Exception as e:
            self.log(f"❌ 请求异常: {e}")
            return None

    def run_scraping(self):
        self.log(f"🚀 开始隐身访问: {TARGET_URL}")
        
        # 1. 获取主页源码
        page_text = self.fetch_url_content(TARGET_URL)
        if not page_text:
            return None

        # 2. 提取 sub 链接 (正则匹配 fn10 开头的链接)
        pattern = re.compile(r"https://fn10[^\s\"'<]+")
        sub_links = list(set(pattern.findall(page_text)))

        if not sub_links:
            self.log(f"❌ 未找到订阅子链接，可能是页面结构变更或反爬升级。")
            # 调试：打印前500个字符看看是什么
            self.log(f"页面预览: {page_text[:200]}")
            return None

        self.log(f"✅ 成功绕过防火墙，找到 {len(sub_links)} 个订阅源")

        # 3. 遍历子链接获取节点
        for sub_url in sub_links:
            self.log(f"🌐 解析子链接: {sub_url} ...")
            content = self.fetch_url_content(sub_url)
            if content:
                decoded = self.safe_base64_decode(content) or content
                lines = decoded.splitlines()
                count = 0
                for node in lines:
                    node = node.strip()
                    if not node: continue
                    if self.is_target_country(self.get_node_name(node)):
                        self.final_node_list.append(node)
                        count += 1
                self.log(f"   -> 提取到 {count} 个目标节点")

        # 去重
        self.final_node_list = list(set(self.final_node_list))
        self.log(f"🎉 最终获取 {len(self.final_node_list)} 个节点")
        
        return "\n".join(self.final_node_list) if self.final_node_list else None

    def upload_to_github(self, content):
        if not GITHUB_TOKEN or not GITHUB_REPO:
            self.log("❌ Token/Repo 未配置")
            return

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

        sha = None
        try:
            resp = requests.get(api_url, headers=headers) # 使用普通 requests 或 curl_cffi 都可以
            if resp.status_code == 200:
                sha = resp.json().get("sha")
        except: pass

        # 再次 base64 编码以便 V2RayN 识别
        final_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        # GitHub API payload
        api_data = {
            "message": f"Update from v2raya {time.strftime('%Y-%m-%d')}",
            "content": base64.b64encode(final_b64.encode("utf-8")).decode("utf-8"),
            "branch": "main"
        }
        if sha: api_data["sha"] = sha

        # 上传请求不用伪装，直接用 requests 即可 (这里复用 session)
        resp = self.session.put(api_url, headers=headers, data=json.dumps(api_data))
        if resp.status_code in [200, 201]:
            self.log("✅ GitHub 更新成功！")
        else:
            self.log(f"❌ 上传失败: {resp.text}")

if __name__ == "__main__":
    app = V2RayScraperStealth()
    nodes = app.run_scraping()
    if nodes:
        app.upload_to_github(nodes)
    else:
        print("⚠️ 未获取到节点，跳过上传。")
