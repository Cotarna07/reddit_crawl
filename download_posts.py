import os
import re
import json
import time
import datetime
import requests
import praw
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm  # 需要 pip install tqdm

# ========== Reddit 凭证 ==========
reddit = praw.Reddit(
    client_id='Zr33iE9lsTMwy83gS7dJkg',
    client_secret='AbntaoukmjaBf0qR_zpW52fvvAjLLA',
    user_agent='python:chen musheng:v1.0 (by /u/CMS_Ducking)',
)

# ========== 常量配置 ==========
LINKS_JSON = "links_store.json"    # 从这里读取要下载的帖子列表
OUTPUT_ROOT = "downloaded_posts"   # 在此目录下，为每个subreddit创建子目录，再在其中按post_id存放
MAX_WORKERS = 5                    # 并发下载媒体的线程数

# ========== 1. 加载/保存链接列表 ==========

def load_links_store():
    """从 links_store.json 加载帖子记录"""
    if not os.path.exists(LINKS_JSON):
        return []
    try:
        with open(LINKS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_links_store(data_list):
    """将更新后的帖子信息写回 links_store.json"""
    with open(LINKS_JSON, "w", encoding="utf-8") as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)


# ========== 2. 提取媒体链接相关函数 ==========

def extract_media_links(text):
    """
    从评论文本中识别各种媒体链接（普通图片、gifv、giphy）。
    可根据实际需求扩充/修改。
    """
    media_links = []
    # 常见图片 (jpg、png、gif)，只匹配 reddit 域名的情况:
    pattern_img = r'(https?://(?:i\.redd\.it|v\.redd\.it|[\w\.]*reddit\.com)/[^\s]+(?:\.jpg|\.png|\.gif))'
    media_links.extend(re.findall(pattern_img, text))

    # gifv
    pattern_gifv = r'(https?://[^\s]+\.gifv)'
    media_links.extend(re.findall(pattern_gifv, text))

    # giphy => 形如 "giphy|xxxx"
    pattern_giphy = r'(giphy\|[a-zA-Z0-9]+)'
    media_links.extend(re.findall(pattern_giphy, text))

    return media_links


# ========== 3. 媒体下载函数 + 主贴下载判定 ==========

downloaded_links = set()  # 记录已下载过的链接，避免重复

def download_file(url, local_path):
    """
    真正的下载逻辑，带简单重复判断及异常处理。
    """
    try:
        if url in downloaded_links:
            return None  # 已下载过
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(url, stream=True, headers=headers, timeout=10) as r:
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        downloaded_links.add(url)
        print(f"[INFO] 下载完成: {local_path}")
        return local_path
    except Exception as e:
        print(f"[ERROR] 下载失败: {url} => {e}")
        return None

def download_image(url, folder):
    """下载普通图片 (jpg, png, gif)"""
    filename = os.path.basename(urlparse(url).path)
    local_path = os.path.join(folder, filename)
    return download_file(url, local_path)

def download_gifv(url, folder):
    """下载 Reddit GIF 动图 (gifv -> mp4)"""
    video_url = url.replace('.gifv', '.mp4')
    filename = os.path.basename(urlparse(video_url).path)
    local_path = os.path.join(folder, filename)
    return download_file(video_url, local_path)

def download_giphy(giphy_str, folder):
    """下载 Giphy 动图 (giphy|<gif_id>)"""
    _, gif_id = giphy_str.split('|', 1)
    gif_url = f"https://media.giphy.com/media/{gif_id}/giphy.gif"
    filename = f"{gif_id}.gif"
    local_path = os.path.join(folder, filename)
    return download_file(gif_url, local_path)

def download_all_media(media_links, folder):
    """
    并发下载一组媒体链接到指定 folder 目录。返回 {url: local_path 或 None}
    """
    results = {}
    os.makedirs(folder, exist_ok=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {}
        for url in media_links:
            if url.endswith('.gifv'):
                future = executor.submit(download_gifv, url, folder)
            elif url.startswith('giphy|'):
                future = executor.submit(download_giphy, url, folder)
            else:
                future = executor.submit(download_image, url, folder)
            future_to_url[future] = url

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                filepath = future.result()
                results[url] = filepath
            except Exception as e:
                print(f"[ERROR] 并发下载出错: {url} => {e}")
                results[url] = None

    return results

def maybe_download_main_media(submission, folder):
    """
    如果主贴 url 是可下载的图片或动图，则将其下载到 folder。
    返回下载后的本地路径 or None。
    """
    url = submission.url
    # 基于后缀简单判断
    if url.endswith(('.jpg', '.png', '.gif')):
        return download_image(url, folder)
    elif url.endswith('.gifv'):
        return download_gifv(url, folder)
    # 若需要处理更多形式，如 mp4、giphy、imgur 等，可自行扩展
    return None


# ========== 4. 递归遍历评论，构建评论数据结构 ==========

def traverse_comments(comment, comments_data, level=0, parent_author=None):
    author_name = str(comment.author) if comment.author else "[deleted]"
    body_text = comment.body
    ups = comment.ups
    media_links = extract_media_links(body_text)

    comments_data.append({
        "level": level,
        "author": author_name,
        "ups": ups,
        "body": body_text,
        "parent_author": parent_author,
        "media_links": media_links
    })

    for reply in comment.replies:
        if isinstance(reply, praw.models.MoreComments):
            continue
        traverse_comments(reply, comments_data, level+1, author_name)


# ========== 5. 下载一个帖子的全部内容到本地 ==========

def download_post_content(post_info):
    """
    给定一条 {'post_id', 'url', 'status', ...} 数据，
    通过 PRAW 获取帖子主体 + 所有评论，并将其写到 Markdown。
    同时下载评论里的媒体文件；
    以 "downloaded_posts/<subreddit_name>/<post_id>/" 为基础路径存放。
    还会检查主贴是否是可下载的图片/动图，并下载。
    """
    post_id = post_info["post_id"]
    url = post_info["url"]

    # 1) 用submission拿到帖子
    submission = reddit.submission(url=url)
    submission.comments.replace_more(limit=None)  # 展开更多评论

    # 获取所属板块名（形如 'memes'）
    subreddit_name = str(submission.subreddit.display_name)

    # 2) 为该帖子创建目录: downloaded_posts/<subreddit>/<post_id>/
    post_folder = os.path.join(OUTPUT_ROOT, subreddit_name, post_id)
    os.makedirs(post_folder, exist_ok=True)

    # 准备存放媒体的子目录
    media_folder = os.path.join(post_folder, "media_files")
    os.makedirs(media_folder, exist_ok=True)

    # 3) 先下载主贴中的图片/动图（如果能）
    main_media_path = maybe_download_main_media(submission, media_folder)

    # 4) 获取评论并构建数据
    all_comments = submission.comments.list()
    comments_data = []
    for c in all_comments:
        if isinstance(c, praw.models.MoreComments):
            continue
        traverse_comments(c, comments_data, level=0, parent_author=None)

    # 5) 收集所有评论媒体链接并并发下载
    all_links = set()
    for item in comments_data:
        for m_link in item["media_links"]:
            all_links.add(m_link)

    download_map = download_all_media(list(all_links), media_folder)

    # 6) 写帖子内容到 Markdown
    md_file_path = os.path.join(post_folder, f"{post_id}.md")
    with open(md_file_path, "w", encoding="utf-8") as f:
        # 帖子头部信息
        f.write(f"# Reddit Post - {submission.title}\n\n")
        f.write(f"- **Subreddit**: r/{subreddit_name}\n")
        f.write(f"- **Author**: {submission.author}\n")
        f.write(f"- **Ups**: {submission.ups}\n")
        f.write(f"- **URL**: {url}\n\n")
        if submission.selftext:
            f.write(f"**Body**:\n{submission.selftext}\n\n")

        # 如果主贴的图片/动图已下载成功，则插入到 MD
        if main_media_path:
            rel_main_path = os.path.relpath(main_media_path, post_folder).replace("\\", "/")
            f.write(f"**Main Media**:\n")
            f.write(f"![main_media]({rel_main_path})\n\n")

        f.write("---\n\n")
        f.write("## Comments:\n\n")

        # 写评论
        for item in comments_data:
            prefix = "  " * item["level"]
            author = item["author"]
            ups = item["ups"]
            body = item["body"]
            p_author = item["parent_author"]
            m_links = item["media_links"]

            if p_author:
                line = f"{prefix}↳ **{author}** 回复 {p_author} (👍 {ups}): {body}\n"
            else:
                line = f"{prefix}**{author}** (👍 {ups}): {body}\n"

            # 插入对应媒体
            for link in m_links:
                local_path = download_map.get(link)
                if local_path:
                    local_path_fixed = local_path.replace("\\", "/")
                    rel_path = os.path.relpath(local_path_fixed, post_folder).replace("\\", "/")
                    line += f"{prefix}  ![media]({rel_path})\n"

            f.write(line + "\n")

    print(f"[INFO] 帖子 {post_id} ({submission.title}) 下载完成 => {md_file_path}")


# ========== 6. 主流程：读取JSON，下载 "new" 帖子 + 进度条 ==========

def main():
    data_list = load_links_store()
    # 先筛选出所有 status=="new" 的帖子
    new_items = [item for item in data_list if item.get("status") == "new"]
    total_new = len(new_items)

    if total_new == 0:
        print("[INFO] 没有需要下载的帖子。")
        return

    print(f"[INFO] 准备下载 {total_new} 个帖子...")

    # 用 tqdm 显示帖子级的下载进度条
    for item in tqdm(new_items, desc="Downloading posts", total=total_new):
        try:
            download_post_content(item)
            # 下载完成后，更新状态
            item["status"] = "downloaded"
            item["last_update"] = str(datetime.date.today())
        except Exception as e:
            print(f"[ERROR] 下载帖子失败: {item['post_id']} => {e}")

        # 为了避免过度请求，对每个帖子稍作延时
        time.sleep(2)

    # 保存更新后的状态
    save_links_store(data_list)
    print(f"\n[DONE] 已下载帖子数: {total_new}")


if __name__ == "__main__":
    main()
