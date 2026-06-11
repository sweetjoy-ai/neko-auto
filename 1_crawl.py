"""
neko-auto — STEP 1: 커뮤니티 크롤링
실행: python3 1_crawl.py [YYMMDD]
자동: APScheduler 1일 2회 (09:00, 21:00 KST)
"""

import json
import sqlite3
import time
import random
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = DATA_DIR / "neko.db"
DATA_DIR.mkdir(exist_ok=True)

TODAY = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%y%m%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
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


def save_posts(posts: list[dict]):
    conn = sqlite3.connect(DB_PATH)
    saved = 0
    for p in posts:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO posts
                (date, source, category, title, content, url, views, likes, comments, crawled_at)
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
            INSERT INTO trends (date, source, keyword, rank, related, crawled_at)
            VALUES (?,?,?,?,?,?)
        """, (t["date"], t["source"], t["keyword"], t["rank"],
              json.dumps(t.get("related",[]), ensure_ascii=False), t["crawled_at"]))
    conn.commit()
    conn.close()


# ── DC인사이드 고양이 갤러리 ───────────────────────────────────────────────
def crawl_dcinside_cat(pages=3) -> list[dict]:
    """DC인사이드 고양이 갤러리 — 인기/추천 게시글 수집"""
    results = []
    base = "https://gall.dcinside.com/board/lists"
    now  = datetime.now().isoformat()

    for page in range(1, pages + 1):
        try:
            params = {"id": "cat", "page": page, "exception_mode": "recommend"}
            resp = requests.get(base, params=params, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")

            rows = soup.select("tr.ub-content")
            for row in rows:
                title_el = row.select_one("td.gall_tit a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href  = title_el.get("href", "")
                url   = "https://gall.dcinside.com" + href if href.startswith("/") else href

                views    = _parse_int(row.select_one("td.gall_count"))
                likes    = _parse_int(row.select_one("td.gall_recommend"))
                comments = _parse_int(row.select_one("td.gall_reply_num"))

                if not title or not url:
                    continue

                results.append({
                    "date":       TODAY,
                    "source":     "dcinside_cat",
                    "category":   "cat_gallery",
                    "title":      title,
                    "content":    "",
                    "url":        url,
                    "views":      views,
                    "likes":      likes,
                    "comments":   comments,
                    "crawled_at": now,
                })

            time.sleep(random.uniform(1.0, 2.0))

        except Exception as e:
            print(f"  [DC인사이드] page {page} 오류: {e}")

    print(f"  ✅ DC인사이드 고양이갤: {len(results)}개 수집")
    return results


# ── 네이버 실시간 검색 트렌드 (DataLab API) ───────────────────────────────
def crawl_naver_trends() -> list[dict]:
    """네이버 DataLab — 반려묘 관련 키워드 트렌드"""
    CAT_KEYWORDS = [
        "고양이 사료", "츄르", "고양이 모래", "고양이 병원",
        "중성화 비용", "고양이 간식", "냥이", "집사",
    ]
    results = []
    now = datetime.now().isoformat()

    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ko", tz=540)

        # 5개씩 배치 (pytrends 제한)
        for i in range(0, len(CAT_KEYWORDS), 5):
            batch = CAT_KEYWORDS[i:i+5]
            pytrends.build_payload(batch, geo="KR", timeframe="now 7-d")
            data = pytrends.interest_over_time()

            if not data.empty:
                latest = data.iloc[-1]
                for rank, kw in enumerate(batch, start=i+1):
                    if kw in latest:
                        results.append({
                            "date":       TODAY,
                            "source":     "google_trends",
                            "keyword":    kw,
                            "rank":       int(latest[kw]),
                            "related":    [],
                            "crawled_at": now,
                        })

            time.sleep(random.uniform(1.5, 2.5))

    except ImportError:
        print("  [Google Trends] pytrends 미설치 — pip install pytrends")
    except Exception as e:
        print(f"  [Google Trends] 오류: {e}")

    # 관련 키워드도 수집
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ko", tz=540)
        pytrends.build_payload(["고양이"], geo="KR", timeframe="now 7-d")
        related = pytrends.related_queries()
        if "고양이" in related and related["고양이"]["rising"] is not None:
            for idx, row in related["고양이"]["rising"].head(10).iterrows():
                results.append({
                    "date":       TODAY,
                    "source":     "google_trends_rising",
                    "keyword":    row["query"],
                    "rank":       idx + 1,
                    "related":    [],
                    "crawled_at": now,
                })
    except Exception:
        pass

    print(f"  ✅ Google Trends: {len(results)}개 수집")
    return results


# ── 세대별 트렌드: 에브리타임 (공개 게시판) ───────────────────────────────
def crawl_everytime_public() -> list[dict]:
    """에브리타임 자유게시판 — 공개 접근 가능한 페이지만"""
    results = []
    now = datetime.now().isoformat()

    # 에브리타임은 로그인 필요 — 공개 검색 결과만 수집
    try:
        url = "https://everytime.kr/search"
        keywords = ["고양이", "집사", "자취방 고양이"]
        for kw in keywords:
            resp = requests.get(url, params={"q": kw}, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            posts = soup.select("article.list")
            for post in posts[:5]:
                title = post.select_one("h2")
                text  = post.select_one("p.text")
                results.append({
                    "date":       TODAY,
                    "source":     "everytime",
                    "category":   "search",
                    "title":      title.get_text(strip=True) if title else kw,
                    "content":    text.get_text(strip=True) if text else "",
                    "url":        url + f"?q={kw}",
                    "views":      0, "likes": 0, "comments": 0,
                    "crawled_at": now,
                })
            time.sleep(1)
    except Exception as e:
        print(f"  [에브리타임] {e} — 로그인 필요, 스킵")

    print(f"  ℹ️  에브리타임: {len(results)}개 (공개 접근 제한)")
    return results


# ── 유튜브 반려묘 채널 댓글 트렌드 ───────────────────────────────────────
def crawl_youtube_cat_comments() -> list[dict]:
    """yt-dlp로 인기 반려묘 채널의 최신 영상 제목 수집"""
    results = []
    now = datetime.now().isoformat()

    CAT_CHANNELS = [
        ("크림히어로즈", "https://www.youtube.com/@creamheroes/videos"),
        ("고양이는액체다", "https://www.youtube.com/@liquidcat/videos"),
    ]

    import subprocess
    for name, channel_url in CAT_CHANNELS:
        try:
            proc = subprocess.run(
                ["yt-dlp", "--flat-playlist", "--dump-json",
                 "--playlist-end", "10", "--no-warnings", channel_url],
                capture_output=True, text=True, timeout=30
            )
            for line in proc.stdout.strip().splitlines():
                try:
                    item = json.loads(line)
                    results.append({
                        "date":       TODAY,
                        "source":     f"youtube_{name}",
                        "category":   "cat_channel",
                        "title":      item.get("title", ""),
                        "content":    item.get("description", "")[:200],
                        "url":        f"https://youtube.com/watch?v={item.get('id','')}",
                        "views":      item.get("view_count", 0) or 0,
                        "likes":      0,
                        "comments":   item.get("comment_count", 0) or 0,
                        "crawled_at": now,
                    })
                except Exception:
                    pass
        except Exception as e:
            print(f"  [YouTube {name}] {e}")

    print(f"  ✅ YouTube 반려묘 채널: {len(results)}개 수집")
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
    print(f"  neko-auto 크롤링 시작 ({TODAY})")
    print(f"{'='*55}")

    init_db()
    all_posts   = []
    all_trends  = []

    print("\n[1/4] DC인사이드 고양이 갤러리...")
    all_posts += crawl_dcinside_cat(pages=3)

    print("\n[2/4] Google Trends 반려묘 키워드...")
    all_trends += crawl_naver_trends()

    print("\n[3/4] 에브리타임 (공개)...")
    all_posts += crawl_everytime_public()

    print("\n[4/4] YouTube 반려묘 채널...")
    all_posts += crawl_youtube_cat_comments()

    saved_posts  = save_posts(all_posts)
    save_trends(all_trends)

    # 결과 요약 저장
    summary = {
        "date":        TODAY,
        "posts_total": len(all_posts),
        "posts_saved": saved_posts,
        "trends":      len(all_trends),
        "sources":     list({p["source"] for p in all_posts}),
        "crawled_at":  datetime.now().isoformat(),
    }
    summary_path = DATA_DIR / f"{TODAY}_crawl_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    print(f"\n{'='*55}")
    print(f"  ✅ 완료: 게시글 {saved_posts}개 저장, 트렌드 {len(all_trends)}개")
    print(f"  📁 {summary_path}")
    print(f"{'='*55}\n")
    return summary


if __name__ == "__main__":
    main()
