// render-worker 진입점. 설정은 환경 변수로 받는다.
import { existsSync } from "node:fs";
import path from "node:path";

import { bundle } from "@remotion/bundler";

import { createApiServer, createFileServer } from "./app.ts";

const env = process.env;
const dataDir = env.MINIBATCH_DATA_DIR ?? "/data";
const port = Number(env.MINIBATCH_RENDER_PORT ?? 8091);
const filePort = Number(env.MINIBATCH_RENDER_FILE_PORT ?? 8092);
const concurrency = Number(env.MINIBATCH_RENDER_CONCURRENCY ?? 2); // 아키텍처 D13
const appDir = path.resolve(import.meta.dirname, "..");

// 이미지 빌드 때 만든 번들(build/)을 쓴다. 없으면(개발 중) 시작할 때 만든다
let serveUrl = path.join(appDir, "build");
if (!existsSync(path.join(serveUrl, "index.html"))) {
  console.log("번들이 없어 새로 만든다 (수십 초)");
  serveUrl = await bundle({ entryPoint: path.join(appDir, "src", "index.ts"), rspack: true });
}

createFileServer(dataDir).listen(filePort, "127.0.0.1");
createApiServer({ dataDir, serveUrl, port, filePort, concurrency }).listen(port, "0.0.0.0", () => {
  console.log(`render-worker :${port} (번들 ${serveUrl}, 동시성 ${concurrency})`);
});
