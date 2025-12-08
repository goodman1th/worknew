import streamlit as st
import datetime
import json
import pandas as pd
import google.generativeai as genai
from io import StringIO, BytesIO
import time
import hmac
import hashlib
import base64
import requests
from urllib.parse import urlparse

# ==========================================
# [SYSTEM] 페이지 설정
# ==========================================
st.set_page_config(
    page_title="AC Team Web Control Tower",
    page_icon="🏯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# [STATE] 마스터 설정 저장소 (하나의 목록에 통합)
# ==========================================
# 1. 마스터 설정 초기화 (여기에 모든 키가 저장됨)
if 'master_config' not in st.session_state:
    st.session_state.master_config = {
        "GOOGLE_API_KEY": "",          # 구글 키
        "NAVER_ACCOUNTS": {}           # 네이버 계정 목록 {별칭: {정보}}
    }

# 2. 채팅 기록 초기화
if 'chat_history' not in st.session_state: 
    st.session_state.chat_history = []

if 'current_role' not in st.session_state: 
    st.session_state.current_role = "AC김시율 (Director)"

# ==========================================
# [LOGIC] 핵심 함수
# ==========================================
def read_uploaded_file(uploaded_file):
    """파일 읽기 함수"""
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
    """자아 패킷 로드"""
    prompts = {
        "AC김시율 (Director)": "당신은 AC팀 총괄 디렉터다. 파트너의 참모로서 건조하고 명확하게 지시하라.",
        "PM (Project Manager)": "당신은 PM이다. 모호한 지시를 실행 가능한 공정으로 분해하라.",
        "Architect (설계자)": "당신은 설계자다. 실행 가능한 완벽한 파이썬 코드를 작성하라.",
        "Executor (수행자)": "당신은 수행자다. 자의적 판단 없이 결과를 보고하라.",
        "Scribe (서기)": "당신은 서기다. 팩트만 기록하라."
    }
    return prompts.get(role, "")

def get_naver_header(method, uri, api_key, secret_key, customer_id):
    """네이버 서명 생성"""
    ts = str(int(time.time() * 1000))
    msg = f"{ts}.{method}.{uri}"
    sign = base64.b64encode(hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()).decode()
    return {
        "Content-Type": "application/json", "X-Timestamp": ts, 
        "X-API-KEY": api_key, "X-Customer": customer_id, "X-Signature": sign
    }

# ==========================================
# [UI] 사이드바: 통합 키 관리소
# ==========================================
with st.sidebar:
    st.header("⚙️ 시스템 통제실")
    
    # [핵심 수정 1] 구글 키 입력 (자동 저장 연결)
    st.subheader("🔑 Brain (Google)")
    
    # 입력창에 현재 저장된 값을 기본값으로 넣고, 변경 시 바로 업데이트
    new_google_key = st.text_input(
        "Google API Key", 
        value=st.session_state.master_config["GOOGLE_API_KEY"], 
        type="password",
        help="입력하면 자동 저장됩니다."
    )
    # 값이 변경되었다면 마스터 설정에 업데이트
    if new_google_key != st.session_state.master_config["GOOGLE_API_KEY"]:
        st.session_state.master_config["GOOGLE_API_KEY"] = new_google_key
        st.success("Google Key 저장 완료!")

    st.divider()
    
    # [핵심 수정 2] 네이버 계정 관리 (Form 사용으로 안정성 확보)
    st.subheader("🏦 Body (Naver Accounts)")
    
    with st.form("account_add_form", clear_on_submit=True):
        st.caption("새로운 계정 추가")
        col_a, col_b = st.columns(2)
        new_alias = col_a.text_input("별칭 (예: 1호점)")
        new_id = col_b.text_input("Customer ID")
        new_key = st.text_input("Access Key", type="password")
        new_secret = st.text_input("Secret Key", type="password")
        
        if st.form_submit_button("계정 추가"):
            if new_alias and new_id and new_key:
                # 마스터 설정에 추가
                st.session_state.master_config["NAVER_ACCOUNTS"][new_alias] = {
                    "id": new_id, "key": new_key, "secret": new_secret
                }
                st.success(f"[{new_alias}] 추가됨")
                st.rerun() # 화면 갱신

    # 등록된 계정 목록 표시 및 삭제
    if st.session_state.master_config["NAVER_ACCOUNTS"]:
        st.write(f"📋 등록된 계정: {len(st.session_state.master_config['NAVER_ACCOUNTS'])}개")
        del_target = st.selectbox("관리할 계정 선택", list(st.session_state.master_config["NAVER_ACCOUNTS"].keys()))
        
        if st.button("선택한 계정 삭제", type="primary"):
            del st.session_state.master_config["NAVER_ACCOUNTS"][del_target]
            st.rerun()

# ==========================================
# [UI] 메인 스테이지
# ==========================================
st.title("🏯 AC Team: Web Conductor v2.1")
st.caption(f"Connected Brain: {'🟢 Online' if st.session_state.master_config['GOOGLE_API_KEY'] else '🔴 Offline'}")

# 탭 구성
tab1, tab2 = st.tabs(["💬 작전 회의실 (Chat)", "📊 실행실 (Naver API)"])

# -------------------------------------------------------
# [Tab 1] 작전 회의실
# -------------------------------------------------------
with tab1:
    col1, col2 = st.columns([1, 4])
    with col1:
        st.session_state.current_role = st.selectbox(
            "🗣️ 대화/명령 주체", 
            ["AC김시율 (Director)", "PM (Project Manager)", "Architect (설계자)", "Executor (수행자)", "Scribe (서기)"]
        )

    # 채팅창
    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # 입력창
    uploaded_file = st.file_uploader("자료 첨부", type=['xlsx', 'csv', 'txt', 'py', 'json'], label_visibility="collapsed")
    
    if prompt := st.chat_input("지시 사항 입력..."):
        # 키 체크
        if not st.session_state.master_config["GOOGLE_API_KEY"]:
            st.error("🚨 구글 키가 없습니다. 사이드바에 입력하세요.")
            st.stop()

        # 메시지 구성
        display_msg = prompt
        full_prompt = prompt
        
        if uploaded_file:
            file_content = read_uploaded_file(uploaded_file)
            full_prompt = f"--- [첨부 파일 내용] ---\n{file_content}\n----------------\n\n[질문]\n{prompt}"
            display_msg = f"📎 **[{uploaded_file.name}]**\n\n{prompt}"

        # 기록 및 표시
        st.session_state.chat_history.append({"role": "user", "content": display_msg})
        with chat_container.chat_message("user"):
            st.markdown(display_msg)

        # AI 호출
        with chat_container.chat_message("assistant"):
            with st.spinner("Think..."):
                try:
                    sys_inst = get_system_prompt(st.session_state.current_role)
                    genai.configure(api_key=st.session_state.master_config["GOOGLE_API_KEY"])
                    model = genai.GenerativeModel('gemini-2.0-flash-exp', system_instruction=sys_inst)
                    
                    response = model.generate_content(full_prompt)
                    st.markdown(response.text)
                    st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"통신 오류: {e}")

# -------------------------------------------------------
# [Tab 2] 실행실 (네이버 리포트)
# -------------------------------------------------------
with tab2:
    st.subheader("Naver 검색광고 리포트 추출")
    
    # 계정 선택
    accounts = st.session_state.master_config["NAVER_ACCOUNTS"]
    if not accounts:
        st.warning("등록된 계정이 없습니다. 사이드바에서 추가하세요.")
    else:
        target_acc_name = st.selectbox("대상 계정", list(accounts.keys()))
        target_acc = accounts[target_acc_name]
        
        if st.button("🚀 리포트 추출 및 엑셀 다운로드", type="primary"):
            try:
                with st.spinner(f"[{target_acc_name}] 접속 중..."):
                    # 1. 기본 설정
                    base_url = "https://api.searchad.naver.com"
                    stat_dt = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    # 2. 생성 요청
                    uri = "/stat-reports"
                    headers = get_naver_header("POST", uri, target_acc['key'], target_acc['secret'], target_acc['id'])
                    res = requests.post(base_url + uri, headers=headers, json={"reportTp": "AD", "statDt": stat_dt})
                    
                    if res.status_code != 200: raise Exception(f"생성 실패: {res.text}")
                    jid = res.json()["reportJobId"]
                    st.toast(f"Job ID 발급: {jid}")
                    
                    # 3. 대기 및 다운로드 URL 확보
                    durl = None
                    progress_text = "상태 확인 중..."
                    my_bar = st.progress(0, text=progress_text)

                    for i in range(10):
                        time.sleep(2)
                        my_bar.progress((i+1)*10, text=f"{progress_text} ({i+1}/10)")
                        
                        uri_chk = f"/stat-reports/{jid}"
                        h = get_naver_header("GET", uri_chk, target_acc['key'], target_acc['secret'], target_acc['id'])
                        r = requests.get(base_url + uri_chk, headers=h)
                        
                        if r.json()["status"] == "BUILT":
                            durl = r.json()["downloadUrl"]
                            break
                    
                    if not durl: raise Exception("다운로드 URL 확보 실패 (Timeout)")
                    
                    # 4. 다운로드 (Clean Signature)
                    parsed = urlparse(durl)
                    h_dl = get_naver_header("GET", parsed.path, target_acc['key'], target_acc['secret'], target_acc['id'])
                    file_res = requests.get(durl, headers=h_dl)
                    
                    # 5. 엑셀 변환
                    df = pd.read_csv(StringIO(file_res.text), sep='\t')
                    rename_map = {'statDt':'날짜', 'salesAmt':'광고비(원)', 'convAmt':'전환매출액(원)', 'impCnt':'노출수', 'clkCnt':'클릭수'}
                    df.rename(columns=rename_map, inplace=True)
                    
                    # 다운로드 버튼 제공
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    data = output.getvalue()
                    
                    st.success(f"✅ 성공! {len(df)}개 데이터 확보됨.")
                    st.download_button(
                        label=f"📥 {target_acc_name}_{stat_dt}.xlsx 다운로드",
                        data=data,
                        file_name=f"Report_{target_acc_name}_{stat_dt}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

            except Exception as e:
                st.error(f"작업 실패: {e}")