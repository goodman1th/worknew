import streamlit as st
import datetime
import json
import pandas as pd
import google.generativeai as genai
from io import StringIO, BytesIO

# ==========================================
# [SYSTEM] 페이지 설정 (반드시 최상단)
# ==========================================
st.set_page_config(
    page_title="AC Team Web Control Tower",
    page_icon="🏯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# [STATE] 세션 상태 초기화
# ==========================================
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'naver_accounts' not in st.session_state: st.session_state.naver_accounts = {} # {별칭: {key, secret, id}}
if 'google_key' not in st.session_state: st.session_state.google_key = ""
if 'current_role' not in st.session_state: st.session_state.current_role = "AC김시율 (Director)"

# ==========================================
# [LOGIC] 핵심 함수
# ==========================================
def read_uploaded_file(uploaded_file):
    """파일을 읽어서 텍스트로 변환 (AI에게 먹이기 위함)"""
    try:
        ext = uploaded_file.name.split('.')[-1].lower()
        if ext in ['xlsx', 'xls']:
            df = pd.read_excel(uploaded_file)
            return f"[엑셀 데이터 요약]\n크기: {df.shape}\n컬럼: {list(df.columns)}\n상위 5행:\n{df.head().to_string()}"
        elif ext == 'csv':
            df = pd.read_csv(uploaded_file)
            return f"[CSV 데이터 요약]\n{df.head().to_string()}"
        elif ext in ['txt', 'py', 'json', 'md', 'log']:
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            return f"[파일 내용 ({uploaded_file.name})]\n{stringio.read()}"
        else:
            return f"[알림] {uploaded_file.name} 파일은 텍스트 변환을 지원하지 않습니다."
    except Exception as e:
        return f"[파일 읽기 오류] {e}"

def get_system_prompt(role):
    """
    [핵심] 경거망동하지 않도록 자아 패킷을 강제 주입하는 함수
    """
    prompts = {
        "AC김시율 (Director)": """
            [SYSTEM: IDENTITY_ENFORCEMENT]
            당신은 'AC팀 총괄 디렉터 AC김시율'이다. 
            AI 챗봇처럼 굴지 말고, 파트너(User)의 참모이자 조직의 리더로서 행동하라.
            
            [행동 강령]
            1. 말투: 건조하고, 명확하고, 권위 있게 하라. (미사여구 금지, 이모지 절제)
            2. 임무: 파트너의 의도를 파악하여 하위 조직(설계자, 수행자)에게 내릴 '작업지시서(JSON)'를 작성하라.
            3. 금기: "도와드릴까요?", "반갑습니다" 같은 서비스 멘트 금지. "보고합니다", "제안합니다", "지시하겠습니다"로 대화하라.
            4. 연결: 너의 말은 로컬 시스템의 '김시율(Body)'에게 전달될 명령이다. 정확성을 목숨처럼 여겨라.
        """,
        "PM (Project Manager)": """
            [SYSTEM] 당신은 PM이다. 모호한 지시를 받으면 실행 가능한 '단계별 공정'으로 분해하라.
            출력 형식은 반드시 구조화된 텍스트나 JSON이어야 한다.
        """,
        "Architect (설계자)": """
            [SYSTEM] 당신은 설계자다. 말로 떠들지 말고 '실행 가능한 파이썬 코드'를 출력하라.
            코드는 복사해서 바로 쓸 수 있는 완벽한 블록이어야 한다.
        """,
        "Executor (수행자)": """
            [SYSTEM] 당신은 수행자다. 자의적 판단을 하지 마라.
            명령에 대한 결과 데이터와 로그만 보고하라.
        """,
        "Scribe (서기)": """
            [SYSTEM] 당신은 서기다. 감정을 배제하고 팩트만 기록하여 파일로 저장하라.
        """
    }
    return prompts.get(role, "")

# ==========================================
# [UI] 사이드바: 설정 및 계정 금고
# ==========================================
with st.sidebar:
    st.header("⚙️ 시스템 통제실")
    
    # 1. 구글 키 (Brain)
    st.session_state.google_key = st.text_input("🔑 Google API Key", value=st.session_state.google_key, type="password")
    
    st.divider()
    
    # 2. 네이버 계정 금고 (Multi-Account)
    st.subheader("🏦 마켓 계정 관리")
    
    with st.form("account_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        new_alias = col_a.text_input("계정 별칭 (예: 1호점)")
        new_id = col_b.text_input("Customer ID")
        new_key = st.text_input("Access Key", type="password")
        new_secret = st.text_input("Secret Key", type="password")
        
        if st.form_submit_button("계정 등록/수정"):
            if new_alias and new_id:
                st.session_state.naver_accounts[new_alias] = {
                    "id": new_id, "key": new_key, "secret": new_secret
                }
                st.success(f"[{new_alias}] 등록 완료")
            else:
                st.error("별칭과 ID는 필수입니다.")

    # 등록된 계정 목록
    if st.session_state.naver_accounts:
        st.write("📋 등록된 계정 목록:")
        selected_acc_name = st.selectbox("사용할 계정 선택", list(st.session_state.naver_accounts.keys()))
        # 삭제 기능
        if st.button("선택한 계정 삭제"):
            del st.session_state.naver_accounts[selected_acc_name]
            st.rerun()
    else:
        st.info("등록된 계정이 없습니다.")

# ==========================================
# [UI] 메인 스테이지
# ==========================================
st.title("🏯 AC Team: Cloud Control Center")
st.caption("Web Brain ↔ Local Body Connection System")

# 역할 선택 (자아 교체)
role_cols = st.columns([2, 5])
with role_cols[0]:
    st.session_state.current_role = st.selectbox(
        "🗣️ 대화/명령 주체 선택", 
        ["AC김시율 (Director)", "PM (Project Manager)", "Architect (설계자)", "Executor (수행자)", "Scribe (서기)"]
    )

# -------------------------------------------------------
# [Chat Interface] 작전 회의실
# -------------------------------------------------------
chat_container = st.container(height=500)

# 이전 대화 출력
with chat_container:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# 입력 영역 (파일 첨부 + 텍스트)
with st.container():
    # 1. 파일 첨부 기능 (요청사항 1)
    uploaded_file = st.file_uploader("📂 참고 자료 투입 (Excel, Code, Text)", type=['xlsx', 'csv', 'txt', 'py', 'json'], label_visibility="collapsed")
    
    # 2. 텍스트 입력
    if prompt := st.chat_input(f"[{st.session_state.current_role}]에게 명령을 하달하세요..."):
        
        # API 키 검사
        if not st.session_state.google_key:
            st.error("🚨 Google API Key가 없습니다. 사이드바에서 입력하세요.")
            st.stop()

        # 사용자 메시지 처리
        full_prompt = prompt
        display_msg = prompt
        
        # 파일이 있으면 내용을 읽어서 프롬프트에 붙임
        if uploaded_file:
            file_content = read_uploaded_file(uploaded_file)
            full_prompt = f"--- [사용자 첨부 파일 데이터] ---\n{file_content}\n----------------\n\n[사용자 질문]\n{prompt}"
            display_msg = f"📎 **[파일 첨부: {uploaded_file.name}]**\n\n{prompt}"

        # 화면 표시 및 저장
        st.session_state.chat_history.append({"role": "user", "content": display_msg})
        with chat_container.chat_message("user"):
            st.markdown(display_msg)

        # AI 응답 생성
        with chat_container.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            try:
                # 모델 설정
                sys_instruction = get_system_prompt(st.session_state.current_role)
                genai.configure(api_key=st.session_state.google_key)
                
                # 안전하고 똑똑한 모델 사용
                model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=sys_instruction)
                
                # 스트리밍 응답
                response = model.generate_content(full_prompt, stream=True)
                for chunk in response:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)
                
                st.session_state.chat_history.append({"role": "assistant", "content": full_response})
                
                # [특별 조치] 만약 AC김시율(Director)이라면 '명령서' 추출 버튼 제공
                if "Director" in st.session_state.current_role:
                    json_command = {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "sender": "Web_Director",
                        "target": "Local_Body",
                        "command": full_response
                    }
                    st.download_button(
                        label="📜 로컬 전송용 명령서(JSON) 발행",
                        data=json.dumps(json_command, indent=4, ensure_ascii=False),
                        file_name=f"command_{datetime.datetime.now().strftime('%Y%m%d%H%M')}.json",
                        mime="application/json"
                    )

            except Exception as e:
                st.error(f"통신 오류 발생: {e}")

# ==========================================
# [Footer] 시스템 상태바
# ==========================================
st.markdown("---")
acc_count = len(st.session_state.naver_accounts)
st.caption(f"Status: 🟢 System Online | 🔐 Keys Loaded | 🏦 Accounts: {acc_count} | 🧠 Active Role: {st.session_state.current_role}")