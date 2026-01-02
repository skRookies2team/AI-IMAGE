"""
Gemini 서비스 모듈
GCP Vertex AI Gemini 모델 초기화 및 관리
"""

import os

try:
    from vertexai.preview.generative_models import GenerativeModel
except ImportError:
    try:
        from vertexai.generative_models import GenerativeModel
    except ImportError:
        raise ImportError(
            "vertexai 패키지를 설치해주세요: pip install google-cloud-aiplatform"
        )

from google.cloud import aiplatform

from config import config
from logger import setup_logger

logger = setup_logger()

# Gemini 모델 인스턴스 (지연 초기화)
_model_instance = None


def initialize_vertex_ai():
    """Vertex AI 초기화"""
    try:
        # 서비스 계정 키 파일이 있으면 사용, 없으면 ADC 사용
        credentials_path = config.get_google_application_credentials()
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        aiplatform.init(project=config.GCP_PROJECT_ID, location=config.GCP_LOCATION)
        logger.info(
            f"Vertex AI 초기화 완료: 프로젝트={config.GCP_PROJECT_ID}, 지역={config.GCP_LOCATION}"
        )
    except Exception as e:
        logger.warning(f"Vertex AI 초기화 경고: {e}")
        logger.info("ADC(Application Default Credentials)를 사용합니다.")


def get_model():
    """모델 인스턴스 반환 (지연 초기화)"""
    global _model_instance
    if _model_instance is None:
        _model_instance = GenerativeModel(config.GEMINI_MODEL_NAME)
        logger.info(f"Gemini 모델 초기화 완료: {config.GEMINI_MODEL_NAME}")
    return _model_instance
