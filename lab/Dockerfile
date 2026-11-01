# 실습 리뷰 실험 이미지 (실습리뷰쇼츠 아키텍처). 과제 하나를 실행하고 기록을 /work 에 남긴다.
# 실행 옵션(내부망·읽기 전용·권한 제거·프록시)은 맥미니의 실험 실행기(lab-runner)가 정한다.
# 버전 고정: Playwright 1.64.1 (브라우저·Node 포함 공식 이미지), Claude Code 2.1.316 (2026-11-01 npm 조회)
FROM mcr.microsoft.com/playwright:v1.64.1-noble
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils curl jq git \
 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code@2.1.316 && npm cache clean --force
WORKDIR /opt/lab
RUN npm init -y >/dev/null && npm install playwright@1.64.1 && npm cache clean --force
COPY run-task.mjs capture.mjs ./
ENV HOME=/home/lab CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_TELEMETRY=1 ENABLE_CLAUDEAI_MCP_SERVERS=false
USER 1000:1000
CMD ["node", "/opt/lab/run-task.mjs"]
