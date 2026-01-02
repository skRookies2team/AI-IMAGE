"""
AI-IMAGE 서버
GCP Vertex AI의 Gemini 2.5 Flash를 사용하여 소설 스타일을 학습하고 이미지를 생성하는 서버

기능:
1. 소설 텍스트 학습: 소설 업로드 시 스타일과 분위기를 분석하여 저장
2. 이미지 생성: 노드별 프롬프트 + 소설 스타일을 결합하여 이미지 생성
"""

from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config
from logger import setup_logger
from services.gemini_service import initialize_vertex_ai
from routers import api_v1_router

# 로거 초기화
logger = setup_logger(level=config.LOG_LEVEL)

# 설정 검증
config.validate()

# 디렉토리 생성
config.STYLES_DIR.mkdir(exist_ok=True, parents=True)
logger.info(f"스타일 디렉토리: {config.STYLES_DIR.absolute()}")

config.IMAGES_DIR.mkdir(exist_ok=True, parents=True)
logger.info(f"이미지 디렉토리: {config.IMAGES_DIR.absolute()}")

# Vertex AI 초기화
initialize_vertex_ai()

# FastAPI 앱 생성
app = FastAPI(
    title="AI-IMAGE Server",
    description="GCP Vertex AI Gemini 2.5 Flash 기반 이미지 생성 서버",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(api_v1_router, prefix="/api/v1", tags=["API v1"])


@app.get("/")
async def root():
    """헬스 체크"""
    return {
        "service": "AI-IMAGE Server",
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    logger.info(f"AI-IMAGE 서버 시작: {config.HOST}:{config.PORT}")
    logger.info(f"설정 정보:\n{config}")
    logger.info(f"로그 레벨: {config.LOG_LEVEL}")
    logger.info(f"로그 파일: logs/ai-image-{datetime.now().strftime('%Y%m%d')}.log")
    uvicorn.run(app, host=config.HOST, port=config.PORT)
