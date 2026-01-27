import os
import requests
import base64
import json
import urllib.parse
import time
import yaml # 需要 import yaml 处理 clash 格式

# ================= 配置 =================
GITHUB_TOKEN = os.environ.get("MY_GIT_TOKEN") 
GITHUB_REPO = os.environ.get("MY_REPO")
GITHUB_FILE_PATH = "sub.txt"

# 这里列出多个高质量的公开订阅源 (Direct Sources)
# 混合了 v2ray 格式和 clash 格式的源，脚本会自动处理
SUBSCRIPTION_SOURCES = [
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray",
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt",
    "https://raw.githubusercontent.com/pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2"
]
# =======================================

class NodeAggregator:
    def __init__(self):
        self.final_node_list = []
        self.headers = {"User-Agent": "Mozilla/5.0"}

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def safe_base64_decode(self, s):
        if not s: return ""
        s = s.strip()
        # 补全 padding
        missing_padding = 4 - len(s) % 4
        if missing_padding: s += '=' * missing_padding
        try:
            return base64.urlsafe_b64decode(s).decode('utf-8', errors='ignore')
        except:
            return ""

    def get_node_name(self, link):
        """尝试从链接中提取备注名称"""
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
        """筛选国家"""
        keywords = ["美国", "United States", " US ", "(US)", "[US]", "🇺🇸", 
                    "英国", "United Kingdom", " UK ", "(UK)", "[UK]", "🇬🇧",
                    "日本", "Japan", "🇯🇵", "新加坡", "Singapore", "🇸🇬",
                    "韩国", "Korea", "🇰🇷", "德国", "Germany", "🇩🇪"]
        if not name: return False # 如果没名字，先保留或丢弃？这里选择丢弃，为了质量
        for kw in keywords:
            if kw.lower() in name.lower():
                return True
        return False

    def fetch_and_parse(self):
        self.log(f"🚀 开始聚合 {len(SUBSCRIPTION_SOURCES)} 个订阅源...")
        
        for url in SUBSCRIPTION_SOURCES:
            self.log(f"🌐 正在抓取: {url} ...")
            try:
                resp = requests.get(url, headers=self.headers, timeout=15)
                if resp.status_code != 200:
                    self.log(f"   ⚠️ 失败: HTTP {resp.status_code}")
                    continue
                
                content = resp.text.strip()
                nodes_found = 0
                
                # 尝试解码 Base64 (V2Ray 标准格式)
                decoded = self.safe_base64_decode(content)
                
                # 如果解码失败，可能它是原文，或者是 Clash 格式
                raw_lines = []
                if decoded:
                    raw_lines = decoded.splitlines()
                else:
                    # 尝试直接按行读取（有些源直接返回 vmess://...）
                    raw_lines = content.splitlines()

                # 遍历每一行进行解析
                for line in raw_lines:
                    line = line.strip()
                    if not line: continue
                    
                    # 只处理 vmess/vless/trojan/ss 链接
                    if line.startswith(("vmess://", "vless://", "trojan://", "ss://")):
                        # 筛选国家
                        name = self.get_node_name(line)
                        if self.is_target_country(name):
                            self.final_node_list.append(line)
                            nodes_found += 1
                
                self.log(f"   ✅ 获取到 {nodes_found} 个有效节点")

            except Exception as e:
                self.log(f"   ❌ 出错: {e}")

        # 去重
        original_count = len(self.final_node_list)
        self.final_node_list = list(set(self.final_node_list))
        self.log(f"\n🎉 聚合完成！")
        self.log(f"   原始数量: {original_count}")
        self.log(f"   去重后数量: {len(self.final_node_list)}")
        
        return "\n".join(self.final_node_list) if self.final_node_list else None

    def upload_to_github(self, content):
        if not GITHUB_TOKEN or not GITHUB_REPO:
            self.log("❌ 错误: 环境变量未配置 (Token/Repo)")
            return

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        # 检查文件是否存在以获取 sha
        sha = None
        try:
            resp = requests.get(api_url, headers=headers)
            if resp.status_code == 200:
                sha = resp.json().get("sha")
        except: pass

        # 构造 Base64 内容
        # 注意：这里我们上传的是"Base64编码后的订阅内容"，因为订阅链接本身就是Base64格式的
        # 为了让 V2RayN 识别，通常还是再次 Base64 编码一下比较稳妥
        final_content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        # GitHub API 需要 Payload 也是 Base64
        upload_data_b64 = base64.b64encode(final_content_b64.encode("utf-8")).decode("utf-8")

        data = {
            "message": f"Auto update nodes {time.strftime('%Y-%m-%d %H:%M')}",
            "content": upload_data_b64, 
            "branch": "main"
        }
        if sha: data["sha"] = sha

        try:
            put_resp = requests.put(api_url, headers=headers, data=json.dumps(data))
            if put_resp.status_code in [200, 201]:
                self.log("✅ GitHub 仓库更新成功！")
            else:
                self.log(f"❌ 上传失败: {put_resp.status_code} - {put_resp.text}")
        except Exception as e:
            self.log(f"❌ 网络请求异常: {e}")

if __name__ == "__main__":
    aggregator = NodeAggregator()
    nodes = aggregator.fetch_and_parse()
    
    if nodes:
        aggregator.upload_to_github(nodes)
    else:
        print("⚠️ 未找到任何有效节点，跳过上传。")
