// 실험 결과물 미리보기 PNG (실습리뷰쇼츠 H5). 영상의 결과물 장면(LArtifact)이 이 그림을 그대로 쓴다.
// html·svg 는 브라우저로 캡처, 이미지는 복사, PDF 는 첫 쪽(pdftoppm). 그 밖의 파일은 미리보기 없음(본문 앞부분은 result.json excerpts).
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const IMAGE = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp"]);
const PAGE = new Set([".html", ".htm", ".svg"]);
const MAX_PREVIEWS = 4;

const outName = (file) => `${file.replace(/[^A-Za-z0-9._-]+/g, "_")}.png`;

export async function capture(files, workspace, previewsDir) {
  const out = [];
  const pages = [];
  for (const f of files) {
    if (out.length + pages.length >= MAX_PREVIEWS) break;
    const ext = path.extname(f.path).toLowerCase();
    const src = path.join(workspace, f.path);
    const dst = path.join(previewsDir, outName(f.path));
    if (IMAGE.has(ext) && f.size < 15_000_000) {
      fs.copyFileSync(src, dst);
      out.push({ path: f.path, preview: path.relative(path.dirname(previewsDir), dst) });
    } else if (ext === ".pdf") {
      const base = dst.replace(/\.png$/, "");
      execFileSync("pdftoppm", ["-png", "-f", "1", "-l", "1", "-r", "80", "-singlefile", src, base], { timeout: 30_000 });
      out.push({ path: f.path, preview: path.relative(path.dirname(previewsDir), `${base}.png`) });
    } else if (PAGE.has(ext)) {
      pages.push({ f, src, dst });
    }
  }
  if (pages.length) {
    const { chromium } = await import("playwright");
    // 컨테이너가 바깥 울타리다(권한 제거·읽기 전용). 브라우저 자체 샌드박스는 그 안에서 못 쓴다
    const browser = await chromium.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
    try {
      const page = await browser.newPage({ viewport: { width: 900, height: 1200 }, deviceScaleFactor: 1 });
      for (const { f, src, dst } of pages) {
        await page.goto(`file://${src}`, { waitUntil: "load", timeout: 15_000 });
        await page.screenshot({ path: dst });
        out.push({ path: f.path, preview: path.relative(path.dirname(previewsDir), dst) });
      }
    } finally {
      await browser.close();
    }
  }
  return out;
}
