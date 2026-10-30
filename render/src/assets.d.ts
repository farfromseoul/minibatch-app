// 번들러(rspack)가 글꼴 파일 import 를 주소 문자열로 바꾼다 (@remotion/bundler shared-bundler-config, 2026-10-30 확인)
declare module "*.woff2" {
  const src: string;
  export default src;
}
