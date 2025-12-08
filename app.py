import streamlit as st
import datetime
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
# [설정] 페이지 기본 설정
# ==========================================
st.set_page_config(
    page_title="AC Team Web Conductor",
    page_icon="🕸️",
    layout="wide"
)

# [상태 초기화] Streamlit은 새로고침될 때마다 리셋되므로 session_state에 저장해야 함
if 'logs' not in st.session_state: st.session_state.logs = []
if 'api_config' not in st.session_state: 
    st.session_state.api_config = {"GOOGLE_API_KEY":"", "NAVER_API_KEY":"", "NAVER_SECRET_KEY":"", "NAVER_CUSTOMER_ID":""}
if 'current_role' not in st.session_state: st.session_state.current_role = "1. AC김시율 (Director)"

# ==========================================
# [함수] 로직 모음
# ==========================================
def log_event(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    st.session_state.logs.append(f"[{ts}] {msg}")

def get_naver_header(method, uri, api_key, secret_key, customer_id):
    ts = str(int(time.time() * 1000))
    msg = f"{ts}.{method}.{uri}"
    sign = base64.b64encode(hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()).decode()
    return {
        "Content-Type": "application/json", "X-Timestamp": ts, 
        "X-API-KEY": api_key, "X-Customer": customer_id, "X-Signature": sign
    }

import time # time 모듈 추가

# ==========================================
# [UI] 사이드바: 설정 및 상태 (수정됨)
# ==========================================
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    
    with st.form("api_config_form"): # 폼(Form)으로 감싸서 엔터/버튼으로 저장
        st.subheader("API Key 관리")
        
        # 기존 값 불러오기 (없으면 빈카ん)
        g_key = st.text_input("Google Gemini Key", value=st.session_state.api_config.get("GOOGLE_API_KEY", ""), type="password")
        n_key = st.text_input("Naver Access Key", value=st.session_state.api_config.get("NAVER_API_KEY", ""), type="password")
        n_sec = st.text_input("Naver Secret Key", value=st.session_state.api_config.get("NAVER_SECRET_KEY", ""), type="password")
        n_id = st.text_input("Naver Customer ID", value=st.session_state.api_config.get("NAVER_CUSTOMER_ID", ""))
        
        # [저장 버튼]
        if st.form_submit_button("💾 설정 저장 (Save Config)"):
            st.session_state.api_config["GOOGLE_API_KEY"] = g_key
            st.session_state.api_config["NAVER_API_KEY"] = n_key
            st.session_state.api_config["NAVER_SECRET_KEY"] = n_sec
            st.session_state.api_config["NAVER_CUSTOMER_ID"] = n_id
            st.success("API 키가 저장되었습니다!")
            
    st.divider()
    st.subheader("📜 시스템 로그")
    for log in reversed(st.session_state.logs[-10:]):
        st.caption(log)
# ==========================================
# [UI] 메인 화면
# ==========================================
st.title("🕸️ AC Team: Web Conductor")
st.markdown("---")

# 탭 구성
tab1, tab2, tab4 = st.tabs(["💬 작전 회의실", "📊 실행실 (Naver)", "💀 분석실 (Guillotine)"])

# -------------------------------------------------------
# [Tab 1] 작전 회의실 (AI Chat)
# -------------------------------------------------------
with tab1:
    col1, col2 = st.columns([1, 3])
    with col1:
        role = st.selectbox("소환 대상", 
            ["1. AC김시율 (Director)", "2. PM (구성)", "3. Architect (설계)", "4. Executor (수행)", "5. Scribe (서기)"])
    
    # 채팅 기록 표시
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 입력창
    if prompt := st.chat_input("지시 사항을 입력하세요..."):
        # 사용자 메시지 표시
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 응답 생성
        if not st.session_state.api_config["GOOGLE_API_KEY"]:
            st.error("Google API Key가 설정되지 않았습니다.")
        else:
            try:
                # 페르소나 정의 (간소화)
                personas = {
                    "1. AC김시율 (Director)": "너는 총괄 디렉터다. 명확히 지시하라.",
                    "2. PM (구성)": "너는 PM이다. 기획하라.",
                    "3. Architect (설계)": "너는 설계자다. 코드를 작성하라.",
                    "4. Executor (수행)": "너는 수행자다. 결과를 보고하라.",
                    "5. Scribe (서기)": "너는 서기다. 기록하라."
                }
                sys_inst = personas.get(role, "")
                
                genai.configure(api_key=st.session_state.api_config["GOOGLE_API_KEY"])
                model = genai.GenerativeModel('gemini-2.0-flash-exp', system_instruction=sys_inst)
                
                with st.chat_message("assistant"):
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                    
            except Exception as e:
                st.error(f"AI 통신 오류: {e}")

# -------------------------------------------------------
# [Tab 2] 실행실 (Naver API)
# -------------------------------------------------------
with tab2:
    st.subheader("Naver 검색광고 리포트 추출")
    
    if st.button("🚀 리포트 추출 및 다운로드", type="primary"):
        cfg = st.session_state.api_config
        if not (cfg["NAVER_API_KEY"] and cfg["NAVER_SECRET_KEY"] and cfg["NAVER_CUSTOMER_ID"]):
            st.error("네이버 API 설정이 필요합니다.")
        else:
            try:
                with st.spinner("네이버 서버 접속 중..."):
                    base_url = "https://api.searchad.naver.com"
                    stat_dt = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    # 1. 생성
                    uri = "/stat-reports"
                    headers = get_naver_header("POST", uri, cfg["NAVER_API_KEY"], cfg["NAVER_SECRET_KEY"], cfg["NAVER_CUSTOMER_ID"])
                    res = requests.post(base_url + uri, headers=headers, json={"reportTp": "AD", "statDt": stat_dt})
                    
                    if res.status_code != 200: raise Exception(res.text)
                    jid = res.json()["reportJobId"]
                    log_event(f"Job ID 발급: {jid}")
                    
                    # 2. 대기
                    durl = None
                    for _ in range(10):
                        time.sleep(2)
                        uri_chk = f"/stat-reports/{jid}"
                        h = get_naver_header("GET", uri_chk, cfg["NAVER_API_KEY"], cfg["NAVER_SECRET_KEY"], cfg["NAVER_CUSTOMER_ID"])
                        r = requests.get(base_url + uri_chk, headers=h)
                        if r.json()["status"] == "BUILT":
                            durl = r.json()["downloadUrl"]
                            break
                    
                    if not durl: raise Exception("다운로드 URL 확보 실패")
                    
                    # 3. 다운로드 (Clean Sig)
                    parsed = urlparse(durl)
                    h_dl = get_naver_header("GET", parsed.path, cfg["NAVER_API_KEY"], cfg["NAVER_SECRET_KEY"], cfg["NAVER_CUSTOMER_ID"])
                    file_res = requests.get(durl, headers=h_dl)
                    
                    # 4. 엑셀 변환
                    df = pd.read_csv(StringIO(file_res.text), sep='\t')
                    rename_map = {'statDt':'날짜', 'salesAmt':'광고비(원)', 'convAmt':'전환매출액(원)', 'impCnt':'노출수', 'clkCnt':'클릭수'}
                    df.rename(columns=rename_map, inplace=True)
                    
                    # 5. 다운로드 버튼 생성
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    data = output.getvalue()
                    
                    st.success("리포트 생성 완료!")
                    st.download_button("📥 엑셀 파일 다운로드", data, file_name=f"Report_{stat_dt}.xlsx")
                    log_event("리포트 다운로드 준비 완료")

            except Exception as e:
                st.error(f"오류 발생: {e}")

# -------------------------------------------------------
# [Tab 4] 분석실 (Guillotine)
# -------------------------------------------------------
with tab4:
    st.subheader("💀 좀비 상품 살생부 작성")
    
    uploaded_file = st.file_uploader("분석할 엑셀 리포트를 업로드하세요", type=['xlsx'])
    
    if uploaded_file and st.button("살생부 분석 실행", type="primary"):
        try:
            df = pd.read_excel(uploaded_file)
            
            # 컬럼 매핑 확인
            cost = '광고비(원)' if '광고비(원)' in df.columns else 'salesAmt'
            sales = '전환매출액(원)' if '전환매출액(원)' in df.columns else 'convAmt'
            imp = '노출수' if '노출수' in df.columns else 'impCnt'
            clk = '클릭수' if '클릭수' in df.columns else 'clkCnt'
            
            # 필터링
            zombies = df[((df[cost]>=5000) & (df[sales]==0)) | ((df[imp]>=100) & (df[clk]==0))]
            count = len(zombies)
            
            if count > 0:
                st.warning(f"총 {count}개의 좀비 상품이 발견되었습니다!")
                st.dataframe(zombies)
                
                # 다운로드
                output_z = BytesIO()
                with pd.ExcelWriter(output_z, engine='xlsxwriter') as writer:
                    zombies.to_excel(writer, index=False)
                data_z = output_z.getvalue()
                
                st.download_button("💀 살생부(Kill List) 다운로드", data_z, file_name=f"Kill_List_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx")
            else:
                st.success("좀비 상품이 없습니다. 깨끗합니다!")
                
        except Exception as e:
            st.error(f"분석 오류: {e}")