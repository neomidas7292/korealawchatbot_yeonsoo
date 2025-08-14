import requests
import xml.etree.ElementTree as ET
import json
import os
import logging
import re
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

        response = None
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            law = root.find("law")

            if law is None:
                return None, None

            return law.findtext("법령ID"), law.findtext("법령명한글")

        except Exception as e:
            # 에러 발생 시 서버에서 받은 실제 응답을 출력 (가능한 경우에만)
            if response is not None and hasattr(response, "text"):
                print("===== API 서버 실제 응답 내용 =====")
                print(response.text)
                print("===================================")
            logging.exception("법령 검색 중 오류 발생")
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
    
    # 3단 비교 관련 메소드들
    def get_three_stage_comparison_detail(self, law_id: str, comparison_type: int = 1) -> Optional[Dict]:
        """3단 비교 본문 상세 조회
        
        Args:
            law_id: 법령 ID
            comparison_type: 비교 종류 (1: 인용조문, 2: 위임조문)
            
        Returns:
            3단 비교 상세 데이터 또는 None
        """
        url = f"{self.base_url}lawService.do"
        params = {
            "OC": self.oc,
            "target": "thdCmp",
            "type": "XML",
            "ID": law_id,
            "knd": comparison_type
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # XML 파싱
            root = ET.fromstring(response.content)
            return self._parse_comparison_detail_xml(root, comparison_type)
            
        except Exception as e:
            st.error(f"3단 비교 상세 조회 중 오류 발생: {str(e)}")
            if hasattr(response, 'text'):
                print("서버 응답:", response.text[:500])
            return None
    
    def _parse_comparison_detail_xml(self, root, comparison_type: int) -> Dict:
        """3단 비교 상세 XML 파싱"""
        if comparison_type == 1:  # 인용조문
            return self._parse_citation_comparison(root)
        else:  # 위임조문
            return self._parse_delegation_comparison(root)
    
    def _parse_citation_comparison(self, root) -> Dict:
        """인용조문 3단 비교 파싱"""
        result = {
            "기본정보": {
                "법령ID": root.findtext(".//법령ID"),
                "법령명": root.findtext(".//법령명"),
                "시행령ID": root.findtext(".//시행령ID"),
                "시행령명": root.findtext(".//시행령명"),
                "시행규칙ID": root.findtext(".//시행규칙ID"),
                "시행규칙명": root.findtext(".//시행규칙명"),
                "시행일자": root.findtext(".//시행일자")
            },
            "인용조문삼단비교": []
        }
        
        # 법률조문들 파싱
        for law_article in root.findall(".//법률조문"):
            article_data = {
                "조번호": law_article.findtext("조번호"),
                "조제목": law_article.findtext("조제목"), 
                "조내용": law_article.findtext("조내용"),
                "시행령조문목록": [],
                "시행규칙조문목록": [],
                "위임행정규칙목록": []
            }
            
            # 시행령조문 파싱
            for decree_article in law_article.findall(".//시행령조문"):
                decree_data = {
                    "조번호": decree_article.findtext("조번호"),
                    "조제목": decree_article.findtext("조제목"),
                    "조내용": decree_article.findtext("조내용")
                }
                article_data["시행령조문목록"].append(decree_data)
            
            # 시행규칙조문 파싱
            for rule_article in law_article.findall(".//시행규칙조문"):
                rule_data = {
                    "조번호": rule_article.findtext("조번호"),
                    "조제목": rule_article.findtext("조제목"),
                    "조내용": rule_article.findtext("조내용")
                }
                article_data["시행규칙조문목록"].append(rule_data)
            
            # 위임행정규칙 파싱
            for admin_rule in law_article.findall(".//위임행정규칙"):
                admin_data = {
                    "위임행정규칙명": admin_rule.findtext("위임행정규칙명"),
                    "위임행정규칙조번호": admin_rule.findtext("위임행정규칙조번호"),
                    "조내용": admin_rule.findtext("조내용")
                }
                article_data["위임행정규칙목록"].append(admin_data)
            
            result["인용조문삼단비교"].append(article_data)
        
        return result
    
    def _parse_delegation_comparison(self, root) -> Dict:
        """위임조문 3단 비교 파싱"""
        result = {
            "기본정보": {
                "법령ID": root.findtext(".//법령ID"),
                "법령명": root.findtext(".//법령명"),
                "법령일련번호": root.findtext(".//법령일련번호"),
                "공포일자": root.findtext(".//공포일자"),
                "공포번호": root.findtext(".//공포번호"),
                "법종구분": root.findtext(".//법종구분"),
                "시행일자": root.findtext(".//시행일자"),
                "제개정구분": root.findtext(".//제개정구분"),
                "삼단비교존재여부": root.findtext(".//삼단비교존재여부")
            },
            "위임조문삼단비교": []
        }
        
        # 법률조문들 파싱
        for law_article in root.findall(".//법률조문"):
            article_data = {
                "조번호": law_article.findtext("조번호"),
                "조가지번호": law_article.findtext("조가지번호"),
                "조제목": law_article.findtext("조제목"), 
                "조내용": law_article.findtext("조내용"),
                "시행령조문목록": [],
                "시행규칙조문목록": []
            }
            
            # 시행령조문 파싱
            for decree_article in law_article.findall(".//시행령조문"):
                decree_data = {
                    "조번호": decree_article.findtext("조번호"),
                    "조가지번호": decree_article.findtext("조가지번호"),
                    "조제목": decree_article.findtext("조제목"),
                    "조내용": decree_article.findtext("조내용")
                }
                article_data["시행령조문목록"].append(decree_data)
            
            # 시행규칙조문 파싱
            for rule_article in law_article.findall(".//시행규칙조문"):
                rule_data = {
                    "조번호": rule_article.findtext("조번호"),
                    "조가지번호": rule_article.findtext("조가지번호"),
                    "조제목": rule_article.findtext("조제목"),
                    "조내용": rule_article.findtext("조내용")
                }
                article_data["시행규칙조문목록"].append(rule_data)
            
            result["위임조문삼단비교"].append(article_data)
        
        return result
    
    def _extract_title_in_parentheses(self, text: str) -> str:
        """텍스트에서 괄호 안의 내용만 추출
        
        Args:
            text: 원본 텍스트
            
        Returns:
            괄호 안의 내용 또는 빈 문자열
        """
        if not text:
            return ""
        
        # 괄호 안의 내용 추출 (첫 번째 괄호만)
        match = re.search(r'\(([^)]+)\)', text)
        if match:
            return match.group(1)
        return ""
    
    def convert_three_stage_comparison_to_chatbot_format(self, comparison_data: Dict) -> List[Dict]:
        """3단 비교 데이터를 챗봇 형식으로 변환
        
        Args:
            comparison_data: 파싱된 3단 비교 데이터
            
        Returns:
            {"조번호", "제목", "내용"} 형태의 리스트
        """
        result = []
        
        # 인용조문 또는 위임조문 데이터 처리
        articles = comparison_data.get("인용조문삼단비교", [])
        if not articles:
            articles = comparison_data.get("위임조문삼단비교", [])
            
        for article in articles:
            # 하위법령내용 통합
            sub_law_content = ""
            
            # 시행령조문 내용 추가
            for decree in article.get("시행령조문목록", []):
                if decree.get("조내용"):
                    decree_title = self._extract_title_in_parentheses(decree.get('조제목', ''))
                    sub_law_content += f"[시행령 {decree.get('조번호', '')}] {decree_title}\n"
                    sub_law_content += f"{decree.get('조내용', '')}\n\n"
            
            # 시행규칙조문 내용 추가
            for rule in article.get("시행규칙조문목록", []):
                if rule.get("조내용"):
                    rule_title = self._extract_title_in_parentheses(rule.get('조제목', ''))
                    sub_law_content += f"[시행규칙 {rule.get('조번호', '')}] {rule_title}\n"
                    sub_law_content += f"{rule.get('조내용', '')}\n\n"
            
            # 위임행정규칙 내용 추가
            for admin in article.get("위임행정규칙목록", []):
                if admin.get("조내용"):
                    sub_law_content += f"[위임행정규칙] {admin.get('위임행정규칙명', '')}\n"
                    sub_law_content += f"{admin.get('조내용', '')}\n\n"
            
            # 법조문 제목에서 괄호 안 내용만 추출
            title = self._extract_title_in_parentheses(article.get("조제목", ""))
            
            # 법조문내용과 하위법령내용을 합쳐서 "내용" 생성
            law_content = article.get("조내용", "")
            combined_content = law_content
            if sub_law_content.strip():
                combined_content += "\n" + sub_law_content.strip()
            
            formatted_article = {
                "조번호": article.get("조번호", ""),
                "제목": title,
                "내용": combined_content
            }
            
            result.append(formatted_article)
        
        return result
    
    def filter_empty_titles(self, chatbot_data: List[Dict]) -> List[Dict]:
        """제목이 빈 문자열이거나 null인 항목들을 제거하는 함수
        
        Args:
            chatbot_data: 챗봇 형식 데이터 리스트
            
        Returns:
            제목이 빈 문자열이나 null이 아닌 항목들만 포함한 리스트
        """
        filtered_data = []
        removed_count = 0
        
        for item in chatbot_data:
            title = item.get("제목")
            # None, 빈 문자열, 공백만 있는 경우 모두 제외
            if title is not None and str(title).strip():
                filtered_data.append(item)
            else:
                removed_count += 1
        
        if removed_count > 0:
            st.info(f"📝 제목이 없는 {removed_count}개 항목을 제거했습니다.")
        
        return filtered_data
    
    def download_three_stage_comparison_as_json(self, law_name: str) -> Optional[List[Dict]]:
        """법령명으로 3단 비교 데이터를 검색하여 챗봇 형식으로 반환
        
        Args:
            law_name: 법령명
            
        Returns:
            챗봇용 3단 비교 데이터 또는 None
        """
        # 1. 법령 ID 검색
        law_id, full_law_name = self.search_law_id(law_name)
        if not law_id:
            return None
        
        # 2. 3단 비교 상세 조회 (위임조문)
        comparison_data = self.get_three_stage_comparison_detail(law_id, comparison_type=2)
        if not comparison_data:
            return None
        
        # 3. 챗봇 형식으로 변환
        chatbot_data = self.convert_three_stage_comparison_to_chatbot_format(comparison_data)
        
        # 4. 제목이 빈 문자열인 항목들 제거
        if chatbot_data:
            chatbot_data = self.filter_empty_titles(chatbot_data)
        
        return chatbot_data if chatbot_data else None

def convert_law_data_to_chatbot_format(law_data: Dict) -> List[Dict]:
    """법령 데이터를 챗봇 형식으로 변환
    
    Args:
        law_data: 법령 API에서 받은 데이터
        
    Returns:
        챗봇용 JSON 형식 리스트 (빈 제목 항목 제거됨)
    """
    chatbot_data = []
    
    for article in law_data.get("조문", []):
        chatbot_item = {
            "조번호": article.get("조문번호", ""),
            "제목": article.get("조문제목", ""),
            "내용": article.get("조문내용", "")
        }
        chatbot_data.append(chatbot_item)
    
    # 제목이 빈 문자열이나 null인 항목들 제거
    filtered_data = []
    removed_count = 0
    
    for item in chatbot_data:
        title = item.get("제목")
        # None, 빈 문자열, 공백만 있는 경우 모두 제외
        if title is not None and str(title).strip():
            filtered_data.append(item)
        else:
            removed_count += 1
    
    if removed_count > 0:
        st.info(f"📝 법령 데이터에서 제목이 없는 {removed_count}개 항목을 제거했습니다.")
    
    return filtered_data