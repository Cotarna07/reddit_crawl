import os
import json
import time
import datetime
import praw

# ========== Reddit 凭证 ==========
reddit = praw.Reddit(
    client_id='Zr33iE9lsTMwy83gS7dJkg',
    client_secret='AbntaoukmjaBf0qR_zpW52fvvAjLLA',
    user_agent='python:chen musheng:v1.0 (by /u/CMS_Ducking)',
)

# ========== 配置 ==========
SUBREDDITS = ["memes"]     # 你想爬取的板块列表，可多个
LIMIT_PER_SUBREDDIT = 1000 # 希望获取多少条帖子（例如 1000）
LINKS_JSON = "links_store.json"  # 用于存储帖子链接状态的 JSON

# 在这里可以选择帖子排序方式：
# 1) "hot" => 热度排序
# 2) "top_all" => 按顶置(得分)在“所有时间”维度排序
SORT_MODE = "top_all"

def load_links_store():
    """加载 JSON 文件，返回一个列表，每个元素是 {'post_id', 'url', 'status', 'first_seen', ...}"""
    if not os.path.exists(LINKS_JSON):
        return []
    try:
        with open(LINKS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_links_store(data_list):
    """保存到 JSON 文件"""
    with open(LINKS_JSON, "w", encoding="utf-8") as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)

def fetch_subreddit_posts(subreddit_name, limit_num=1000, mode="top_all"):
    """
    根据 mode 获取指定数量的帖子链接和 ID。
    mode 可以是:
      - "hot":  按热度获取
      - "top_all": 按顶置(得分)获取，时间范围为 all
    返回 [{'post_id':..., 'url':..., 'title':..., ...}, ...]
    """
    sub = reddit.subreddit(subreddit_name)
    results = []

    if mode == "hot":
        submissions = sub.hot(limit=limit_num)
    elif mode == "top_all":
        # time_filter="all" => 获取所有时间维度的最高得分帖子
        submissions = sub.top(time_filter="all", limit=limit_num)
    else:
        raise ValueError(f"不支持的排序模式: {mode}")

    for submission in submissions:
        post_id = submission.id
        title = submission.title
        # 这里用 submission.permalink 拼出帖子在 Reddit 上的完整链接
        url = f"https://www.reddit.com{submission.permalink}"

        results.append({
            "post_id": post_id,
            "title": title,
            "url": url
        })

    return results

def main():
    # 1) 先加载现有链接仓库
    store_data = load_links_store()

    # 转成一个 dict 方便快速查重: post_id -> (dict 数据)
    store_dict = {item["post_id"]: item for item in store_data}

    # 2) 对每个 Subreddit 获取指定方式的帖子链接
    for sub_name in SUBREDDITS:
        print(f"[INFO] 正在获取 Subreddit: {sub_name}, 排序模式: {SORT_MODE}, limit={LIMIT_PER_SUBREDDIT}")
        new_posts = fetch_subreddit_posts(sub_name, LIMIT_PER_SUBREDDIT, SORT_MODE)

        # 3) 更新/合并到 store_dict
        for post in new_posts:
            pid = post["post_id"]
            if pid not in store_dict:
                store_dict[pid] = {
                    "post_id": pid,
                    "title": post["title"],
                    "url": post["url"],
                    "status": "new",  # 初始状态为 new
                    "first_seen": str(datetime.date.today()),  # 记录首次发现日期
                    "last_update": None  # 之后更新时再填
                }
    
        # 把每个板块抓完后，稍微休眠一会儿，避免请求过于频繁
        time.sleep(5)

    # 4) 把合并后的结果写回列表并保存
    updated_list = list(store_dict.values())
    save_links_store(updated_list)

    print(f"[DONE] 已更新链接存储，共计 {len(updated_list)} 条记录。")

if __name__ == "__main__":
    main()
