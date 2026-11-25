import streamlit as st
import streamlit.components.v1 as components
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import os
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
# 페이지 기본 설정 (모바일·PC 반응형)
# ==========================================
st.set_page_config(
    page_title="이서블리 블로그 자동화 스튜디오",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 비밀번호 잠금장치 (타인 무단 접속 및 API 키 보호)
# ==========================================
def check_password():
    app_pw = st.secrets.get("APP_PASSWORD", "")
    if not app_pw:
        return True
    if st.session_state.get("authenticated", False):
        return True

    st.markdown("### 🔒 이서블리 전용 블로그 자동화 스튜디오")
    pw_input = st.text_input("접속 비밀번호를 입력하세요", type="password")
    if st.button("로그인", type="primary"):
        if pw_input == app_pw:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")
    return False

if not check_password():
    st.stop()

# 제미나이 API 클라이언트 초기화 (Secrets 또는 사이드바 입력 지원)
default_api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 설정 및 운영 매뉴얼")
    api_key_input = st.text_input("Gemini API Key", value=default_api_key, type="password")
    st.divider()
    st.markdown("""
    **📌 일 방문자 1만+ 운영 매뉴얼**
    * **하루 목표**: 3~5개 (패션 2~3 + 이슈 1~2)
    * **골든타임**:
      * `07:00~09:00` 전날 방송 착장·화제 장면
      * `12:00~13:30` 점심 연예인 SNS 근황
      * `22:00~24:00` 저녁 포토월·인스타 업로드
    """)

if not api_key_input:
    st.warning("왼쪽 사이드바(>)를 열거나 Streamlit Secrets에 GEMINI_API_KEY를 설정해 주세요.")
    st.stop()

client = genai.Client(
    api_key=api_key_input.strip(),
    http_options=types.HttpOptions(timeout=50000)
)

# ==========================================
# 문체 및 모드별 프롬프트 규칙
# ==========================================
DEFAULT_STYLES = {
    "1. 이서블리 기본 스타일 (친근한 30대 리뷰어 · ㅎㅎ/ㅋㅋ 자연스러운 호흡)": (
        "너는 트렌디한 스타·패션·라이프 블로거야. "
        "친근하고 센스 있는 30대 여성 블로거 톤(해요체, 감탄사, 적당한 이모지 💕✨🤍💡🥰)으로 작성하되, "
        "'안녕하세요 블로거 이서블리예요' 같은 자기소개 인사말은 절대 쓰지 말고 첫 줄부터 바로 화제 된 이야기로 직진해.\n"
        "[구어체 및 친근감 규칙]\n"
        "- 과하지 않게 친한 언니·동생에게 말하듯 자연스러운 타이밍에만 'ㅎㅎ' 또는 'ㅋㅋ'를 글 전체에서 2~3번 정도 섞어줘.\n"
        "[구성 규칙]\n"
        "- 도입부: 자기소개 없이 바로 화제 된 핵심 포인트를 3~5줄 짧은 호흡 + 인용구 1줄로 임팩트 있게 시작해.\n"
        "- 본문 전개: 원문에 등장하는 핵심 포인트/인물을 '#1. 소제목 ✨', '#2. 소제목 🤍' 형태로 빠짐없이 섹션으로 나누어 작성해.\n"
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
        "- 본문 전개: 원문에 나오는 핵심 내용을 '#1.', '#2.', '#3.', '#4.' 순서대로 누락 없이 각각 독립된 섹션으로 알차게 정리해.\n"
        "- 마무리: 핵심 요약 + 담백한 끝인사"
    ),
}

FASHION_FORMAT_RULES = (
    "\n\n[👗 패션·착장 분석 모드 전용 규칙 · 상위 5% 황금 글자 수 · 3색 심플 음영 서식]\n"
    "1. [네이버 상위 5% 애드포스트 황금 글자 수 준수 (공백 제외 1,500~2,000자 / 공백 포함 2,000~2,600자)]: "
    "네이버 홈피드 노출과 본문 중간 애드포스트 광고 수익이 극대화되는 '공백 제외 1,500자 ~ 2,000자' 분량을 반드시 채워 작성해!\n"
    "2. [자기소개 금지 & 맨 위 제목 2가지 추천]: "
    "'안녕하세요 블로거 누구입니다' 같은 자기소개 인사말은 절대 쓰지 마! 맨 첫 줄부터 아래 형식으로 제목 2가지만 먼저 제시해 줘:\n"
    "   [제목 추천 1 - 이서블리 시그니처형] (후킹 문구 + 연예인/브랜드/아이템 포인트 + 이모지 ✨ 조합)\n"
    "   [제목 추천 2 - 상위 5% 검색 유입형] (핵심 검색 키워드 중심의 깔끔하고 클릭을 부르는 제목)\n"
    "   그 다음 줄에 '===' 를 적고 자기소개 없이 바로 본문 첫 문장을 시작해.\n"
    "3. [인물별 다중 착장(사진 2~3장 이상) 및 모든 룩 균형 반영]: "
    "[참고 원문 및 사진 배치 순서]에 있는 사진들 중 각 인물마다 서로 다른 코디가 담긴 2~3장(예: [사진 1], [사진 3] 등 실제 번호)을 섹션 안에 3~5줄 글과 번갈아 배치하고, "
    "첫 번째 착장뿐만 아니라 나머지 사진 속 착장(다른 컬러·아이템)과 실생활 코디 팁까지 반드시 함께 다뤄야 해!\n"
    "4. [첨부 사진 실제 착장·색상 100% 정확 일치]: "
    "첨부된 실제 사진([첨부 사진 1번]~[첨부 사진 N번])을 직접 눈으로 확인하고, 각 [사진 N] 위아래에는 해당 사진에 실제로 보이는 옷의 정확한 색상, 아이템 종류, 핏, 액세서리만 묘사해.\n"
    "5. [모바일 한 줄 20자 이내 줄바꿈 & 3~5줄 문단 고정]: "
    "모든 일반 문장은 쉼표(,), 마침표(.), 느낌표(!), 물음표(?) 뒤나 의미 구절 단위로 줄바꿈(엔터)해서 한 줄이 20자를 넘지 않게 맞춰! "
    "한 문단은 3~5줄로 구성하고 문단 사이 빈 줄을 넣어 '3~5줄 글 → [사진 N] → 3~5줄 글' 리듬을 유지해.\n"
    "6. [심플 3색 파스텔 형광펜 음영 + 포인트 글자색 + 인용구 적용 (한 줄 고정)]: (일반 마크다운 **, ##, * 금지)\n"
    "   - 연노랑 형광펜 (4~5군데): 핵심 코디 공식이나 가장 중요한 꿀팁은 '[[강조할 문구]]' 로 감싸줘.\n"
    "   - 연하늘(스카이블루) 형광펜 (3~4군데): 핵심 아이템명이나 컬러 조합 공식은 '[b[강조할 문구]b]' 로 감싸줘.\n"
    "   - 연핑크 형광펜 (2~3군데): 분위기 포인트나 추천 룩(하객룩, 데이트룩 등)은 '[p[강조할 문구]p]' 로 감싸줘.\n"
    "   - 포인트 글자색+볼드 (5~7군데): 핵심 브랜드명이나 키워드는 '((강조할 단어))' 로 감싸 선명한 포인트 글자색과 볼드를 입혀줘.\n"
    "   - 두꺼운 블랙 볼드 (5~7군데): 중요 키워드는 '<<강조할 단어>>' 로 감싸 두껍게 강조해줘.\n"
    "   - ★매우 중요(줄바꿈 금지)★: 위 강조 기호로 감싼 문구는 20자 이내로 짧게 만들어 절대 중간에 줄바꿈 없이 한 줄 안에 온전히 적어!\n"
    "   - 인용구 박스 (2~3군데): 도입부 핵심 요약 한 줄과 마무리 총평 핵심 한 줄에는 줄 맨 앞에 '> ' 를 붙여 인용구 박스로 강조해.\n"
    "   - 구분선: 섹션이 바뀔 때마다 단독 줄에 '---' 를 넣어 구분해.\n"
    "7. [실생활 코디·컬러 배색·소품 팁 포함]: "
    "실생활 옷 조합 공식(어떤 옷+어떤 옷), 팩트 기반 상·하의 컬러 배색 추천(블랙+그레이+아이보리, 네이비+크림, 브라운+아이보리 등), 안경·벨트·가방 소품 활용 팁을 꼭 포함해.\n"
    "8. [맨 마지막 11pt 출처 표기 & 태그 30개]: "
    "맨 마지막 줄에는 원문에 출처가 있으면 '출처- (원문 출처)'를, 없으면 정확히 '출처-' 만 단독 줄로 적고, 바로 다음 줄 '===TAGS===' 아래에 검색 태그 30개를 쉼표로 구분해 출력해."
)

ISSUE_FORMAT_RULES = (
    "\n\n[🔥 연예인 이슈·근황 모드 전용 규칙 · 상위 5% 황금 글자 수 · 3색 심플 음영 서식]\n"
    "1. [네이버 상위 5% 애드포스트 황금 글자 수 준수 (공백 제외 1,500~2,000자 / 공백 포함 2,000~2,600자)]: "
    "네이버 홈피드 노출과 본문 중간 애드포스트 광고 수익이 극대화되는 '공백 제외 1,500자 ~ 2,000자' 분량을 반드시 채워 흥미진진하게 작성해!\n"
    "2. [패션 코디 추천 금지 & 이슈 스토리텔링 집중]: "
    "이 모드는 일반 연예인 이슈·방송 화제·SNS 근황 포스팅이므로, 억지로 옷·가방·컬러 배색 추천을 끼워 넣지 마! "
    "대신 ① 화제가 된 결정적 계기(사건·발언·방송 장면), ② 구체적인 전말과 비하인드 스토리, ③ 네티즌·팬들의 실시간 반응 포인트, ④ 향후 방송·컴백·활동 일정 전망 순으로 알차게 구성해.\n"
    "3. [자기소개 금지 & 맨 위 제목 2가지 추천]: "
    "'안녕하세요 블로거 누구입니다' 같은 자기소개 인사말은 절대 쓰지 마! 맨 첫 줄부터 아래 형식으로 제목 2가지만 먼저 제시해 줘:\n"
    "   [제목 추천 1 - 이서블리 이슈 후킹형] (궁금증을 유발하는 핵심 한 줄 + 인물/프로그램명 + 이모지 ✨ 조합)\n"
    "   [제목 추천 2 - 상위 5% 검색 유입형] (인물명 + 핵심 사건/방송 키워드 중심의 클릭을 부르는 제목)\n"
    "   그 다음 줄에 '===' 를 적고 자기소개 없이 바로 본문 첫 문장을 시작해.\n"
    "4. [첨부 사진 장면·표정·상황 100% 정확 일치]: "
    "첨부된 실제 사진([첨부 사진 1번]~[첨부 사진 N번])을 직접 눈으로 확인하고, 원문에 있는 사진 번호([사진 1]~[사진 N])를 각 소제목 섹션마다 2~3장씩 3~5줄 글과 번갈아 배치하며 해당 사진 속 실제 장면·표정·분위기와 일치하게 묘사해.\n"
    "5. [모바일 한 줄 20자 이내 줄바꿈 & 3~5줄 문단 고정]: "
    "모든 일반 문장은 쉼표(,), 마침표(.), 느낌표(!), 물음표(?) 뒤나 의미 구절 단위로 줄바꿈(엔터)해서 한 줄이 20자를 넘지 않게 맞춰! "
    "한 문단은 3~5줄로 구성하고 문단 사이 빈 줄을 넣어 '3~5줄 글 → [사진 N] → 3~5줄 글' 리듬을 유지해.\n"
    "6. [심플 3색 파스텔 형광펜 음영 + 포인트 글자색 + 인용구 적용 (한 줄 고정)]: (일반 마크다운 **, ##, * 금지)\n"
    "   - 연노랑 형광펜 (4~5군데): 이번 이슈의 핵심 팩트나 결정적 한 줄 요약은 '[[강조할 문구]]' 로 감싸줘.\n"
    "   - 연하늘(스카이블루) 형광펜 (3~4군데): 화제가 된 발언, 방송 장면, 작품/프로그램명은 '[b[강조할 문구]b]' 로 감싸줘.\n"
    "   - 연핑크 형광펜 (2~3군데): 설레는 근황, 반전 매력, 팬들 반응 포인트는 '[p[강조할 문구]p]' 로 감싸줘.\n"
    "   - 포인트 글자색+볼드 (5~7군데): 핵심 인물명이나 결정적 키워드는 '((강조할 단어))' 로 감싸 선명한 포인트 글자색과 볼드를 입혀줘.\n"
    "   - 두꺼운 블랙 볼드 (5~7군데): 중요 키워드는 '<<강조할 단어>>' 로 감싸 두껍게 강조해줘.\n"
    "   - ★매우 중요(줄바꿈 금지)★: 위 강조 기호로 감싼 문구는 20자 이내로 짧게 만들어 절대 중간에 줄바꿈 없이 한 줄 안에 온전히 적어!\n"
    "   - 인용구 박스 (2~3군데): 도입부 이슈 핵심 요약 한 줄과 마무리 총평 핵심 한 줄에는 줄 맨 앞에 '> ' 를 붙여 인용구 박스로 강조해.\n"
    "   - 구분선: 소제목 섹션이 바뀔 때마다 단독 줄에 '---' 를 넣어 구분해.\n"
    "7. [맨 마지막 11pt 출처 표기 & 태그 30개]: "
    "맨 마지막 줄에는 원문에 출처가 있으면 '출처- (원문 출처)'를, 없으면 정확히 '출처-' 만 단독 줄로 적고, 바로 다음 줄 '===TAGS===' 아래에 인물·이슈·방송 관련 검색 태그 30개를 쉼표로 구분해 출력해."
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
            or stripped.startswith(("[제목", "#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜", "[사진", "> "))
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
            or item.startswith(("[제목", "#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜", "[사진", "> "))
        )
        if (
            not is_spec
            and visible_len(item) <= 3
            and merged_lines
            and merged_lines[-1] != ""
            and not merged_lines[-1].startswith(("[제목", "#", "💡", "✍️", "✅", "[사진", "> ", "---", "==="))
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
        elif stripped in ("---", "===") or stripped.startswith(("#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜", "[사진", "> ")):
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
        elif stripped.startswith(("#1.", "#2.", "#3.", "#4.", "#5.", "#6.", "1.", "2.", "3.", "4.", "💡", "✍️", "✅", "🎨", "👜")):
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

def render_web_copy_button(html_payload, plain_payload, btn_label="📋 원고 서식 그대로 복사 (네이버 에디터용)", key_id="copy1"):
    """모바일 사파리·크롬·PC 브라우저 모두에서 리치 텍스트(형광펜·볼드·인용구) 클립보드 복사를 지원하는 버튼"""
    html_json = json.dumps(html_payload)
    plain_json = json.dumps(plain_payload)
    comp_html = f"""
    <button id="{key_id}" onclick="copyRich()" style="
        width: 100%; padding: 12px; background-color: #03C75A; color: white;
        border: none; border-radius: 8px; font-size: 15px; font-weight: bold; cursor: pointer;">
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
            document.getElementById('{key_id}').innerText = '✅ 서식 복사 완료! 블로그에 붙여넣기 하세요';
        }} catch (e) {{
            await navigator.clipboard.writeText(textStr);
            document.getElementById('{key_id}').innerText = '✅ 텍스트 복사 완료!';
        }}
    }}
    </script>
    """
    components.html(comp_html, height=55)

# ==========================================
# 크롤링 및 이미지 가공 엔진
# ==========================================
def process_unique_image(pil_img):
    rgb_im = pil_img.convert("RGB")
    w, h = rgb_im.size
    crop_x = max(2, int(w * 0.01))
    crop_y = max(2, int(h * 0.01))
    cropped = rgb_im.crop((crop_x, crop_y, w - crop_x, h - crop_y))
    cropped = ImageEnhance.Brightness(cropped).enhance(1.03)
    cropped = ImageEnhance.Contrast(cropped).enhance(1.04)
    cropped = ImageEnhance.Sharpness(cropped).enhance(1.08)

    cw, ch = cropped.size
    border_side = max(10, int(cw * 0.015))
    border_bottom = max(14, int(ch * 0.02))
    return ImageOps.expand(cropped, border=(border_side, border_side, border_side, border_bottom), fill=(255, 255, 255))

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
                edited_im = process_unique_image(im)
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

def fetch_nate_ent_ranking():
    results, seen_urls = [], set()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"}
    for page_u in ["https://news.nate.com/rank/interest?sc=ent", "https://news.nate.com/ent/recent?mid=e0101"]:
        try:
            req = urllib.request.Request(page_u, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_b = resp.read()
                try:
                    h_str = raw_b.decode("euc-kr")
                except UnicodeDecodeError:
                    h_str = raw_b.decode("utf-8", errors="ignore")
            for href, inner_html in re.findall(r'<a[^>]+href=["\']((?:https?:)?//news\.nate\.com/view/[^"\']+)["\'][^>]*>(.*?)</a>', h_str, re.DOTALL | re.IGNORECASE):
                clean_u = ("https:" + href if href.startswith("//") else href).split("?")[0]
                if clean_u in seen_urls:
                    continue
                tit_m = re.search(r'class=["\'][^"\']*tit[^"\']*["\'][^>]*>(.*?)</', inner_html, re.DOTALL | re.IGNORECASE)
                title_txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", tit_m.group(1) if tit_m else inner_html))).strip()
                if len(title_txt) >= 10:
                    seen_urls.add(clean_u)
                    results.append({"source": "네이트연예", "title": title_txt, "url": clean_u})
                if len(results) >= 20:
                    break
        except Exception:
            continue
    return results

def fetch_google_news_rss(keyword):
    rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(keyword)}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
    results = []
    with urllib.request.urlopen(req, timeout=10) as resp:
        root_xml = ET.fromstring(resp.read())
    for item in root_xml.findall(".//item")[:15]:
        t_el, l_el = item.find("title"), item.find("link")
        if t_el is not None and l_el is not None and t_el.text and l_el.text:
            results.append({"source": f"실시간({keyword})", "title": html.unescape(t_el.text).strip(), "url": l_el.text.strip()})
    return results

# ==========================================
# 메인 웹 UI 렌더링
# ==========================================
st.title("✨ 이서블리 블로그 자동화 스튜디오")
st.caption("모바일(아이폰/갤럭시) & PC 겸용 · 패션·착장 분석 / 연예인 이슈 듀얼 모드")

# 상단 듀얼 모드 선택 탭
mode_choice = st.radio(
    "작성할 포스팅 모드를 선택하세요:",
    ["👗 탭 1: 패션·착장 분석 모드", "🔥 탭 2: 연예인 이슈·근황 모드"],
    horizontal=True
)
is_issue_mode = ("이슈" in mode_choice)

style_choice = st.selectbox("적용할 블로그 문체 스타일", list(DEFAULT_STYLES.keys()))

# 실시간 기사 크롤링 확장 패널
with st.expander("🔥 실시간 연예·패션 기사 긁어오기 (네이트 랭킹 + 키워드 검색)"):
    col_k1, col_k2 = st.columns([3, 1])
    with col_k1:
        kw_input = st.text_input("검색 키워드", value="예능 하이라이트" if is_issue_mode else "공항패션")
    with col_k2:
        st.write("")
        st.write("")
        if st.button("기사 수집하기", use_container_width=True):
            with st.spinner("실시간 기사를 수집하고 있습니다..."):
                news_list = fetch_nate_ent_ranking()
                try:
                    news_list.extend(fetch_google_news_rss(kw_input))
                except Exception:
                    pass
                st.session_state["crawled_news"] = news_list

    if "crawled_news" in st.session_state and st.session_state["crawled_news"]:
        options_map = {f"[{item['source']}] {item['title']}": item["url"] for item in st.session_state["crawled_news"]}
        picked_titles = st.multiselect("변환할 기사를 선택하세요 (여러 개 가능):", list(options_map.keys()))
        if st.button("선택한 기사 URL 아래 입력창에 넣기"):
            st.session_state["url_box_val"] = "\n".join([options_map[t] for t in picked_titles])
            st.rerun()

# URL 입력 및 원고 생성 영역
url_raw_input = st.text_area(
    "1. 변환할 블로그 또는 기사 URL 입력 (줄바꿈으로 여러 개 동시 입력 가능)",
    value=st.session_state.get("url_box_val", ""),
    height=100,
    placeholder="https://blog.naver.com/... 또는 기사 주소를 붙여넣으세요"
)

extra_note_input = st.text_input(
    "공통 강조 포인트 (선택사항)",
    placeholder="예: 방송 속 결정적 멘트와 팬 반응 강조" if is_issue_mode else "예: 하객룩 코디 추천 및 컬러 배색 팁 강조"
)

if st.button("✨ 선택한 모드로 원고 & 고화질 사진 일괄 생성", type="primary", use_container_width=True):
    urls = [u.strip() for u in url_raw_input.splitlines() if u.strip().startswith("http")]
    if not urls:
        st.warning("유효한 URL(https://...)을 하나 이상 입력해 주세요.")
    else:
        st.session_state["generated_results"] = []
        active_rules = ISSUE_FORMAT_RULES if is_issue_mode else FASHION_FORMAT_RULES
        full_sys_prompt = DEFAULT_STYLES[style_choice] + active_rules

        for idx, target_u in enumerate(urls, start=1):
            with st.spinner(f"[{idx}/{len(urls)}] 본문·고화질 사진 추출 및 상위 5% 황금 글자 수 원고 생성 중..."):
                try:
                    p_title, o_body, img_bytes_list, ai_thumbs = extract_blog_text_and_photos(target_u)
                    img_cnt = len(img_bytes_list)

                    mode_inst = (
                        "2. [연예인 이슈·근황 모드]: 옷·가방 코디 추천은 쓰지 말고 사건·방송·SNS 근황 전말과 대중 반응을 스토리텔링해 줘!\n"
                        if is_issue_mode
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
                    if extra_note_input.strip():
                        prompt_txt += f"[추가 강조 요청]: {extra_note_input.strip()}\n"
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
                                config=types.GenerateContentConfig(system_instruction=full_sys_prompt),
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

                        st.session_state["generated_results"].append({
                            "title": p_title,
                            "body": body_clean,
                            "html": build_naver_html(body_clean),
                            "plain": strip_all_markers(body_clean),
                            "tags": tags_clean,
                            "images": img_bytes_list,
                        })
                except Exception as e:
                    st.error(f"{idx}번 URL 처리 중 오류 발생: {e}")

# 생성 결과 출력 카드 (모바일·PC 원클릭 복사 및 ZIP 다운로드)
if "generated_results" in st.session_state and st.session_state["generated_results"]:
    st.divider()
    for r_idx, res in enumerate(st.session_state["generated_results"], start=1):
        c_len = len(re.sub(r"\s+", "", res["plain"]))
        st.subheader(f"📄 결과 {r_idx}: {res['title']} (공백 제외 {c_len}자 · 고화질 사진 {len(res['images'])}장)")

        # 서식 포함 복사 버튼
        render_web_copy_button(res["html"], res["plain"], key_id=f"copy_btn_{r_idx}")

        # 고화질 가공 사진 ZIP 일괄 다운로드 및 미리보기
        if res["images"]:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for img_i, img_b in enumerate(res["images"], start=1):
                    zf.writestr(f"사진_{img_i}.jpg", img_b)
            st.download_button(
                label=f"📦 가공된 고화질 사진 {len(res['images'])}장 한 번에 다운로드 (ZIP)",
                data=zip_buf.getvalue(),
                file_name=f"이서블리_사진_{r_idx}.zip",
                mime="application/zip",
                key=f"zip_dl_{r_idx}",
                use_container_width=True
            )
            with st.expander(f"🖼️ 저장된 고화질 사진 {len(res['images'])}장 미리보기"):
                cols = st.columns(min(5, len(res["images"])))
                for img_i, img_b in enumerate(res["images"]):
                    cols[img_i % 5].image(img_b, caption=f"사진 {img_i + 1}", use_container_width=True)

        st.text_area("완성된 원고 본문", value=res["body"], height=320, key=f"body_area_{r_idx}")
        st.text_input("네이버 유입 최적화 추천 태그 30개", value=res["tags"], key=f"tag_area_{r_idx}")