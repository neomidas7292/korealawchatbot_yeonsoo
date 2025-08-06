from google import genai
import os
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re
import pickle
import hashlib
from pathlib import Path
import concurrent.futures
from typing import List, Dict, Tuple

# 불용어 정의
LEGAL_STOPWORDS = [
    # 기본 불용어
    '것', '등', '때', '경우', '바', '수', '점', '면', '이', '그', '저', '은', '는', '을', '를', '에', '의', '으로', 
    '따라', '또는', '및', '있다', '한다', '되어', '인한', '대한', '관한', '위한', '통한', '같은', '다른',
    
    # 법령 구조 불용어
    '조항', '규정', '법률', '법령', '조문', '항목', '세부', '내용', '사항', '요건', '기준', '방법', '절차',
    
    # 일반적인 동사/형용사
    '해당', '관련', '포함', '제외', '적용', '시행', '준용', '의하다', '하다', '되다', '있다', '없다', '같다'
]

# 캐싱 시스템
def get_file_hash(file_content):
    """파일 해시 생성"""
    return hashlib.md5(file_content.encode()).hexdigest()

def save_cache(file_name, file_hash, vec, mat, chunks):
    """캐시 저장"""
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    
    cache_file = cache_dir / f"{file_name}_{file_hash}.pkl"
    with open(cache_file, 'wb') as f:
        pickle.dump((vec, mat, chunks), f)

def load_cache(file_name, file_hash):
    """캐시 로드"""
    cache_file = Path("cache") / f"{file_name}_{file_hash}.pkl"
    if cache_file.exists():
        with open(cache_file, 'rb') as f:
            return pickle.load(f)
    return None

# 임베딩 생성 함수들
def create_embeddings_for_json_data(json_data, file_name):
    """JSON 데이터로부터 임베딩 생성"""
    try:
        # JSON 데이터를 문자열로 변환하여 해시 생성
        json_str = json.dumps(json_data, ensure_ascii=False, sort_keys=True)
        file_hash = get_file_hash(json_str)
        
        # 캐시 확인
        cached_data = load_cache(file_name, file_hash)
        if cached_data:
            return cached_data
        
        # 청크 생성
        chunks = []
        for item in json_data:
            if isinstance(item, dict):
                chunk_parts = []
                if "조번호" in item:
                    chunk_parts.append(f"[{item['조번호']}]")
                if "제목" in item:
                    chunk_parts.append(f"({item['제목']})")
                if "내용" in item:
                    chunk_parts.append(item['내용'])    
                
                if chunk_parts:
                    chunks.append(" ".join(chunk_parts))
        
        if not chunks:
            return None, None, []
        
        # 벡터화 최적화
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words=LEGAL_STOPWORDS,
            min_df=1,
            max_df=0.8,
            sublinear_tf=True,
            use_idf=True,
            smooth_idf=True,
            norm='l2'
        )
        
        matrix = vectorizer.fit_transform(chunks)
        
        # 캐시 저장
        save_cache(file_name, file_hash, vectorizer, matrix, chunks)
        
        return vectorizer, matrix, chunks
        
    except Exception as e:
        raise Exception(f"임베딩 생성 중 오류: {str(e)}")

def create_embeddings_for_text_optimized(file_content, file_name):
    """최적화된 임베딩 생성 (캐싱 포함)"""
    try:
        # 캐시 확인
        file_hash = get_file_hash(file_content)
        cached_data = load_cache(file_name, file_hash)
        if cached_data:
            return cached_data
        
        # JSON 파싱
        data = json.loads(file_content)
        if not isinstance(data, list):
            return None, None, []
        
        return create_embeddings_for_json_data(data, file_name)
        
    except Exception as e:
        raise Exception(f"임베딩 생성 중 오류: {str(e)}")

def create_embeddings_for_text(file_content):
    """기존 함수 (호환성 유지)"""
    return create_embeddings_for_text_optimized(file_content, "temp")

# 사용자 쿼리 전처리 및 유사어 생성
class QueryPreprocessor:
    """사용자 쿼리 전처리 및 유사어 생성 클래스"""
    
    def __init__(self):
        GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        
    def extract_keywords_and_synonyms(self, query: str) -> str:
        """키워드 추출 및 유사어 생성 - 단순화된 버전"""
        prompt = f"""
당신은 대한민국 법령 전문가입니다. 다음 질문을 분석하여 검색에 도움이 되는 키워드와 유사어를 생성해주세요.

질문: "{query}"

다음 작업을 수행해주세요:
1. 핵심 키워드 추출
2. 각 키워드의 유사어, 동의어, 관련어 생성
3. 복합어의 경우 단어 분리도 포함
4. 검색에 유용한 모든 관련 단어들을 나열

응답 형식: 키워드와 유사어들을 공백으로 구분하여 한 줄로 나열해주세요.
예시: 근로 근무 노동 일 업무 기준 규정 법률 조항 휴가 휴일 연차 유급휴가

단어들만 나열하고 다른 설명은 하지 마세요.
"""
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            # 응답에서 키워드들만 추출
            keywords_text = response.text.strip()
            # 불필요한 문자 제거하고 단어들만 추출
            keywords = re.findall(r'[가-힣]{2,}', keywords_text)
            return ' '.join(keywords)
            
        except Exception as e:
            print(f"키워드 추출 오류: {e}")
            # 폴백: 원본 쿼리에서 한글 단어 추출
            fallback_keywords = re.findall(r'[가-힣]{2,}', query)
            return ' '.join(fallback_keywords)
    
    def generate_similar_questions(self, original_query: str) -> List[str]:
        """유사한 질문 생성"""
        prompt = f"""
다음 질문과 유사한 의미를 가진 질문들을 3개 생성해주세요. 
법령 검색에 도움이 되도록 다양한 표현과 용어를 사용해주세요.

원본 질문: "{original_query}"

유사 질문 3개를 다음 형식으로 생성해주세요:
1. (첫 번째 유사 질문)
2. (두 번째 유사 질문)
3. (세 번째 유사 질문)

각 질문은 원본과 의미는 같지만 다른 표현이나 용어를 사용해주세요.
"""
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            # 응답에서 질문들 추출
            questions = []
            lines = response.text.strip().split('\n')
            for line in lines:
                # 숫자와 점으로 시작하는 줄에서 질문 추출
                match = re.search(r'^\d+\.\s*(.+)', line.strip())
                if match:
                    questions.append(match.group(1))
            
            # 최대 5개까지만 반환
            return questions[:3]
            
        except Exception as e:
            print(f"유사 질문 생성 오류: {e}")
            # 폴백: 원본 질문만 반환
            return [original_query]


# 검색함수 (핵심키워드 및 유사어 활용)    
def search_relevant_chunks(query, expanded_keywords, vectorizer, tfidf_matrix, text_chunks, top_k=3, threshold=0.01):
    """단순화된 검색 함수 (사전 계산된 키워드 사용)"""
    
    try:
        # 1. 쿼리 전처리 로직이 제거됨 (API 호출 방지)
        
        # 2. 원본 쿼리와 미리 확장된 키워드로 검색
        search_queries = [query, expanded_keywords]
        
        # 3. 여러 검색으로 결과 수집
        all_similarities = []
        
        for search_query in search_queries:
            q_vec = vectorizer.transform([search_query])
            sims = cosine_similarity(q_vec, tfidf_matrix).flatten()
            
            # 원본 쿼리에 더 높은 가중치
            weight = 1.0 if search_query == query else 0.8
            weighted_sims = sims * weight
            
            all_similarities.append(weighted_sims)
        
        # 4. 최고 점수로 결합
        if all_similarities:
            combined_sims = np.maximum.reduce(all_similarities)
        else:
            combined_sims = cosine_similarity(vectorizer.transform([query]), tfidf_matrix).flatten()
        
        # 5. 상위 결과 선택
        indices = combined_sims.argsort()[-top_k:][::-1]
        
        selected_chunks = []
        for i in indices:
            if combined_sims[i] > threshold:
                selected_chunks.append(text_chunks[i])
        
        # 임계값 이상인 청크가 없으면 상위 결과 반환
        if not selected_chunks:
            selected_chunks = [text_chunks[i] for i in indices[:top_k]]
        
        return "\n\n".join(selected_chunks)
    
    except Exception as e:
        raise Exception(f"검색 중 오류 발생: {str(e)}")

# 병렬 처리 함수들
def process_single_file(file_data):
    """단일 파일 처리 함수"""
    file_name, file_content = file_data
    try:
        vec, mat, chunks = create_embeddings_for_text_optimized(file_content, file_name)
        return file_name, vec, mat, chunks, len(chunks) if chunks else 0
    except Exception as e:
        return file_name, None, None, None, 0

def process_json_data(file_name, json_data):
    """JSON 데이터 처리 함수"""
    try:
        vec, mat, chunks = create_embeddings_for_json_data(json_data, file_name)
        return file_name, vec, mat, chunks, len(chunks) if chunks else 0
    except Exception as e:
        return file_name, None, None, None, 0

# Gemini 모델 반환
def get_model():
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    client = genai.Client(api_key=GOOGLE_API_KEY)
    return client

def get_model_head():
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    client = genai.Client(api_key=GOOGLE_API_KEY)
    return client

import queue

# 기존 stream_agent_response_to_queue 함수를 다음으로 교체:

def get_agent_response(law_name: str, question: str, history: str, embedding_data: Dict, expanded_keywords: str):
    """
    에이전트 응답을 일반적인 방식으로 생성하는 동기 함수.
    스트리밍 없이 완성된 답변만 반환.
    """
    if law_name not in embedding_data:
        return law_name, "해당 법령 데이터를 찾을 수 없습니다."

    vec, mat, chunks = embedding_data[law_name]
    if vec is None:
        return law_name, "해당 법령 데이터를 처리할 수 없습니다."

    try:
        final_context = search_relevant_chunks(question, expanded_keywords, vec, mat, chunks)
        
        if not final_context:
            return law_name, "관련 법령 조항을 찾을 수 없습니다."

        prompt = f"""
        당신은 대한민국 {law_name} 법률 전문가입니다.

        아래는 질문과 관련된 법령 조항들입니다:
        {final_context}

        이전 대화:
        {history}

        질문: {question}

        # 응답 지침
        1. 제공된 법령 조항에 기반하여 정확하게 답변해주세요.
        2. 답변에 사용한 법령 조항(조번호, 제목)을 명확히 인용해주세요.
        3. 관련된 조항이 여러 개인 경우 모두 참고하여 종합적으로 답변해주세요.
        4. 법령에 명시되지 않은 내용은 추측하지 말고, 알 수 없다고 답변해주세요.
        5. 법령 조항 번호와 제목을 정확히 인용하여 신뢰성을 높여주세요.
        """
        
        client = get_model()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        return law_name, response.text

    except Exception as e:
        return law_name, f"답변 생성 중 오류: {str(e)}"



def analyze_query(question: str) -> Tuple[str, List[str], str]:
    """사용자 쿼리 분석 및 키워드 생성 (동기 함수)"""
    preprocessor = QueryPreprocessor()
    
    # 1. 유사 쿼리 3개 생성 (API 호출 1회)
    similar_questions = preprocessor.generate_similar_questions(question)
    
    # 2. 원본 + 유사 쿼리를 합쳐 키워드 및 유사어 생성 (API 호출 1회)
    combined_query_text = " ".join([question] + similar_questions)
    expanded_keywords = preprocessor.extract_keywords_and_synonyms(combined_query_text)
    
    return question, similar_questions, expanded_keywords

def get_head_agent_response_stream(responses, question, history):
    """
    헤드 에이전트 통합 답변을 스트리밍으로 생성하는 제너레이터 함수
    """
    successful_responses = []
    error_messages = []

    for r in responses:
        if isinstance(r, Exception):
            error_messages.append(f"- 답변 생성 중 오류 발생: {r}")
        elif isinstance(r, tuple) and len(r) == 2:
            name, result = r
            if isinstance(result, Exception):
                error_messages.append(f"- {name} 전문가 답변 생성 오류: {result}")
            else:
                successful_responses.append((name, result))
        else:
            error_messages.append(f"- 알 수 없는 형식의 응답: {r}")

    # 성공적인 응답만 결합
    combined = "\n\n".join([f"=== {n} 전문가 답변 ===\n{r}" for n, r in successful_responses])
    
    # 오류 메시지가 있는 경우 프롬프트에 포함
    if error_messages:
        error_info = "\n".join(error_messages)
        combined += f"\n\n--- 일부 답변 생성 실패 ---\n{error_info}"

    # 모든 답변이 실패한 경우
    if not successful_responses:
        yield f"모든 법률 전문가의 답변을 가져오는 데 실패했습니다.\n{combined}"
        return

    prompt = f"""
당신은 법률 전문가로서 여러 법령 자료를 통합하여 종합적인 답변을 제공하는 전문가입니다.

{combined}

이전 대화:
{history}

질문: {question}

# 응답 지침
1. 여러 전문가 답변을 분석하고 통합하여 최종 답변을 제공합니다.
2. 제공된 법령 조항들에 기반하여 정확하게 답변해주세요.
3. 답변에 사용한 법령 조항(조번호, 제목)을 명확히 인용해주세요.
4. 관련 조항이 여러 법령에 걸쳐 있는 경우 모두 참고하여 종합적으로 답변해주세요.
5. 법령에 명시되지 않은 내용은 추측하지 말고, 알 수 없다고 답변해주세요.
6. 답변은 두괄식으로 작성하며, 결론을 먼저 제시합니다.
7. 상충되는 내용이 있는 경우 이를 명확히 구분하여 설명합니다.
8. 일부 답변 생성에 실패한 경우, 해당 사실을 언급하고 성공한 답변만으로 종합적인 결론을 내립니다.
"""
    
    try:
        client = get_model_head()
        response_stream = client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
                
    except Exception as e:
        yield f"최종 답변 생성 중 오류가 발생했습니다: {str(e)}"

# def get_head_agent_response(responses, question, history):
#     """헤드 에이전트 통합 답변 (예외 처리 기능 추가)"""
    
#     successful_responses = []
#     error_messages = []

#     for r in responses:
#         if isinstance(r, Exception):
#             # gather에서 발생한 예외 처리
#             error_messages.append(f"- 답변 생성 중 오류 발생: {r}")
#         elif isinstance(r, tuple) and len(r) == 2:
#             name, result = r
#             if isinstance(result, Exception):
#                 # get_law_agent_response_async에서 반환된 예외 처리
#                 error_messages.append(f"- {name} 전문가 답변 생성 오류: {result}")
#             else:
#                 successful_responses.append((name, result))
#         else:
#             # 예상치 못한 형식의 결과 처리
#             error_messages.append(f"- 알 수 없는 형식의 응답: {r}")

#     # 성공적인 응답만 결합
#     combined = "\n\n".join([f"=== {n} 전문가 답변 ===\n{r}" for n, r in successful_responses])
    
#     # 오류 메시지가 있는 경우 프롬프트에 포함
#     if error_messages:
#         error_info = "\n".join(error_messages)
#         combined += f"\n\n--- 일부 답변 생성 실패 ---\n{error_info}"

#     # 모든 답변이 실패한 경우
#     if not successful_responses:
#         return f"모든 법률 전문가의 답변을 가져오는 데 실패했습니다.\n{combined}"

#     prompt = f"""
# 당신은 법률 전문가로서 여러 법령 자료를 통합하여 종합적인 답변을 제공하는 전문가입니다.

# {combined}

# 이전 대화:
# {history}

# 질문: {question}

# # 응답 지침
# 1. 여러 전문가 답변을 분석하고 통합하여 최종 답변을 제공합니다.
# 2. 제공된 법령 조항들에 기반하여 정확하게 답변해주세요.
# 3. 답변에 사용한 법령 조항(조번호, 제목)을 명확히 인용해주세요.
# 4. 관련 조항이 여러 법령에 걸쳐 있는 경우 모두 참고하여 종합적으로 답변해주세요.
# 5. 법령에 명시되지 않은 내용은 추측하지 말고, 알 수 없다고 답변해주세요.
# 6. 답변은 두괄식으로 작성하며, 결론을 먼저 제시합니다.
# 7. 상충되는 내용이 있는 경우 이를 명확히 구분하여 설명합니다.
# 8. 일부 답변 생성에 실패한 경우, 해당 사실을 언급하고 성공한 답변만으로 종합적인 결론을 내립니다.
# """
#     try:
#         client = get_model_head()
#         response = client.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=prompt
#         )
#         return response.text
#     except Exception as e:
#         return f"최종 답변 생성 중 오류가 발생했습니다: {str(e)}"