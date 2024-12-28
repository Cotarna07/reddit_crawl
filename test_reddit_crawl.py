import requests
import json

# Reddit 帖子的 URL（.json 格式）
post_url = "https://www.reddit.com/r/meme/comments/1h1a3sf/why_is_that_guy_a_meme_anyway_im_confused/.json"

# 设置 User-Agent（必须设置）
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# 发送 GET 请求获取 JSON 数据
response = requests.get(post_url, headers=headers)

# 如果请求成功，处理数据
if response.status_code == 200:
    post_data = response.json()

    # 提取帖子信息
    post = post_data[0]['data']['children'][0]['data']
    post_info = {
        "title": post['title'],
        "score": post['score'],  # 帖子的点赞数
        "url": post['url'],
        "author": post['author'],
        "created_utc": post['created_utc'],  # 创建时间
        "content": post['selftext'],
        "num_comments": post['num_comments'],  # 评论数
        "comments": []  # 存储评论及其层级关系
    }

    # 递归提取评论和回复的函数
    def extract_comments(comments_data):
        comments = []
        for comment in comments_data:
            comment_data = {
                "author": comment['data']['author'],
                "body": comment['data']['body'],
                "created_utc": comment['data']['created_utc'],
                "score": comment['data']['score'],  # 评论的点赞数
                "replies": []  # 存储回复
            }

            # 如果有回复，递归调用 extract_comments
            if isinstance(comment['data'].get('replies'), dict):
                comment_data['replies'] = extract_comments(comment['data']['replies']['data']['children'])

            comments.append(comment_data)

        return comments

    # 提取评论和回复
    comments = post_data[1]['data']['children']
    post_info["comments"] = extract_comments(comments)

    # 保存为 JSON 文件
    with open('reddit_post_data_all_comments_pretty.json', 'w', encoding='utf-8') as f:
        json.dump(post_info, f, ensure_ascii=False, indent=4)

    print("Reddit 数据已保存为 'reddit_post_data_all_comments_pretty.json'")

else:
    print(f"请求失败，状态码: {response.status_code}")
