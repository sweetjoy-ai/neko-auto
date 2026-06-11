"""
mochi-nyang — STEP 1: 일본 반려묘 커뮤니티 크롤링
수집처: ニコニコ動画API, はてなブックマーク, Yahoo Japan RSS, Google Trends JP
※ 5ch / ガールズちゃんねる / Nitter는 해외 IP 차단으로 제외
실행: python3 1_crawl.py [YYMMDD]
"""

import json
import re
import sqlite3
import sys
import time
import random
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BASE_DIR = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = DATA_DIR / "neko.db"
DATA_DIR.mkdir(exist_ok=True)

TODAY = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%y%m%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9",
}


# ── DB 초기화 ──────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    # 기존 테이블이 url UNIQUE라면 재생성
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, source TEXT, category TEXT,
            title TEXT, content TEXT, url TEXT,
            views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0, crawled_at TEXT,
            UNIQUE(date, url)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, source TEXT, keyword TEXT,
            rank INTEGER, related TEXT, crawled_at TEXT
        )
    """)
    # 구버전 posts 테이블이 있으면 데이터 이전 후 교체
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "posts" in tables and "posts_v2" in tables:
        conn.execute("INSERT OR IGNORE INTO posts_v2 SELECT * FROM posts")
        conn.execute("DROP TABLE posts")
    if "posts_v2" in tables:
        conn.execute("ALTER TABLE posts_v2 RENAME TO posts") if "posts" not in tables else None
    conn.commit()
    conn.close()


def save_posts(posts: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    saved = 0
    for p in posts:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO posts
                (date,source,category,title,content,url,views,likes,comments,crawled_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (p["date"], p["source"], p["category"], p["title"],
                  p.get("content",""), p["url"], p.get("views",0),
                  p.get("likes",0), p.get("comments",0), p["crawled_at"]))
            saved += conn.rowcount
        except Exception:
            pass
    conn.commit()
    conn.close()
    return saved


def save_trends(trends: list[dict]):
    conn = sqlite3.connect(DB_PATH)
    for t in trends:
        conn.execute("""
            INSERT INTO trends (date,source,keyword,rank,related,crawled_at)
            VALUES (?,?,?,?,?,?)
        """, (t["date"], t["source"], t["keyword"], t["rank"],
              json.dumps(t.get("related",[]), ensure_ascii=False), t["crawled_at"]))
    conn.commit()
    conn.close()


# ── 1. ニコニコ動画 猫 인기영상 (API) ─────────────────────────────────────
def crawl_nicovideo() -> list[dict]:
    """ニコニコ動画 공개 API — 猫 태그 인기영상"""
    results = []
    now = datetime.now().isoformat()

    queries = [
        ("猫 あるある",  "cat_daily"),
        ("猫 ツンデレ",  "cat_tsundere"),
        ("猫 テレワーク","cat_telework"),
        ("猫 集合",     "cat_compilation"),
    ]

    api = "https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search"

    for q_text, category in queries:
        try:
            params = {
                "q": q_text,
                "targets": "tags,description",
                "fields": "contentId,title,description,viewCounter,commentCounter,likeCounter",
                "_sort": "-viewCounter",
                "_limit": 10,
                "_context": "mochi-nyang",
            }
            resp = requests.get(api, params=params, headers=HEADERS, timeout=15)
            data = resp.json()

            for item in data.get("data", []):
                vid = item.get("contentId","")
                results.append({
                    "date":       TODAY,
                    "source":     "nicovideo",
                    "category":   category,
                    "title":      item.get("title","")[:120],
                    "content":    item.get("description","")[:200],
                    "url":        f"https://www.nicovideo.jp/watch/{vid}",
                    "views":      item.get("viewCounter", 0),
                    "likes":      item.get("likeCounter", 0),
                    "comments":   item.get("commentCounter", 0),
                    "crawled_at": now,
                })
            time.sleep(random.uniform(0.8, 1.5))
        except Exception as e:
            print(f"  [ニコニコ '{q_text}'] {e}")

    print(f"  ✅ ニコニコ動画: {len(results)}개 수집")
    return results


# ── 2. はてなブックマーク 猫 태그 (공개 RSS API) ──────────────────────────
def crawl_hatena_cat() -> list[dict]:
    """はてなブックマーク — 猫 태그 인기 기사 (BS4 XML 파서 사용)"""
    results = []
    now = datetime.now().isoformat()

    feeds = [
        ("hatena_cat",  f"https://b.hatena.ne.jp/search/text?q={quote('猫')}&users=10&mode=rss"),
        ("hatena_neko", f"https://b.hatena.ne.jp/search/text?q={quote('ねこ+集合')}&users=5&mode=rss"),
        ("hatena_pet",  f"https://b.hatena.ne.jp/search/text?q={quote('保護猫')}&users=5&mode=rss"),
    ]

    for source_id, url in feeds:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "lxml-xml")

            for item in soup.find_all("item")[:20]:
                title = item.find("title")
                link  = item.find("link") or item.find("guid")
                desc  = item.find("description")

                t = title.get_text(strip=True) if title else ""
                l = link.get_text(strip=True) if link else ""
                d = desc.get_text(strip=True)[:200] if desc else ""

                if not t or not l:
                    continue

                results.append({
                    "date":       TODAY,
                    "source":     source_id,
                    "category":   "cat_news",
                    "title":      t[:120],
                    "content":    d,
                    "url":        l,
                    "views":      0, "likes": 0, "comments": 0,
                    "crawled_at": now,
                })
            time.sleep(random.uniform(0.8, 1.5))

        except Exception as e:
            print(f"  [はてな {source_id}] {e}")

    print(f"  ✅ はてなブックマーク: {len(results)}개 수집")
    return results


# ── 3. Yahoo Japan 뉴스 RSS — 猫 ──────────────────────────────────────────
def crawl_yahoo_japan_cat() -> list[dict]:
    """Yahoo Japan — 猫 키워드 뉴스 검색 (RSS)"""
    results = []
    now = datetime.now().isoformat()

    # Yahoo Japan 뉴스 검索 RSS
    search_terms = ["猫", "ねこ 集合", "ペット 猫"]
    CAT_KEYWORDS = ["猫","ねこ","ネコ","キャット","ペット","にゃん","里親","保護猫"]

    for term in search_terms:
        url = f"https://news.yahoo.co.jp/search?p={quote(term)}&ei=UTF-8&rs=rss"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "lxml-xml")

            for item in soup.find_all("item")[:15]:
                title = item.find("title")
                link  = item.find("link") or item.find("guid")
                desc  = item.find("description")

                t = title.get_text(strip=True) if title else ""
                l = link.get_text(strip=True) if link else ""
                d = desc.get_text(strip=True)[:200] if desc else ""

                if not t or not l:
                    continue
                if not any(kw in t + d for kw in CAT_KEYWORDS):
                    continue

                results.append({
                    "date":       TODAY,
                    "source":     "yahoo_jp",
                    "category":   "cat_news_jp",
                    "title":      t[:120],
                    "content":    d,
                    "url":        l,
                    "views":      0, "likes": 0, "comments": 0,
                    "crawled_at": now,
                })
            time.sleep(1.0)

        except Exception as e:
            print(f"  [Yahoo Japan '{term}'] {e}")

    print(f"  ✅ Yahoo Japan: {len(results)}개 수집")
    return results


# ── 4. Google Trends JP — 반려묘 키워드 ───────────────────────────────────
def crawl_google_trends_jp() -> list[dict]:
    """Google Trends JP — 猫 관련 키워드 트렌드 (재시도 로직 포함)"""
    results = []
    now = datetime.now().isoformat()

    JP_KEYWORDS = [
        "猫 ご飯", "キャットフード", "猫砂",
        "ツンデレ猫", "テレワーク 猫", "ペットフード 値上がり",
    ]

    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ja-JP", tz=540, timeout=(10,25))

        # 3개씩 배치 (429 방지)
        for i in range(0, len(JP_KEYWORDS), 3):
            batch = JP_KEYWORDS[i:i+3]
            try:
                pytrends.build_payload(batch, geo="JP", timeframe="now 7-d")
                data = pytrends.interest_over_time()
                if not data.empty:
                    latest = data.iloc[-1]
                    for rank, kw in enumerate(batch, start=i+1):
                        if kw in latest:
                            results.append({
                                "date":       TODAY,
                                "source":     "google_trends_jp",
                                "keyword":    kw,
                                "rank":       int(latest[kw]),
                                "related":    [],
                                "crawled_at": now,
                            })
                time.sleep(random.uniform(3.0, 5.0))  # 429 방지 대기
            except Exception as e:
                print(f"  [Trends 배치{i}] {e}")
                time.sleep(10)

    except ImportError:
        print("  [Google Trends] pytrends 미설치")
    except Exception as e:
        print(f"  [Google Trends JP] {e}")

    print(f"  ✅ Google Trends JP: {len(results)}개 수집")
    return results


# ── 5. ニコニコ 급상승 태그 트렌드 ───────────────────────────────────────
def crawl_nicovideo_trends() -> list[dict]:
    """ニコニコ動画 — 猫 관련 인기 태그 수집 (트렌드 대용)"""
    results = []
    now = datetime.now().isoformat()

    try:
        url = "https://www.nicovideo.jp/tag/%E7%8C%AB?sort=h&order=d"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # JSON-LD 또는 메타 태그에서 인기 태그 추출
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string)
                keywords = data.get("keywords", [])
                if isinstance(keywords, list):
                    for rank, kw in enumerate(keywords[:15], start=1):
                        results.append({
                            "date":       TODAY,
                            "source":     "nicovideo_tags",
                            "keyword":    kw,
                            "rank":       rank,
                            "related":    [],
                            "crawled_at": now,
                        })
            except Exception:
                pass

    except Exception as e:
        print(f"  [ニコニコ tags] {e}")

    print(f"  ✅ ニコニコ 태그 트렌드: {len(results)}개 수집")
    return results


# ── 메인 ──────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  mochi-nyang 크롤링 시작 ({TODAY})")
    print(f"{'='*55}")

    init_db()
    all_posts  = []
    all_trends = []

    print("\n[1/5] ニコニコ動画 인기영상...")
    all_posts += crawl_nicovideo()

    print("\n[2/5] はてなブックマーク 猫...")
    all_posts += crawl_hatena_cat()

    print("\n[3/5] Yahoo Japan RSS 猫뉴스...")
    all_posts += crawl_yahoo_japan_cat()

    print("\n[4/5] Google Trends JP...")
    all_trends += crawl_google_trends_jp()

    print("\n[5/5] ニコニコ 태그 트렌드...")
    all_trends += crawl_nicovideo_trends()

    saved = save_posts(all_posts)
    save_trends(all_trends)

    summary = {
        "date":        TODAY,
        "posts_total": len(all_posts),
        "posts_saved": saved,
        "trends":      len(all_trends),
        "sources":     list({p["source"] for p in all_posts}),
        "crawled_at":  datetime.now().isoformat(),
    }
    (DATA_DIR / f"{TODAY}_crawl_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )

    print(f"\n{'='*55}")
    print(f"  ✅ 완료: 게시글 {saved}개 저장, 트렌드 {len(all_trends)}개")
    print(f"{'='*55}\n")
    return summary


if __name__ == "__main__":
    main()
