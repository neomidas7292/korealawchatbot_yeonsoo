import requests
import xml.etree.ElementTree as ET
import json
import re
from typing import Optional, Tuple, List, Dict
import streamlit as st

class AdminAPI:
    def __init__(self, oc: str):
        """행정규칙 API 클래스 초기화
        
        Args:
            oc: API 키
        """
        self.oc = oc
        self.base_url = "http://www.law.go.kr/DRF/"
    
    def search_admin_rule_id(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """행정규칙명으로 검색해서 첫 번째 행정규칙의 ID를 반환
        
        Args:
            query: 검색할 행정규칙명
            
        Returns:
            Tuple[행정규칙ID, 행정규칙명] 또는 (None, None)
        """
        url = f"{self.base_url}lawSearch.do"
        params = {
            "OC": self.oc,
            "target": "admrul",
            "type": "XML",
            "query": query,
            "search": 1,
            "display": 1
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            admrul = root.find("admrul")
            
            if admrul is None:
                return None, None
            
            return admrul.findtext("행정규칙일련번호"), admrul.findtext("행정규칙명")
        
        except Exception as e:
            st.error(f"행정규칙 검색 중 오류 발생: {str(e)}")
            return None, None
    
    def get_admin_rule_json(self, rule_id: str) -> Optional[Dict]:
        """행정규칙 ID로 행정규칙 데이터 조회
        
        Args:
            rule_id: 행정규칙 ID
            
        Returns:
            행정규칙 데이터 또는 None
        """
        url = f"{self.base_url}lawService.do"
        params = {
            "OC": self.oc,
            "target": "admrul",
            "type": "JSON",
            "ID": rule_id
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            st.error(f"행정규칙 데이터 조회 중 오류 발생: {str(e)}")
            return None
    
    def clean_rule_data(self, rule_data: Dict) -> List[str]:
        """JSON 데이터에서 조문 내용만 리스트로 추출"""
        return rule_data.get("AdmRulService", {}).get("조문내용", {})
    
    def parse_text_to_json(self, text):
        """
        PDF에서 추출한 텍스트를 조문별로 파싱하여 JSON 구조로 변환하는 함수
        """
        print(f"📝 파싱할 텍스트 타입: {type(text)}")
        print(f"📝 파싱할 텍스트 길이: {len(text) if isinstance(text, str) else '문자열이 아님'}")
        
        # text가 문자열이 아닌 경우 처리
        if not isinstance(text, str):
            print(f"📝 텍스트가 문자열이 아닙니다. 실제 타입: {type(text)}")
            if isinstance(text, (list, dict)):
                print(f"📝 텍스트 내용: {text}")
            return []
        
        print(f"📝 파싱할 텍스트 (처음 500자):\n{text[:500]}")
        print(f"📝 파싱할 텍스트 (마지막 500자):\n{text[-500:]}")
        
        조문들 = []  # 파싱된 모든 조문을 저장할 리스트
        
        # 조문 패턴을 정규식으로 정의 - 텍스트 내 어디서든 찾을 수 있도록 수정
        조문_패턴 = re.compile(r"(제\d+(?:-\d+)?조(?:의\d+)?)\((.*?)\)")
        
        print(f"📝 조문 패턴: {조문_패턴.pattern}")
        
        # 전체 텍스트에서 조문 패턴을 찾아서 분할
        조문_매치들 = list(조문_패턴.finditer(text))
        print(f"📝 발견된 조문 매치 수: {len(조문_매치들)}")
        
        # 조문별로 내용 추출
        for i, 매치 in enumerate(조문_매치들):
            조번호 = 매치.group(1)
            제목 = 매치.group(2)
            
            # 현재 조문의 시작 위치
            현재_시작 = 매치.end()
            
            # 다음 조문의 시작 위치 (마지막 조문이면 텍스트 끝까지)
            if i + 1 < len(조문_매치들):
                다음_시작 = 조문_매치들[i + 1].start()
            else:
                다음_시작 = len(text)
            
            # 조문 내용 추출
            내용 = text[현재_시작:다음_시작].strip()
            
            print(f"📝 조문 {i+1}: {조번호}({제목})")
            print(f"📝 내용 길이: {len(내용)}")
            print(f"📝 내용 (처음 100자): {내용[:100]}")
            
            조문들.append({
                "조번호": 조번호,
                "제목": 제목,
                "내용": 내용
            })
        
        print(f"📝 총 파싱된 조문 수: {len(조문들)}")
        
        return 조문들
    
    
    def remove_bracketed_text(self, 내용: str) -> str:
        """내용에서 꺾쇠괄호(<>)나 대괄호([]) 안의 텍스트를 제거"""
        return re.sub(r"<.*?>|\[.*?\]", "", 내용).strip()
    
    def clean_admin_rule_data(self, rule_data: Dict, rule_id: str, rule_name: str) -> Dict:
        """필요한 정보만 추출하여 정제된 데이터 반환 (조 단위로 고정)
        
        Args:
            rule_data: 행정규칙 원본 데이터
            rule_id: 행정규칙 ID
            rule_name: 행정규칙명
            
        Returns:
            정제된 행정규칙 데이터
        """
        # 조문 내용 추출
        cleaned_rule_data = self.clean_rule_data(rule_data)

        # 리스트의 각 딕셔너리에서 '조문내용' 값만 추출하여 하나의 문자열로 합칩니다.
        if isinstance(cleaned_rule_data, list):
            # 리스트의 각 항목(item)이 딕셔너리이면 '조문내용' 값을, 문자열이면 그 자체를 사용합니다.
            text = "\n".join([
                item.get('조문내용', '') if isinstance(item, dict) else str(item)
                for item in cleaned_rule_data
            ])
        else:
            # 리스트가 아닌 다른 형태일 경우를 대비해 문자열로 변환합니다.
            text = str(cleaned_rule_data)
        
        # 텍스트를 조문별로 파싱
        파싱된_데이터 = self.parse_text_to_json(text)
        
        # 각 조문의 내용을 정제
        정제된_조문들 = []
        for 조문 in 파싱된_데이터:
            정제된_내용 = self.remove_bracketed_text(조문["내용"])
            정제된_조문들.append({
                "조번호": 조문["조번호"],
                "제목": 조문["제목"],
                "내용": 정제된_내용
            })
        
        # 최종 데이터 구조 생성
        cleaned_data = {
            "행정규칙ID": rule_id,
            "행정규칙명": rule_name,
            "조문": 정제된_조문들
        }
        
        return cleaned_data
    
    def download_admin_rule_as_json(self, query: str) -> Optional[Dict]:
        """행정규칙을 검색하여 JSON 데이터로 반환
        
        Args:
            query: 검색할 행정규칙명
            
        Returns:
            정제된 행정규칙 데이터 또는 None
        """
        # 1. 행정규칙 ID 검색
        rule_id, rule_name = self.search_admin_rule_id(query)
        if not rule_id:
            return None
        
        # 2. 행정규칙 데이터 조회
        rule_data = self.get_admin_rule_json(rule_id)
        if not rule_data:
            return None
        
        # 3. 데이터 정제
        cleaned_data = self.clean_admin_rule_data(rule_data, rule_id, rule_name)
        
        return cleaned_data
    
    def batch_download_admin_rules(self, rule_names: List[str]) -> Dict[str, Dict]:
        """여러 행정규칙을 일괄 다운로드
        
        Args:
            rule_names: 다운로드할 행정규칙명 리스트
            
        Returns:
            {행정규칙명: 행정규칙데이터} 형태의 딕셔너리
        """
        results = {}
        
        for rule_name in rule_names:
            st.info(f"'{rule_name}' 다운로드 중...")
            
            cleaned_data = self.download_admin_rule_as_json(rule_name)
            if cleaned_data:
                results[rule_name] = cleaned_data
                st.success(f"✅ '{rule_name}' 다운로드 완료 ({len(cleaned_data.get('조문', []))}개 조문)")
            else:
                st.error(f"❌ '{rule_name}' 다운로드 실패")
        
        return results

def convert_admin_rule_data_to_chatbot_format(rule_data: Dict) -> List[Dict]:
    """행정규칙 데이터를 챗봇 형식으로 변환
    
    Args:
        rule_data: 행정규칙 API에서 받은 데이터
        
    Returns:
        챗봇용 JSON 형식 리스트
    """
    chatbot_data = []
    
    for article in rule_data.get("조문", []):
        chatbot_item = {
            "조번호": article.get("조번호", ""),
            "제목": article.get("제목", ""),
            "내용": article.get("내용", "")
        }
        chatbot_data.append(chatbot_item)
    
    return chatbot_data

if __name__ == "__main__":
    # Streamlit을 사용하지 않는 환경을 위한 Mock 객체 (없으면 에러 방지)
    class MockStreamlit:
        def error(self, message): print(f"ERROR: {message}")
        def info(self, message): print(f"INFO: {message}")
        def success(self, message): print(f"SUCCESS: {message}")
        def json(self, data): print(json.dumps(data, indent=2, ensure_ascii=False)) # JSON 예쁘게 출력
        def write(self, message): print(message)

    if 'st' not in locals():
        st = MockStreamlit()

    # --- 설정 ---
    oc_key = "yschoi0817" # <-- 여기에 당신의 API 키를 넣으세요!
    search_query = "외국환거래규정"

    # --- 실행 ---
    if oc_key == "":
        st.error("⚠️ API 키를 입력해야 합니다.")
    else:
        admin_api = AdminAPI(oc_key)
        st.info(f"'{search_query}' 검색 중...")
        
        cleaned_data = admin_api.download_admin_rule_as_json(search_query)
        
        if cleaned_data:
            st.success(f"'{search_query}' 다운로드 및 정제 완료!")
            st.json(cleaned_data)
            
            # 챗봇 형식으로 변환된 데이터 첫 5개 조문만 출력
            chatbot_format_data = convert_admin_rule_data_to_chatbot_format(cleaned_data)
            st.info("\n--- 챗봇 형식 데이터 (일부) ---")
            st.json(chatbot_format_data[:5]) 
        else:
            st.error(f"'{search_query}' 검색 실패.")