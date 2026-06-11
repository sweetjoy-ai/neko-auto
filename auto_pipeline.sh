#!/bin/bash
# neko-auto 자동 파이프라인
# 크론: 0 0,12 * * * (09:00, 21:00 KST)

set -euo pipefail
APP="/home/ubuntu/mochi-nyang"
LOG="$APP/data/pipeline.log"

cd "$APP"
source venv/bin/activate

echo "" >> "$LOG"
echo "=====================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M')] 파이프라인 시작" >> "$LOG"

# STEP 1: 크롤링
echo "[STEP 1] 크롤링..." >> "$LOG"
python3 1_crawl.py >> "$LOG" 2>&1

# STEP 2: 분석
echo "[STEP 2] 분석..." >> "$LOG"
python3 2_analyze.py >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M')] 파이프라인 완료" >> "$LOG"
