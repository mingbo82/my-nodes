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
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# ================= 配置 =================
GITHUB_TOKEN = os.environ.get("MY_GIT_TOKEN") 
GITHUB_REPO = os.environ.get("MY_REPO")
GITHUB_FILE_PATH = "sub.txt"
# 备用 URL：如果主 URL 挂了，可以加其他的，这里暂时只用一个
TARGET_URL = "https://v2raya.net/free-nodes/free-v2ray-node-subscriptions.html"
# =======================================

class V2RayScraperAction:
    def __init__(self):
        self.final_node_list = []

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
        # --- 关键修改：增加伪装和优化加载策略 ---
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        # 1. 忽略证书错误
        chrome_options.add_argument("--ignore-certificate-errors")
        # 2. 只有当 DOM 加载完成就继续，不等待图片和样式
        chrome_options.page_load_strategy = 'eager' 
        # 3. 伪装 User-Agent，防止被识别为无头浏览器
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        # 4. 隐藏 Selenium 特征
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        driver = None
        page_text = ""
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # 设置加载超时时间为 30 秒（原代码是无限等，导致卡死）
            driver.set_page_load_timeout(30)
            
            try:
                driver.get(TARGET_URL)
            except TimeoutException:
                self.log("⚠️ 页面加载超时，但这可能不影响结果，尝试强制读取已加载内容...")
                # 超时后停止加载，直接读取当前已有的 HTML
                driver.execute_script("window.stop();")
            
            # 稍微等一下 JS 渲染
            time.sleep(5)
            page_text = driver.page_source
            
        except Exception as e:
            self.log(f"❌ 浏览器严重错误: {e}")
            if driver: driver.quit()
            return None
        finally:
            if driver: driver.quit()

        if not page_text:
            self.log("❌ 未获取到网页内容")
            return None

        # 正则提取 fn10 开头的链接
        pattern = re.compile(r"https://fn10[^\s\"'<]+")
        sub_links = list(set(pattern.findall(page_text)))

        if not sub_links:
            self.log(f"❌ 未找到链接 (页面源码长度: {len(page_text)})")
            # 调试：有时候可能被 Cloudflare 拦截显示了验证码页面
            if "Cloudflare" in page_text:
                self.log("⚠️ 检测到 Cloudflare 拦截")
            return None

        self.log(f"✅ 找到 {len(sub_links)} 个订阅源，开始解析...")

        headers = {"User-Agent": "Mozilla/5.0"}
        for sub_url in sub_links:
            try:
                # 订阅链接通常响应快，给 10秒 超时即可
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

        # 去重
        self.final_node_list = list(set(self.final_node_list))
        self.log(f"🎉 筛选出 {len(self.final_node_list)} 个节点")
        return "\n".join(self.final_node_list) if self.final_node_list else None

    def upload_to_github(self, content):
        if not GITHUB_TOKEN or not GITHUB_REPO:
            self.log("❌ 未配置 Token 或 Repo 信息 (环境变量缺失)")
            return

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

        sha = None
        try:
            resp = requests.get(api_url, headers=headers)
            if resp.status_code == 200:
                sha = resp.json().get("sha")
        except: pass

        # 这里做一个双重 Base64 只是为了符合某些订阅格式习惯，或者直接原文上传
        # GitHub API 要求 content 字段必须是 base64 编码的
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        data = {
            "message": f"Auto update {time.strftime('%m-%d %H:%M')}",
            "content": content_b64,
            "branch": "main"
        }
        if sha: data["sha"] = sha

        resp = requests.put(api_url, headers=headers, data=json.dumps(data))
        if resp.status_code in [200, 201]:
            self.log("✅ GitHub 更新成功")
        else:
            self.log(f"❌ GitHub API 报错: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    app = V2RayScraperAction()
    nodes = app.run_scraping()
    if nodes:
        app.upload_to_github(nodes)
    else:
        print("⚠️ 本次没有抓取到节点，跳过上传。")
