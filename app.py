import requests
import json
from datetime import datetime, timedelta

def create_report_v4_1(base_url, headers, report_type="AD"):
    """
    [v4.1] 네이버 검색광고 리포트 생성 요청 함수
    - 변경점 1: statDt를 오늘 날짜 기준 2일 전(D-2)으로 고정
    - 변경점 2: 400 에러 중 code 20007(데이터 집계 중) 발생 시 오류 무시 및 대기 신호 반환
    """
    
    # 1. statDt 설정 (D-2)
    target_date = datetime.now() - timedelta(days=2)
    stat_dt = target_date.strftime('%Y-%m-%d')
    
    uri = '/stat-reports'
    url = f"{base_url}{uri}"
    
    payload = {
        "reportType": report_type,
        "statDt": stat_dt
    }
    
    try:
        # API 요청 실행
        response = requests.post(url, headers=headers, json=payload)
        
        # 응답 처리
        if response.status_code in (200, 201):
            return response.json()
            
        elif response.status_code == 400:
            try:
                error_body = response.json()
                # 오류 코드 20007 확인 (수정사항 반영)
                # 20007: 리포트 생성 가능 시간이 아님 (데이터 집계 중 등)
                if str(error_body.get('code')) == '20007':
                    return {
                        "status": "WAITING", 
                        "message": "Code 20007 detected - Ignored as per v4.1"
                    }
                else:
                    # 그 외 400 에러는 그대로 반환
                    return error_body
            except ValueError:
                return {"error": "Invalid JSON body", "raw": response.text}
                
        else:
            # 기타 상태 코드
            return {
                "status_code": response.status_code, 
                "raw_response": response.text
            }
            
    except Exception as e:
        return {"internal_error": str(e)}