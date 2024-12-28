import os
import re
import requests
import praw
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# -----------------------
# 1. Reddit 客户端初始化
# -----------------------
reddit = praw.Reddit(
    client_id='Zr33iE9lsTMwy83gS7dJkg',
    client_secret='AbntaoukmjaBf0qR_zpW52fvvAjLLA',
    user_agent='python:chen musheng:v1.0 (by /u/CMS_Ducking)',
)

# 目标帖子链接
post_url = 'https://www.reddit.com/r/memes/comments/ig9u4z/she_did_her_best_ok/'
post = reddit.submission(url=post_url)

# 创建保存媒体文件的文件夹
media_dir = 'media_files'
os.makedirs(media_dir, exist_ok=True)

# 获取帖子评论
post.comments.replace_more(limit=None)
comments = post.comments.list()

# 用于避免重复下载
downloaded_links = set()

# Markdown 文件名
markdown_file = "reddit_comments.md"


# -----------------------
# 2. 下载函数：使用正斜杠
# -----------------------
def download_file(url, local_path):
    """真正的下载逻辑，可被其他函数复用"""
    try:
        # 若已下载过则跳过
        if url in downloaded_links:
            return None
        
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


def download_image(url):
    """普通图片 (jpg, png, gif)"""
    filename = os.path.basename(urlparse(url).path)
    local_path = os.path.join(media_dir, filename)
    return download_file(url, local_path)


def download_gifv(url):
    """下载 Reddit GIF 动图 (gifv -> mp4)"""
    # 简化处理：直接把 .gifv 替换成 .mp4
    video_url = url.replace('.gifv', '.mp4')
    filename = os.path.basename(urlparse(video_url).path)
    local_path = os.path.join(media_dir, filename)
    return download_file(video_url, local_path)


def download_giphy(giphy_str):
    """下载 Giphy 动图 (giphy|<gif_id>)"""
    _, gif_id = giphy_str.split('|', 1)
    gif_url = f"https://media.giphy.com/media/{gif_id}/giphy.gif"
    filename = f"{gif_id}.gif"
    local_path = os.path.join(media_dir, filename)
    return download_file(gif_url, local_path)


# -----------------------
# 3. 提取媒体链接
# -----------------------
def extract_media_links(comment_body):
    """提取评论中的媒体链接"""
    media_links = []
    # 匹配常见图片 (jpg、png、gif)
    pattern_img = r'(https?://(?:i\.redd\.it|v\.redd\.it|[\w\.]*reddit\.com)/[^\s]+(?:\.jpg|\.png|\.gif))'
    media_links.extend(re.findall(pattern_img, comment_body))

    # gifv
    pattern_gifv = r'(https?://[^\s]+\.gifv)'
    media_links.extend(re.findall(pattern_gifv, comment_body))

    # giphy
    pattern_giphy = r'(giphy\|[a-zA-Z0-9]+)'
    media_links.extend(re.findall(pattern_giphy, comment_body))

    return media_links


# -----------------------
# 4. 并发下载
# -----------------------
def download_all_media(media_links):
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {}
        for url in media_links:
            if url.endswith('.gifv'):
                future = executor.submit(download_gifv, url)
            elif url.startswith('giphy|'):
                future = executor.submit(download_giphy, url)
            else:
                future = executor.submit(download_image, url)

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


# -----------------------
# 5. 递归遍历评论
# -----------------------
comments_data = []

def traverse_comments(comment, level=0, parent_author=None):
    author_name = str(comment.author) if comment.author else "[deleted]"
    body_text = comment.body
    links = extract_media_links(body_text)

    comments_data.append({
        "level": level,
        "author": author_name,
        "ups": comment.ups,
        "body": body_text,
        "parent_author": parent_author,
        "media_links": links,
    })

    # 处理子评论
    for reply in comment.replies:
        if isinstance(reply, praw.models.MoreComments):
            continue
        traverse_comments(reply, level + 1, author_name)


# -----------------------
# 6. 主逻辑
# -----------------------
def main():
    print(f"帖子标题: {post.title}")
    print("-" * 40)

    # 构建评论数据
    for c in comments:
        if isinstance(c, praw.models.MoreComments):
            continue
        traverse_comments(c)

    # 收集所有媒体链接，去重
    all_media_links = set()
    for item in comments_data:
        for l in item["media_links"]:
            all_media_links.add(l)

    # 批量下载
    download_results = download_all_media(list(all_media_links))

    # 写入 Markdown
    with open(markdown_file, 'w', encoding='utf-8') as f:
        f.write(f"# Reddit Post: {post.title}\n\n")
        f.write("## Comments:\n\n")

        for item in comments_data:
            level = item["level"]
            prefix = "  " * level
            author = item["author"]
            ups = item["ups"]
            body = item["body"]
            parent = item["parent_author"]
            media_links = item["media_links"]

            if parent:
                comment_line = f"{prefix}↳ **{author}** 回复 {parent} (👍 {ups}): {body}\n"
            else:
                comment_line = f"{prefix}**{author}** (👍 {ups}): {body}\n"

            # 写完评论正文后，插入媒体
            for m_link in media_links:
                local_path = download_results.get(m_link)
                if local_path:
                    # 注意：这里把 Windows 的反斜杠都替换成正斜杠
                    local_path_fixed = local_path.replace("\\", "/")
                    comment_line += f"{prefix}  ![media]({local_path_fixed})\n"

            f.write(comment_line + "\n")

    print(f"[DONE] 评论和媒体已保存到 {markdown_file}")


if __name__ == "__main__":
    main()
