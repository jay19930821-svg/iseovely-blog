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
import time
import base64
import http.cookiejar
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
    http_options=types.HttpOptions(timeout=60000)
)

# ==========================================
# 기본 데이터 (운영 매뉴얼, 문체 프로필, 3대 모드 규칙)
# ==========================================
DEFAULT_STRATEGY_MEMO = """📌 [일 방문자 1만+ 달성 운영 매뉴얼]

1️⃣ 하루 목표 발행량 & 간격
- 하루 3~5개 포스팅 (패션 2~3개 + 연예 이슈 1~2개 황금 비율)
- 2~3시간 간격 예약 발행으로 홈피드 노출 빈도 극대화

2️⃣ 추천 발행 골든타임
- [오전 07:00 ~ 09:00] 전날 밤 드라마·예능 착장 & 방송 화제 장면
- [오후 12:00 ~ 13:30] 점심시간 실시간 연예인 SNS 근황·이슈
- [밤 22:00 ~ 24:00] 저녁 포토월·인스타 업로드 (다음 날 새벽 홈피드 유입)

3️⃣ 모드별 소재 활용 팁
- [👗 패션·착장 모드]: 네이트 실시간 관심뉴스 1~20위 + 패션 블로그 인기 1~20위 동시 활용
- [🔥 연예인 이슈 모드]: 네이트 연예 실시간 급상승 관심뉴스 1~20위 선택 일괄 변환
- [🍽️ 맛집 후기 모드]: 직접 찍은 사진 불러오기 → 체험단 가이드라인 입력 후 바로 생성

4️⃣ 자동화 프로그램 30초 발행 순서
① 상단에서 [👗 패션], [🔥 이슈], [🍽️ 맛집] 모드 선택
② 네이트 실시간 1~20위 기사 선택 또는 맛집 사진 업로드
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
    "첨부된 실제 사진이 있으면 직접 확인하고 각 [사진 N] 위아래에는 해당 사진에 실제로 보이는 옷 색상·아이템·핏만 묘사해. (첨부 사진이 0장이면 [사진 N] 표기 없이 본문만 작성해.)\n"
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
    "첨부된 실제 사진이 있으면 직접 확인하고 각 소제목 섹션마다 [사진 1]~[사진 N]을 3~5줄 글과 번갈아 배치하며 해당 사진 속 실제 장면·표정과 일치하게 묘사해. (첨부 사진이 0장이면 [사진 N] 표기 없이 작성해.)\n"
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
# 해외 IP 차단 우회 멀티 파이프라인 (r.jina.ai + 직통)
# ==========================================
def process_unique_image(pil_img, apply_crop=True):
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

def decode_google_news_url(source_url):
    if "news.google.com" not in source_url:
        return source_url

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        ("Accept-Language", "ko-KR,ko;q=0.9,en-US;q=0.8"),
    ]

    try:
        path_part = urllib.parse.urlparse(source_url).path.split("/")[-1]
        padded = path_part + "=" * (-len(path_part) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        url_match = re.search(rb"https?://[^\x00-\x1f\x7f\"'<>]+", decoded_bytes)
        if url_match:
            cand = url_match.group(0).decode("utf-8", errors="ignore")
            if "news.google.com" not in cand:
                return cand
    except Exception:
        pass

    try:
        article_id = urllib.parse.urlparse(source_url).path.split("/")[-1]
        fetch_u = f"https://news.google.com/articles/{article_id}"
        with opener.open(fetch_u, timeout=10) as resp:
            final_u = resp.geturl()
            if "news.google.com" not in final_u:
                return final_u
            html_str = resp.read().decode("utf-8", errors="ignore")

        ts_m = re.search(r'data-n-a-ts=["\'](\d+)["\']', html_str)
        sg_m = re.search(r'data-n-a-sg=["\']([^"\']+)["\']', html_str)
        if ts_m and sg_m:
            ts_val, sg_val = ts_m.group(1), sg_m.group(1)
            payload_inner = (
                f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"KR:ko",null,1,null,null,null,null,null,0,1],'
                f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{article_id}",{ts_val},"{sg_val}"]'
            )
            req_body = urllib.parse.urlencode({
                "f.req": json.dumps([[["Fbv4je", payload_inner, None, "generic"]]])
            }).encode("utf-8")

            api_req = urllib.request.Request(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                data=req_body,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            )
            with opener.open(api_req, timeout=10) as api_resp:
                api_txt = api_resp.read().decode("utf-8", errors="ignore")
            real_m = re.search(r'\["garturlres","(https?://[^"]+)"', api_txt)
            if real_m:
                return real_m.group(1).replace("\\u003d", "=").replace("\\u0026", "&")
    except Exception:
        pass

    return source_url

def normalize_target_url(raw_url):
    u = decode_google_news_url(raw_url.strip())
    if "blog.naver.com/" in u and "m.blog.naver.com/" not in u:
        blog_id_m = re.search(r"blogId=([^&]+)", u)
        log_no_m = re.search(r"logNo=(\d+)", u)
        if blog_id_m and log_no_m:
            return f"https://m.blog.naver.com/{blog_id_m.group(1)}/{log_no_m.group(1)}"
        u = u.replace("https://blog.naver.com/", "https://m.blog.naver.com/").replace("http://blog.naver.com/", "https://m.blog.naver.com/")
    return u

def fetch_via_jina_reader(target_url):
    """해외 클라우드 서버에서 한국 사이트 차단을 뚫고 렌더링된 마크다운(링크+이미지 포함) 추출"""
    if "news.google.com" in target_url:
        raise ValueError("구글 뉴스 암호화 링크를 원본 블로그 주소로 변환하지 못했습니다. 다른 패션 블로그 항목을 선택해 주세요.")
    jina_u = f"https://r.jina.ai/{target_url}"
    req = urllib.request.Request(
        jina_u,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/plain, text/markdown, */*",
            "X-Return-Format": "markdown",
        }
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def fetch_html_smart(target_url, referer="https://news.nate.com/"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": referer,
    }
    try:
        req = urllib.request.Request(target_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            final_url = resp.geturl()
            raw_bytes = resp.read()
            try:
                page_html = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                page_html = raw_bytes.decode("euc-kr", errors="ignore")
        if len(page_html) > 1000 and ("news.nate.com/view/" in page_html or "se-main-container" in page_html or "realArtcContents" in page_html or "artcContents" in page_html):
            return final_url, page_html
    except Exception:
        pass
    return target_url, ""

def fetch_nate_ent_top20():
    """네이트 연예 실시간 급상승 관심뉴스 1~20위(news.nate.com/rank/interest?sc=ent) 수집 (해외 IP 우회 포함)"""
    results = []
    seen_urls = set()
    seen_titles = set()

    rank_targets = [
        "https://news.nate.com/rank/interest?sc=ent",
        "https://m.news.nate.com/rank/interest?sc=ent",
    ]

    # 1차: 직통 HTML 파싱 시도
    for r_url in rank_targets:
        _, h_str = fetch_html_smart(r_url)
        if not h_str:
            continue
        matches = re.findall(
            r'<a[^>]+href=["\']((?:https?:)?//(?:m\.)?news\.nate\.com/view/[^"\']+)["\'][^>]*>(.*?)</a>',
            h_str,
            re.DOTALL | re.IGNORECASE
        )
        for href, inner_html in matches:
            clean_u = ("https:" + href if href.startswith("//") else href).split("?")[0]
            clean_u = clean_u.replace("://m.news.nate.com/", "://news.nate.com/")
            if clean_u in seen_urls:
                continue
            tit_m = re.search(r'class=["\'][^"\']*(?:tit|subject|title)[^"\']*["\'][^>]*>(.*?)</', inner_html, re.DOTALL | re.IGNORECASE)
            raw_t = tit_m.group(1) if tit_m else inner_html
            title_txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw_t))).strip()
            title_txt = re.sub(r"^\d{1,2}\s+", "", title_txt).strip()
            if len(title_txt) >= 10 and title_txt not in seen_titles:
                seen_urls.add(clean_u)
                seen_titles.add(title_txt)
                results.append({"source": "네이트연예", "title": title_txt, "url": clean_u})
                if len(results) >= 20:
                    return results[:20]

    # 2차: 해외 IP 차단으로 직통 실패 시 r.jina.ai 리더 엔진으로 네이트 관심뉴스 1~20위 마크다운 링크 파싱
    if len(results) < 10:
        for r_url in rank_targets:
            try:
                md_txt = fetch_via_jina_reader(r_url)
                md_links = re.findall(
                    r'\[([^\]]{8,150})\]\((https?://(?:m\.)?news\.nate\.com/view/[^\s\)]+)\)',
                    md_txt
                )
                for raw_t, href in md_links:
                    clean_u = href.split("?")[0].replace("://m.news.nate.com/", "://news.nate.com/")
                    if clean_u in seen_urls:
                        continue
                    if raw_t.strip().startswith("!") or "Image" in raw_t:
                        continue
                    title_txt = re.sub(r"!\[.*?\]\(.*?\)", "", raw_t)
                    title_txt = re.sub(r"\s+", " ", title_txt).strip()
                    title_txt = re.sub(r"^\d{1,2}\s+", "", title_txt).strip()
                    if len(title_txt) >= 10 and title_txt not in seen_titles:
                        seen_urls.add(clean_u)
                        seen_titles.add(title_txt)
                        results.append({"source": "네이트연예", "title": title_txt, "url": clean_u})
                        if len(results) >= 20:
                            return results[:20]
            except Exception:
                continue

    return results[:20]

def fetch_fashion_blogs_top20():
    """탭 1 전용: 공감수·댓글수·인플루언서 반응이 검증된 상위 인기 패션 블로그 1~20위 필터링 수집"""
    verified_results = []
    fallback_results = []
    seen_urls = set()
    seen_titles = set()

    queries = [
        "연예인 공항패션 착장",
        "연예인 사복패션 브랜드",
        "드라마 제작발표회 패션",
        "연예인 인스타 사복 코디",
    ]

    fashion_keywords = ["공항패션", "사복", "패션", "착장", "코디", "브랜드", "가방", "원피스", "자켓", "화보", "제작발표회", "하객룩"]

    for q in queries:
        if len(verified_results) >= 20:
            break
        m_search_u = f"https://m.search.naver.com/search.naver?where=m_blog&sm=mtb_jum&query={urllib.parse.quote(q)}"
        _, h_str = fetch_html_smart(m_search_u, referer="https://m.naver.com/")
        if not h_str:
            pc_search_u = f"https://search.naver.com/search.naver?ssc=tab.blog.all&sm=tab_jum&query={urllib.parse.quote(q)}"
            _, h_str = fetch_html_smart(pc_search_u, referer="https://www.naver.com/")

        if h_str:
            blocks = re.split(r'<li[^>]+class=["\'][^"\']*(?:bx|view_wrap|lst_total)[^"\']*["\']', h_str, flags=re.IGNORECASE)
            if len(blocks) <= 1:
                blocks = [h_str]

            for blk in blocks:
                link_m = re.search(
                    r'<a[^>]+href=["\'](https?://(?:m\.)?blog\.naver\.com/[a-zA-Z0-9_-]+/\d+[^"\']*)["\'][^>]*>(.*?)</a>',
                    blk,
                    re.DOTALL | re.IGNORECASE
                )
                if not link_m:
                    continue

                clean_u = link_m.group(1).split("?")[0].replace("://blog.naver.com/", "://m.blog.naver.com/")
                if clean_u in seen_urls:
                    continue

                all_a_texts = [
                    re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t_html))).strip()
                    for _, t_html in re.findall(r'<a[^>]+href=["\']https?://(?:m\.)?blog\.naver\.com/[^"\']+["\'][^>]*>(.*?)</a>', blk, re.DOTALL | re.IGNORECASE)
                ]
                title_txt = max(all_a_texts, key=len) if all_a_texts else ""
                if len(title_txt) < 10 or title_txt in seen_titles:
                    continue

                like_m = re.search(r'(?:공감|좋아요)\s*(\d+)', blk)
                cmt_m = re.search(r'댓글\s*(\d+)', blk)
                is_influencer = bool(re.search(r'(?:in\.naver\.com|인플루언서|influencer)', blk, re.IGNORECASE))

                like_cnt = int(like_m.group(1)) if like_m else 0
                cmt_cnt = int(cmt_m.group(1)) if cmt_m else 0
                has_fashion_kw = any(fk in title_txt for fk in fashion_keywords)

                seen_urls.add(clean_u)
                seen_titles.add(title_txt)

                if is_influencer or like_cnt >= 3 or cmt_cnt >= 1:
                    badge = "인플루언서" if is_influencer else f"공감 {like_cnt}" if like_cnt > 0 else f"댓글 {cmt_cnt}"
                    verified_results.append({
                        "source": f"상위인기·{badge}",
                        "title": title_txt,
                        "url": clean_u,
                    })
                elif has_fashion_kw and len(fallback_results) < 20:
                    fallback_results.append({
                        "source": "패션블로그",
                        "title": title_txt,
                        "url": clean_u,
                    })

                if len(verified_results) >= 20:
                    break

        if len(verified_results) < 10:
            try:
                md_txt = fetch_via_jina_reader(m_search_u)
                for line in md_txt.splitlines():
                    m_link = re.search(r'\[([^\]]{10,120})\]\((https?://(?:m\.)?blog\.naver\.com/[a-zA-Z0-9_-]+/\d+)\)', line)
                    if not m_link:
                        continue
                    raw_t, href = m_link.group(1), m_link.group(2)
                    clean_u = href.split("?")[0].replace("://blog.naver.com/", "://m.blog.naver.com/")
                    title_txt = re.sub(r"!\[.*?\]\(.*?\)", "", raw_t).strip()
                    if clean_u in seen_urls or len(title_txt) < 10 or title_txt in seen_titles:
                        continue

                    seen_urls.add(clean_u)
                    seen_titles.add(title_txt)
                    is_inf_md = ("인플루언서" in line or "in.naver.com" in line or "공감" in line)
                    if is_inf_md:
                        verified_results.append({"source": "상위인기블로그", "title": title_txt, "url": clean_u})
                    elif any(fk in title_txt for fk in fashion_keywords) and len(fallback_results) < 20:
                        fallback_results.append({"source": "패션블로그", "title": title_txt, "url": clean_u})
                    if len(verified_results) >= 20:
                        break
            except Exception:
                pass

    combined = verified_results + [item for item in fallback_results if item["url"] not in {v["url"] for v in verified_results}]
    return combined[:20]

def extract_blog_text_and_photos(raw_url):
    """직통 HTML + r.jina.ai 마크다운 병행 추출로 본문과 고화질 사진(최대 10장) 100% 확보"""
    url = normalize_target_url(raw_url)
    final_url, page_html = fetch_html_smart(url)

    bad_words = [
        "logo", "icon", "banner", "btn", "ad", "sprite", "1x1", "avatar",
        "profile", "blank", "emoticon", "sticker", "map", "static.naver",
        "blogpfthumb", "ogq", "gfmarket", "storep", "transparent",
        "journalist", "reporter", "sns_", "copyright", "qr", "btn_", "svg",
        "se-sticker", "link_thumb", "oglink"
    ]
    saved_images_bytes = []
    ai_thumbs = []
    url_to_photo_tag = {}
    tried_urls = set()

    def try_fetch_image_bytes(target_img_url):
        candidates = [target_img_url]
        if "thumbnews.nateimg.co.kr" in target_img_url and "///" in target_img_url:
            orig_part = target_img_url.split("///", 1)[1]
            if orig_part.startswith("//"):
                orig_part = "https:" + orig_part
            elif not orig_part.startswith("http"):
                orig_part = "https://" + orig_part
            candidates.insert(0, orig_part)

        norm_u = target_img_url.replace("mblogthumb-phinf.pstatic.net", "postfiles.pstatic.net")
        base_u = norm_u.split("?")[0]
        if "postfiles.pstatic.net" in base_u or "blogfiles.pstatic.net" in base_u:
            candidates = [base_u + "?type=w966", base_u + "?type=w800", base_u, target_img_url]

        dl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
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
        u_clean = html.unescape(raw_img_url).strip().rstrip("\\").rstrip("'").rstrip('"')
        if u_clean.startswith("//"):
            u_clean = "https:" + u_clean
        elif u_clean.startswith("/"):
            u_clean = urllib.parse.urljoin(final_url, u_clean)
        if not u_clean.startswith("http") or any(b in u_clean.lower() for b in bad_words):
            return None

        path_only = urllib.parse.urlparse(u_clean).path
        base_key = path_only if ("pstatic.net" in u_clean or "nateimg.co.kr" in u_clean) else u_clean.split("?")[0]
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
                if im.size[0] < 200 or im.size[1] < 160:
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

    page_title = "연예인 패션·이슈 기사"
    body_res = ""

    # 경로 A: 직통 HTML 파싱
    if page_html:
        og_title = re.search(r'(?:property|name)=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
        if og_title:
            page_title = html.unescape(og_title.group(1)).strip()
        else:
            t_m = re.search(r"<title>(.*?)</title>", page_html, re.IGNORECASE | re.DOTALL)
            if t_m:
                page_title = html.unescape(t_m.group(1)).strip()

        og_img_m = re.search(r'(?:property|name)=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
        og_img_url = html.unescape(og_img_m.group(1)).strip() if og_img_m else ""

        body_html = ""
        se_start = re.search(r'<div[^>]+class=["\'][^"\']*se-main-container[^"\']*["\'][^>]*>', page_html, re.IGNORECASE)
        if se_start:
            sub_html = page_html[se_start.end():]
            end_m = re.search(r'(?:<!--\s*//\s*SE_DOC_HEADER_END|<div[^>]+class=["\'][^"\']*(?:post_tag|section_t1|btn_like_area|post_writer|another_category|recommend_post|comment_area))', sub_html, re.IGNORECASE)
            body_html = sub_html[:end_m.start()] if end_m else sub_html
        else:
            for pattern in [
                r'id=["\']realArtcContents["\'][^>]*>(.*?)</div>\s*<!--',
                r'id=["\']artcContents["\'][^>]*>(.*?)</div>',
                r'id=["\']comp_news_article["\'][^>]*>(.*?)</article>',
                r'id=["\']dic_area["\'][^>]*>(.*?)</article>',
                r'id=["\']articleBody["\'][^>]*>(.*?)</(?:div|article|section)>',
                r'<article[^>]*>(.*?)</article>',
            ]:
                m = re.search(pattern, page_html, re.DOTALL | re.IGNORECASE)
                if m and len(m.group(1)) > 150:
                    body_html = m.group(1)
                    break
            if not body_html:
                body_html = page_html

        clean_html = re.sub(r"<script.*?>.*?</script>", "", body_html, flags=re.DOTALL)
        clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL)

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
                src_m = re.search(r'(?:data-lazy-src|data-original|data-src|src)=["\']((?:https?:)?//[^"\']+|/[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', tag_str, re.IGNORECASE)
                if src_m:
                    candidate_src = src_m.group(1)
            if not candidate_src:
                return "\n"
            marker = download_and_save_single_img(candidate_src)
            return f"\n{marker}\n" if marker else "\n"

        html_with_markers = re.sub(r"<(?:img|a|div)\b[^>]*>", replace_media_tag, clean_html, flags=re.IGNORECASE)

        if len(saved_images_bytes) < 10:
            scan_target = html.unescape(body_html if se_start else page_html)
            raw_cdn_imgs = re.findall(
                r'(?:https?:)?//(?:postfiles|blogfiles|mblogthumb-phinf|ssl|imgnews)\.pstatic\.net/[^"\'\s<>\\]+|(?:https?:)?//[^"\'\s<>\\]*nateimg\.co\.kr/[^"\'\s<>\\]+',
                scan_target,
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

        if len(saved_images_bytes) == 0 and og_img_url:
            mk = download_and_save_single_img(og_img_url)
            if mk:
                html_with_markers = f"{mk}\n" + html_with_markers

        text_only = re.sub(r"<[^>]+>", "\n", html_with_markers)
        lines = [line.strip() for line in html.unescape(text_only).splitlines() if line.strip()]
        body_res = "\n".join(lines)[:12000]

    # 경로 B: 본문이 부족하거나, 네이버 블로그에서 지연 로딩으로 사진이 1장 이하만 잡혔을 때 r.jina.ai 렌더링 결과에서 나머지 사진 10장까지 추가 수집
    if len(body_res.strip()) < 80 or ("blog.naver.com" in url and len(saved_images_bytes) <= 1):
        try:
            md_text = fetch_via_jina_reader(url)
            if md_text and len(md_text.strip()) >= 80:
                if page_title == "연예인 패션·이슈 기사":
                    title_m = re.search(r"^Title:\s*(.+)$", md_text, re.MULTILINE)
                    if title_m:
                        page_title = title_m.group(1).strip()

                md_body = md_text.split("Markdown Content:", 1)[1] if "Markdown Content:" in md_text else md_text

                def replace_md_img(m):
                    img_u = m.group(1).strip()
                    mk = download_and_save_single_img(img_u)
                    return f"\n{mk}\n" if mk else "\n"

                md_with_markers = re.sub(r"!\[[^\]]*\]\((https?://[^\s\)]+)\)", replace_md_img, md_body)
                if len(body_res.strip()) < 80:
                    md_clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", md_with_markers)
                    lines = [ln.strip() for ln in md_clean.splitlines() if ln.strip() and not ln.strip().startswith(("URL Source:", "Published Time:"))]
                    body_res = "\n".join(lines)[:12000]
                elif saved_images_bytes:
                    all_markers = "\n".join([f"[사진 {i}]" for i in range(1, len(saved_images_bytes) + 1)])
                    body_res = f"{all_markers}\n" + body_res
        except Exception:
            pass

    if len(body_res.strip()) < 50:
        raise ValueError("해당 기사/블로그 원문을 읽어오지 못했습니다.")

    return page_title, body_res, saved_images_bytes, ai_thumbs

def fetch_clean_nate_photos_for_blog(blog_title, blog_body):
    """블로그 글의 워터마크 사진 대비용: 구글 뉴스 RSS로 한국 연예 보도기사 원문을 찾아 고화질 원본 사진(최대 10장) 추출"""
    combined_src = f"{blog_title} {blog_body[:250]}"
    clean_t = re.sub(r"\[[^\]]*\]|\([^\)]*\)|\[사진\s*\d+\]", " ", combined_src)
    clean_t = re.sub(r"[^\w\s가-힣]", " ", clean_t)
    stop_words = {
        "패션", "코디", "착장", "정보", "브랜드", "가격", "어디꺼", "스타일", "룩",
        "모음", "총정리", "추천", "블로그", "네이버", "요즘", "화제", "인스타", "사복",
        "공항패션", "제작발표회", "출국", "입국", "근황", "일상", "데일리룩", "아이템", "포토"
    }
    tokens = []
    for w in clean_t.split():
        if len(w) >= 2 and w not in stop_words and w not in tokens:
            tokens.append(w)

    search_queries = []
    if len(tokens) >= 2:
        search_queries.append(f"{tokens[0]} {tokens[1]} 패션")
        search_queries.append(f"{tokens[0]} {tokens[1]}")
    elif tokens:
        search_queries.append(f"{tokens[0]} 패션")

    article_urls = []
    seen_u = set()

    for q in search_queries:
        if len(article_urls) >= 4:
            break
        rss_u = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            req = urllib.request.Request(rss_u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_bytes = resp.read()
            root = ET.fromstring(xml_bytes)
            for item in root.findall(".//item"):
                link_el = item.find("link")
                if link_el is None or not link_el.text:
                    continue
                real_u = decode_google_news_url(link_el.text.strip())
                if "news.google.com" in real_u or "blog.naver.com" in real_u or "youtube.com" in real_u:
                    continue
                if real_u not in seen_u:
                    seen_u.add(real_u)
                    article_urls.append(real_u)
                    if len(article_urls) >= 4:
                        break
        except Exception:
            continue

    clean_images = []
    clean_thumbs = []
    matched_sources = []

    for art_u in article_urls:
        if len(clean_images) >= 10:
            break
        try:
            art_title, _, imgs, thumbs = extract_blog_text_and_photos(art_u)
            if imgs:
                matched_sources.append(art_title[:30])
                for im_b, th_im in zip(imgs, thumbs):
                    if len(clean_images) >= 10:
                        break
                    clean_images.append(im_b)
                    clean_thumbs.append(th_im)
        except Exception:
            continue

    return clean_images, clean_thumbs, matched_sources

def generate_with_gemini(contents, sys_prompt):
    err_logs = []
    # 내 API 키에서 실제로 지원되는 generateContent 모델 목록 자동 조회 + 우선순위 정렬
    preferred = ["gemini-3.5-flash", "gemini-3.5-pro-preview", "gemini-2.5-pro", "gemini-3.5-flash-lite"]
    available_models = list(preferred)
    try:
        for m in client.models.list():
            m_id = getattr(m, "name", "").replace("models/", "")
            methods = getattr(m, "supported_actions", []) or getattr(m, "supported_generation_methods", [])
            if m_id and "gemini" in m_id and "embed" not in m_id and "imagen" not in m_id and "veo" not in m_id:
                if not methods or "generateContent" in methods:
                    if m_id not in available_models:
                        available_models.append(m_id)
    except Exception:
        pass

    trimmed_contents = []
    img_added = 0
    for item in contents:
        if isinstance(item, str):
            trimmed_contents.append(item)
        elif img_added < 4:
            trimmed_contents.append(item)
            img_added += 1

    text_only_contents = [c for c in contents if isinstance(c, str) and not c.startswith("[첨부 사진")]

    for attempt in range(2):
        for m_name in available_models[:5]:
            try:
                resp = client.models.generate_content(
                    model=m_name,
                    contents=trimmed_contents if attempt == 0 else text_only_contents,
                    config=types.GenerateContentConfig(system_instruction=sys_prompt),
                )
                if resp and resp.text:
                    return resp.text
            except Exception as e:
                err_str = str(e)
                err_logs.append(f"[{m_name}] {err_str[:90]}")
                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str:
                    time.sleep(5)
                continue

    raise RuntimeError("구글 AI 서버 일시 트래픽 폭주(503)입니다. 2~3분 후 다시 눌러주세요! 상세: " + " / ".join(dict.fromkeys(err_logs)))

# ==========================================
# 세션 상태 초기화 (탭별 100% 독립 저장소)
# ==========================================
if "active_mode" not in st.session_state:
    st.session_state["active_mode"] = "fashion"
if "strategy_memo" not in st.session_state:
    st.session_state["strategy_memo"] = DEFAULT_STRATEGY_MEMO

for m_key in ("fashion", "issue", "food"):
    if f"archive_{m_key}" not in st.session_state:
        st.session_state[f"archive_{m_key}"] = []
    if f"sel_idx_{m_key}" not in st.session_state:
        st.session_state[f"sel_idx_{m_key}"] = 0
    if f"news_{m_key}" not in st.session_state:
        st.session_state[f"news_{m_key}"] = []
    if f"urls_{m_key}" not in st.session_state:
        st.session_state[f"urls_{m_key}"] = ""

# ==========================================
# 메인 2단 레이아웃
# ==========================================
left_col, right_col = st.columns([2.4, 1.0], gap="medium")

with left_col:
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
    mode_archive_key = f"archive_{cur_mode}"
    mode_sel_key = f"sel_idx_{cur_mode}"
    mode_news_key = f"news_{cur_mode}"
    mode_urls_key = f"urls_{cur_mode}"

    if cur_mode == "fashion":
        st.markdown('<div class="mode-banner-fashion">👗 현재 모드: [패션·착장 분석 전용] — 아이템·브랜드·컬러 배색·실생활 코디 팁 중심으로 작성합니다.</div>', unsafe_allow_html=True)
    elif cur_mode == "issue":
        st.markdown('<div class="mode-banner-issue">🔥 현재 모드: [연예인 이슈·근황 전용] — 사건·방송 핵심 요약, 대중 반응, 비하인드 스토리 중심으로 작성합니다.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="mode-banner-food">🍽️ 현재 모드: [맛집 후기 자동화 전용] — 직접 찍은 음식·매장 사진 분석 + 협찬/체험단 가이드라인을 반영해 작성합니다.</div>', unsafe_allow_html=True)

    style_choice = st.selectbox(
        "0. 적용할 블로그 문체 스타일 선택 (심플 3색 파스텔 형광펜 · 포인트 글자색 · 인용구 자동 적용)",
        list(DEFAULT_STYLES.keys()),
        key=f"style_sel_{cur_mode}"
    )

    if cur_mode in ("fashion", "issue"):
        is_issue = (cur_mode == "issue")

        with st.container(border=True):
            st.markdown("**🔥 네이트(NATE) 실시간 급상승 관심뉴스 1~20위 긁어오기**")

            if not is_issue:
                nc1, nc2 = st.columns(2)
                with nc1:
                    if st.button("🏆 네이트 실시간 관심뉴스 1~20위 불러오기", type="primary", use_container_width=True, key="btn_nate_fashion"):
                        with st.spinner("네이트 실시간 급상승 관심뉴스 1~20위를 불러오는 중..."):
                            fetched = fetch_nate_ent_top20()
                            st.session_state[mode_news_key] = fetched
                            if not fetched:
                                st.error("네이트 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
                with nc2:
                    if st.button("👗 패션 블로그 인기 1~20위 불러오기", type="primary", use_container_width=True, key="btn_blog_fashion"):
                        with st.spinner("연예인 패션 인기 블로그 1~20위를 불러오는 중..."):
                            fetched = fetch_fashion_blogs_top20()
                            st.session_state[mode_news_key] = fetched
            else:
                if st.button("🏆 네이트 실시간 급상승 관심뉴스 1~20위 불러오기", type="primary", use_container_width=True, key="btn_nate_issue"):
                    with st.spinner("네이트 실시간 급상승 관심뉴스 1~20위를 불러오는 중..."):
                        fetched = fetch_nate_ent_top20()
                        st.session_state[mode_news_key] = fetched
                        if not fetched:
                            st.error("네이트 서버에서 목록을 받아오지 못했습니다. 잠시 후 다시 시도해 주세요.")

            if st.session_state[mode_news_key]:
                st.caption(f"총 {len(st.session_state[mode_news_key])}개의 실시간 기사가 수집되었습니다. 변환할 기사를 여러 개 체크한 뒤 아래 버튼을 눌러주세요.")
                selected_items = []
                with st.container(height=260):
                    for idx_n, item in enumerate(st.session_state[mode_news_key], start=1):
                        if st.checkbox(f"{idx_n:02d}위. [{item['source']}] {item['title']}", key=f"chk_{cur_mode}_{idx_n}"):
                            selected_items.append(item)

                if st.button("✅ 선택한 기사 URL 아래 입력창에 넣기", type="primary", use_container_width=True, key=f"btn_put_{cur_mode}"):
                    if not selected_items:
                        st.warning("위 1~20위 목록에서 기사를 하나 이상 체크해 주세요!")
                    else:
                        existing_u = st.session_state.get(f"textarea_url_{cur_mode}", "").strip()
                        picked_urls = [it["url"] for it in selected_items]
                        new_u = "\n".join(picked_urls)
                        combined_u = (existing_u + "\n" + new_u).strip() if existing_u else new_u
                        st.session_state[mode_urls_key] = combined_u
                        st.session_state[f"textarea_url_{cur_mode}"] = combined_u
                        st.rerun()

        u_hdr1, u_hdr2 = st.columns([4, 1])
        with u_hdr1:
            st.markdown(f"**1. {'연예인 이슈·근황' if is_issue else '패션·착장 분석'} 네이트 기사 / 네이버 블로그 URL 붙여넣기 (줄바꿈으로 동시 입력)**")
        with u_hdr2:
            if st.button("🧹 URL 비우기", use_container_width=True, key=f"btn_clear_{cur_mode}"):
                st.session_state[mode_urls_key] = ""
                st.session_state[f"textarea_url_{cur_mode}"] = ""
                st.rerun()

        if f"textarea_url_{cur_mode}" not in st.session_state:
            st.session_state[f"textarea_url_{cur_mode}"] = st.session_state.get(mode_urls_key, "")

        url_box = st.text_area(
            "URL 입력",
            height=95,
            label_visibility="collapsed",
            placeholder="https://news.nate.com/view/... 또는 https://blog.naver.com/... 주소를 입력하세요",
            key=f"textarea_url_{cur_mode}"
        )
        st.session_state[mode_urls_key] = url_box

        extra_note = st.text_input(
            "강조 포인트 (선택사항)",
            placeholder="예: 방송 속 결정적 멘트 강조, 팬들 반응 위주로 써줘" if is_issue else "예: 하객룩 코디 추천 강조, 키작녀 비율 보완 팁 위주로 써줘",
            key=f"extra_note_{cur_mode}"
        )

        btn_label = "🔥 [이슈 모드] 선택한 문체로 입력한 URL 일괄 변환 & 보관함 저장" if is_issue else "👗 [패션 모드] 선택한 문체로 입력한 URL 일괄 변환 & 보관함 저장"
        if st.button(btn_label, type="primary", use_container_width=True, key=f"btn_gen_{cur_mode}"):
            urls = [u.strip() for u in url_box.splitlines() if u.strip().startswith("http")]
            if not urls:
                st.warning("URL 입력창에 유효한 웹 주소(https://...)를 하나 이상 입력해 주세요!")
            else:
                mode_tag = "[이슈]" if is_issue else "[패션]"
                active_rules = ISSUE_FORMAT_RULES if is_issue else FASHION_FORMAT_RULES
                sys_prompt = DEFAULT_STYLES[style_choice] + active_rules
                generated_any = False

                for idx, target_u in enumerate(urls, start=1):
                    with st.spinner(f"[{idx}/{len(urls)}] {mode_tag} 본문·고화질 사진 추출 및 상위 5% 원고 일괄 작성 중..."):
                        try:
                            p_title, o_body, img_bytes_list, ai_thumbs = extract_blog_text_and_photos(target_u)
                            if len(o_body.strip()) < 50:
                                raise ValueError("해당 URL에서 본문을 읽어오지 못했습니다. 주소가 올바른지 확인해 주세요.")

                            # 탭 1(패션 모드)에서 블로그 URL 입력 시: 블로그 사진 최대 10장은 그대로 유지 + 워터마크 대비용 원본 기사 사진 별도 수집
                            article_imgs_list = []
                            matched_srcs = []
                            if not is_issue and "blog.naver.com" in normalize_target_url(target_u):
                                article_imgs_list, _, matched_srcs = fetch_clean_nate_photos_for_blog(p_title, o_body)
                                if matched_srcs:
                                    o_body = f"[참고용 원본 보도기사 출처: {', '.join(matched_srcs)}]\n\n" + o_body

                            img_cnt = len(img_bytes_list)
                            mode_inst = (
                                "2. [연예인 이슈·근황 모드]: 옷·가방 코디 추천은 쓰지 말고 사건·방송·SNS 근황 전말과 대중 반응을 스토리텔링해 줘!\n"
                                if is_issue
                                else "2. [패션·착장 분석 모드]: 각 인물 섹션마다 서로 다른 착장 사진 2~3장을 배치하고 컬러 배색·실생활 코디 팁을 포함해 줘!\n"
                            )
                            photo_guide = (
                                f"4. 첨부된 실제 사진 {img_cnt}장을 확인하고 각 [사진 N] 위아래에 실제 장면·착장과 일치하는 내용을 써줘.\n"
                                if img_cnt > 0
                                else "4. 본문 중간에 [사진 1], [사진 2] 등 사진 번호 표기는 넣지 말고 3~5줄 문단과 인용구·형광펜 서식만 깔끔하게 구성해 줘.\n"
                            )
                            prompt_txt = (
                                f"[중요 지시사항]\n"
                                f"1. 네이버 상위 5% 애드포스트 기준인 '공백 제외 1,500자 ~ 2,000자' 분량을 정확히 맞춰 풍성하게 작성해 줘!\n"
                                f"{mode_inst}"
                                f"3. 자기소개 멘트 절대 금지! 맨 위 [제목 추천 1], [제목 추천 2] 직후 바로 핵심 내용으로 시작해.\n"
                                f"{photo_guide}"
                                f"5. 한 줄 20자 이내 줄바꿈, 3~5줄 문단 리듬 유지, 3색 파스텔 형광펜([[ ]], [b[ ]b], [p[ ]p]) 적용!\n"
                                f"6. 마지막 줄에 '출처-' 표기 후 바로 아래 '===TAGS===' 다음 줄에 태그 30개를 쉼표로 구분해 뽑아줘.\n"
                            )
                            if extra_note.strip():
                                prompt_txt += f"[추가 강조 요청]: {extra_note.strip()}\n"
                            prompt_txt += f"\n[원본 제목]: {p_title}\n\n[참고 원문 및 사진 순서표]:\n{o_body}"

                            contents = [prompt_txt]
                            for i_idx, th in enumerate(ai_thumbs[:10], start=1):
                                contents.append(f"[첨부 사진 {i_idx}번]")
                                contents.append(th)

                            full_resp = generate_with_gemini(contents, sys_prompt)

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
                            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                            art_badge = f" + 기사원본 {len(article_imgs_list)}장" if article_imgs_list else ""
                            label_str = f"{ts_str[:15]}_{mode_tag}_{p_title[:22]} [추출사진 {img_cnt}장{art_badge} · 공백제외 {c_len}자]"

                            st.session_state[mode_archive_key].insert(0, {
                                "id": ts_str,
                                "label": label_str,
                                "title": p_title,
                                "body": body_clean,
                                "html": build_naver_html(body_clean),
                                "plain": plain_clean,
                                "tags": tags_clean,
                                "images": img_bytes_list,
                                "article_images": article_imgs_list,
                                "matched_sources": matched_srcs,
                                "char_count": c_len,
                            })
                            st.session_state[mode_sel_key] = 0
                            generated_any = True
                        except Exception as e:
                            st.error(f"{idx}번 URL 처리 오류: {e}")

                if generated_any:
                    st.rerun()

    else:
        st.markdown("**1. 직접 찍은 맛집 사진 불러오기 (최대 15장 · 갤럭시/아이폰/PC 사진 선택)**")
        uploaded_food_files = st.file_uploader(
            "맛집 사진 선택",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="uploader_food"
        )

        f_col1, f_col2 = st.columns(2)
        with f_col1:
            store_name_input = st.text_input("식당 상호명 & 지역 (필수)", placeholder="예: 부평 투파인드피터 / 신중동 럭키족발", key="food_store")
        with f_col2:
            menu_info_input = st.text_input("주문한 메뉴 & 가격/특징", placeholder="예: 참나무 장작 바베큐 족발, 오복쟁반막국수", key="food_menu")

        food_guideline_input = st.text_area(
            "협찬/체험단 가이드라인 또는 강조할 맛 포인트 (선택사항)",
            height=80,
            placeholder="예: 네이버 영수증 리뷰 시 살얼음 막걸리 무료 증정 이벤트 강조, 데이트 코스로 추천하는 분위기 강조",
            key="food_guide"
        )

        if st.button("🍽️ [맛집 모드] 업로드한 사진으로 맛집 리뷰 원고 & 사진 보정 일괄 생성", type="primary", use_container_width=True, key="btn_gen_food"):
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

                        full_resp = generate_with_gemini(contents, sys_prompt)

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
                        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        title_clean = store_name_input.strip()
                        label_str = f"{ts_str[:15]}_[맛집]_{title_clean[:24]} [보정사진 {img_cnt}장 · 공백제외 {c_len}자]"

                        st.session_state[mode_archive_key].insert(0, {
                            "id": ts_str,
                            "label": label_str,
                            "title": title_clean,
                            "body": body_clean,
                            "html": build_naver_html(body_clean),
                            "plain": plain_clean,
                            "tags": tags_clean,
                            "images": food_img_bytes,
                            "article_images": [],
                            "matched_sources": [],
                            "char_count": c_len,
                        })
                        st.session_state[mode_sel_key] = 0
                        st.rerun()
                    except Exception as e:
                        st.error(f"맛집 원고 생성 중 오류 발생: {e}")

    # ==========================================================
    # 2. 현재 탭 전용 생성 완료 보관함 & 3. 크롤링 사진 갤러리 & 4. 원고/태그
    # ==========================================================
    st.divider()
    mode_kor = {"fashion": "👗 패션·착장", "issue": "🔥 연예인 이슈", "food": "🍽️ 맛집 후기"}[cur_mode]
    arc_h1, arc_h2, arc_h3 = st.columns([3, 1, 1.2])
    with arc_h1:
        st.markdown(f"**2. [{mode_kor}] 생성 완료 보관함 (탭별 독립 저장)**")
    with arc_h2:
        if st.button("🗑️ 선택 항목 삭제", use_container_width=True, key=f"btn_del_{cur_mode}"):
            if st.session_state[mode_archive_key]:
                idx_del = st.session_state[mode_sel_key]
                st.session_state[mode_archive_key].pop(idx_del)
                st.session_state[mode_sel_key] = 0
                st.rerun()
    with arc_h3:
        st.link_button("✍️ 네이버 블로그 글쓰기", "https://blog.naver.com/GoBlogWrite.naver", use_container_width=True)

    if st.session_state[mode_archive_key]:
        labels = [it["label"] for it in st.session_state[mode_archive_key]]
        sel_idx = st.selectbox(
            "보관함 목록 선택",
            range(len(labels)),
            index=min(st.session_state[mode_sel_key], len(labels) - 1),
            format_func=lambda i: labels[i],
            label_visibility="collapsed",
            key=f"sel_arc_{cur_mode}_{len(labels)}"
        )
        st.session_state[mode_sel_key] = sel_idx
        cur_item = st.session_state[mode_archive_key][sel_idx]
        item_uid = cur_item["id"]

        # 크롤링 및 가공된 사진 바로 보기 갤러리 (1. 본문 추출 사진 / 2. 원본 기사 보도사진 구분 표시)
        art_imgs = cur_item.get("article_images", [])
        matched_srcs = cur_item.get("matched_sources", [])

        st.markdown(f"**🖼️ 1. 추출 및 보정 완료된 본문 사진 ({len(cur_item['images'])}장)**")
        if cur_item["images"]:
            with st.container(border=True):
                cols_per_row = 5
                for row_start in range(0, len(cur_item["images"]), cols_per_row):
                    row_imgs = cur_item["images"][row_start:row_start + cols_per_row]
                    g_cols = st.columns(cols_per_row)
                    for col_i, img_b in enumerate(row_imgs):
                        pic_num = row_start + col_i + 1
                        g_cols[col_i].image(img_b, caption=f"[본문사진 {pic_num}]", use_container_width=True)
        else:
            st.caption("※ 이 기사/링크에서는 추출 가능한 본문 이미지가 없었습니다.")

        if cur_mode == "fashion":
            src_info = f" (참고 기사: {', '.join(matched_srcs)})" if matched_srcs else ""
            st.markdown(f"**📰 2. 워터마크 대비용 · 자동 탐색된 원본 기사 보도사진 ({len(art_imgs)}장)**{src_info}")
            if art_imgs:
                with st.container(border=True):
                    cols_per_row = 5
                    for row_start in range(0, len(art_imgs), cols_per_row):
                        row_imgs = art_imgs[row_start:row_start + cols_per_row]
                        g_cols = st.columns(cols_per_row)
                        for col_i, img_b in enumerate(row_imgs):
                            pic_num = row_start + col_i + 1
                            g_cols[col_i].image(img_b, caption=f"[원본기사 {pic_num}]", use_container_width=True)
            else:
                st.caption("※ 개인 인스타 사복 등 매칭되는 언론사 보도기사 사진이 없는 주제입니다.")

        st.markdown(f"**3. 완성된 원고 본문 (공백 제외 {cur_item['char_count']}자 · 3색 파스텔 음영 & 컬러/인용구 적용)**")

        act_c1, act_c2 = st.columns(2)
        with act_c1:
            render_web_copy_button(
                cur_item["html"],
                cur_item["plain"],
                btn_label="📋 원고 서식 그대로 복사 (네이버 에디터 Ctrl+V)",
                key_id=f"copy_rich_{item_uid}"
            )
        with act_c2:
            total_zip_cnt = len(cur_item["images"]) + len(art_imgs)
            if total_zip_cnt > 0:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for img_i, img_b in enumerate(cur_item["images"], start=1):
                        zf.writestr(f"1_본문추출사진_{img_i}.jpg", img_b)
                    for art_i, art_b in enumerate(art_imgs, start=1):
                        zf.writestr(f"2_원본기사사진_{art_i}.jpg", art_b)
                st.download_button(
                    label=f"📦 사진 전체 {total_zip_cnt}장 구분 ZIP 다운로드 (본문 {len(cur_item['images'])} + 기사원본 {len(art_imgs)})",
                    data=zip_buf.getvalue(),
                    file_name=f"이서블리_{cur_mode}_{sel_idx+1}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key=f"zip_dl_{item_uid}"
                )

        st.text_area(
            "완성된 원고 본문",
            value=cur_item["body"],
            height=360,
            label_visibility="collapsed",
            key=f"res_body_{item_uid}"
        )

        tag_cnt = len([t for t in cur_item["tags"].split(",") if t.strip()])
        st.markdown(f"**4. 네이버 유입 최적화 추천 태그 ({tag_cnt}개 — 아래 박스를 전체 선택해 복사하세요)**")
        st.text_area(
            "추천 태그 30개",
            value=cur_item["tags"],
            height=75,
            label_visibility="collapsed",
            key=f"res_tags_{item_uid}"
        )
    else:
        st.info(f"[{mode_kor}] 탭에서 생성된 원고가 아직 없습니다. 위에서 입력 후 변환 버튼을 눌러주세요.")

# ==========================================
# 우측 전용 사이드 패널: 일 방문자 1만+ 트래픽 공략 & 운영 메모장
# ==========================================
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
