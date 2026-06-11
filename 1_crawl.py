"""
mochi-nyang — STEP 1: 일본 반려묘 커뮤니티 크롤링
수집처: 5ch猫板, ガールズちゃんねる, ニコニコ動画, Google Trends(JP)
실행: python3 1_crawl.py [YYMMDD]
"""

import json
import re
import sqlite3
import subprocess
import sys
import time
import random
from datetime import datetime
from pathlib import Path

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT,
            source    TEXT,
            category  TEXT,
            title     TEXT,
            content   TEXT,
            url       TEXT UNIQUE,
            views     INTEGER DEFAULT 0,
            likes     INTEGER DEFAULT 0,
            comments  INTEGER DEFAULT 0,
            crawled_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trends (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            date     TEXT,
            source   TEXT,
            keyword  TEXT,
            rank     INTEGER,
            related  TEXT,
            crawled_at TEXT
        )
    """)
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


# ── 1. 5ch 猫板 ────────────────────────────────────────────────────────────
def crawl_5ch_cat() -> list[dict]:
    """5ch猫板 — 인기 스레드 수집 (날 것의 집사 감정)"""
    results = []
    now = datetime.now().isoformat()

    urls = [
        ("cat",   "https://neko.5ch.net/cat/"),       # 猫板
        ("peko",  "https://peko.5ch.net/cat/"),        # 미러
    ]

    for board_id, url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            # 스레드 목록
            threads = soup.select("div.thread") or soup.select("tr.thread")
            if not threads:
                # 일반 목록 형식
                threads = soup.select("a[href*='read.cgi']")

            for t in threads[:30]:
                if hasattr(t, "get_text"):
                    title = t.get_text(strip=True)[:100]
                    href  = t.get("href","") if t.name == "a" else ""
                else:
                    a = t.select_one("a")
                    if not a:
                        continue
                    title = a.get_text(strip=True)[:100]
                    href  = a.get("href","")

                if not title or len(title) < 3:
                    continue
                # 猫・ねこ・ニャン 관련만
                if not any(kw in title for kw in ["猫","ねこ","ニャン","にゃん","ネコ","キャット"]):
                    pass  # 5ch 猫板 자체가 고양이 판이므로 필터 완화

                full_url = href if href.startswith("http") else f"https://neko.5ch.net{href}"
                results.append({
                    "date":       TODAY,
                    "source":     "5ch_cat",
                    "category":   "cat_board",
                    "title":      title,
                    "content":    "",
                    "url":        full_url or url,
                    "views":      0, "likes": 0, "comments": 0,
                    "crawled_at": now,
                })
            break  # 첫 번째 성공하면 중단

        except Exception as e:
            print(f"  [5ch {board_id}] {e}")

    print(f"  ✅ 5ch 猫板: {len(results)}개 수집")
    return results


# ── 2. ガールズちゃんねる 猫カテゴリ ──────────────────────────────────────
def crawl_girlschannel_cat() -> list[dict]:
    """ガールズちゃんねる — 猫・ペット 토픽 수집 (여성 집사 공감 포인트)"""
    results = []
    now = datetime.now().isoformat()

    search_urls = [
        ("cat_search", "https://girlschannel.net/topics/search/?q=%E7%8C%AB"),       # 猫
        ("pet_search", "https://girlschannel.net/topics/search/?q=%E3%83%9A%E3%83%83%E3%83%88%E7%8C%AB"),  # ペット猫
    ]

    for source_id, url in search_urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            topics = soup.select("article.topic") or soup.select("li.topic-item")
            if not topics:
                topics = soup.select("div.topic-list-item")

            for topic in topics[:20]:
                title_el = topic.select_one("h2") or topic.select_one("h3") or topic.select_one(".topic-title")
                link_el  = topic.select_one("a[href*='/topics/']")
                count_el = topic.select_one(".count") or topic.select_one(".comment-count")

                if not title_el:
                    continue

                title  = title_el.get_text(strip=True)[:100]
                href   = link_el.get("href","") if link_el else ""
                full_url = f"https://girlschannel.net{href}" if href.startswith("/") else href
                comments = _parse_int(count_el)

                results.append({
                    "date":       TODAY,
                    "source":     "girlschannel",
                    "category":   "cat_women",
                    "title":      title,
                    "content":    "",
                    "url":        full_url or url,
                    "views":      0, "likes": 0,
                    "comments":   comments,
                    "crawled_at": now,
                })
            time.sleep(random.uniform(1.0, 2.0))

        except Exception as e:
            print(f"  [ガールズちゃんねる {source_id}] {e}")

    print(f"  ✅ ガールズちゃんねる: {len(results)}개 수집")
    return results


# ── 3. ニコニコ動画 猫 인기영상 ───────────────────────────────────────────
def crawl_nicovideo_cat() -> list[dict]:
    """ニコニコ動画 — 猫 태그 인기영상 수집 (탄막 공감 타이밍 분석용)"""
    results = []
    now = datetime.now().isoformat()

    # ニコニコ 검색 API (공개)
    api_url = "https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search"
    params = {
        "q":        "猫 集合",
        "targets":  "tags",
        "fields":   "contentId,title,description,viewCounter,commentCounter,likeCounter,tags",
        "filters[genre][0]": "動物",
        "_sort":    "-viewCounter",
        "_limit":   20,
        "_context": "mochi-nyang-crawler",
    }

    try:
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()

        for item in data.get("data", []):
            video_id = item.get("contentId","")
            results.append({
                "date":       TODAY,
                "source":     "nicovideo",
                "category":   "cat_video",
                "title":      item.get("title","")[:100],
                "content":    item.get("description","")[:200],
                "url":        f"https://www.nicovideo.jp/watch/{video_id}",
                "views":      item.get("viewCounter", 0),
                "likes":      item.get("likeCounter", 0),
                "comments":   item.get("commentCounter", 0),
                "crawled_at": now,
            })

    except Exception as e:
        print(f"  [ニコニコ API] {e} — 일반 검색 시도")
        # 폴백: 웹 스크래핑
        try:
            url = "https://www.nicovideo.jp/search/%E7%8C%AB?sort=h&order=d"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("li.VideoItem") or soup.select("div.item")
            for item in items[:15]:
                title_el = item.select_one(".VideoItem-title") or item.select_one("p.title")
                link_el  = item.select_one("a[href*='/watch/']")
                if not title_el:
                    continue
                href = link_el.get("href","") if link_el else ""
                results.append({
                    "date":       TODAY,
                    "source":     "nicovideo",
                    "category":   "cat_video",
                    "title":      title_el.get_text(strip=True)[:100],
                    "content":    "",
                    "url":        f"https://www.nicovideo.jp{href}" if href.startswith("/") else href,
                    "views":      0, "likes": 0, "comments": 0,
                    "crawled_at": now,
                })
        except Exception as e2:
            print(f"  [ニコニコ 폴백] {e2}")

    print(f"  ✅ ニコニコ動画: {len(results)}개 수집")
    return results


# ── 4. Google Trends 일본 반려묘 키워드 ───────────────────────────────────
def crawl_google_trends_jp() -> list[dict]:
    """Google Trends — 일본(JP) 반려묘 관련 키워드 트렌드"""
    results = []
    now = datetime.now().isoformat()

    JP_CAT_KEYWORDS = [
        "猫 ご飯", "キャットフード", "猫砂", "猫 病院",
        "去勢手術", "猫 おやつ", "ツンデレ猫", "テレワーク 猫",
        "猫 物価", "ペットフード 値上がり",
    ]

    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ja-JP", tz=540)

        for i in range(0, len(JP_CAT_KEYWORDS), 5):
            batch = JP_CAT_KEYWORDS[i:i+5]
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
            time.sleep(random.uniform(1.5, 2.5))

        # 급상승 키워드
        pytrends.build_payload(["猫"], geo="JP", timeframe="now 7-d")
        related = pytrends.related_queries()
        if "猫" in related and related["猫"]["rising"] is not None:
            for idx, row in related["猫"]["rising"].head(10).iterrows():
                results.append({
                    "date":       TODAY,
                    "source":     "google_trends_jp_rising",
                    "keyword":    row["query"],
                    "rank":       idx + 1,
                    "related":    [],
                    "crawled_at": now,
                })

    except ImportError:
        print("  [Google Trends] pytrends 미설치")
    except Exception as e:
        print(f"  [Google Trends JP] {e}")

    print(f"  ✅ Google Trends JP: {len(results)}개 수집")
    return results


# ── 5. Twitter/X 일본 猫 트렌드 (공개 트렌드 페이지) ─────────────────────
def crawl_twitter_cat_trends() -> list[dict]:
    """Twitter/X — 猫 관련 공개 트렌드 수집 (API 없이)"""
    results = []
    now = datetime.now().isoformat()

    # Nitter 미러 (X API 없이 접근 가능한 공개 인스턴스)
    nitter_instances = [
        "https://nitter.net/search?q=%E7%8C%AB&f=tweets",
        "https://nitter.1d4.us/search?q=%E7%8C%AB",
    ]

    for url in nitter_instances:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            tweets = soup.select("div.tweet-content") or soup.select("p.tweet-text")
            for tw in tweets[:20]:
                text = tw.get_text(strip=True)[:150]
                if text:
                    results.append({
                        "date":       TODAY,
                        "source":     "twitter_nitter",
                        "category":   "cat_twitter",
                        "title":      text,
                        "content":    "",
                        "url":        url,
                        "views":      0, "likes": 0, "comments": 0,
                        "crawled_at": now,
                    })
            if results:
                break
        except Exception as e:
            print(f"  [Twitter Nitter] {e}")

    if not results:
        print("  ℹ️  Twitter: Nitter 인스턴스 불안정 — 스킵")

    print(f"  ✅ Twitter/X: {len(results)}개 수집")
    return results


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def _parse_int(el) -> int:
    if not el:
        return 0
    txt = re.sub(r"[^\d]", "", el.get_text())
    return int(txt) if txt else 0


# ── 메인 ──────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  mochi-nyang 크롤링 시작 ({TODAY})")
    print(f"{'='*55}")

    init_db()
    all_posts  = []
    all_trends = []

    print("\n[1/5] 5ch 猫板...")
    all_posts += crawl_5ch_cat()

    print("\n[2/5] ガールズちゃんねる...")
    all_posts += crawl_girlschannel_cat()

    print("\n[3/5] ニコニコ動画...")
    all_posts += crawl_nicovideo_cat()

    print("\n[4/5] Google Trends JP...")
    all_trends += crawl_google_trends_jp()

    print("\n[5/5] Twitter/X (공개)...")
    all_posts += crawl_twitter_cat_trends()

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
    summary_path = DATA_DIR / f"{TODAY}_crawl_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    print(f"\n{'='*55}")
    print(f"  ✅ 완료: 게시글 {saved}개 저장, 트렌드 {len(all_trends)}개")
    print(f"{'='*55}\n")
    return summary


if __name__ == "__main__":
    main()
