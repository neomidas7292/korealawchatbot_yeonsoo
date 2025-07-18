import requests
import xml.etree.ElementTree as ET
import json
import os
from typing import Optional, Tuple, List, Dict
import streamlit as st

class LawAPI:
    def __init__(self, oc: str):
        """법령 API 클래스 초기화
        
        Args:
            oc: API 키
        """
        self.oc = oc
        self.base_url = "http://www.law.go.kr/DRF/"
    
    def search_law_id(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """법령명으로 검색해서 첫 번째 법령의 ID를 반환
        
        Args:
            query: 검색할 법령명
            
        Returns:
            Tuple[법령ID, 법령명한글] 또는 (None, None)
        """
        url = f"{self.base_url}lawSearch.do"
        params = {
            "OC": self.oc,
            "target": "law",
            "type": "XML",
            "query": query
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            law = root.find("law")
            
            if law is None:
                return None, None
            
            return law.findtext("법령ID"), law.findtext("법령명한글")
        
        except Exception as e:
                # ✅ 추가된 디버깅 코드
            # 에러가 발생했을 때 서버가 보낸 실제 응답 내용을 출력합니다.
            print("===== API 서버 실제 응답 내용 =====")
            print(response.text)
            print("===================================")
            st.error(f"법령 검색 중 오류 발생: {str(e)}")
            return None, None
    
    def get_law_json(self, law_id: str) -> Optional[Dict]:
        """법령 ID로 법령 데이터 조회
        
        Args:
            law_id: 법령 ID
            
        Returns:
            법령 데이터 또는 None
        """
        url = f"{self.base_url}lawService.do"
        params = {
            "OC": self.oc,
            "target": "law",
            "type": "JSON",
            "ID": law_id
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            st.error(f"법령 데이터 조회 중 오류 발생: {str(e)}")
            return None
    
    def clean_law_data(self, law_data: Dict) -> Dict:
        """필요한 정보만 추출하여 정제된 데이터 반환 (조 단위로 고정)
        
        Args:
            law_data: 법령 원본 데이터
            
        Returns:
            정제된 법령 데이터
        """
        # 기본정보에서 법령ID와 법령명 추출
        basic_info = law_data.get("법령", {}).get("기본정보", {})
        cleaned_data = {
            "법령ID": basic_info.get("법령ID"),
            "법령명_한글": basic_info.get("법령명_한글"),
            "조문": []
        }
        
        # 조문 데이터 추출
        law_content = law_data.get("법령", {})
        if "조문" in law_content:
            articles = law_content["조문"]
            if "조문단위" in articles:
                # 조문단위가 단일 항목인 경우 리스트로 감싸기
                if isinstance(articles["조문단위"], dict):
                    articles_list = [articles["조문단위"]]
                else:
                    articles_list = articles["조문단위"]

                for article in articles_list:
                    full_content = article.get("조문내용", "")
                    
                    # 항 데이터가 있는 경우 조문내용에 추가
                    if "항" in article:
                        full_content += self._extract_all_content_from_items(article["항"])
                    
                    article_data = {
                        "조문번호": article.get("조문번호"),
                        "조문제목": article.get("조문제목"),
                        "조문내용": full_content.strip()  # 공백 제거
                    }
                    cleaned_data["조문"].append(article_data)
        
        return cleaned_data
    
    def _extract_all_content_from_items(self, items) -> str:
        """항 데이터에서 모든 텍스트 내용을 추출"""
        content = ""
        
        # items가 딕셔너리 하나인 경우에도 처리하도록 수정
        if isinstance(items, dict):
            items = [items]  # 리스트로 변환하여 반복문 처리

        if isinstance(items, list):
            for item in items:
                hang_content = item.get("항내용")
                if hang_content:
                    # 항내용이 리스트인 경우 문자열로 변환
                    if isinstance(hang_content, list):
                        content += "\n" + " ".join(str(i) for i in hang_content)
                    else:
                        content += "\n" + str(hang_content)
                
                if "호" in item:
                    content += self._extract_all_content_from_subitems(item["호"])
        
        return content
    
    def _extract_all_content_from_subitems(self, subitems) -> str:
        """호 데이터에서 모든 텍스트 내용을 추출"""
        content = ""
        
        # subitems가 딕셔너리 하나인 경우에도 처리하도록 수정
        if isinstance(subitems, dict):
            subitems = [subitems]  # 리스트로 변환하여 반복문 처리

        if isinstance(subitems, list):
            for subitem in subitems:
                ho_content = subitem.get("호내용")
                if ho_content:
                    # 호내용이 리스트인 경우 문자열로 변환
                    if isinstance(ho_content, list):
                        content += "\n" + " ".join(str(i) for i in ho_content)
                    else:
                        content += "\n" + str(ho_content)
        
        return content
    
    def download_law_as_json(self, query: str) -> Optional[Dict]:
        """법령을 검색하여 JSON 데이터로 반환
        
        Args:
            query: 검색할 법령명
            
        Returns:
            정제된 법령 데이터 또는 None
        """
        # 1. 법령 ID 검색
        law_id, law_name = self.search_law_id(query)
        if not law_id:
            return None
        
        # 2. 법령 데이터 조회
        law_data = self.get_law_json(law_id)
        if not law_data:
            return None
        
        # 3. 데이터 정제
        cleaned_data = self.clean_law_data(law_data)
        
        return cleaned_data
    
    def save_law_json_file(self, query: str, filename: str) -> bool:
        """법령을 검색하여 JSON 파일로 저장
        
        Args:
            query: 검색할 법령명
            filename: 저장할 파일명
            
        Returns:
            성공 여부
        """
        cleaned_data = self.download_law_as_json(query)
        if not cleaned_data:
            return False
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(cleaned_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            st.error(f"파일 저장 중 오류 발생: {str(e)}")
            return False
    
    def batch_download_laws(self, law_names: List[str]) -> Dict[str, Dict]:
        """여러 법령을 일괄 다운로드
        
        Args:
            law_names: 다운로드할 법령명 리스트
            
        Returns:
            {법령명: 법령데이터} 형태의 딕셔너리
        """
        results = {}
        
        for law_name in law_names:
            st.info(f"'{law_name}' 다운로드 중...")
            
            cleaned_data = self.download_law_as_json(law_name)
            if cleaned_data:
                results[law_name] = cleaned_data
                st.success(f"✅ '{law_name}' 다운로드 완료 ({len(cleaned_data.get('조문', []))}개 조문)")
            else:
                st.error(f"❌ '{law_name}' 다운로드 실패")
        
        return results

def convert_law_data_to_chatbot_format(law_data: Dict) -> List[Dict]:
    """법령 데이터를 챗봇 형식으로 변환
    
    Args:
        law_data: 법령 API에서 받은 데이터
        
    Returns:
        챗봇용 JSON 형식 리스트
    """
    chatbot_data = []
    
    for article in law_data.get("조문", []):
        chatbot_item = {
            "조번호": article.get("조문번호", ""),
            "제목": article.get("조문제목", ""),
            "내용": article.get("조문내용", "")
        }
        chatbot_data.append(chatbot_item)
    
    return chatbot_data