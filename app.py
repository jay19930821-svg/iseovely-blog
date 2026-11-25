import streamlit as st
import streamlit.components.v1 as components
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
import html
import io
import json
import zipfile
from datetime import datetime
from PIL import Image, ImageEnhance, ImageOps
from google import genai
from google.genai import types

# ==========================================
# 페이지 기본 설정 (PC 2단 분할 + 모바일 반응형)
# ==========================================
st.set_page_config(
    page_title="이서블리 전용 - 패션·이슈·맛집 올인원 자동화",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 커스텀 CSS (PC 프로그램과 동일한 컬러감 및 가독성 강화)
st.markdown("""
<style>
    .block-container {
        padding-top: 3.8rem;
        padding-bottom: 2rem;
        max-width: 1440px;
    }
    .mode-banner-fashion {
        background-color: #DBEAFE;
        color: #1E3A8A;
        padding: 10px 14px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 14px;
        margin-bottom: 12px;
        border-left: 5px solid #1E3A8A;
    }
    .mode-banner-issue {
        background-color: #FFE4E6;
        color: #9F1239;
        padding: 10px 14px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 14px;
        margin-bottom: 12px;
        border-left: 5px solid #BE123C;
    }
    .mode-banner-food {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 10px 14px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 14px;
        margin-bottom: 12px;
        border-left: 5px solid #D97706;
    }
    .memo-box-header {
        background-color: #FFFBEB;
        color: #92400E;
        padding: 8px 12px;
        border-radius: 8px 8px 0 0;
        border: 1px solid #FDE68A;
        font-weight: 700;
        font-size: 15px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 비밀번호 잠금장치 (Secrets 기반 보안)
# ==========================================
def check_password():
    app_pw = str(st.secrets.get("APP_PASSWORD", "")).strip()
    if not app_pw:
        return True
    if st.session_state.get("authenticated", False):
        return True

    st.markdown("### 🔒 이서블리 전용 - 패션·착장 & 연예인 이슈 & 맛집 후기 올인원 자동화")
    st.caption("허가된 사용자만 접근할 수 있습니다. Secrets에 설정한 비밀번호를 입력해 주세요.")
    col_pw1, col_pw2 = st.columns([2, 1])
    with col_pw1:
        pw_input = st.text_input("접속 비밀번호", type="password", label_visibility="collapsed", placeholder="비밀번호를 입력하세요")
    with col_pw2:
        login_clicked = st.button("🔓 로그인", type="primary", use_container_width=True)

    if login_clicked:
        if pw_input == app_pw:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다. Streamlit Secrets의 APP_PASSWORD 값을 확인해 주세요.")
    return False

if not check_password():
    st.stop()

# 제미나이 API 클라이언트 초기화
default_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
with st.sidebar:
    st.header("⚙️ API 및 환경 설정")
    api_key_input = st.text_input("Gemini API Key", value=default_api_key, type="password")
    if st.button("🔒 로그아웃", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

if not api_key_input:
    st.warning("Streamlit Secrets에 `GEMINI_API_KEY`를 설정하거나 왼쪽 사이드바(>)에서 키를 입력해 주세요.")
    st.stop()

client = genai.Client(
    api_key=api_key_input.strip(),
    http_options=types.HttpOptions(timeout=50000)
)

# ==========================================
# 기본 데이터 (운영 매뉴얼, 문체 프로필, 3대 모드 규칙)
# ==========================================
DEFAULT_STRATEGY_MEMO = """📌 [일 방문자 1만+ 달성 운영 매뉴얼]

1️⃣ 하루 목표 발행량 & 간격
• 하루 3~5개 포스팅 (패션 2~3개 + 연예 이슈 1~2개 황금 비율)
• 2~3시간 간격 예약 발행으로 홈피드 노출 빈도 극대화

2️⃣ 추천 발행 골든타임
• [오전 07:00 ~ 09:00] 전날 밤 드라마·예능 착장 & 방송 화제 장면
• [오후 12:00 ~ 13:30] 점심시간 실시간 연예인 SNS 근황·이슈
• [밤 22:00 ~ 24:00] 저녁 포토월·인스타 업로드 (다음 날 새벽 홈피드 유입)

3️⃣ 모드별 소재 활용 팁
• [👗 패션·착장 모드]: 공항패션, 사복, 제작발표회, 가방·뷰티 아이템
• [🔥 연예인 이슈 모드]: 예능 하이라이트, 드라마 비하인드, 열애/결혼, 컴백 근황
• [🍽️ 맛집 후기 모드]: 직접 찍은 사진 불러오기 → 체험단 가이드라인 입력 후 바로 생성

4️⃣ 자동화 프로그램 30초 발행 순서
① 상단에서 [👗 패션], [🔥 이슈], [🍽️ 맛집] 모드 선택
② 기사 URL 입력 또는 맛집 사진 업로드
③ 생성 완료 후 [원고 서식 그대로 복사] → 에디터 Ctrl+V
④ [가공된 사진 ZIP 다운로드] → 압축 풀기 후 사진 배치 & 태그 30개 복사!

✏️ [나만의 오늘 메모 / 예약 스케줄 기록]
- 08:00 예약: 
- 12:30 예약: 
- 18:00 예약: 
- 22:30 예약: 
"""

DEFAULT_STYLES = {
    "1. 이서블리 기본 스타일 (친근한 30대 리뷰어 · ㅎㅎ/ㅋㅋ 자연스러운 호흡)": (
        "너는 트렌디한 스타·패션·라이프·맛집 블로거야. "
        "친근하고 센스 있는 30대 여성 블로거 톤(해요체, 감탄사, 적당한 이모지 💕✨🤍💡🥰🍽️)으로 작성하되, "
        "'안녕하세요 블로거 이서블리예요' 같은 자기소개 인사말은 절대 쓰지 말고 첫 줄부터 바로 핵심 포인트로 직진해.\n"
        "[구어체 및 친근감 규칙]\n"
        "- 과하지 않게 친한 언니·동생에게 말하듯 자연스러운 타이밍에만 'ㅎㅎ' 또는 'ㅋㅋ'를 글 전체에서 2~3번 정도 섞어줘.\n"
        "[구성 규칙]\n"
        "- 도입부: 자기소개 없이 바로 화제 된 핵심 포인트 또는 방문 계기를 3~5줄 짧은 호흡 + 인용구 1줄로 임팩트 있게 시작해.\n"
        "- 본문 전개: 핵심 내용을 '#1. 소제목 ✨', '#2. 소제목 🤍' 형태로 빠짐없이 섹션으로 나누어 작성해.\n"
        "- 마무리: '✍️ 마무리 총평' 아래 전체 요약 + 댓글 유도 질문"
    ),
    "2. 블로거 jisun0410_ 스타일 (모바일 최적화 · 담백하고 감각적인 정리형)": (
        "너는 네이버 인기 블로거(jisun0410_ 레퍼런스)의 문체와 모바일 레이아웃을 100% 그대로 구사하는 블로거야. "
        "자기소개 인사말 없이 첫 줄부터 바로 핵심 포인트로 담백하고 세련되게 시작해.\n"
        "[jisun0410_ 핵심 모바일 문단·줄바꿈 규칙]\n"
        "- 모든 일반 문장은 쉼표(,), 마침표(.), 느낌표(!) 또는 의미 단위로 끊어 한 줄에 20자를 절대 넘지 않게 줄바꿈(엔터)해.\n"
        "- 단, 형광펜/컬러/볼드 강조 기호가 들어간 문구는 한 줄에 온전히 적어.\n"
        "- 3~5줄의 짧은 본문 블록이 끝나면 [사진 N]이 들어가도록 리듬을 맞춰.\n"
        "[구성 규칙]\n"
        "- 본문 전개: 핵심 내용을 '#1.', '#2.', '#3.', '#4.' 순서대로 누락 없이 각각 독립된 섹션으로 알차게 정리해.\n"
        "- 마무리: 핵심 요약 + 담백한 끝인사"
    ),
}

COMMON_RICH_FORMAT_RULES = (
    "5. [모바일 한 줄 20자 이내 줄바꿈 & 3~5줄 문단 고정]: "
    "모든 일반 문장은 쉼표(,), 마침표(.), 느낌표(!), 물음표(?) 뒤나 의미 구절 단위로 줄바꿈(엔터)해서 한 줄이 20자를 넘지 않게 맞춰! "
    "한 문단은 3~5줄로 구성하고 문단 사이 빈 줄을 넣어 '3~5줄 글 → [사진 N] → 3~5줄 글' 리듬을 유지해.\n"
    "6. [심플 3색 파스텔 형광펜 음영 + 포인트 글자색 + 인용구 적용 (한 줄 고정)]: (일반 마크다운 **, ##, * 금지)\n"
    "   - 연노랑 형광펜 (4~5군데): 가장 중요한 핵심 꿀팁이나 한 줄 요약은 '[[강조할 문구]]' 로 감싸줘.\n"
    "   - 연하늘(스카이블루) 형광펜 (3~4군데): 핵심 아이템명, 메뉴명, 장면 이름은 '[b[강조할 문구]b]' 로 감싸줘.\n"
    "   - 연핑크 형광펜 (2~3군데): 분위기 포인트, 추천 대상(하객룩, 데이트, 모임 등)은 '[p[강조할 문구]p]' 로 감싸줘.\n"
    "   - 포인트 글자색+볼드 (5~7군데): 핵심 브랜드명·인물명·상호명은 '((강조할 단어))' 로 감싸 선명한 포인트 글자색과 볼드를 입혀줘.\n"
    "   - 두꺼운 블랙 볼드 (5~7군데): 중요 키워드는 '<<강조할 단어>>' 로 감싸 두껍게 강조해줘.\n"
    "   - ★매우 중요(줄바꿈 금지)★: 위 강조 기호로 감싼 문구는 20자 이내로 짧게 만들어 절대 중간에 줄바꿈 없이 한 줄 안에 온전히 적어!\n"
    "   - 인용구 박스 (2~3군데): 도입부 핵심 요약 한 줄과 마무리 총평 핵심 한 줄에는 줄 맨 앞에 '> ' 를 붙여 인용구 박스로 강조해.\n"
    "   - 구분선: 소제목 섹션이 바뀔 때마다 단독 줄에 '---' 를 넣어 구분해.\n"
)

FASHION_FORMAT_RULES = (
    "\n\n[👗 패션·착장 분석 모드 전용 규칙 · 상위 5% 황금 글자 수 · 3색 심플 음영 서식]\n"
    "1. [네이버 상위 5% 애드포스트 황금 글자 수 준수 (공백 제외 1,500~2,000자)]: "
    "네이버 홈피드 노출과 중간 애드포스트 수익이 극대화되는 '공백 제외 1,500자 ~ 2,000자' 분량을 반드시 채워 작성해!\n"
    "2. [자기소개 금지 & 맨 위 제목 2가지 추천]: "
    "자기소개 인사말 절대 금지! 맨 첫 줄부터 아래 형식으로 제목 2가지만 먼저 제시해 줘:\n"
    "   [제목 추천 1 - 이서블리 시그니처형] (후킹 문구 + 연예인/브랜드/아이템 포인트 + 이모지 ✨ 조합)\n"
    "   [제목 추천 2 - 상위 5% 검색 유입형] (핵심 검색 키워드 중심의 깔끔하고 클릭을 부르는 제목)\n"
    "   그 다음 줄에 '===' 를 적고 자기소개 없이 바로 본문 첫 문장을 시작해.\n"
    "3. [인물별 다중 착장(사진 2~3장 이상) 및 모든 룩 균형 반영]: "
    "각 인물 섹션마다 서로 다른 코디가 담긴 2~3장([사진 1], [사진 3] 등)을 3~5줄 글과 번갈아 배치하고, "
    "나머지 사진 속 착장(다른 컬러·아이템)과 실생활 코디 조합·컬러 배색·소품 팁을 꼭 포함해!\n"
    "4. [첨부 사진 실제 착장·색상 100% 정확 일치]: "
    "첨부된 실제 사진을 직접 확인하고 각 [사진 N] 위아래에는 해당 사진에 실제로 보이는 옷 색상·아이템·핏만 묘사해.\n"
    + COMMON_RICH_FORMAT_RULES +
    "7. [맨 마지막 11pt 출처 표기 & 태그 30개]: "
    "맨 마지막 줄에는 원문에 출처가 있으면 '출처- (원문 출처)'를, 없으면 정확히 '출처-' 만 단독 줄로 적고, 바로 다음 줄 '===TAGS===' 아래에 검색 태그 30개를 쉼표로 구분해 출력해."
)

ISSUE_FORMAT_RULES = (
    "\n\n[🔥 연예인 이슈·근황 모드 전용 규칙 · 상위 5% 황금 글자 수 · 3색 심플 음영 서식]\n"
    "1. [네이버 상위 5% 애드포스트 황금 글자 수 준수 (공백 제외 1,500~2,000자)]: "
    "네이버 홈피드 노출과 중간 애드포스트 수익이 극대화되는 '공백 제외 1,500자 ~ 2,000자' 분량을 반드시 채워 흥미진진하게 작성해!\n"
    "2. [패션 코디 추천 금지 & 이슈 스토리텔링 집중]: "
    "억지로 옷·가방·컬러 배색 추천을 끼워 넣지 마! 대신 ① 화제가 된 결정적 계기(사건·발언·방송 장면), "
    "② 구체적인 전말과 비하인드 스토리, ③ 네티즌·팬들의 실시간 반응 포인트, ④ 향후 방송·컴백·활동 일정 전망 순으로 알차게 구성해.\n"
    "3. [자기소개 금지 & 맨 위 제목 2가지 추천]: "
    "자기소개 인사말 절대 금지! 맨 첫 줄부터 아래 형식으로 제목 2가지만 먼저 제시해 줘:\n"
    "   [제목 추천 1 - 이서블리 이슈 후킹형] (궁금증을 유발하는 핵심 한 줄 + 인물/프로그램명 + 이모지 ✨ 조합)\n"
    "   [제목 추천 2 - 상위 5% 검색 유입형] (인물명 + 핵심 사건/방송 키워드 중심의 클릭을 부르는 제목)\n"
    "   그 다음 줄에 '===' 를 적고 자기소개 없이 바로 본문 첫 문장을 시작해.\n"
    "4. [첨부 사진 장면·표정·상황 100% 정확 일치]: "
    "첨부된 실제 사진을 직접 확인하고 각 소제목 섹션마다 [사진 1]~[사진 N]을 3~5줄 글과 번갈아 배치하며 해당 사진 속 실제 장면·표정과 일치하게 묘사해.\n"
    + COMMON_RICH_FORMAT_RULES +
    "7. [맨 마지막 11pt 출처 표기 & 태그 30개]: "
    "맨 마지막 줄에는 원문에 출처가 있으면 '출처- (원문 출처)'를, 없으면 정확히 '출처-' 만 단독 줄로 적고, 바로 다음 줄 '===TAGS===' 아래에 인물·이슈·방송 관련 검색 태그 30개를 쉼표로 구분해 출력해."
)

FOOD_FORMAT_RULES = (
    "\n\n[🍽️ 맛집 후기 자동화 모드 전용 규칙 · 실방문 생생 리뷰 · 3색 심플 음영 서식]\n"
    "1. [네이버 상위 5% 맛집 리뷰 황금 글자 수 준수 (공백 제외 1,200~1,800자)]: "
    "체류시간과 저장(지도 클릭)을 높이는 알차고 생생한 '공백 제외 1,200자 ~ 1,800자' 분량으로 작성해!\n"
    "2. [자기소개 금지 & 맨 위 맛집 제목 2가지 추천]: "
    "자기소개 인사말 절대 금지! 맨 첫 줄부터 아래 형식으로 제목 2가지만 먼저 제시해 줘:\n"
    "   [제목 추천 1 - 이서블리 맛집 후킹형] (지역명 + 상호명 + 시그니처 메뉴/식감 강조 + 이모지 🍽️✨)\n"
    "   [제목 추천 2 - 상위 5% 지역맛집 검색형] (지역역/동네 + 맛집 키워드 + 대표메뉴 중심 제목)\n"
    "   그 다음 줄에 '===' 를 적고 바로 본문 첫 문장을 시작해.\n"
    "3. [업로드된 실제 맛집 사진 100% 정밀 묘사 및 순서 배치]: "
    "첨부된 실제 사진([첨부 사진 1번]~[첨부 사진 N번])을 눈으로 직접 보고, 외관·인테리어·메뉴판·기본찬·메인 음식 비주얼·클로즈업 먹방 컷 순서에 맞춰 "
    "[사진 1]~[사진 N]을 3~5줄 글과 번갈아 모두 배치해! 사진에 없는 메뉴나 인테리어를 지어내지 마.\n"
    "4. [체계적인 맛집 정보 구성]: "
    "① 방문 계기 & 위치/주차/웨이팅 팁, ② 매장 분위기 & 좌석 구성, ③ 주문 메뉴 & 실제 맛·식감·양 디테일 후기, ④ 재방문 의사 & 추천 대상(데이트, 가족모임, 회식 등) 순으로 구성해.\n"
    + COMMON_RICH_FORMAT_RULES +
    "7. [협찬/가이드라인 문구 & 맨 마지막 출처 표기 + 태그 30개]: "
    "입력된 체험단/협찬 가이드라인 필수 키워드나 공정위 문구가 있다면 자연스럽게 반영하고, "
    "맨 마지막 줄에는 '출처-' 를 단독 줄로 적은 뒤 바로 다음 줄 '===TAGS===' 아래에 지역명+맛집+메뉴 관련 태그 30개를 쉼표로 구분해 출력해."
)

# ==========================================
# 텍스트 포맷팅 및 HTML 클립보드 변환 유틸
# ==========================================
def fix_broken_inline_tags(text):
    tag_pairs = [
        (r"\[\[", r"\]\]"),
        (r"\[b\[", r"\]b\]"),
        (r"\[p\[", r"\]p\]"),
        (r"<<", r">>"),
        (r"\(\(", r"\)\)"),
    ]
    for open_t, close_t in tag_pairs:
        pattern = re.compile(open_t + r"(.*?)" + close_t, re.DOTALL)
        text = pattern.sub(lambda m: m.group(0).replace("\r", " ").replace("\n", " "), text)
    return re.sub(r" {2,}", " ", text)

def strip_all_markers(s):
    s = re.sub(r"\[\[(.*?)\]\]", r"\1", s)
    s = re.sub(r"\[b\[(.*?)\]b\]", r"\1", s)
    s = re.sub(r"\[p\[(.*?)\]p\]", r"\1", s)
    s = re.sub(r"<<(.*?)>>", r"\1", s)
    s = re.sub(r"\(\((.*?)\)\)", r"\1", s)
    return s

def visible_len(s):
    return len(strip_all_markers(s))

def tokenize_preserving_tags(line):
    pattern = re.compile(r"(\[\[.*?\]\]|\[b\[.*?\]b\]|\[p\[.*?\]p\]|<<.*?>>|\(\(.*?\)\))")
    parts = pattern.split(line)
    tokens = []
    for part in parts:
        if not part:
            continue
        if pattern.fullmatch(part):
            tokens.append(part.strip())
        else:
            for w in part.split(" "):
                if w.strip():
                    tokens.append(w.strip())
    return tokens

def smart_mobile_wrap(line, max_chars=20):
    if visible_len(line) <= max_chars:
        return [line]
    tokens = tokenize_preserving_tags(line)
    phrase_lines, buf = [], []
    for tok in tokens:
        buf.append(tok)
        is_tag = tok.startswith(("[[", "[b[", "[p[", "<<", "(("))
        if not is_tag and tok[-1] in (",", ".", "!", "?"):
            phrase_lines.append(" ".join(buf))
            buf = []
    if buf:
        phrase_lines.append(" ".join(buf))

    wrapped = []
    for phrase in phrase_lines:
        if visible_len(phrase) <= max_chars:
            wrapped.append(phrase)
            continue
        cur = ""
        for tok in tokenize_preserving_tags(phrase):
            if not cur:
                cur = tok
                continue
            cand = cur + " " + tok
            if visible_len(cand) <= max_chars:
                cur = cand
            else:
                wrapped.append(cur)
                cur = tok
        if cur:
            wrapped.append(cur)

    final_lines = []
    for w_line in wrapped:
        if final_lines and visible_len(w_line) <= 3:
            final_lines[-1] = final_lines[-1] + " " + w_line
        else:
            final_lines.append(w_line)
    return final_lines

def format_mobile_paragraph_spacing(raw_body):
    fixed_body = fix_broken_inline_tags(raw_body)
    lines = fixed_body.split("\n")
    source_line = ""
    processed_blocks = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("출처-", "출처:", "출처 -", "출처 :")):
            clean_src = re.sub(r"^출처\s*[-:]\s*", "출처- ", stripped).strip()
            source_line = "출처-" if clean_src == "출처-" else clean_src
            continue
        if stripped == "":
            processed_blocks.append("")
            continue
        is_special = (
            stripped in ("---", "===")
            or stripped.startswith(("[제목", "#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜", "🍽️", "[사진", "> "))
        )
        if is_special:
            processed_blocks.append(stripped)
        else:
            processed_blocks.extend(smart_mobile_wrap(stripped, max_chars=20))

    merged_lines = []
    for item in processed_blocks:
        if item == "":
            merged_lines.append("")
            continue
        is_spec = (
            item in ("---", "===")
            or item.startswith(("[제목", "#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜", "🍽️", "[사진", "> "))
        )
        if (
            not is_spec
            and visible_len(item) <= 3
            and merged_lines
            and merged_lines[-1] != ""
            and not merged_lines[-1].startswith(("[제목", "#", "💡", "✍️", "✅", "🍽️", "[사진", "> ", "---", "==="))
        ):
            merged_lines[-1] = merged_lines[-1] + " " + item
        else:
            merged_lines.append(item)

    cleaned_lines = []
    consecutive_text_lines = 0
    for stripped in merged_lines:
        if stripped == "":
            if len(cleaned_lines) >= 2 and cleaned_lines[-1] == "" and cleaned_lines[-2] == "":
                continue
            cleaned_lines.append("")
            consecutive_text_lines = 0
        elif stripped.startswith("[제목 추천"):
            cleaned_lines.append(stripped)
            consecutive_text_lines = 0
        elif stripped in ("---", "===") or stripped.startswith(("#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜", "🍽️", "[사진", "> ")):
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            cleaned_lines.append(stripped)
            cleaned_lines.append("")
            consecutive_text_lines = 0
        else:
            if consecutive_text_lines >= 4:
                cleaned_lines.append("")
                consecutive_text_lines = 0
            cleaned_lines.append(stripped)
            consecutive_text_lines += 1

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    cleaned_lines.append("")
    cleaned_lines.append("")
    cleaned_lines.append(source_line if source_line else "출처-")
    return "\n".join(cleaned_lines).strip()

def render_inline_highlights(escaped_text):
    text = re.sub(
        r"\[\[(.*?)\]\]",
        r'<span style="background-color: #FFF3BF; padding: 2px 5px; font-weight: 700; color: #111111;">\1</span>',
        escaped_text,
    )
    text = re.sub(
        r"\[b\[(.*?)\]b\]",
        r'<span style="background-color: #D0EBFF; padding: 2px 5px; font-weight: 700; color: #0B3B60;">\1</span>',
        text,
    )
    text = re.sub(
        r"\[p\[(.*?)\]p\]",
        r'<span style="background-color: #FFDEEB; padding: 2px 5px; font-weight: 700; color: #5C1633;">\1</span>',
        text,
    )
    text = re.sub(
        r"&lt;&lt;(.*?)&gt;&gt;",
        r'<strong style="font-weight: 700; color: #000000;">\1</strong>',
        text,
    )
    text = re.sub(
        r"\(\((.*?)\)\)",
        r'<strong style="color: #E64980; font-weight: 700;">\1</strong>',
        text,
    )
    return text

def build_naver_html(plain_text):
    lines = plain_text.split("\n")
    html_parts = [
        '<div style="font-family: \'Noto Sans KR\', \'맑은 고딕\', sans-serif; '
        'font-size: 15px; font-weight: normal; line-height: 1.85; color: #333333; text-align: left;">'
    ]
    for line in lines:
        stripped = line.strip()
        escaped = html.escape(line)
        styled_line = render_inline_highlights(escaped)

        if stripped.startswith("출처-"):
            html_parts.append(f'<p style="font-size: 11pt; font-weight: normal; color: #666666; margin-top: 16px;">{escaped}</p>')
        elif stripped.startswith("[제목 추천"):
            html_parts.append(f'<p style="font-size: 16px; font-weight: 700; color: #1E3A8A; background-color: #EFF6FF; padding: 6px 10px; margin: 4px 0;">{escaped}</p>')
        elif stripped in ("---", "==="):
            html_parts.append('<hr style="border: 0; border-top: 1px solid #D1D5DB; margin: 22px auto; width: 45%;">')
        elif stripped.startswith("&gt; "):
            quote_content = render_inline_highlights(stripped[5:])
            html_parts.append(
                '<blockquote style="border-left: 4px solid #03C75A; background-color: #F8FAFC; '
                'padding: 12px 16px; margin: 14px 0; font-size: 15px; font-weight: 600; color: #1E293B;">'
                f'{quote_content}</blockquote>'
            )
        elif stripped.startswith(("#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜", "🍽️")):
            sub_clean = strip_all_markers(escaped)
            html_parts.append(f'<p style="font-size: 18px; font-weight: 700; color: #111111; margin-top: 14px; margin-bottom: 8px;">{sub_clean}</p>')
        elif stripped.startswith("[사진"):
            html_parts.append(f'<p style="font-size: 14px; font-weight: 700; color: #03C75A; margin: 14px 0;">{escaped}</p>')
        elif stripped == "":
            html_parts.append("<p><br></p>")
        else:
            html_parts.append(f'<p style="font-size: 15px; font-weight: normal; margin: 2px 0;">{styled_line}</p>')
    html_parts.append("</div>")
    return "".join(html_parts)

def render_web_copy_button(html_payload, plain_payload, btn_label="📋 원고 서식 그대로 복사 (네이버 에디터용)", key_id="copy_main"):
    html_json = json.dumps(html_payload)
    plain_json = json.dumps(plain_payload)
    comp_html = f"""
    <button id="{key_id}" onclick="copyRich()" style="
        width: 100%; padding: 10px 14px; background-color: #03C75A; color: white;
        border: none; border-radius: 6px; font-size: 14px; font-weight: bold; cursor: pointer;">
        {btn_label}
    </button>
    <script>
    async function copyRich() {{
        const htmlStr = {html_json};
        const textStr = {plain_json};
        try {{
            const blobHtml = new Blob([htmlStr], {{ type: 'text/html' }});
            const blobText = new Blob([textStr], {{ type: 'text/plain' }});
            await navigator.clipboard.write([new ClipboardItem({{
                'text/html': blobHtml,
                'text/plain': blobText
            }})]);
            document.getElementById('{key_id}').innerText = '✅ 서식 복사 완료! 블로그 에디터에 붙여넣기 하세요';
        }} catch (e) {{
            await navigator.clipboard.writeText(textStr);
            document.getElementById('{key_id}').innerText = '✅ 본문 복사 완료!';
        }}
    }}
    </script>
    """
    components.html(comp_html, height=48)

# ==========================================
# 이미지 가공 및 해외 서버 호환 크롤링 엔진
# ==========================================
def process_unique_image(pil_img, apply_crop=True):
    """중복 이미지 회피용 1% 미세 크롭(기사/블로그용) + 선명도·밝기 보정 + 슬림 화이트 프레임"""
    rgb_im = ImageOps.exif_transpose(pil_img).convert("RGB")
    w, h = rgb_im.size
    if apply_crop:
        crop_x = max(2, int(w * 0.01))
        crop_y = max(2, int(h * 0.01))
        processed = rgb_im.crop((crop_x, crop_y, w - crop_x, h - crop_y))
    else:
        processed = rgb_im

    processed = ImageEnhance.Brightness(processed).enhance(1.03)
    processed = ImageEnhance.Contrast(processed).enhance(1.04)
    processed = ImageEnhance.Sharpness(processed).enhance(1.08)

    cw, ch = processed.size
    border_side = max(10, int(cw * 0.015))
    border_bottom = max(14, int(ch * 0.02))
    return ImageOps.expand(processed, border=(border_side, border_side, border_side, border_bottom), fill=(255, 255, 255))

def normalize_blog_url(raw_url):
    u = raw_url.strip()
    if "blog.naver.com/" in u and "m.blog.naver.com/" not in u:
        blog_id_m = re.search(r"blogId=([^&]+)", u)
        log_no_m = re.search(r"logNo=(\d+)", u)
        if blog_id_m and log_no_m:
            return f"https://m.blog.naver.com/{blog_id_m.group(1)}/{log_no_m.group(1)}"
        u = u.replace("https://blog.naver.com/", "https://m.blog.naver.com/").replace("http://blog.naver.com/", "https://m.blog.naver.com/")
    return u

def extract_blog_text_and_photos(raw_url):
    url = normalize_blog_url(raw_url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        final_url = resp.geturl()
        raw_bytes = resp.read()
        try:
            page_html = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            page_html = raw_bytes.decode("euc-kr", errors="ignore")

    if "news.google.com" in final_url:
        ext_m = re.search(r'href=["\'](https?://(?!(?:news\.google|www\.google|accounts\.google))[^"\']+)["\']', page_html)
        if ext_m:
            real_news_url = html.unescape(ext_m.group(1))
            req2 = urllib.request.Request(real_news_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                final_url = resp2.geturl()
                raw_bytes2 = resp2.read()
                try:
                    page_html = raw_bytes2.decode("utf-8")
                except UnicodeDecodeError:
                    page_html = raw_bytes2.decode("euc-kr", errors="ignore")

    og_title = re.search(r'(?:property|name)=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
    page_title = html.unescape(og_title.group(1)).strip() if og_title else "블로그 포스팅"

    body_html = ""
    se_start = re.search(r'<div[^>]+class=["\'][^"\']*se-main-container[^"\']*["\'][^>]*>', page_html, re.IGNORECASE)
    if se_start:
        sub_html = page_html[se_start.end():]
        end_m = re.search(r'(?:<!--\s*//\s*SE_DOC_HEADER_END|<div[^>]+class=["\'][^"\']*(?:post_tag|section_t1|btn_like_area|post_writer|another_category|recommend_post|comment_area))', sub_html, re.IGNORECASE)
        body_html = sub_html[:end_m.start()] if end_m else sub_html[:150000]
    else:
        for pattern in [
            r'id=["\']comp_news_article["\'][^>]*>(.*?)</article>',
            r'id=["\']dic_area["\'][^>]*>(.*?)</article>',
            r'id=["\']realArtcContents["\'][^>]*>(.*?)</div>\s*<!--',
            r'id=["\']artcContents["\'][^>]*>(.*?)</div>',
            r'itemprop=["\']articleBody["\'][^>]*>(.*?)</(?:div|article|section)>',
            r'class=["\'][^"\']*article[_-]body[^"\']*["\'][^>]*>(.*?)</(?:div|article)>',
            r'id=["\']postViewArea["\'][^>]*>(.*?)</div>',
        ]:
            m = re.search(pattern, page_html, re.DOTALL | re.IGNORECASE)
            if m and len(m.group(1)) > 150:
                body_html = m.group(1)
                break
        if not body_html:
            body_html = page_html

    clean_html = re.sub(r"<script.*?>.*?</script>", "", body_html, flags=re.DOTALL)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL)

    bad_words = ["logo", "icon", "banner", "btn", "ad", "sprite", "1x1", "avatar", "profile", "blank", "emoticon", "sticker", "map", "static.naver", "blogpfthumb", "ogq", "gfmarket", "storep", "transparent", "journalist", "reporter"]
    saved_images_bytes = []
    ai_thumbs = []
    url_to_photo_tag = {}
    tried_urls = set()

    def try_fetch_image_bytes(target_img_url):
        base_u = target_img_url.split("?")[0]
        candidates = [base_u + "?type=w966", base_u, target_img_url] if ("postfiles.pstatic.net" in base_u or "blogfiles.pstatic.net" in base_u) else [target_img_url, base_u]
        dl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": final_url,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        for cand_u in candidates:
            try:
                img_req = urllib.request.Request(cand_u, headers=dl_headers)
                with urllib.request.urlopen(img_req, timeout=8) as img_resp:
                    data = img_resp.read()
                if len(data) >= 4000:
                    return data
            except Exception:
                continue
        return None

    def download_and_save_single_img(raw_img_url):
        u_clean = html.unescape(raw_img_url).strip()
        if u_clean.startswith("//"):
            u_clean = "https:" + u_clean
        if not u_clean.startswith("http") or any(b in u_clean.lower() for b in bad_words):
            return None

        base_key = u_clean.split("?")[0] if ("pstatic.net" in u_clean or "nateimg.co.kr" in u_clean) else u_clean
        if base_key in url_to_photo_tag:
            return url_to_photo_tag[base_key]
        if base_key in tried_urls or len(saved_images_bytes) >= 10:
            return None
        tried_urls.add(base_key)

        data = try_fetch_image_bytes(u_clean)
        if not data:
            return None
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.size[0] < 180 or im.size[1] < 180:
                    return None
                edited_im = process_unique_image(im, apply_crop=True)
                buf = io.BytesIO()
                edited_im.save(buf, format="JPEG", quality=98, subsampling=0)
                saved_images_bytes.append(buf.getvalue())

                thumb = edited_im.copy()
                thumb.thumbnail((512, 512))
                ai_thumbs.append(thumb)

                marker = f"[사진 {len(saved_images_bytes)}]"
                url_to_photo_tag[base_key] = marker
                return marker
        except Exception:
            return None

    def replace_media_tag(match):
        tag_str = match.group(0)
        if "oglink" in tag_str.lower() or "profile" in tag_str.lower():
            return "\n"
        candidate_src = ""
        linkdata_m = re.search(r'data-linkdata=["\']([^"\']+)["\']', tag_str, re.IGNORECASE)
        if linkdata_m:
            try:
                ld_json = json.loads(html.unescape(linkdata_m.group(1)))
                if isinstance(ld_json, dict) and ld_json.get("src"):
                    candidate_src = ld_json["src"]
            except Exception:
                pass
        if not candidate_src:
            src_m = re.search(r'(?:data-lazy-src|data-src|src)=["\']((?:https?:)?//[^"\']+)["\']', tag_str, re.IGNORECASE)
            if src_m:
                candidate_src = src_m.group(1)
        if not candidate_src:
            return "\n"
        marker = download_and_save_single_img(candidate_src)
        return f"\n{marker}\n" if marker else "\n"

    html_with_markers = re.sub(r"<(?:img|a|div)\b[^>]*>", replace_media_tag, clean_html, flags=re.IGNORECASE)
    if len(saved_images_bytes) < 10:
        raw_cdn_imgs = re.findall(
            r'https?://(?:postfiles|blogfiles|mblogthumb-phinf|ssl|imgnews)\.pstatic\.net/[^"\'\s<>\\]+|https?://[^"\'\s<>\\]*nateimg\.co\.kr/[^"\'\s<>\\]+',
            html.unescape(clean_html),
            re.IGNORECASE,
        )
        extra_markers = []
        for r_url in raw_cdn_imgs:
            mk = download_and_save_single_img(r_url)
            if mk and mk not in extra_markers:
                extra_markers.append(mk)
            if len(saved_images_bytes) >= 10:
                break
        if extra_markers:
            html_with_markers += "\n" + "\n".join(extra_markers)

    text_only = re.sub(r"<[^>]+>", "\n", html_with_markers)
    lines = [line.strip() for line in html.unescape(text_only).splitlines() if line.strip()]
    return page_title, "\n".join(lines)[:12000], saved_images_bytes, ai_thumbs

def fetch_realtime_ent_news(keyword="", is_issue=False):
    """해외 클라우드 서버(Streamlit)에서도 100% 작동하는 구글 뉴스 한국어 실시간 RSS 다중 수집기"""
    results = []
    seen_titles = set()
    queries = []

    if keyword.strip():
        queries.append((f"키워드({keyword.strip()})", keyword.strip()))
    if is_issue:
        queries.append(("실시간연예이슈", "연예 방송 화제 근황"))
    else:
        queries.append(("실시간스타패션", "연예인 공항패션 사복패션 제작발표회"))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }

    for tag_label, q_str in queries:
        rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q_str)}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            req = urllib.request.Request(rss_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                root_xml = ET.fromstring(resp.read())
            for item in root_xml.findall(".//item")[:15]:
                t_el, l_el = item.find("title"), item.find("link")
                if t_el is not None and l_el is not None and t_el.text and l_el.text:
                    clean_t = html.unescape(t_el.text).strip()
                    if clean_t not in seen_titles:
                        seen_titles.add(clean_t)
                        results.append({
                            "source": tag_label,
                            "title": clean_t,
                            "url": l_el.text.strip(),
                        })
        except Exception:
            continue
    return results

# ==========================================
# 세션 상태 초기화 (보관함 및 메모장)
# ==========================================
if "active_mode" not in st.session_state:
    st.session_state["active_mode"] = "fashion"
if "archive_list" not in st.session_state:
    st.session_state["archive_list"] = []
if "selected_archive_idx" not in st.session_state:
    st.session_state["selected_archive_idx"] = 0
if "strategy_memo" not in st.session_state:
    st.session_state["strategy_memo"] = DEFAULT_STRATEGY_MEMO

# ==========================================
# 메인 2단 레이아웃 (좌측: 3탭 올인원 작업창 / 우측: 운영 매뉴얼 메모장)
# ==========================================
left_col, right_col = st.columns([2.4, 1.0], gap="medium")

with left_col:
    # ★ 상단 3대 모드 전환 탭 바 (PC 버전 UI 그대로 구현) ★
    t_col1, t_col2, t_col3 = st.columns(3, gap="small")
    with t_col1:
        if st.button(
            "👗 탭 1: 패션·착장 분석",
            type="primary" if st.session_state["active_mode"] == "fashion" else "secondary",
            use_container_width=True
        ):
            st.session_state["active_mode"] = "fashion"
            st.rerun()
    with t_col2:
        if st.button(
            "🔥 탭 2: 연예인 이슈·근황",
            type="primary" if st.session_state["active_mode"] == "issue" else "secondary",
            use_container_width=True
        ):
            st.session_state["active_mode"] = "issue"
            st.rerun()
    with t_col3:
        if st.button(
            "🍽️ 탭 3: 맛집 후기 자동화",
            type="primary" if st.session_state["active_mode"] == "food" else "secondary",
            use_container_width=True
        ):
            st.session_state["active_mode"] = "food"
            st.rerun()

    cur_mode = st.session_state["active_mode"]

    # 모드 안내 배너
    if cur_mode == "fashion":
        st.markdown('<div class="mode-banner-fashion">👗 현재 모드: [패션·착장 분석 전용] — 아이템·브랜드·컬러 배색·실생활 코디 팁 중심으로 작성합니다.</div>', unsafe_allow_html=True)
    elif cur_mode == "issue":
        st.markdown('<div class="mode-banner-issue">🔥 현재 모드: [연예인 이슈·근황 전용] — 사건·방송 핵심 요약, 대중 반응, 비하인드 스토리 중심으로 작성합니다.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="mode-banner-food">🍽️ 현재 모드: [맛집 후기 자동화 전용] — 직접 찍은 음식·매장 사진 분석 + 협찬/체험단 가이드라인을 반영해 작성합니다.</div>', unsafe_allow_html=True)

    # 0. 문체 스타일 선택
    style_choice = st.selectbox(
        "0. 적용할 블로그 문체 스타일 선택 (심플 3색 파스텔 형광펜 · 포인트 글자색 · 인용구 자동 적용)",
        list(DEFAULT_STYLES.keys())
    )

    # ==========================================================
    # 입력 영역 분기: [패션/이슈 URL 모드] vs [맛집 사진 업로드 모드]
    # ==========================================================
    if cur_mode in ("fashion", "issue"):
        is_issue = (cur_mode == "issue")

        with st.expander("🔥 실시간 연예·패션 기사 긁어오기 (해외 서버 차단 없는 실시간 뉴스 수집)", expanded=False):
            c_kw1, c_kw2 = st.columns([3, 1])
            with c_kw1:
                kw_val = st.text_input(
                    "검색 키워드 입력",
                    value="예능 하이라이트" if is_issue else "공항패션",
                    key="news_kw_input"
                )
            with c_kw2:
                st.write("")
                st.write("")
                if st.button("🔍 기사 수집하기", use_container_width=True):
                    with st.spinner("실시간 뉴스 피드에서 기사를 가져오는 중..."):
                        fetched = fetch_realtime_ent_news(kw_val, is_issue=is_issue)
                        st.session_state["crawled_news"] = fetched
                        if not fetched:
                            st.warning("검색 결과가 없습니다. 다른 연예인 이름이나 키워드로 다시 검색해 주세요.")

            # 원클릭 추천 키워드 버튼
            preset_kws = (
                ["예능 하이라이트", "드라마 비하인드", "SNS 근황", "열애 결혼", "컴백 인터뷰"]
                if is_issue
                else ["공항패션", "출근길 패션", "제작발표회", "사복패션", "예능 착장"]
            )
            p_cols = st.columns(len(preset_kws))
            for idx_p, p_kw in enumerate(preset_kws):
                if p_cols[idx_p].button(p_kw, key=f"preset_{cur_mode}_{idx_p}", use_container_width=True):
                    with st.spinner(f"'{p_kw}' 최신 기사 수집 중..."):
                        st.session_state["crawled_news"] = fetch_realtime_ent_news(p_kw, is_issue=is_issue)

            if st.session_state.get("crawled_news"):
                news_map = {f"[{it['source']}] {it['title']}": it["url"] for it in st.session_state["crawled_news"]}
                picked_list = st.multiselect("변환할 기사를 선택하세요 (여러 개 동시 선택 가능):", list(news_map.keys()))
                if st.button("✅ 선택한 기사 URL 아래 입력창에 넣기", type="primary"):
                    existing_u = st.session_state.get("url_input_val", "").strip()
                    new_u = "\n".join([news_map[t] for t in picked_list])
                    st.session_state["url_input_val"] = (existing_u + "\n" + new_u).strip() if existing_u else new_u
                    st.rerun()

        u_hdr1, u_hdr2 = st.columns([4, 1])
        with u_hdr1:
            st.markdown(f"**1. {'연예인 이슈·근황' if is_issue else '패션·착장 분석'} 블로그 / 기사 URL 붙여넣기 (줄바꿈으로 동시 입력)**")
        with u_hdr2:
            if st.button("🧹 URL 비우기", use_container_width=True):
                st.session_state["url_input_val"] = ""
                st.rerun()

        url_box = st.text_area(
            "URL 입력",
            value=st.session_state.get("url_input_val", ""),
            height=95,
            label_visibility="collapsed",
            placeholder="https://blog.naver.com/... 또는 위 [실시간 기사 긁어오기]에서 선택한 주소를 입력하세요"
        )
        st.session_state["url_input_val"] = url_box

        extra_note = st.text_input(
            "강조 포인트 (선택사항)",
            placeholder="예: 방송 속 결정적 멘트 강조, 팬들 반응 위주로 써줘" if is_issue else "예: 하객룩 코디 추천 강조, 키작녀 비율 보완 팁 위주로 써줘"
        )

        btn_label = "🔥 [이슈 모드] 선택한 문체로 입력한 URL 일괄 변환 & 보관함 저장" if is_issue else "👗 [패션 모드] 선택한 문체로 입력한 URL 일괄 변환 & 보관함 저장"
        if st.button(btn_label, type="primary", use_container_width=True):
            urls = [u.strip() for u in url_box.splitlines() if u.strip().startswith("http")]
            if not urls:
                st.warning("URL 입력창에 유효한 웹 주소(https://...)를 하나 이상 입력해 주세요!")
            else:
                mode_tag = "[이슈]" if is_issue else "[패션]"
                active_rules = ISSUE_FORMAT_RULES if is_issue else FASHION_FORMAT_RULES
                sys_prompt = DEFAULT_STYLES[style_choice] + active_rules

                for idx, target_u in enumerate(urls, start=1):
                    with st.spinner(f"[{idx}/{len(urls)}] {mode_tag} 본문·고화질 사진 추출 및 상위 5% 원고 작성 중..."):
                        try:
                            p_title, o_body, img_bytes_list, ai_thumbs = extract_blog_text_and_photos(target_u)
                            img_cnt = len(img_bytes_list)

                            mode_inst = (
                                "2. [연예인 이슈·근황 모드]: 옷·가방 코디 추천은 쓰지 말고 사건·방송·SNS 근황 전말과 대중 반응을 스토리텔링해 줘!\n"
                                if is_issue
                                else "2. [패션·착장 분석 모드]: 각 인물 섹션마다 서로 다른 착장 사진 2~3장을 배치하고 컬러 배색·실생활 코디 팁을 포함해 줘!\n"
                            )
                            prompt_txt = (
                                f"[중요 지시사항]\n"
                                f"1. 네이버 상위 5% 애드포스트 기준인 '공백 제외 1,500자 ~ 2,000자' 분량을 정확히 맞춰 작성해 줘!\n"
                                f"{mode_inst}"
                                f"3. 자기소개 멘트 절대 금지! 맨 위 [제목 추천 1], [제목 추천 2] 직후 바로 핵심 내용으로 시작해.\n"
                                f"4. 첨부된 실제 사진 {img_cnt}장을 확인하고 각 [사진 N] 위아래에 실제 장면·착장과 일치하는 내용을 써줘.\n"
                                f"5. 한 줄 20자 이내 줄바꿈, 3~5줄 문단 + [사진 N] 리듬 유지, 3색 파스텔 형광펜([[ ]], [b[ ]b], [p[ ]p]) 적용!\n"
                                f"6. 마지막 줄에 '출처-' 표기 후 바로 아래 '===TAGS===' 다음 줄에 태그 30개를 쉼표로 구분해 뽑아줘.\n"
                            )
                            if extra_note.strip():
                                prompt_txt += f"[추가 강조 요청]: {extra_note.strip()}\n"
                            prompt_txt += f"\n[원본 제목]: {p_title}\n\n[참고 원문 및 사진 순서표]:\n{o_body}"

                            contents = [prompt_txt]
                            for i_idx, th in enumerate(ai_thumbs[:10], start=1):
                                contents.append(f"[첨부 사진 {i_idx}번]")
                                contents.append(th)

                            full_resp = ""
                            for m_name in ["gemini-3.5-flash-lite", "gemini-3.5-flash"]:
                                try:
                                    resp = client.models.generate_content(
                                        model=m_name,
                                        contents=contents,
                                        config=types.GenerateContentConfig(system_instruction=sys_prompt),
                                    )
                                    if resp.text:
                                        full_resp = resp.text
                                        break
                                except Exception:
                                    continue

                            if full_resp:
                                if "===TAGS===" in full_resp:
                                    b_part, t_part = full_resp.split("===TAGS===", 1)
                                    body_clean = format_mobile_paragraph_spacing(b_part.strip())
                                    tags_list = [t.strip().lstrip("#") for t in t_part.split(",") if t.strip()][:30]
                                    tags_clean = ", ".join(dict.fromkeys(tags_list))
                                else:
                                    body_clean = format_mobile_paragraph_spacing(full_resp.strip())
                                    tags_clean = ""

                                plain_clean = strip_all_markers(body_clean)
                                c_len = len(re.sub(r"\s+", "", plain_clean))
                                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                                label_str = f"{ts_str}_{mode_tag}_{p_title[:24]} [고화질사진 {img_cnt}장 · 공백제외 {c_len}자]"

                                st.session_state["archive_list"].insert(0, {
                                    "label": label_str,
                                    "title": p_title,
                                    "body": body_clean,
                                    "html": build_naver_html(body_clean),
                                    "plain": plain_clean,
                                    "tags": tags_clean,
                                    "images": img_bytes_list,
                                    "char_count": c_len,
                                })
                                st.session_state["selected_archive_idx"] = 0
                        except Exception as e:
                            st.error(f"{idx}번 URL 처리 오류: {e}")

    else:
        # ==========================================================
        # [탭 3: 맛집 후기 자동화 모드 UI]
        # ==========================================================
        st.markdown("**1. 직접 찍은 맛집 사진 불러오기 (최대 15장 · 갤럭시/아이폰/PC 사진 선택)**")
        uploaded_food_files = st.file_uploader(
            "맛집 사진 선택",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

        f_col1, f_col2 = st.columns(2)
        with f_col1:
            store_name_input = st.text_input("식당 상호명 & 지역 (필수)", placeholder="예: 부평 투파인드피터 / 신중동 럭키족발")
        with f_col2:
            menu_info_input = st.text_input("주문한 메뉴 & 가격/특징", placeholder="예: 참나무 장작 바베큐 족발, 오복쟁반막국수")

        food_guideline_input = st.text_area(
            "협찬/체험단 가이드라인 또는 강조할 맛 포인트 (선택사항)",
            height=80,
            placeholder="예: 네이버 영수증 리뷰 시 살얼음 막걸리 무료 증정 이벤트 강조, 데이트 코스로 추천하는 분위기 강조"
        )

        if st.button("🍽️ [맛집 모드] 업로드한 사진으로 맛집 리뷰 원고 & 사진 보정 일괄 생성", type="primary", use_container_width=True):
            if not uploaded_food_files:
                st.warning("맛집 사진을 1장 이상 업로드해 주세요!")
            elif not store_name_input.strip():
                st.warning("식당 상호명 & 지역을 입력해 주세요!")
            else:
                with st.spinner(f"업로드된 사진 {len(uploaded_food_files)}장 보정 및 생생 맛집 후기 원고 작성 중..."):
                    try:
                        food_img_bytes = []
                        food_thumbs = []
                        for up_f in uploaded_food_files[:15]:
                            with Image.open(up_f) as raw_im:
                                edited_im = process_unique_image(raw_im, apply_crop=False)
                                buf = io.BytesIO()
                                edited_im.save(buf, format="JPEG", quality=96, subsampling=0)
                                food_img_bytes.append(buf.getvalue())

                                th = edited_im.copy()
                                th.thumbnail((512, 512))
                                food_thumbs.append(th)

                        img_cnt = len(food_img_bytes)
                        sys_prompt = DEFAULT_STYLES[style_choice] + FOOD_FORMAT_RULES
                        prompt_txt = (
                            f"[맛집 후기 작성 지시사항]\n"
                            f"1. 상호명 및 지역: {store_name_input.strip()}\n"
                            f"2. 주문 메뉴 및 특징: {menu_info_input.strip() or '첨부된 사진 속 메뉴 참고'}\n"
                            f"3. 추가 강조/가이드라인: {food_guideline_input.strip() or '실제 방문 후기 톤으로 생생하게 작성'}\n"
                            f"4. 첨부된 실제 사진 {img_cnt}장([첨부 사진 1번]~[첨부 사진 {img_cnt}번])의 순서와 실제 음식·매장 모습을 정확히 일치시켜 "
                            f"[사진 1]~[사진 {img_cnt}]까지 본문 3~5줄마다 하나도 빠짐없이 배치해 줘!\n"
                            f"5. 공백 제외 1,200~1,800자 분량, 한 줄 20자 이내 줄바꿈, 3색 파스텔 형광펜([[ ]], [b[ ]b], [p[ ]p]) 적용, "
                            f"마지막 줄 '출처-' 및 '===TAGS===' 아래 맛집 태그 30개를 출력해 줘.\n"
                        )

                        contents = [prompt_txt]
                        for i_idx, th in enumerate(food_thumbs, start=1):
                            contents.append(f"[첨부 사진 {i_idx}번]")
                            contents.append(th)

                        full_resp = ""
                        for m_name in ["gemini-3.5-flash-lite", "gemini-3.5-flash"]:
                            try:
                                resp = client.models.generate_content(
                                    model=m_name,
                                    contents=contents,
                                    config=types.GenerateContentConfig(system_instruction=sys_prompt),
                                )
                                if resp.text:
                                    full_resp = resp.text
                                    break
                            except Exception:
                                continue

                        if full_resp:
                            if "===TAGS===" in full_resp:
                                b_part, t_part = full_resp.split("===TAGS===", 1)
                                body_clean = format_mobile_paragraph_spacing(b_part.strip())
                                tags_list = [t.strip().lstrip("#") for t in t_part.split(",") if t.strip()][:30]
                                tags_clean = ", ".join(dict.fromkeys(tags_list))
                            else:
                                body_clean = format_mobile_paragraph_spacing(full_resp.strip())
                                tags_clean = ""

                            plain_clean = strip_all_markers(body_clean)
                            c_len = len(re.sub(r"\s+", "", plain_clean))
                            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                            title_clean = store_name_input.strip()
                            label_str = f"{ts_str}_[맛집]_{title_clean[:24]} [보정사진 {img_cnt}장 · 공백제외 {c_len}자]"

                            st.session_state["archive_list"].insert(0, {
                                "label": label_str,
                                "title": title_clean,
                                "body": body_clean,
                                "html": build_naver_html(body_clean),
                                "plain": plain_clean,
                                "tags": tags_clean,
                                "images": food_img_bytes,
                                "char_count": c_len,
                            })
                            st.session_state["selected_archive_idx"] = 0
                    except Exception as e:
                        st.error(f"맛집 원고 생성 중 오류 발생: {e}")

    # ==========================================================
    # 2. 생성 완료 보관함 & 3. 완성된 원고 본문 & 4. 추천 태그 30개
    # ==========================================================
    st.divider()
    arc_h1, arc_h2, arc_h3 = st.columns([3, 1, 1.2])
    with arc_h1:
        st.markdown("**2. 생성 완료 보관함 ([패션] / [이슈] / [맛집] 자동 구분)**")
    with arc_h2:
        if st.button("🗑️ 선택 항목 삭제", use_container_width=True):
            if st.session_state["archive_list"]:
                idx_del = st.session_state["selected_archive_idx"]
                st.session_state["archive_list"].pop(idx_del)
                st.session_state["selected_archive_idx"] = 0
                st.rerun()
    with arc_h3:
        st.link_button("✍️ 네이버 블로그 글쓰기", "https://blog.naver.com/GoBlogWrite.naver", use_container_width=True)

    if st.session_state["archive_list"]:
        labels = [it["label"] for it in st.session_state["archive_list"]]
        sel_idx = st.selectbox(
            "보관함 목록 선택",
            range(len(labels)),
            index=min(st.session_state["selected_archive_idx"], len(labels) - 1),
            format_func=lambda i: labels[i],
            label_visibility="collapsed"
        )
        st.session_state["selected_archive_idx"] = sel_idx
        cur_item = st.session_state["archive_list"][sel_idx]

        # 3. 완성된 원고 본문 헤더 및 원클릭 서식 복사 + 사진 ZIP 다운로드
        st.markdown(f"**3. 완성된 원고 본문 (공백 제외 {cur_item['char_count']}자 · 3색 파스텔 음영 & 컬러/인용구 적용)**")

        act_c1, act_c2 = st.columns(2)
        with act_c1:
            render_web_copy_button(
                cur_item["html"],
                cur_item["plain"],
                btn_label="📋 원고 서식 그대로 복사 (네이버 에디터 Ctrl+V)",
                key_id=f"copy_rich_{sel_idx}"
            )
        with act_c2:
            if cur_item["images"]:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for img_i, img_b in enumerate(cur_item["images"], start=1):
                        zf.writestr(f"사진_{img_i}.jpg", img_b)
                st.download_button(
                    label=f"📦 가공된 사진 {len(cur_item['images'])}장 ZIP 다운로드",
                    data=zip_buf.getvalue(),
                    file_name=f"이서블리_사진_{sel_idx+1}.zip",
                    mime="application/zip",
                    use_container_width=True
                )

        if cur_item["images"]:
            with st.expander(f"🖼️ 가공된 고화질 사진 {len(cur_item['images'])}장 미리보기"):
                p_cols = st.columns(min(5, len(cur_item["images"])))
                for img_i, img_b in enumerate(cur_item["images"]):
                    p_cols[img_i % 5].image(img_b, caption=f"사진 {img_i+1}", use_container_width=True)

        st.text_area(
            "완성된 원고 본문",
            value=cur_item["body"],
            height=360,
            label_visibility="collapsed",
            key=f"res_body_{sel_idx}"
        )

        # 4. 네이버 유입 최적화 추천 태그 30개
        tag_cnt = len([t for t in cur_item["tags"].split(",") if t.strip()])
        st.markdown(f"**4. 네이버 유입 최적화 추천 태그 ({tag_cnt}개 — 아래 박스를 전체 선택해 복사하세요)**")
        st.text_area(
            "추천 태그 30개",
            value=cur_item["tags"],
            height=75,
            label_visibility="collapsed",
            key=f"res_tags_{sel_idx}"
        )
    else:
        st.info("위에서 기사 URL을 입력하거나 맛집 사진을 업로드한 뒤 변환 버튼을 누르면 이곳에 원고와 사진이 생성됩니다.")

# ==========================================================
# 우측 전용 사이드 패널: 일 방문자 1만+ 트래픽 공략 & 운영 메모장
# ==========================================================
with right_col:
    st.markdown('<div class="memo-box-header">📋 1만+ 방문자 공략 & 운영 메모장</div>', unsafe_allow_html=True)
    memo_edited = st.text_area(
        "운영 메모장",
        value=st.session_state["strategy_memo"],
        height=640,
        label_visibility="collapsed"
    )
    m_b1, m_b2 = st.columns(2)
    with m_b1:
        if st.button("💾 내 메모 저장", type="primary", use_container_width=True):
            st.session_state["strategy_memo"] = memo_edited
            st.toast("메모가 현재 세션에 저장되었습니다!", icon="✅")
    with m_b2:
        if st.button("🔄 기본값 복원", use_container_width=True):
            st.session_state["strategy_memo"] = DEFAULT_STRATEGY_MEMO
            st.rerun()
