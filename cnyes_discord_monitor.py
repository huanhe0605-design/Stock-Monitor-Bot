import requests
import json
import time
import os
import re
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
NIM_API_KEY = os.getenv("GROQ_API_KEY")
NEWS_TRACKING_FILE = 'tracked_news.json'
MAX_TRACKED_NEWS = 500

def load_tracked_news():
    if os.path.exists(NEWS_TRACKING_FILE):
        try:
            with open(NEWS_TRACKING_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_tracked_news(tracked_news):
    if len(tracked_news) > MAX_TRACKED_NEWS:
        tracked_news = tracked_news[-MAX_TRACKED_NEWS:]
    with open(NEWS_TRACKING_FILE, 'w') as f:
        json.dump(tracked_news, f)

def get_cnyes_news():
    url = 'https://api.cnyes.com/media/api/v1/newslist/category/headline?limit=5'
    for attempt in range(3):
        try:
            response = requests.get(url, verify=False, timeout=10)
            data = response.json()
            return data['items']['data']
        except Exception as e:
            print(f"⚠️ 鉅亨網連線異常，3秒後進行第 {attempt + 2} 次重試... ({e})", flush=True)
            time.sleep(3)
    return []

def get_jinshi_news():
    url = 'https://rsshub.rssforever.com/jinshi/flash'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    items = []
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            text = response.text
            item_blocks = re.findall(r'<item>(.*?)</item>', text, re.DOTALL)
            
            for block in item_blocks[:5]:
                title_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', block, re.DOTALL)
                if not title_match:
                    title_match = re.search(r'<title>(.*?)</title>', block, re.DOTALL)
                link_match = re.search(r'<link>(.*?)</link>', block, re.DOTALL)
                
                if title_match and link_match:
                    title = title_match.group(1).strip()
                    title = re.sub(r'<[^>]+>', '', title)
                    link = link_match.group(1).strip()
                    items.append({
                        'title': f"【金十快訊】{title}",
                        'summary': "", 
                        'newsId': link
                    })
            return items
        except Exception as e:
            print(f"⚠️ 金十數據連線異常，3秒後重試... ({e})", flush=True)
            time.sleep(3)
    return []

def analyze_news(news_item):
    if not NIM_API_KEY:
        print("🚨 錯誤：雲端環境變數中找不到 GROQ_API_KEY！", flush=True)
        return None
    
    print(f"準備分析: {news_item['title'][:30]}...", flush=True)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NIM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""你是一位資深的國際頂級宏觀經濟與財經專家。請針對以下新聞進行深度分析。

請務必嚴格按照以下【輸出格式】回答，不要寫任何多餘的解釋或引言：

**【所屬市場】**：[請填寫：台股 / 美股 / 國際全球]
**【市場趨勢判斷】**：[請填寫：重大利多 / 利多 / 中立 / 利空 / 重大利空]
**【AI 信心指數】**：[請填寫 1 到 5 顆星，例如：⭐⭐⭐⭐⭐]

---

**【核心利害關係分析】**
[請用 2-3 句繁體中文精準說明這則新聞。若新聞內容涉及地緣政治、軍事、天災、央行決策或黑天鵝事件，請精準點出該事件將如何強烈衝擊美股、台股或全球經濟。]

---

**【具體受連動影響之 3 檔股票/ETF】**
1. [股票名稱/代號] - [受牽連或看好的理由]
2. [股票名稱/代號] - [受牽連或看好的理由]
3. [股票名稱/代號] - [受牽連或看好的理由]

新聞標題：{news_item['title']}
新聞摘要：{news_item['summary']}"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=60)
            if response.status_code != 200:
                print(f"🚨 AI 伺服器拒絕連線！詳細原因: {response.text}", flush=True)
                return None
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            print(f"⚠️ AI 思考超時或異常，正在重新呼叫 (第 {attempt + 2} 次重試)... ({e})", flush=True)
            time.sleep(3)
    return None

def send_discord_alert(news_item, analysis):
    analysis_header = analysis[:150]
    bot_name = "🇹🇼 台股情報站"
    color = 0x808080 
    
    source_prefix = "⚡ " if "【金十快訊】" in news_item['title'] else "📰 "
    
    if "美股" in analysis_header or "國際" in analysis_header or "全球" in analysis_header:
        bot_name = "🌎 國際與美股情報站"
        if "利多" in analysis_header: color = 0x00FF00
        elif "利空" in analysis_header: color = 0xFF0000
    else:
        bot_name = "🇹🇼 台股情報站"
        if "利多" in analysis_header: color = 0xFF0000
        elif "利空" in analysis_header: color = 0x00FF00

    content_tag = ""
    if "重大利空" in analysis_header or "戰爭" in news_item['title'] or "開戰" in news_item['title']:
        content_tag = "⚠️ **【緊急重大警訊通知】** @everyone"
        color = 0xFF0000

    news_url = f"https://news.cnyes.com/news/id/{news_item.get('newsId', '')}" if not str(news_item.get('newsId', '')).startswith('http') else news_item['newsId']

    payload = {
        "content": content_tag,
        "username": bot_name,  
        "embeds": [{
            "title": f"{source_prefix}{news_item['title']}",
            "description": analysis,
            "url": news_url,
            "color": color,
            "footer": {
                "text": "💡 智能財經監控系統 (鉅亨網 x 金十數據)"
            }
        }]
    }
    
    for attempt in range(3):
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, verify=False, timeout=10)
            break 
        except Exception as e:
            print(f"⚠️ Discord 推播異常，3秒後重試... ({e})", flush=True)
            time.sleep(3)

if __name__ == "__main__":
    print("🚀 雲端排程自動化版：神獸開始巡邏！", flush=True)
    tracked_news = load_tracked_news()
    
    cnyes_items = get_cnyes_news()
    jinshi_items = get_jinshi_news()
    all_news = cnyes_items + jinshi_items
    
    print(f"共掃描到 {len(cnyes_items)} 則鉅亨頭條, {len(jinshi_items)} 則金十快訊", flush=True)
    
    new_count = 0
    for item in all_news:
        news_id = item['newsId']
        if news_id not in tracked_news:
            analysis = analyze_news(item)
            if analysis:
                send_discord_alert(item, analysis)
                tracked_news.append(news_id)
                new_count += 1
                time.sleep(2) 
                
    if new_count > 0:
    save_tracked_news(tracked_news)
    print(f"✨ 檢查完畢，共更新並發送了 {new_count} 則新快訊！", flush=True)
else:
    print("😴 沒有發現全新新聞，收工休息！", flush=True)
