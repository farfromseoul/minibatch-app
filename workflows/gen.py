# -*- coding: utf-8 -*-
"""MiniBatch n8n C 워크플로 4개 JSON 생성 (작업 순서 24, 아키텍처 D2·D27). n8n 2.43.6 노드 정의에 맞춤."""
import json
import pathlib
import re
import uuid

OUT = pathlib.Path(__file__).parent  # 저장소 workflows/ 에 바로 쓴다
DECIDE = (pathlib.Path(__file__).parent / "decide.mjs").read_text(encoding="utf-8").replace("export function", "function")

API = {"httpHeaderAuth": {"id": "mbJobApi0000001", "name": "MiniBatch job-api"}}
TG = {"telegramApi": {"id": "mbTelegram00001", "name": "MiniBatch 텔레그램"}}
SETTINGS = {"executionOrder": "v1", "timezone": "Asia/Seoul", "saveManualExecutions": True,
            "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all"}

CONFIG_JS = """// 설정: 여기 한 곳만 고친다. 텔레그램 chat id 는 비밀 값이 아니다 (봇 토큰은 자격 증명 'MiniBatch 텔레그램' 에)
return [{ json: {
  api: 'http://job-api:8080',                 // compose 안의 job-api 주소
  chatId: 'CHAT_ID_를_여기에',                 // 25번 ③에서 확인한 내 chat id (숫자)
  formBase: 'http://localhost:5678/form',     // 승인 폼 주소 (이 MacBook 브라우저에서 연다)
  category: 'ai-it',
} }];"""


class WF:
    def __init__(self, name):
        self.name, self.nodes, self.conn, self.x = name, [], {}, 0

    def add(self, name, type_, version, params, pos, creds=None, **extra):
        n = {"parameters": params, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.name}/{name}")), "name": name,
             "type": type_, "typeVersion": version, "position": pos}
        if creds:
            n["credentials"] = creds
        n.update(extra)
        self.nodes.append(n)
        return name

    def link(self, a, b, out=0, inp=0):
        outs = self.conn.setdefault(a, {"main": []})["main"]
        while len(outs) <= out:
            outs.append([])
        outs[out].append({"node": b, "type": "main", "index": inp})

    def save(self, fname, active=False, about=None, notes=None):
        """about: 워크플로 왼쪽 위에 붙이는 '전체 흐름' 메모. notes: 노드 이름 → 역할 (노드 아래에 보인다, 2026-10-20 사용자)"""
        for n in self.nodes:
            if notes and n["name"] in notes:
                n["notes"], n["notesInFlow"] = notes[n["name"]], True
        assert not notes or set(notes) <= {n["name"] for n in self.nodes}, set(notes) - {n["name"] for n in self.nodes}
        if about:
            xs = [n["position"][0] for n in self.nodes]
            ys = [n["position"][1] for n in self.nodes]
            height = 80 + 22 * about.count("\n")
            self.add("전체 흐름", "n8n-nodes-base.stickyNote", 1,
                     {"content": about, "width": 760, "height": height, "color": 5},
                     [min(xs), min(ys) - height - 60])
        data = {"name": self.name, "nodes": self.nodes, "connections": self.conn, "settings": SETTINGS,
                "active": active, "pinData": {}, "tags": [], "meta": {"templateCredsSetupCompleted": False}}
        (OUT / fname).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def code(wf, name, js, pos):
    return wf.add(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)


def http(wf, name, method, url, pos, body=None, auth=True, full=False, timeout=60000, on_error=None):
    p = {"method": method, "url": url}
    if auth:
        p.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
    if body is not None:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    p["options"] = {"timeout": timeout, "response": {"response": {"neverError": True, "fullResponse": full}}}
    extra = {"onError": on_error} if on_error else {}
    return wf.add(name, "n8n-nodes-base.httpRequest", 4.2, p, pos, API if auth else None, **extra)


def telegram(wf, name, text, pos):
    # 텔레그램 노드는 parse_mode 를 비우면 Markdown(Legacy)로 보낸다. 오류 코드의 '_'(no_candidates 등)가 짝 없는 서식으로
    # 읽혀 400 "can't parse entities" → 워크플로가 멈췄다 (2026-10-18). HTML 로 보내고 &·<·> 만 바꾼다
    assert text.startswith("={{") and text.endswith("}}"), text
    escaped = "={{ String(" + text[3:-2].strip() + ").replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }}"
    return wf.add(name, "n8n-nodes-base.telegram", 1.2,
                  {"chatId": "={{ $('설정').first().json.chatId }}", "text": escaped,
                   "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"}}, pos, TG)


def switch(wf, name, expr, n, pos):
    return wf.add(name, "n8n-nodes-base.switch", 3.2, {"mode": "expression", "numberOutputs": n, "output": expr}, pos)


def cron(wf, name, exprs, pos):
    return wf.add(name, "n8n-nodes-base.scheduleTrigger", 1.2,
                  {"rule": {"interval": [{"field": "cronExpression", "expression": e} for e in exprs]}}, pos)


def manual(wf, pos):
    return wf.add("수동 실행", "n8n-nodes-base.manualTrigger", 1, {}, pos)


def form_trigger(wf, name, path, title, desc, pos):
    return wf.add(name, "n8n-nodes-base.formTrigger", 2.3,
                  {"path": path, "formTitle": title, "formDescription": desc,
                   "formFields": {"values": [{"fieldLabel": "승인자", "placeholder": "운영자", "requiredField": True}]},
                   "options": {"buttonLabel": "목록 열기", "appendAttribution": False}},
                  pos, webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, f"minibatch/{path}")))


def form_page(wf, name, title, desc, pos):
    return wf.add(name, "n8n-nodes-base.form", 2.5,
                  {"operation": "page", "defineForm": "json", "jsonOutput": "={{ JSON.stringify($json.fields) }}",
                   "options": {"formTitle": title, "formDescription": desc, "buttonLabel": "제출"}}, pos)


def form_done(wf, name, title, message, pos):
    return wf.add(name, "n8n-nodes-base.form", 2.5,
                  {"operation": "completion", "respondWith": "text", "completionTitle": title,
                   "completionMessage": message, "options": {}}, pos)



# ---------------------------------------------------------------- 설명 (2026-10-20 사용자: 워크플로마다 용도와 노드 역할이 보이게)
ABOUT1 = "## 1. 생산 (하루 10편)\n**언제**: 매일 06~23시 매시 정각, 텔레그램 /run (job-api 가 이미 돌고 있으면 막는다), 수동 실행\n**하는 일**: ① job-api 에 '이어 할 작업'을 묻고, 없으면 새 작업(진행 중 시리즈의 다음 화, 없으면 단독 주제)을 만든다 ② 그 작업을 주제→대본→대본 검토→장면→음성→타임라인→소재→렌더→품질 검사→업로드 순서로 한 단계씩 요청한다 ③ 업로드가 끝나면 job-api 가 텔레그램으로 [승인(공개)][반려] 를 보낸다(이 워크플로는 다음 작업으로)\n**막히면**: 업로드 한도·앞 화 업로드 대기는 그 작업을 두고 다음 작업으로 넘어간다. 실패는 텔레그램 '⚠️ MiniBatch 실패'\n**지금 상태 보기**: 0번 현황 폼, 텔레그램 /status (화별: 아직 안 만듦·만드는 중·한도 대기·검토 대기·공개)"
NOTES1 = {
    '지금 생산 (텔레그램 /run)': 'POST /webhook/minibatch-produce-now: job-api 가 텔레그램 /run 을 받으면 부른다',
    '설정': 'job-api 주소·chat id·카테고리. 여기 한 곳만 고친다',
    '단계 순서': 'GET /pipeline: 단계 이름 순서',
    '이어 할 작업': 'GET /jobs/next: 끝나지 않았고 기다릴 이유가 없는 작업 하나',
    '이어 할 작업 있나': '있으면 그 작업, 없으면 새 작업 만들기',
    '새 작업 만들기': 'POST /jobs: 진행 중 시리즈의 다음 화(없으면 단독 주제)',
    '새 작업 결과': '201=새 작업. 409=하루 한도·검토 적체·앞 화 제작 중·후보 없음',
    '만들었나': '만들었으면 진행, 알릴 이유면 텔레그램, 아니면 끝',
    '알림: 만들지 않음': '후보 없음·검토 적체만 알린다',
    '작업 정함': '이번에 진행할 작업 ID',
    '작업 상태': 'GET /jobs/{id}: 단계별 시도 기록',
    '다음 행동': '다음에 실행할 단계·기다림·되돌리기·실패를 정한다 (decide.mjs)',
    '행동': 'next=다음 작업, fail=실패 알림, stop=끝, 그 밖=기다렸다 요청',
    '다음 작업으로': '검토 대기가 됐거나 한도·앞 화를 기다리는 작업은 두고 다음 작업',
    '알림: 실패': '단계가 실패하면 텔레그램으로 알린다',
    '기다리기': '단계가 끝나길 잠깐 기다린다',
    '요청 종류': 'run=단계 실행, reset=앞 단계부터 다시',
    '단계 요청': 'POST /jobs/{id}/steps/{step}',
    '되돌리기': 'POST /jobs/{id}/reset?from=: 품질 검사 실패 등',
}
ABOUT2 = '## 2. 영상 검토 폼 (예비)\n**언제**: 폼 주소를 열 때만 (평소에는 텔레그램 [승인(공개)][반려] 버튼을 쓴다)\n**하는 일**: 검토 대기(REVIEW) 영상을 시리즈·화 순서로 보여 주고 승인(바로 공개)·반려·보류를 받는다. 시리즈는 앞 화부터 승인해야 한다\n**지금 상태 보기**: 0번 현황 폼, 텔레그램 /status'
NOTES2 = {
    '검토 대기 목록': 'GET /jobs?status=REVIEW',
    '폼 만들기': '영상 링크 + 승인/반려/보류 선택',
    '처리 목록': '고른 것을 화 순서대로',
    '승인·반려 요청': 'POST /jobs/{id}/approve 또는 reject',
    '결과 정리': '공개 결과를 한 줄씩',
}
ABOUT3 = "## 3. 시리즈 계획\n**위 흐름 (매시 50분)**: 승인 대기 계획이 없고 진행 중 시리즈의 남은 화가 10편보다 적으면 job-api 에 '주제 묻기'를 요청 → job-api 가 하루 한 번 텔레그램으로 주제·화 수를 묻는다(D37)\n→ 답 `주제, 화수`, [자동으로 정하기], `/series 주제, 화수` 가 오면 job-api 가 계획을 만들고 [계획 승인] 메시지를 보낸다 → 승인하면 앞 시리즈가 끝난 뒤 1화부터 생산\n**아래 흐름 (폼)**: 텔레그램 대신 브라우저에서 승인 대기 계획을 보고 승인한다\n**지금 상태 보기**: 0번 현황 폼의 [다음 계획](승인 대기·텔레그램 보낸 시각)과 [주제 질문] 줄, 텔레그램 /status"
NOTES3 = {
    '시리즈 목록': 'GET /series: 시리즈별 남은 화 수',
    '계획이 필요한가': '승인 대기 계획이 있으면 멈춤. 남은 화 10 미만이면 진행',
    '주제 묻기 (텔레그램)': 'POST /series/request: 오늘 안 물었으면 텔레그램으로 묻는다(하루 한 번)',
    '알림 문장': '실패만 텔레그램으로',
    '승인 대기 계획': 'GET /series?status=PROPOSED',
    '계획 폼 만들기': '계획 내용 + 보류/승인',
    '계획 승인 요청': 'POST /series/{id}/approve',
}
ABOUT4 = "## 4. 상태 감시\n**언제**: 5분마다\n**하는 일**: job-api /healthz 를 보고 새 경고(디스크, YouTube 토큰 만료 임박, 작업자 응답 없음 등)만 텔레그램으로 보낸다. 같은 경고는 한 번, 사라지면 '회복'\n**영상·시리즈 진행 상태는 여기 없다**: 0번 현황 폼, 텔레그램 /status"
NOTES4 = {
    'healthz': 'GET /healthz: 서비스·토큰·디스크 점검',
    '새 경고인가': '지난번과 다를 때만 알린다',
}
ABOUT5 = '## 5. 취소 폼\n**언제**: 폼 주소를 열 때만\n**하는 일**: 공개 전 작업과 끝나지 않은 시리즈(승인 대기 계획 포함)를 취소한다. 이미 올린 비공개 영상은 YouTube 에 그대로 남는다\n**지금 상태 보기**: 0번 현황 폼, 텔레그램 /status'
NOTES5 = {
    '작업 목록': 'GET /jobs',
    '시리즈 목록': 'GET /series',
    '폼 만들기': '취소할 수 있는 것만 유지/취소로',
    '취소 목록': '시리즈 먼저, 그다음 작업',
}
ABOUT6 = '## 6. ASMR 확인 (D38)\n**언제**: 매시 정각 (수동 실행도 됨)\n**하는 일**: job-api 에 inbox 확인을 요청한다. 새 영상은 job-api 가 텔레그램으로 미리보기 + [업로드 승인][버리기] 를 보내고, 승인되면 비공개 업로드 → [공개 승인] → 공개. 하루 3편, 넘으면 다음 날\n**파일 위치**: 맥미니 ~/minibatch-data/asmr/ inbox → uploaded → published (버린 것 rejected)\n**지금 상태 보기**: 0번 현황 폼 [ASMR] 줄, 텔레그램 /status, GET /asmr/videos'
NOTES6 = {
    'inbox 확인': 'POST /asmr/scan: 새 영상 승인 요청 + 승인된 영상 올리기',
    '알림 문장': '실패만 텔레그램으로',
}

# ---------------------------------------------------------------- 0. 현황 보기 (2026-10-20)
w = WF("MiniBatch 0 현황 보기")
ft = w.add("현황 폼", "n8n-nodes-base.formTrigger", 2.3,
           {"path": "minibatch-status", "formTitle": "MiniBatch 현황",
            "formDescription": "시리즈 화별 상태, 다음 계획, 주제 질문, ASMR 을 한 번에 봅니다. 텔레그램 /status 와 같은 내용입니다.",
            "formFields": {"values": [{"fieldLabel": "메모", "placeholder": "비워도 됩니다", "requiredField": False}]},
            "options": {"buttonLabel": "현황 보기", "appendAttribution": False}},
           [0, 0], webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "minibatch/minibatch-status")))
cfg = code(w, "설정", CONFIG_JS, [220, 0])
ov = http(w, "현황 가져오기", "GET", "={{ $('설정').first().json.api }}/overview", [440, 0])
mk = code(w, "현황 화면 만들기", """// job-api 가 만든 요약(text)을 그대로 보여 준다
const esc = s => String(s ?? '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
const r = $input.first().json;
const html = r.text ? `<pre style="white-space:pre-wrap;font-size:14px;line-height:1.5">${esc(r.text)}</pre>`
                    : `<p>job-api 응답 없음: ${esc(JSON.stringify(r).slice(0, 300))}</p>`;
return [{ json: { fields: [{ fieldType: 'html', fieldName: 'status', html }] } }];""", [660, 0])
pg = form_page(w, "현황 화면", "MiniBatch 현황", "다시 보려면 폼 주소를 새로 엽니다.", [880, 0])
done = form_done(w, "끝", "닫았습니다", "다시 보려면 폼 주소를 새로 엽니다.", [1100, 0])
for a, b in [(ft, cfg), (cfg, ov), (ov, mk), (mk, pg), (pg, done)]:
    w.link(a, b)
w.save("minibatch-0-status.json", about="""## 0. 현황 보기
**언제**: 폼 주소를 열 때 (텔레그램에서는 /status)
**보여 주는 것**: ① 진행 중 시리즈의 화별 상태: 아직 안 만듦 · 만드는 중(단계) · 한도 대기(다음 시도 시각) · 앞 화 기다림 · 검토 대기(비공개 업로드됨) · 공개 ② 다음 계획: 승인 대기 · 텔레그램 보낸 시각 ③ 주제 질문 상태 ④ 단독 영상 ⑤ ASMR 대기 수 ⑥ 오늘 업로드 수
**자세히**: 작업 하나는 GET /jobs/{id} (단계별 시도·오류), n8n 실행 기록은 1번 워크플로 Executions""",
       notes={"현황 가져오기": "GET /overview (읽기만 한다)", "현황 화면 만들기": "요약 글을 그대로 보여 준다"})

# ---------------------------------------------------------------- 1. 생산
w = WF("MiniBatch 1 생산 (하루 10편)")
t1 = cron(w, "매일 06시 몰아서, 07~23시 매시 이어서", ["0 0 6-23 * * *"], [0, 0])
t2 = manual(w, [0, 200])
# 텔레그램 /run (2026-10-31): job-api 가 내부망으로 부른다(n8n 포트는 맥미니 127.0.0.1 에만 열려 있다). 겹침 검사는 job-api 가 한다
t3 = w.add("지금 생산 (텔레그램 /run)", "n8n-nodes-base.webhook", 2,
           {"httpMethod": "POST", "path": "minibatch-produce-now", "responseMode": "onReceived", "options": {}},
           [0, -200], webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "minibatch/minibatch-produce-now")))
cfg = code(w, "설정", CONFIG_JS, [220, 100])
pipe = http(w, "단계 순서", "GET", "={{ $('설정').first().json.api }}/pipeline", [440, 100])
# 이어 할 작업은 job-api 가 정한다 (D31): 끝나지 않은 작업 중 기다릴 이유(업로드 한도, 앞 화 업로드 전)가 없는 것. 없으면 새 작업
jobs = http(w, "이어 할 작업", "GET", "={{ $('설정').first().json.api }}/jobs/next", [660, 100])
sw0 = switch(w, "이어 할 작업 있나", "={{ $json.jobId ? 0 : 1 }}", 2, [1100, 100])
new = http(w, "새 작업 만들기", "POST", "={{ $('설정').first().json.api }}/jobs", [1320, 260], body="={}", full=True)
newr = code(w, "새 작업 결과", """// 201 이면 새 작업. 409 는 하루 한도·검토 적체·앞 화 제작 중·후보 없음 (D15·D27)
const r = $input.first().json;
if (r.statusCode === 201) return [{ json: { jobId: r.body.id } }];
const code = r.body?.error?.code || String(r.statusCode);
const msg = r.body?.error?.message || '';
const notify = ['no_candidates', 'review_backlog_full'].includes(code)
  ? `ℹ️ MiniBatch: 새 작업을 만들지 않음 (${code})\\n${msg}` : null;
return [{ json: { jobId: null, code, notify } }];""", [1540, 260])
sw1 = switch(w, "만들었나", "={{ $json.jobId ? 0 : ($json.notify ? 1 : 2) }}", 3, [1760, 260])
tgn = telegram(w, "알림: 만들지 않음", "={{ $json.notify }}", [1980, 400])
end0 = w.add("끝(할 일 없음)", "n8n-nodes-base.noOp", 1, {}, [1980, 560])
fix = code(w, "작업 정함", "return [{ json: { jobId: $input.first().json.jobId } }];", [2200, 100])
st = http(w, "작업 상태", "GET", "={{ $('설정').first().json.api }}/jobs/{{ $('작업 정함').first().json.jobId }}", [2420, 100])
dec = code(w, "다음 행동", DECIDE + """
// ---- n8n 에서 부르는 부분 (위 함수는 decide.test.mjs 로 시험)
const job = $input.first().json;
const pipeline = $('단계 순서').first().json.steps;
const d = decide(job, pipeline, { now: new Date(), runIndex: $runIndex, maxRuns: 360, maxResets: 2 });
return [{ json: { ...d, jobId: job.id, topic: job.topic, seriesId: job.seriesId,
                  episodeNumber: job.episodeNumber, url: job.publication?.url || null } }];""", [2640, 100])
sw2 = switch(w, "행동", "={{ ({ done: 0, next: 0, fail: 1, stop: 2 })[$json.action] ?? 3 }}", 4, [2860, 100])
nxt = w.add("다음 작업으로", "n8n-nodes-base.noOp", 1, {}, [3080, -160])  # 검토 대기 알림은 job-api 가 [승인][반려] 버튼과 함께 보낸다 (D28). next: 기다리는 작업은 두고 (D31)
tgf = telegram(w, "알림: 실패", "={{ `⚠️ MiniBatch 실패: ${$json.topic} (${$json.jobId})\\n${$json.message}` }}", [3080, 20])
end1 = w.add("끝(멈춤)", "n8n-nodes-base.noOp", 1, {}, [3080, 180])
wt = w.add("기다리기", "n8n-nodes-base.wait", 1.1, {"amount": "={{ Math.max(1, $json.waitSec || 1) }}", "unit": "seconds"},
           [3080, 340], webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "minibatch/produce-wait")))
sw3 = switch(w, "요청 종류", "={{ ({ run: 0, reset: 1 })[$json.action] ?? 2 }}", 3, [3300, 340])
req = http(w, "단계 요청", "POST", "={{ $('설정').first().json.api }}/jobs/{{ $json.jobId }}/steps/{{ $json.step }}",
           [3520, 260], body="={}")
rst = http(w, "되돌리기", "POST", "={{ $('설정').first().json.api }}/jobs/{{ $json.jobId }}/reset?from={{ $json.from }}", [3520, 440])
for a, b in [(t1, cfg), (t2, cfg), (t3, cfg), (cfg, pipe), (pipe, jobs), (jobs, sw0), (new, newr), (newr, sw1),
             (fix, st), (st, dec), (dec, sw2), (nxt, jobs), (wt, sw3), (req, st), (rst, st)]:
    w.link(a, b)
w.link(sw0, fix, 0); w.link(sw0, new, 1)
w.link(sw1, fix, 0); w.link(sw1, tgn, 1); w.link(sw1, end0, 2)
w.link(sw2, nxt, 0); w.link(sw2, tgf, 1); w.link(sw2, end1, 2); w.link(sw2, wt, 3)
w.link(sw3, req, 0); w.link(sw3, rst, 1); w.link(sw3, st, 2)
w.save("minibatch-1-produce.json", about=ABOUT1, notes=NOTES1)

# ---------------------------------------------------------------- 2. 영상 검토 폼
w = WF("MiniBatch 2 영상 검토 폼")
ft = form_trigger(w, "영상 검토 폼", "minibatch-review", "MiniBatch 영상 검토",
                  "검토 대기 영상을 승인(바로 공개)·반려합니다. 시리즈는 앞 화부터 승인해야 뒤 화 승인이 됩니다.", [0, 0])
cfg = code(w, "설정", CONFIG_JS, [220, 0])
lst = http(w, "검토 대기 목록", "GET", "={{ $('설정').first().json.api }}/jobs?status=REVIEW", [440, 0])
spl = code(w, "작업 하나씩", """const items = $input.first().json.items || [];
return items.length ? items.map(j => ({ json: { id: j.id } })) : [{ json: { id: null } }];""", [660, 0])
det = http(w, "작업 상세", "GET", "={{ $('설정').first().json.api }}/jobs/{{ $json.id || 'none' }}", [880, 0])
mk = code(w, "폼 만들기", """// 시리즈·화 순서대로 보여 준다. 화마다 영상 링크와 승인/반려/보류, 반려 사유
const esc = s => String(s ?? '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
const jobs = $input.all().map(i => i.json).filter(j => j && j.id && j.status === 'REVIEW');
jobs.sort((a, b) => (a.seriesId || '~').localeCompare(b.seriesId || '~') || (a.episodeNumber || 0) - (b.episodeNumber || 0)
                    || a.createdAt.localeCompare(b.createdAt));
if (!jobs.length) return [{ json: { empty: true, fields: [] } }];
const fields = [];
for (const j of jobs) {
  const vid = j.publication?.videoId;
  const head = j.seriesId ? `${esc(j.seriesId)} ${j.episodeNumber}화` : '단독 주제';
  const links = vid ? `<a href="https://www.youtube.com/shorts/${vid}" target="_blank">영상 보기(비공개)</a> · <a href="https://studio.youtube.com/video/${vid}/edit" target="_blank">Studio</a>` : '영상 없음';
  fields.push({ fieldType: 'html', fieldName: `h_${j.id}`, html: `<h3>${head}: ${esc(j.topic)}</h3><p>${links} · ${esc(j.id)}</p>` });
  fields.push({ fieldType: 'dropdown', fieldName: j.id, fieldLabel: `${head} 결정`,
                fieldOptions: { values: [{ option: '보류' }, { option: '승인' }, { option: '반려' }] }, requiredField: true });
  fields.push({ fieldType: 'text', fieldName: `${j.id}__reason`, fieldLabel: '반려 사유 (반려일 때)' });
}
return [{ json: { empty: false, fields, order: jobs.map(j => j.id) } }];""", [1100, 0])
sw = switch(w, "검토할 영상 있나", "={{ $json.empty ? 1 : 0 }}", 2, [1320, 0])
pg = form_page(w, "검토 화면", "MiniBatch 영상 검토", "시리즈는 앞 화부터 승인해야 합니다. 앞 화를 보류하면 같은 시리즈 뒤 화 승인은 거절됩니다.", [1540, -100])
none = form_done(w, "끝: 검토 대기 없음", "검토 대기 영상이 없습니다", "새 영상이 만들어지면 텔레그램으로 알립니다.", [1540, 160])
plan = code(w, "처리 목록", """// 폼에서 고른 것을 화 순서대로 요청 목록으로 만든다 (보류는 빼고)
const by = $('검토 화면').first().json;
const who = $('영상 검토 폼').first().json['승인자'] || '운영자';
const out = [];
for (const id of $('폼 만들기').first().json.order) {
  const d = by[id];
  if (d === '승인') out.push({ json: { jobId: id, path: 'approve', body: { approvedBy: who } } });
  if (d === '반려') out.push({ json: { jobId: id, path: 'reject', body: { rejectedBy: who, reason: by[`${id}__reason`] || '사유 없음' } } });
}
return out.length ? out : [{ json: { jobId: null } }];""", [1760, -100])
sw2 = switch(w, "처리할 것 있나", "={{ $json.jobId ? 0 : 1 }}", 2, [1980, -100])
loop = w.add("한 화씩", "n8n-nodes-base.splitInBatches", 3, {"batchSize": 1, "options": {}}, [2200, -200])
do = http(w, "승인·반려 요청", "POST", "={{ $('설정').first().json.api }}/jobs/{{ $json.jobId }}/{{ $json.path }}", [2420, -120],
          body="={{ JSON.stringify($json.body) }}", full=True, timeout=120000)
res = code(w, "결과 정리", """// 요청 목록과 응답을 차례로 맞춘다
const req = $('처리 목록').all().map(i => i.json);
const res = $input.all().map(i => i.json);
const lines = req.map((r, i) => {
  const x = res[i] || {};
  const ok = x.statusCode === 200;
  const pub = x.body?.publish;
  const tail = ok ? (r.path === 'approve' ? (pub?.ok ? `→ ${pub.status}` : `승인됨, 공개 실패: ${pub?.error || pub?.skipped || ''}`) : '→ 반려')
                  : `실패: ${x.body?.error?.message || x.statusCode}`;
  return `${r.jobId} ${r.path === 'approve' ? '승인' : '반려'} ${tail}`;
});
return [{ json: { message: lines.join('\\n') } }];""", [2420, -320])
done = form_done(w, "끝: 결과", "처리했습니다", "={{ $json.message }}", [2640, -320])
nothing = form_done(w, "끝: 바꾼 것 없음", "바꾼 것이 없습니다", "모두 보류했습니다.", [2200, 60])
for a, b in [(ft, cfg), (cfg, lst), (lst, spl), (spl, det), (det, mk), (mk, sw), (pg, plan), (plan, sw2), (do, loop), (res, done)]:
    w.link(a, b)
w.link(sw, pg, 0); w.link(sw, none, 1)
w.link(sw2, loop, 0); w.link(sw2, nothing, 1)
w.link(loop, res, 0); w.link(loop, do, 1)
w.save("minibatch-2-review-form.json", about=ABOUT2, notes=NOTES2)

# ---------------------------------------------------------------- 3. 시리즈 계획 (만들기 + 승인 폼)
w = WF("MiniBatch 3 시리즈 계획")
t1 = cron(w, "매시 50분 (남은 화 확인)", ["0 50 5-22 * * *"], [0, 0])
t2 = manual(w, [0, 200])
cfg = code(w, "설정", CONFIG_JS, [220, 100])
lst = http(w, "시리즈 목록", "GET", "={{ $('설정').first().json.api }}/series", [440, 100])
need = code(w, "계획이 필요한가", """// 승인 대기 계획이 없고, 진행 중 시리즈의 남은 화가 하루치(10)보다 적으면 새 계획 (D27)
const items = $input.first().json.items || [];
if (items.some(s => s.status === 'PROPOSED')) return [];
const left = items.filter(s => ['APPROVED', 'ACTIVE'].includes(s.status)).reduce((n, s) => n + (s.counts?.planned || 0), 0);
return left >= 10 ? [] : [{ json: { left } }];""", [660, 100])
# D37: 계획을 바로 만들지 않고 텔레그램으로 주제·화 수를 묻는다. job-api 가 하루 한 번만 묻고, 답이 오면 계획을 만든다
mkp = http(w, "주제 묻기 (텔레그램)", "POST", "={{ $('설정').first().json.api }}/series/request", [880, 100],
           body="={{ JSON.stringify({ category: $('설정').first().json.category, episodeCount: 10 }) }}", full=True)
msg = code(w, "알림 문장", """// 묻기는 job-api 가 텔레그램으로 보낸다 (D37). 여기서는 실패만 알린다 (오늘 이미 물었으면 asked=false 로 200)
const r = $input.first().json;
if (r.statusCode === 200) return [];
return [{ json: { text: `⚠️ MiniBatch 다음 시리즈 주제 묻기 실패 (${r.statusCode}): ${r.body?.error?.message || ''}` } }];""", [1100, 100])
tg = telegram(w, "알림: 계획", "={{ $json.text }}", [1320, 100])
for a, b in [(t1, cfg), (t2, cfg), (cfg, lst), (lst, need), (need, mkp), (mkp, msg), (msg, tg)]:
    w.link(a, b)

ft = form_trigger(w, "시리즈 계획 승인 폼", "minibatch-series", "MiniBatch 시리즈 계획",
                  "LLM 이 만든 시리즈 계획을 보고 승인합니다. 승인한 시리즈는 다음 생산 일정부터 1화씩 만들어집니다.", [0, 500])
cfg2 = code(w, "설정 ", CONFIG_JS, [220, 500])
pl = http(w, "승인 대기 계획", "GET", "={{ $('설정 ').first().json.api }}/series?status=PROPOSED", [440, 500])
sp = code(w, "계획 하나씩", """const items = $input.first().json.items || [];
return items.length ? items.map(s => ({ json: { id: s.id } })) : [{ json: { id: null } }];""", [660, 500])
sd = http(w, "계획 상세", "GET", "={{ $('설정 ').first().json.api }}/series/{{ $json.id || 'none' }}", [880, 500])
mk = code(w, "계획 폼 만들기", """const esc = s => String(s ?? '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
const list = $input.all().map(i => i.json).filter(s => s && s.id && s.status === 'PROPOSED');
if (!list.length) return [{ json: { empty: true, fields: [] } }];
const fields = [];
for (const s of list) {
  const chars = (s.bible?.characters || []).map(c => `${esc(c.name)}(${esc(c.role)})`).join(', ');
  const eps = (s.episodes || []).map(e => `<li><b>${esc(e.title)}</b> — ${esc(e.outline)}</li>`).join('');
  fields.push({ fieldType: 'html', fieldName: `h_${s.id}`,
                html: `<h3>${esc(s.title)}</h3><p>${esc(s.bible?.premise)}</p><p>인물: ${chars} · 말투: ${esc(s.bible?.tone)}</p><ol>${eps}</ol>` });
  fields.push({ fieldType: 'dropdown', fieldName: s.id, fieldLabel: `${s.title} 결정`,
                fieldOptions: { values: [{ option: '보류' }, { option: '승인' }] }, requiredField: true });
}
return [{ json: { empty: false, fields, order: list.map(s => s.id) } }];""", [1100, 500])
sw = switch(w, "승인할 계획 있나", "={{ $json.empty ? 1 : 0 }}", 2, [1320, 500])
pg = form_page(w, "계획 화면", "MiniBatch 시리즈 계획", "고칠 곳이 있으면 보류하고 알려 주세요(계획 수정은 API 로).", [1540, 400])
none = form_done(w, "끝: 승인 대기 계획 없음", "승인 대기 계획이 없습니다", "남은 화가 10편보다 적어지면 텔레그램으로 다음 시리즈 주제를 묻습니다(하루 한 번).", [1540, 660])
plan = code(w, "승인 목록", """const by = $('계획 화면').first().json;
const who = $('시리즈 계획 승인 폼').first().json['승인자'] || '운영자';
const out = $('계획 폼 만들기').first().json.order.filter(id => by[id] === '승인').map(id => ({ json: { id, approvedBy: who } }));
return out.length ? out : [{ json: { id: null } }];""", [1760, 400])
sw2 = switch(w, "승인할 것 있나", "={{ $json.id ? 0 : 1 }}", 2, [1980, 400])
ap = http(w, "계획 승인 요청", "POST", "={{ $('설정 ').first().json.api }}/series/{{ $json.id }}/approve", [2200, 320],
          body="={{ JSON.stringify({ approvedBy: $json.approvedBy }) }}", full=True)
res = code(w, "승인 결과", """const lines = $input.all().map(i => i.json).map(x => x.statusCode === 200 ? `${x.body.title} → ${x.body.status}` : `실패: ${x.body?.error?.message || x.statusCode}`);
return [{ json: { message: lines.join('\\n') } }];""", [2420, 320])
done = form_done(w, "끝: 승인 결과", "처리했습니다", "={{ $json.message }}", [2640, 320])
nothing = form_done(w, "끝: 바꾼 것 없음", "바꾼 것이 없습니다", "모두 보류했습니다.", [2200, 520])
for a, b in [(ft, cfg2), (cfg2, pl), (pl, sp), (sp, sd), (sd, mk), (mk, sw), (pg, plan), (plan, sw2), (ap, res), (res, done)]:
    w.link(a, b)
w.link(sw, pg, 0); w.link(sw, none, 1)
w.link(sw2, ap, 0); w.link(sw2, nothing, 1)
w.save("minibatch-3-series-plan.json", about=ABOUT3, notes=NOTES3)

# ---------------------------------------------------------------- 4. 상태 감시
w = WF("MiniBatch 4 상태 감시")
t1 = w.add("5분마다", "n8n-nodes-base.scheduleTrigger", 1.2,
           {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, [0, 0])
cfg = code(w, "설정", CONFIG_JS, [220, 0])
hz = http(w, "healthz", "GET", "={{ $('설정').first().json.api }}/healthz", [440, 0], auth=False, timeout=15000,
          on_error="continueRegularOutput")
judge = code(w, "새 경고인가", """// 같은 경고는 한 번만 보낸다. 사라지면 '회복'. 갱신 토큰 6일째 경고도 여기로 온다 (테스트 상태, 7일 만료)
const st = $getWorkflowStaticData('global');
const r = $input.first().json;
let problems = [];
if (r.error || !r.status) problems = [`job-api 응답 없음: ${r.error?.message || JSON.stringify(r.error || r).slice(0, 200)}`];
else {
  if (r.status !== 'ok') problems.push(`상태 ${r.status}`);
  problems = problems.concat(r.warnings || []);
}
const key = problems.join(' | ');
if (key === (st.last || '')) return [];
st.last = key;
return [{ json: { text: key ? `⚠️ MiniBatch 상태 경고\\n- ${problems.join('\\n- ')}` : '✅ MiniBatch 상태 회복 (경고 없음)' } }];""", [660, 0])
tg = telegram(w, "알림: 상태", "={{ $json.text }}", [880, 0])
for a, b in [(t1, cfg), (cfg, hz), (hz, judge), (judge, tg)]:
    w.link(a, b)
w.save("minibatch-4-health.json", about=ABOUT4, notes=NOTES4)


# ---------------------------------------------------------------- 5. 취소 폼 (D29, 2026-10-17)
w = WF("MiniBatch 5 취소 폼")
ft = w.add("취소 폼", "n8n-nodes-base.formTrigger", 2.3,
           {"path": "minibatch-cancel", "formTitle": "MiniBatch 취소",
            "formDescription": "공개 전 작업과 진행 중 시리즈를 취소합니다. 취소한 작업은 다시 실행되지 않고, 이미 올린 비공개 영상은 그대로 남습니다.",
            "formFields": {"values": [{"fieldLabel": "승인자", "placeholder": "운영자", "requiredField": True}]},
            "options": {"buttonLabel": "목록 열기", "appendAttribution": False}},
           [0, 0], webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "minibatch/minibatch-cancel")))
cfg = code(w, "설정", CONFIG_JS, [220, 0])
jl = http(w, "작업 목록", "GET", "={{ $('설정').first().json.api }}/jobs", [440, 0])
sl = http(w, "시리즈 목록", "GET", "={{ $('설정').first().json.api }}/series", [660, 0])
mk = code(w, "폼 만들기", """// 공개 전 작업(D29 취소 가능 상태)과 끝나지 않은 시리즈를 보여 준다
const esc = s => String(s ?? '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
const JOB_OK = ['PENDING', 'RUNNING', 'WAITING', 'FAILED', 'REVIEW', 'REJECTED'];
const SERIES_OK = ['PROPOSED', 'APPROVED', 'ACTIVE', 'PAUSED'];
const jobs = ($('작업 목록').first().json.items || []).filter(j => JOB_OK.includes(j.status));
const series = ($input.first().json.items || []).filter(s => SERIES_OK.includes(s.status));
if (!jobs.length && !series.length) return [{ json: { empty: true, fields: [] } }];
const fields = [];
const opts = { values: [{ option: '유지' }, { option: '취소' }] };
if (series.length) fields.push({ fieldType: 'html', fieldName: 'h_series', html: '<h3>시리즈</h3><p>시리즈를 취소하면 공개 전 화와 작업도 함께 취소됩니다.</p>' });
for (const s of series) {
  fields.push({ fieldType: 'dropdown', fieldName: `s__${s.id}`, fieldLabel: `${s.title} (${s.status}, 남은 화 ${s.counts?.planned ?? '?'})`, fieldOptions: opts, requiredField: true });
}
if (jobs.length) fields.push({ fieldType: 'html', fieldName: 'h_jobs', html: '<h3>작업 (공개 전)</h3><p>시리즈 화를 취소하면 그 시리즈는 멈춤(PAUSED)이 됩니다.</p>' });
for (const j of jobs) {
  const head = j.seriesId ? `${esc(j.seriesId)} ${j.episodeNumber}화` : '단독';
  fields.push({ fieldType: 'dropdown', fieldName: `j__${j.id}`, fieldLabel: `${head}: ${j.topic} (${j.status}${j.currentStep ? ', ' + j.currentStep : ''})`, fieldOptions: opts, requiredField: true });
}
fields.push({ fieldType: 'text', fieldName: 'reason', fieldLabel: '취소 사유', requiredField: true });
return [{ json: { empty: false, fields } }];""", [880, 0])
sw = switch(w, "취소할 것 있나", "={{ $json.empty ? 1 : 0 }}", 2, [1100, 0])
pg = form_page(w, "취소 화면", "MiniBatch 취소", "취소할 항목만 '취소'로 바꾸고 사유를 적어 제출합니다.", [1320, -100])
none = form_done(w, "끝: 취소할 것 없음", "취소할 것이 없습니다", "공개 전 작업이나 진행 중 시리즈가 없습니다.", [1320, 160])
plan = code(w, "취소 목록", """// 시리즈를 먼저 취소한다 (그 시리즈의 작업은 함께 취소된다). 남은 작업은 하나씩
const by = $('취소 화면').first().json;
const who = $('취소 폼').first().json['승인자'] || '운영자';
const body = { cancelledBy: who, reason: by.reason || '사유 없음' };
const out = [];
for (const [k, v] of Object.entries(by)) if (k.startsWith('s__') && v === '취소') out.push({ json: { path: `series/${k.slice(3)}/cancel`, label: k.slice(3), body } });
for (const [k, v] of Object.entries(by)) if (k.startsWith('j__') && v === '취소') out.push({ json: { path: `jobs/${k.slice(3)}/cancel`, label: k.slice(3), body } });
return out.length ? out : [{ json: { path: null } }];""", [1540, -100])
sw2 = switch(w, "취소할 것 골랐나", "={{ $json.path ? 0 : 1 }}", 2, [1760, -100])
loop = w.add("하나씩", "n8n-nodes-base.splitInBatches", 3, {"batchSize": 1, "options": {}}, [1980, -200])
do = http(w, "취소 요청", "POST", "={{ $('설정').first().json.api }}/{{ $json.path }}", [2200, -120],
          body="={{ JSON.stringify($json.body) }}", full=True)
res = code(w, "결과 정리", """// 시리즈를 먼저 취소하면 그 시리즈 작업은 이미 취소돼 409(not_cancellable)가 날 수 있다: 이미 취소됨으로 본다
const req = $('취소 목록').all().map(i => i.json);
const res = $input.all().map(i => i.json);
const lines = req.map((r, i) => {
  const x = res[i] || {};
  if (x.statusCode === 200) return `${r.label} → ${x.body?.status}`;
  if (x.body?.error?.code === 'not_cancellable') return `${r.label} → 이미 취소·공개됨 (${x.body.error.message})`;
  return `${r.label} → 실패: ${x.body?.error?.message || x.statusCode}`;
});
return [{ json: { message: lines.join('\\n') } }];""", [2200, -320])
done = form_done(w, "끝: 결과", "처리했습니다", "={{ $json.message }}", [2420, -320])
nothing = form_done(w, "끝: 바꾼 것 없음", "바꾼 것이 없습니다", "모두 유지했습니다.", [1980, 60])
for a, b in [(ft, cfg), (cfg, jl), (jl, sl), (sl, mk), (mk, sw), (pg, plan), (plan, sw2), (do, loop), (res, done)]:
    w.link(a, b)
w.link(sw, pg, 0); w.link(sw, none, 1)
w.link(sw2, loop, 0); w.link(sw2, nothing, 1)
w.link(loop, res, 0); w.link(loop, do, 1)
w.save("minibatch-5-cancel-form.json", about=ABOUT5, notes=NOTES5)

# ---------------------------------------------------------------- 6. ASMR 채널 확인 (D38, 2026-10-20)
w = WF("MiniBatch 6 ASMR 확인")
t1 = cron(w, "매시 정각", ["0 0 * * * *"], [0, 0])
t2 = manual(w, [0, 200])
cfg = code(w, "설정", CONFIG_JS, [220, 100])
scan = http(w, "inbox 확인", "POST", "={{ $('설정').first().json.api }}/asmr/scan", [440, 100], full=True, timeout=900000)
msg = code(w, "알림 문장", """// 승인 요청·업로드 결과는 job-api 가 텔레그램으로 보낸다 (D38). 여기서는 확인 실패만 알린다
const r = $input.first().json;
if (r.statusCode === 200) return [];
return [{ json: { text: `⚠️ MiniBatch ASMR inbox 확인 실패 (${r.statusCode}): ${r.body?.error?.message || ''}` } }];""", [660, 100])
tg = telegram(w, "알림: ASMR", "={{ $json.text }}", [880, 100])
for a, b in [(t1, cfg), (t2, cfg), (cfg, scan), (scan, msg), (msg, tg)]:
    w.link(a, b)
w.save("minibatch-6-asmr.json", about=ABOUT6, notes=NOTES6)

# ---------------------------------------------------------------- 7. IT 뉴스 후보 (D40, 2026-10-25)
w = WF("MiniBatch 7 IT 뉴스 후보")
t1 = cron(w, "매일 07시", ["0 0 7 * * *"], [0, 0])
t2 = manual(w, [0, 200])
cfg = code(w, "설정", CONFIG_JS, [220, 100])
nd = http(w, "후보 모아 보내기", "POST", "={{ $('설정').first().json.api }}/news/daily", [440, 100], full=True, timeout=1800000)
msg = code(w, "알림 문장", """// 후보 메시지는 job-api 가 텔레그램으로 보낸다 (D40). 여기서는 실패만 알린다
const r = $input.first().json;
if (r.statusCode === 200) return [];
return [{ json: { text: `⚠️ MiniBatch IT 뉴스 후보 모으기 실패 (${r.statusCode}): ${r.body?.error?.message || ''}\n텔레그램 /news 로 다시 할 수 있습니다` } }];""", [660, 100])
tg = telegram(w, "알림: 뉴스", "={{ $json.text }}", [880, 100])
for a, b in [(t1, cfg), (t2, cfg), (cfg, nd), (nd, msg), (msg, tg)]:
    w.link(a, b)
w.save("minibatch-7-news.json", about="""## 7. IT 뉴스 후보 (D40)
**언제**: 매일 07:00 (수동 실행도 됨, 텔레그램 /news 와 같음)
**하는 일**: job-api 가 GeekNews RSS 새 글(48시간 안)을 모으고, 글 페이지에서 원문 링크·추천 수를 읽고(최대 15개), 원문을 읽어 LLM 으로 평가(점수·3줄 요약·품질·저작권)한 뒤 상위 5개를 텔레그램으로 보낸다
**고르기**: 텔레그램 [이걸로 만들기] → it-news 단독 작업(하루 최대 3편) → 1번 생산이 시리즈보다 먼저 만든다
**지금 상태 보기**: 텔레그램 /status 의 [IT 뉴스] 줄, GET /news/items""",
       notes={"후보 모아 보내기": "POST /news/daily: 모으기·평가·보내기 (몇 분 걸림)", "알림 문장": "실패만 텔레그램으로"})

# 노드 이름이 연결과 맞는지 확인
for f in sorted(OUT.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    names = {n["name"] for n in d["nodes"]}
    assert len(names) == len(d["nodes"]), f"{f.name}: 노드 이름 중복"
    for a, v in d["connections"].items():
        assert a in names, (f.name, a)
        for outs in v["main"]:
            for c in outs:
                assert c["node"] in names, (f.name, c["node"])
    refs = set(re.findall(r"\$\('([^']+)'\)", f.read_text(encoding="utf-8")))
    assert refs <= names, (f.name, refs - names)
    print(f.name, len(d["nodes"]), "노드")
