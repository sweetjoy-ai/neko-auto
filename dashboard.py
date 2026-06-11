"""
neko-auto — Streamlit 대시보드
실행: streamlit run dashboard.py --server.port 8502 --server.baseUrlPath youtube/mochi-nyang
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = DATA_DIR / "neko.db"
DATA_DIR.mkdir(exist_ok=True)

TODAY = datetime.now().strftime("%y%m%d")

st.set_page_config(
    page_title="neko-auto | Spacejoy",
    page_icon="🐱",
    layout="wide",
)

# ── 스타일 ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: #faf7f2; }
.block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ── 브레드크럼 ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:12px; color:#999; padding:8px 0 4px; border-bottom:1px solid #eee; margin-bottom:16px;">
  <a href="https://spacejoy.withlinkus.com" style="color:#b8895a; text-decoration:none;">main</a>
  <span style="margin:0 6px; color:#ccc;">›</span>
  <a href="https://spacejoy.withlinkus.com/youtube" style="color:#b8895a; text-decoration:none;">youtube</a>
  <span style="margin:0 6px; color:#ccc;">›</span>
  <span style="color:#555;">mochi-nyang</span>
</div>
""", unsafe_allow_html=True)

st.title("🐱 neko-auto")
st.caption("일본어 숏폼 채널 — 반려묘 집사 공감 콘텐츠 자동화")

# ── 날짜 선택 ──────────────────────────────────────────────────────────────
col_date, col_refresh = st.columns([3, 1])
with col_date:
    selected_date = st.text_input("날짜 (YYMMDD)", value=TODAY, label_visibility="collapsed")
with col_refresh:
    if st.button("🔄 새로고침"):
        st.rerun()

date_str = selected_date.strip() or TODAY
summary_file  = DATA_DIR / f"{date_str}_crawl_summary.json"
analysis_file = DATA_DIR / f"{date_str}_analysis.txt"
episode_file  = DATA_DIR / f"{date_str}_episode.txt"

crawl_done    = summary_file.exists()
analysis_done = analysis_file.exists()
episode_done  = episode_file.exists()


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def load_summary():
    if summary_file.exists():
        return json.loads(summary_file.read_text())
    return None

def load_posts(limit=50):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM posts WHERE date=? ORDER BY likes DESC, views DESC LIMIT ?",
            (date_str, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

def load_trends():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trends WHERE date=? ORDER BY rank DESC",
            (date_str,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════
# STEP 1: 크롤링
# ══════════════════════════════════════════════════════════════════════════
with st.expander("🕷️ STEP 1 — 커뮤니티 크롤링", expanded=not crawl_done):
    if crawl_done:
        summary = load_summary()
        st.success(f"✅ 크롤링 완료 — 게시글 {summary.get('posts_saved','?')}개, 트렌드 {summary.get('trends','?')}개")
        st.caption(f"수집 시각: {summary.get('crawled_at','')[:16]}")

        posts = load_posts()
        trends = load_trends()

        if posts:
            st.markdown("**📋 수집된 게시글**")
            tab_dc, tab_yt, tab_etc = st.tabs(["DC인사이드", "YouTube", "기타"])
            with tab_dc:
                dc_posts = [p for p in posts if "dcinside" in p["source"]]
                for p in dc_posts[:20]:
                    st.markdown(f"[{p['title'][:60]}]({p['url']}) 👍{p['likes']} 👁{p['views']}")
            with tab_yt:
                yt_posts = [p for p in posts if "youtube" in p["source"]]
                for p in yt_posts[:20]:
                    st.markdown(f"[{p['title'][:60]}]({p['url']}) 👁{p['views']}")
            with tab_etc:
                etc_posts = [p for p in posts if "dcinside" not in p["source"] and "youtube" not in p["source"]]
                for p in etc_posts[:20]:
                    st.markdown(f"- [{p['source']}] {p['title'][:60]}")

        if trends:
            st.markdown("**📈 트렌드 키워드**")
            cols = st.columns(5)
            for i, t in enumerate(trends[:10]):
                cols[i % 5].metric(t["keyword"], f"관심도 {t['rank']}")

        if st.button("🔄 크롤링 다시 실행", key="recrawl"):
            with st.spinner("크롤링 중..."):
                result = subprocess.run(
                    [sys.executable, str(BASE_DIR / "1_crawl.py"), date_str],
                    capture_output=True, text=True, cwd=str(BASE_DIR),
                    env={**__import__('os').environ}
                )
            st.rerun()
    else:
        st.info("매일 09:00, 21:00 자동 수집\n\n수동으로 지금 수집하려면 아래 버튼을 누르세요.")
        if st.button("▶ 지금 크롤링 시작", key="crawl_now"):
            with st.spinner("크롤링 중... (약 1~2분)"):
                result = subprocess.run(
                    [sys.executable, str(BASE_DIR / "1_crawl.py"), date_str],
                    capture_output=True, text=True, cwd=str(BASE_DIR),
                    env={**__import__('os').environ}
                )
            if (DATA_DIR / f"{date_str}_crawl_summary.json").exists():
                st.success("수집 완료!")
                st.rerun()
            else:
                st.error(f"수집 실패\n\n{result.stdout[-300:]}\n{result.stderr[-300:]}")


# ══════════════════════════════════════════════════════════════════════════
# STEP 2: 키워드 분석 + 에피소드 아이디어
# ══════════════════════════════════════════════════════════════════════════
with st.expander("🤖 STEP 2 — Gemini 분석 + 에피소드 아이디어", expanded=crawl_done and not analysis_done):
    if not crawl_done:
        st.warning("⬆️ STEP 1 크롤링을 먼저 완료하세요.")
    elif analysis_done:
        analysis_text = analysis_file.read_text(encoding="utf-8")
        st.markdown(analysis_text)

        edited = st.text_area("✏️ 아이디어 수정/메모", value=analysis_text, height=400, key="edit_analysis")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 저장", key="save_analysis"):
                analysis_file.write_text(edited, encoding="utf-8")
                st.success("저장됨!")
        with col2:
            if st.button("🔄 분석 다시 실행", key="reanalyze"):
                analysis_file.unlink(missing_ok=True)
                st.rerun()
    else:
        st.info("Gemini가 오늘의 트렌드를 분석하고 에피소드 아이디어를 생성합니다.")
        if st.button("▶ 분석 시작", key="analyze_now"):
            with st.spinner("Gemini 분석 중..."):
                result = subprocess.run(
                    [sys.executable, str(BASE_DIR / "2_analyze.py"), date_str],
                    capture_output=True, text=True, cwd=str(BASE_DIR),
                    env={**__import__('os').environ}
                )
            if analysis_file.exists():
                st.success("분석 완료!")
                st.rerun()
            else:
                st.error(f"분석 실패\n\n{result.stdout[-300:]}\n{result.stderr[-300:]}")


# ══════════════════════════════════════════════════════════════════════════
# STEP 3: 대본 작성
# ══════════════════════════════════════════════════════════════════════════
with st.expander("📝 STEP 3 — 대본 작성", expanded=analysis_done and not episode_done):
    if not analysis_done:
        st.warning("⬆️ STEP 2 분석을 먼저 완료하세요.")
    else:
        st.info("위 에피소드 아이디어 중 하나를 골라 대본을 생성하거나 직접 작성하세요.")

        idea_input = st.text_area(
            "선택한 에피소드 아이디어 입력",
            placeholder="예) 동물병원 대기실에서 예방접종 맞으러 온 고양이 인터뷰...",
            height=120, key="idea_input"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🤖 AI 대본 생성", key="gen_script") and idea_input:
                with st.spinner("대본 생성 중..."):
                    result = subprocess.run(
                        [sys.executable, "-c",
                         f"""
import sys; sys.path.insert(0, '{BASE_DIR}')
import os; os.chdir('{BASE_DIR}')
from analyze import generate_episode_script
import pathlib
script = generate_episode_script('''{idea_input}''')
pathlib.Path('{episode_file}').write_text(script, encoding='utf-8')
print(script)
"""],
                        capture_output=True, text=True, cwd=str(BASE_DIR),
                        env={**__import__('os').environ}
                    )
                if episode_file.exists():
                    st.rerun()
                else:
                    st.error(result.stderr[-300:])

        if episode_done:
            script_text = episode_file.read_text(encoding="utf-8")
            edited_script = st.text_area("📄 대본 편집", value=script_text, height=500, key="edit_script")
            if st.button("💾 대본 저장", key="save_script"):
                episode_file.write_text(edited_script, encoding="utf-8")
                st.success("저장됨!")


# ══════════════════════════════════════════════════════════════════════════
# STEP 4: 영상 제작 (예정)
# ══════════════════════════════════════════════════════════════════════════
with st.expander("🎬 STEP 4 — 영상 제작 (Coming Soon)", expanded=False):
    st.info("🚧 추후 추가 예정\n\n- AI 음성 합성 (TTS)\n- 자막 자동 생성\n- 영상 편집 자동화")


# ── 사이드바: 최근 기록 ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📅 최근 작업")
    recent = sorted(DATA_DIR.glob("*_crawl_summary.json"), reverse=True)[:7]
    for f in recent:
        d = f.stem.replace("_crawl_summary", "")
        has_analysis = (DATA_DIR / f"{d}_analysis.txt").exists()
        has_episode  = (DATA_DIR / f"{d}_episode.txt").exists()
        status = "🎬" if has_episode else ("🤖" if has_analysis else "🕷️")
        if st.button(f"{status} {d}", key=f"hist_{d}"):
            st.query_params["date"] = d
            st.rerun()

    st.markdown("---")
    st.markdown("### ⚙️ 자동화 상태")
    st.markdown("🟢 크롤러: 09:00, 21:00 KST")
    st.markdown("🔵 분석: 크롤링 후 자동")
