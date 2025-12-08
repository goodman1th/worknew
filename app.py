import streamlit as st
import datetime
import time
import requests
import hmac
import hashlib
import base64
import os
import json
import google.generativeai as genai
import pandas as pd
from urllib.parse import urlparse
from io import StringIO, BytesIO

# ==========================================
# [SYSTEM] 페이지 설정
# ==========================================
st.set_page_config(
    page_title="AC Team Web Conductor",
    page_icon="🏯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# [STATE] 마스터 설정 저장소
# ==========================================
if 'master_config' not in st.session_state:
    st.session_state.master_config = {
        "GOOGLE_API_KEY": "",          
        "NAVER_ACCOUNTS": {}           
    }

if 'chat_history' not in st.session_state: 
    st.session_state.chat_history = []

if 'current_role' not in st.session_state: 
    st.session_state.current_role = "AC김시율 (Director)"

if 'logs' not in st.session_state:
    st.session_state.logs = []

# ==========================================
# [LOGIC] 핵심 함수
# ==========================================
def log_event(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    st.session_state.logs.append(f"[{ts}] {msg}")

def read_uploaded_file(uploaded_file):
    try:
        ext = uploaded_file.name.split('.')[-1].lower()
        if ext in ['xlsx', 'xls']:
            df = pd.read_excel(uploaded_file)
            return f"[엑셀 요약]\n크기: {df.shape}\n컬럼: {list(df.columns)}\n상위 5행:\n{df.head().to_string()}"
        elif ext == 'csv':
            df = pd.read_csv(uploaded_file)
            return f"[CSV 요약]\n{df.head().to_string()}"
        elif ext in ['txt', 'py', 'json', 'md', 'log']:
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            return f"[파일 내용]\n{stringio.read()}"
        else:
            return f"[알림] {uploaded_file.name} 텍스트 변환 불가"
    except Exception as e:
        return f"[파일 읽기 오류] {e}"

def get_system_prompt(role):
    prompts = {
        "AC김시율 (Director)": "당신은 총괄 디렉터다. 핵심만 명확하게 지시하라.",
        "PM (Project Manager)": "당신은 PM이다. 업무를 구조화하라.",
        "Architect (설계자)": "당신은 설계자다. 실행 가능한 파이썬 코드를 작성하라.",
        "Executor (수행자)": "당신은 수행자다. 결과만 보고하라.",
        "Scribe (서기)": "당신은 서기다. 팩트만 기록하라."
    }
    return prompts.get(role, "")

def get_naver_header(method, uri, api_key, secret_key, customer_id):
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
    
    st.subheader("🔑 Brain (Google)")
    new_google_key = st.text_input(
        "Google API Key", 
        value=st.session_state.master_config["GOOGLE_API_KEY"], 
        type="password",
        help="입력하면 자동 저장됩니다."
    )
    if new_google_key != st.session_state.master_config["GOOGLE_API_KEY"]:
        st.session_state.master_config["GOOGLE_API_KEY"] = new_google_key
        st.success("Google Key 저장 완료!")

    st.divider()
    
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
                st.session_state.master_config["NAVER_ACCOUNTS"][new_alias] = {
                    "id": new_id, "key": new_key, "secret": new_secret
                }
                st.success(f"[{new_alias}] 추가됨")
                st.rerun()

    if st.session_state.master_config["NAVER_ACCOUNTS"]:
        st.write(f"📋 등록된 계정: {len(st.session_state.master_config['NAVER_ACCOUNTS'])}개")
        del_target = st.selectbox("관리할 계정 선택", list(st.session_state.master_config["NAVER_ACCOUNTS"].keys()))
        if st.button("선택한 계정 삭제", type="primary"):
            del st.session_state.master_config["NAVER_ACCOUNTS"][del_target]
            st.rerun()

# ==========================================
# [UI] 메인 스테이지
# ==========================================
st.title("🏯 AC Team: Web Conductor v2.2")
st.caption("Status: 🟢 System Online | 💀 Analysis Lab Added")

# 탭 구성 (분석실 복구!)
tab1, tab2, tab4 = st.tabs(["💬 작전 회의실", "📊 실행실 (Naver API)", "💀 분석실 (Guillotine)"])

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

    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    uploaded_file = st.file_uploader("자료 첨부", type=['xlsx', 'csv', 'txt', 'py', 'json'], label_visibility="collapsed")
    
    if prompt := st.chat_input("지시 사항 입력..."):
        if not st.session_state.master_config["GOOGLE_API_KEY"]:
            st.error("🚨 구글 키가 없습니다. 사이드바에 입력하세요.")
            st.stop()

        display_msg = prompt
        full_prompt = prompt
        
        if uploaded_file:
            file_content = read_uploaded_file(uploaded_file)
            full_prompt = f"--- [첨부 파일] ---\n{file_content}\n----------------\n\n[질문]\n{prompt}"
            display_msg = f"📎 **[{uploaded_file.name}]**\n\n{prompt}"

        st.session_state.chat_history.append({"role": "user", "content": display_msg})
        with chat_container.chat_message("user"):
            st.markdown(display_msg)

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
    
    accounts = st.session_state.master_config["NAVER_ACCOUNTS"]
    if not accounts:
        st.warning("등록된 계정이 없습니다. 사이드바에서 추가하세요.")
    else:
        target_acc_name = st.selectbox("대상 계정", list(accounts.keys()))
        target_acc = accounts[target_acc_name]
        
        if st.button("🚀 리포트 추출 및 다운로드", type="primary"):
            try:
                with st.spinner(f"[{target_acc_name}] 접속 중..."):
                    base_url = "https://api.searchad.naver.com"
                    stat_dt = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    # 1. 생성
                    uri = "/stat-reports"
                    headers = get_naver_header("POST", uri, target_acc['key'], target_acc['secret'], target_acc['id'])
                    res = requests.post(base_url + uri, headers=headers, json={"reportTp": "AD", "statDt": stat_dt})
                    
                    if res.status_code != 200: raise Exception(f"생성 실패: {res.text}")
                    jid = res.json()["reportJobId"]
                    st.toast(f"Job ID 발급: {jid}")
                    
                    # 2. 대기
                    durl = None
                    my_bar = st.progress(0, text="상태 확인 중...")
                    for i in range(10):
                        time.sleep(2)
                        my_bar.progress((i+1)*10)
                        uri_chk = f"/stat-reports/{jid}"
                        h = get_naver_header("GET", uri_chk, target_acc['key'], target_acc['secret'], target_acc['id'])
                        r = requests.get(base_url + uri_chk, headers=h)
                        if r.json()["status"] == "BUILT":
                            durl = r.json()["downloadUrl"]
                            break
                    
                    if not durl: raise Exception("다운로드 URL 확보 실패")
                    
                    # 3. 다운로드 & 변환
                    parsed = urlparse(durl)
                    h_dl = get_naver_header("GET", parsed.path, target_acc['key'], target_acc['secret'], target_acc['id'])
                    file_res = requests.get(durl, headers=h_dl)
                    
                    df = pd.read_csv(StringIO(file_res.text), sep='\t')
                    rename_map = {'statDt':'날짜', 'salesAmt':'광고비(원)', 'convAmt':'전환매출액(원)', 'impCnt':'노출수', 'clkCnt':'클릭수'}
                    df.rename(columns=rename_map, inplace=True)
                    
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    data = output.getvalue()
                    
                    st.success(f"✅ 성공! {len(df)}개 데이터 확보.")
                    st.download_button(f"📥 {target_acc_name}_{stat_dt}.xlsx", data, file_name=f"Report_{target_acc_name}_{stat_dt}.xlsx")

            except Exception as e:
                st.error(f"작업 실패: {e}")

# -------------------------------------------------------
# [Tab 4] 분석실 (Guillotine) - [복구 완료]
# -------------------------------------------------------
with tab4:
    st.subheader("💀 좀비 상품 살생부 작성")
    st.info("💡 네이버 리포트 엑셀 파일을 업로드하면, '돈만 먹는 상품'을 자동으로 걸러냅니다.")
    
    uploaded_kill_file = st.file_uploader("분석할 리포트 업로드 (Excel)", type=['xlsx'])
    
    if uploaded_kill_file and st.button("🔪 살생부 분석 실행", type="primary"):
        try:
            df = pd.read_excel(uploaded_kill_file)
            
            # 컬럼 매핑 (한글/영어 호환)
            cols = df.columns
            cost = '광고비(원)' if '광고비(원)' in cols else 'salesAmt'
            sales = '전환매출액(원)' if '전환매출액(원)' in cols else 'convAmt'
            imp = '노출수' if '노출수' in cols else 'impCnt'
            clk = '클릭수' if '클릭수' in cols else 'clkCnt'
            
            # 필터링 조건
            cond_a = (df[cost] >= 5000) & (df[sales] == 0)
            cond_b = (df[imp] >= 100) & (df[clk] == 0)
            
            zombies = df[cond_a | cond_b].copy()
            count = len(zombies)
            
            if count > 0:
                st.error(f"🚨 총 {count}개의 좀비 상품 발견!")
                st.dataframe(zombies)
                
                # 다운로드
                output_z = BytesIO()
                with pd.ExcelWriter(output_z, engine='xlsxwriter') as writer:
                    zombies.to_excel(writer, index=False)
                data_z = output_z.getvalue()
                
                st.download_button(
                    label="💀 살생부(Kill List) 다운로드",
                    data=data_z,
                    file_name=f"Kill_List_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.balloons()
                st.success("✨ 축하합니다! 좀비 상품이 하나도 없습니다. 광고 효율이 완벽합니다.")
                
        except Exception as e:
            st.error(f"분석 오류: {e}")