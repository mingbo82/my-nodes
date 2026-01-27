import os
import re
import requests
import base64
import json
import urllib.parse
import time

# ================= 配置 =================
GITHUB_TOKEN = os.environ.get("MY_GIT_TOKEN") 
GITHUB_REPO = os.environ.get("MY_REPO")
GITHUB_FILE_PATH = "sub.txt"
TARGET_URL = "https://v2raya.net/free-nodes/free-v2ray-node-subscriptions.html"
# =======================================

class V2RayProxyScraper:
    def __init__(self):
        self.final_node_list = []
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

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

    def fetch_via_proxy(self, target_url):
        """尝试通过多个中间人服务获取内容"""
        # 方案1: Jina AI (通常最稳，把网页转为 Markdown)
        proxy_jina = f"https://r.jina.ai/{target_url}"
        # 方案2: CorsProxy (直接透传)
        proxy_cors = f"https://corsproxy.io/?{target_url}"
        
        proxies = [
            ("Jina AI", proxy_jina),
            ("CorsProxy", proxy_cors)
        ]

        for p_name, p_url in proxies:
            self.log(f"🔄 尝试通过 [{p_name}] 中转访问...")
            try:
                # Jina 需要特殊的 header 确保不缓存太久
                headers = self.headers.copy()
                if "jina.ai" in p_url:
                    headers["X-No-Cache"] = "true"
                    headers["X-With-Links-Summary"] = "true"

                resp = requests.get(p_url, headers=headers, timeout=20)
                if resp.status_code == 200 and len(resp.text) > 100:
                    self.log(f"✅ [{p_name}] 访问成功！")
                    return resp.text
                else:
                    self.log(f"⚠️ [{p_name}] 返回状态码 {resp.status_code} 或内容过短")
            except Exception as e:
                self.log(f"❌ [{p_name}] 连接错误: {str(e)[:50]}...")
        
        return None

    def run_scraping(self):
        self.log(f"🚀 开始任务，目标: {TARGET_URL}")
        
        # 1. 获取主页源码 (通过中间人)
        page_text = self.fetch_via_proxy(TARGET_URL)
        if not page_text:
            self.log("❌ 所有中间人代理均失败，无法获取主页。")
            return None

        # 2. 提取 sub 链接
        # 兼容 HTML 和 Markdown 格式的链接提取
        # 匹配 https://fn10... 直到遇到空格、引号或括号
        pattern = re.compile(r"(https://fn10[a-zA-Z0-9\.\/\-_]+)")
        sub_links = list(set(pattern.findall(page_text)))

        if not sub_links:
            self.log(f"❌ 未在页面中找到 fn10 开头的链接。")
            self.log(f"调试 - 页面前200字符: {page_text[:200]}")
            return None

        self.log(f"✅ 提取到 {len(sub_links)} 个订阅源链接，准备解析...")

        # 3. 遍历子链接获取节点
        for sub_url in sub_links:
            # 清理一下链接可能粘连的标点符号
            sub_url = sub_url.rstrip(').,]"')
            
            self.log(f"🌐 正在请求子链接: {sub_url} ...")
            
            # 同样使用中间人去下载子链接，防止直接请求被封
            content = self.fetch_via_proxy(sub_url)
            
            if content:
                # 尝试解码，有时候中间人会把内容包装在 JSON 里，或者直接返回文本
                # 先简单清洗
                if "Proxy" in content and "Error" in content:
                    continue

                decoded = self.safe_base64_decode(content)
                # 如果解码失败，且内容里包含 vmess://，说明已经是明文
                if not decoded and "vmess://" in content:
                    decoded = content
                
                if decoded:
                    lines = decoded.splitlines()
                    count = 0
                    for node in lines:
                        node = node.strip()
                        if not node: continue
                        if self.is_target_country(self.get_node_name(node)):
                            self.final_node_list.append(node)
                            count += 1
                    self.log(f"   -> 成功提取 {count} 个节点")
                else:
                    self.log("   -> 解析失败：Base64解码无效且非明文")

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
            resp = requests.get(api_url, headers=headers)
            if resp.status_code == 200:
                sha = resp.json().get("sha")
        except: pass

        # 再次 base64 编码以便 V2RayN 识别
        final_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        api_data = {
            "message": f"Update via Proxy {time.strftime('%Y-%m-%d')}",
            "content": base64.b64encode(final_b64.encode("utf-8")).decode("utf-8"),
            "branch": "main"
        }
        if sha: api_data["sha"] = sha

        resp = requests.put(api_url, headers=headers, data=json.dumps(api_data))
        if resp.status_code in [200, 201]:
            self.log("✅ GitHub 更新成功！")
        else:
            self.log(f"❌ 上传失败: {resp.text}")

if __name__ == "__main__":
    app = V2RayProxyScraper()
    nodes = app.run_scraping()
    if nodes:
        app.upload_to_github(nodes)
    else:
        print("⚠️ 未获取到节点，跳过上传。")
