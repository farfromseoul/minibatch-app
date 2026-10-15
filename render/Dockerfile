# MiniBatch render-worker: Remotion 렌더 서버. Remotion 공식 Docker 예시를 따른다 (docs/docker).
FROM node:22.23.3-bookworm-slim

# Chrome Headless Shell 이 쓰는 라이브러리 (공식 목록) + 한국어 글꼴(Noto CJK, 공식 문서 권장)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libnss3 libdbus-1-3 libatk1.0-0 libgbm-dev libasound2 libxrandr2 \
      libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1 libatk-bridge2.0-0 \
      libpango-1.0-0 libcairo2 libcups2 \
      fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN chown node:node /app
USER node

# 잠금 파일 그대로 설치한다 (공식 예시의 npm i 대신 npm ci: 버전이 바뀌지 않는다)
COPY --chown=node:node package.json package-lock.json tsconfig.json remotion.config.ts ./
RUN npm ci --no-audit --no-fund

# Chrome Headless Shell 을 이미지 안에 받아 둔다 (실행 때 내려받지 않게)
RUN npx remotion browser ensure

COPY --chown=node:node src ./src

EXPOSE 8091
# 렌더 서버(server/render-server.ts)는 작업 순서 20에서 생긴다. 지금은 버전 확인만 한다
CMD ["npx", "remotion", "versions"]
