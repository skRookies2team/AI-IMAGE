"""
설정 관리 모듈
모든 설정값을 환경 변수에서 로드하여 관리
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class Config:
    """애플리케이션 설정 클래스"""
    
    # GCP 설정
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    GCP_LOCATION: str = os.getenv("GCP_LOCATION", "us-central1")
    GEMINI_MODEL_NAME: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash-exp")
    GCP_SERVICE_ACCOUNT_KEY_PATH: str = os.getenv("GCP_SERVICE_ACCOUNT_KEY_PATH", "")
    
    # 서버 설정
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8001"))
    
    # 디렉토리 설정
    STYLES_DIR: Path = Path(os.getenv("STYLES_DIR", "styles"))
    IMAGES_DIR: Path = Path(os.getenv("IMAGES_DIR", "images"))
    
    # 이미지 생성 API 설정
    IMAGE_GENERATION_API: str = os.getenv("IMAGE_GENERATION_API", "imagen")  # "imagen", "dalle", "placeholder"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # AWS S3 설정
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-northeast-2")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
    
    # 로깅 설정
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    @classmethod
    def validate(cls) -> None:
        """필수 설정값 검증"""
        if not cls.GCP_PROJECT_ID:
            raise ValueError("GCP_PROJECT_ID 환경 변수가 설정되지 않았습니다.")
    
    @classmethod
    def get_google_application_credentials(cls) -> str | None:
        """GOOGLE_APPLICATION_CREDENTIALS 환경 변수 반환 또는 설정"""
        if cls.GCP_SERVICE_ACCOUNT_KEY_PATH:
            key_path = Path(cls.GCP_SERVICE_ACCOUNT_KEY_PATH)
            if key_path.exists():
                return str(key_path.absolute())
        return os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    @classmethod
    def __repr__(cls) -> str:
        """설정 정보 문자열 표현"""
        return f"""Config(
    GCP_PROJECT_ID={cls.GCP_PROJECT_ID},
    GCP_LOCATION={cls.GCP_LOCATION},
    GEMINI_MODEL_NAME={cls.GEMINI_MODEL_NAME},
    HOST={cls.HOST},
    PORT={cls.PORT},
    STYLES_DIR={cls.STYLES_DIR},
    IMAGES_DIR={cls.IMAGES_DIR},
    IMAGE_GENERATION_API={cls.IMAGE_GENERATION_API},
    S3_BUCKET_NAME={cls.S3_BUCKET_NAME},
    AWS_REGION={cls.AWS_REGION},
    LOG_LEVEL={cls.LOG_LEVEL}
)"""


# 전역 설정 인스턴스
config = Config()


