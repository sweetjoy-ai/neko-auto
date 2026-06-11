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

## 🎭 모찌냥 에피소드 아이디어 5개
모찌냥 컨셉: "자학 개그 + 현실 수용 + 무해한 웃음"
감정 구조: 슬픔/불편함 → 더 웃긴 진실 폭로 → 자학적 수용 → 순수한 웃음(あははは)

각 아이디어를 아래 형식으로 작성:
- 타입: A(자기무능력 자각) / B(민망한진실 폭로) / C(긍정적 재해석)
- 장소 + 의상:
- 현실/불편함 (공감 포인트):
- 자학 포인트 (뒤집는 웃긴 진실):
- 마무리 웃음 방향:
- 일본 집사 공감 이유:

## 💡 이번 주 추천 콘텐츠 방향
타입 A/B/C 각각 1개씩, 소재와 이유 포함

## ⚠️ 주목할 일본 이슈/트렌드
모찌냥 에피소드로 만들기 좋은 오늘의 핫 이슈
"""

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


MOCHI_CONCEPT = """
■ 채널 컨셉: 모찌냥 (もちにゃん)
"자학 개그 + 현실 수용 + 무해한 웃음"

■ 감정 구조 (반드시 이 흐름으로)
  슬픔/불편한 현실 제시
  → 더 웃긴 측면 or 민망한 진실 폭로
  → 자학적 수용 (담담하게 체념)
  → 순수한 웃음으로 마무리 (깔깔깔 / あははは)

■ 에피소드 타입 3가지
  타입 A (자기 무능력 자각형)
    심각한 문제 → 극단적 해결책 언급 → 자신의 무능력 깨달음 → 웃음
    예) 물가 올라 사냥해야지 → "근데 평생 한 번도 못 잡았는데" → 아하하

  타입 B (민망한 진실 폭로형)
    선한 행동 시도 → 숨겨진 민망한 사실 → 뒤늦은 깨달음 → 웃음
    예) 발바닥 베개 해줬는데 → "발 며칠 안 씻었는데" → 아하하

  타입 C (긍정적 재해석형)
    슬픈 현실 → 담한 수용 → 긍정적 프레이밍 → 웃음
    예) 츄루 못 먹어 → "이 참에 다이어트!" → 아하하

■ 핵심 원칙
  - 냉소 없이 진짜 즐거움으로 마무리
  - 자학이지만 상처받지 않는 톤
  - 공감 먼저, 웃음은 자연스럽게
  - 마지막 웃음은 반드시 순수하고 무해하게
"""

# ── 에피소드 대본 생성 ─────────────────────────────────────────────────────
def generate_episode_script(idea: str) -> str:
    """선택된 에피소드 아이디어로 모찌냥 스타일 대본 생성"""
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
당신은 일본어 숏폼 유튜브 채널 "모찌냥(もちにゃん)"의 전속 대본 작가입니다.

{MOCHI_CONCEPT}

■ 에피소드 아이디어 (이 소재로 대본 작성):
{idea}

■ 형식 규칙
- 총 길이: 30~40초 (텍스트 기준 200~250자 일본어)
- 대사는 모두 일본어로 작성, 괄호 안에 한국어 번역 병기
- 모찌냥 목소리: 담담하고 느릿느릿, 갑자기 자각할 때만 텐션 올라감
- 리포터: 친절하고 공감적, 모찌냥 반응에 같이 웃어줌
- 마지막 웃음은 반드시 「あははははは〜！」로 끝낼 것
- 字幕(자막): 「次回もお楽しみに🐾」로 마무리

반드시 한국어로 메타 정보를 작성하고, 대사만 일본어+한국어 병기로 작성하세요.

---

## 🎬 제목 (한국어)
## 🗾 일본어 제목
## 📍 장소 / 의상
## 🎭 타입: A / B / C 중 선택 + 한 줄 설명

## 📝 대본

[오프닝 — 3초]
(장면 묘사)
(마이크 등장)

[질문 — 5초]
リポーター: 「」(한국어 번역)

[본문 — 18~22초]
モチニャン: 「」(한국어)
(행동/표정 묘사)
「」(한국어)

[엔딩 — 6초] ⭐ 자학 포인트
モチニャン: 「」(한국어)
(자각 묘사)
「あははははは〜！」(아하하하하~!)

字幕: 「次回もお楽しみに🐾」

---

## 💡 웃음 포인트 (3줄)
## 🏷️ 해시태그: 일본어 5개
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
