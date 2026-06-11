"""
neko-auto — STEP 2: Gemini 키워드 분석 + 에피소드 아이디어 생성
실행: python3 2_analyze.py [YYMMDD]
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

BASE_DIR = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = DATA_DIR / "neko.db"

TODAY = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%y%m%d")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ── DB에서 오늘 수집 데이터 로드 ───────────────────────────────────────────
def load_today_posts() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM posts WHERE date=? ORDER BY likes DESC, views DESC LIMIT 100",
        (TODAY,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_today_trends() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM trends WHERE date=? ORDER BY rank DESC LIMIT 50",
        (TODAY,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Gemini 분석 ────────────────────────────────────────────────────────────
def run_keyword_analysis(posts: list[dict], trends: list[dict]) -> str:
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    posts_text = "\n".join(
        f"- [{p['source']}] {p['title']} (👍{p['likes']} 👁{p['views']})"
        for p in posts[:50]
    )
    trends_text = "\n".join(
        f"- {t['keyword']} (관심도:{t['rank']})"
        for t in trends[:20]
    )

    prompt = f"""
당신은 일본어 숏폼 유튜브 채널 "모찌냥(もちにゃん)"의 콘텐츠 기획자입니다.
일본 반려묘 집사 커뮤니티(5ch猫板, ガールズちゃんねる, ニコニコ動画)의 데이터를 분석하여
일본 집사들이 공감할 숏폼 에피소드 아이디어를 발굴합니다.

일본 특유의 공감 코드:
- ツンデレ 고양이 (간식 줄 때만 반응, 평소엔 무시)
- テレワーク 중 고양이 방해
- 物価高 / ペットフード 값 동반 상승 (집사들의 최대 痛点)
- 5ch식 날 것의 감정 표현

오늘({TODAY}) 수집된 일본 커뮤니티 데이터:

[인기 게시글 / 스레드]
{posts_text}

[Google Trends JP 키워드]
{trends_text}

반드시 한국어로 작성해주세요.

다음 형식으로 분석해주세요:

## 📊 오늘의 일본 집사 공감 키워드 TOP 10
각 키워드와 일본 특유의 공감 이유 1줄 설명

## 🎭 에피소드 아이디어 5개
형식: 고양이 리포터 인터뷰 스타일 (일본 숏폼 특화)
- 장소: (어디서)
- 상황: (무슨 상황)
- 대화: 리포터 질문 + 고양이 답변 (2~3줄)
- 일본 공감 포인트: (왜 일본 시청자에게 먹히는지)
- 추천 해시태그: #猫 등 일본어 3개

## 💡 이번 주 추천 콘텐츠 방향
3가지 bullet point (일본 트렌드 반영)

## ⚠️ 주목할 일본 이슈/트렌드
오늘 특별히 눈에 띄는 일본 집사 커뮤니티 이슈
"""

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


# ── 에피소드 대본 생성 ─────────────────────────────────────────────────────
def generate_episode_script(idea: str) -> str:
    """선택된 에피소드 아이디어로 일본어 숏폼 대본 생성"""
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
당신은 일본어 숏폼 유튜브 채널의 대본 작가입니다.
"고양이 리포터 인터뷰" 스타일의 1분 이내 숏폼 대본을 작성합니다.

에피소드 아이디어:
{idea}

반드시 한국어로 작성해주세요.

다음 형식으로 대본을 작성해주세요:

## 🎬 영상 제목 (한국어)
## 🗾 일본어 제목
## ⏱️ 예상 길이: 45~60초

## 📝 대본

[오프닝 — 3초]
리포터가 카메라 보며 장소 소개

[인터뷰 — 30~40초]
리포터: (질문)
고양이: (답변) — 자막/더빙용
리포터: (반응 또는 추가 질문)
고양이: (마무리 답변)

[엔딩 — 5초]
리포터 마무리 멘트

## 🏷️ 추천 해시태그 (일본어 5개 + 한국어 3개)
## 📌 촬영 포인트
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


# ── 텔레그램 알림 ──────────────────────────────────────────────────────────
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [텔레그램] 설정 없음, 스킵")
        return
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                  "parse_mode": "Markdown"},
            timeout=10
        )
        print("  ✅ 텔레그램 알림 발송")
    except Exception as e:
        print(f"  [텔레그램] 오류: {e}")


# ── 메인 ──────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  neko-auto 분석 시작 ({TODAY})")
    print(f"{'='*55}")

    if not GEMINI_API_KEY:
        print("  ❌ GEMINI_API_KEY 없음")
        return

    posts  = load_today_posts()
    trends = load_today_trends()
    print(f"  📊 게시글 {len(posts)}개, 트렌드 {len(trends)}개 로드")

    if not posts and not trends:
        print("  ⚠️  데이터 없음 — 먼저 1_crawl.py 실행하세요")
        return

    print("\n  🤖 Gemini 분석 중...")
    analysis = run_keyword_analysis(posts, trends)

    # 저장
    analysis_path = DATA_DIR / f"{TODAY}_analysis.txt"
    analysis_path.write_text(analysis, encoding="utf-8")
    print(f"  💾 저장: {analysis_path}")

    # 텔레그램 알림
    summary_msg = (
        f"🐱 *neko-auto 분석 완료* ({TODAY})\n\n"
        f"게시글 {len(posts)}개 분석\n"
        f"트렌드 키워드 {len(trends)}개 분석\n\n"
        f"대시보드에서 에피소드 아이디어를 확인하세요!"
    )
    send_telegram(summary_msg)

    print(f"\n{'='*55}")
    print(f"  ✅ 분석 완료")
    print(f"{'='*55}\n")
    return analysis


if __name__ == "__main__":
    main()
