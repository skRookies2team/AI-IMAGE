"""
AI-IMAGE 서버
GCP Vertex AI의 Gemini 2.5 Flash를 사용하여 소설 스타일을 학습하고 이미지를 생성하는 서버

기능:
1. 소설 텍스트 학습: 소설 업로드 시 스타일과 분위기를 분석하여 저장
2. 이미지 생성: 노드별 프롬프트 + 소설 스타일을 결합하여 이미지 생성
"""

import os
import json
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime
import logging
import hashlib
import asyncio
from fastapi import Request

try:
    # Vertex AI GenerativeModel import 시도
    from vertexai.preview.generative_models import GenerativeModel
except ImportError:
    try:
        # 대체 경로 시도
        from vertexai.generative_models import GenerativeModel
    except ImportError:
        raise ImportError(
            "vertexai 패키지를 설치해주세요: pip install google-cloud-aiplatform"
        )

from google.cloud import aiplatform
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import httpx

# AWS S3 import
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

# 설정 모듈 import
from config import config

# 로깅 모듈 import 및 초기화
from logger import setup_logger
logger = setup_logger(level=config.LOG_LEVEL)

# S3 import 실패 로깅
if not S3_AVAILABLE:
    logger.warning("⚠️ boto3가 설치되지 않았습니다. S3 기능을 사용할 수 없습니다.")

# 설정 검증
config.validate()

# STYLES_DIR 생성
config.STYLES_DIR.mkdir(exist_ok=True, parents=True)
logger.info(f"📁 스타일 디렉토리: {config.STYLES_DIR.absolute()}")

# IMAGES_DIR 생성
config.IMAGES_DIR.mkdir(exist_ok=True, parents=True)
logger.info(f"📁 이미지 디렉토리: {config.IMAGES_DIR.absolute()}")

app = FastAPI(
    title="AI-IMAGE Server",
    description="GCP Vertex AI Gemini 2.5 Flash 기반 이미지 생성 서버",
    version="1.0.0"
)

# CORS 설정 (프론트엔드와 백엔드에서 접근 가능하도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== GCP Vertex AI 설정 ====================

# Vertex AI 초기화
try:
    # 서비스 계정 키 파일이 있으면 사용, 없으면 ADC(Application Default Credentials) 사용
    credentials_path = config.get_google_application_credentials()
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    
    aiplatform.init(project=config.GCP_PROJECT_ID, location=config.GCP_LOCATION)
    logger.info(f"✅ Vertex AI 초기화 완료: 프로젝트={config.GCP_PROJECT_ID}, 지역={config.GCP_LOCATION}")
except Exception as e:
    logger.warning(f"⚠️ Vertex AI 초기화 경고: {e}")
    logger.info("ADC(Application Default Credentials)를 사용합니다.")

# Gemini 모델 초기화 (지연 초기화 - 실제 사용 시점에 초기화)
_model_instance = None

def get_model():
    """모델 인스턴스 반환 (지연 초기화)"""
    global _model_instance
    if _model_instance is None:
        _model_instance = GenerativeModel(config.GEMINI_MODEL_NAME)
        logger.info(f"✅ Gemini 모델 초기화 완료: {config.GEMINI_MODEL_NAME}")
    return _model_instance

# STYLES_DIR은 config에서 관리


# ==================== Pydantic 모델 ====================

class NovelStyleRequest(BaseModel):
    """소설 스타일 학습 요청"""
    story_id: str = Field(..., description="소설 ID")
    novel_text: Optional[str] = Field(None, description="소설 전체 텍스트 (직접 제공 시)")
    title: Optional[str] = Field(None, description="소설 제목")
    # S3에서 소설 텍스트 다운로드 (novel_text가 없을 경우)
    novel_s3_url: Optional[str] = Field(None, description="소설 텍스트 S3 presigned URL (다운로드용)")
    novel_s3_bucket: Optional[str] = Field(None, description="소설 텍스트 S3 버킷 (novel_s3_url이 없을 경우)")
    novel_s3_key: Optional[str] = Field(None, description="소설 텍스트 S3 키 (novel_s3_url이 없을 경우)")
    # 썸네일 이미지 S3 업로드
    thumbnail_s3_url: Optional[str] = Field(None, description="썸네일 이미지 S3 presigned URL (업로드용)")
    thumbnail_s3_bucket: Optional[str] = Field(None, description="썸네일 이미지 S3 버킷 (thumbnail_s3_url이 없을 경우)")
    thumbnail_s3_key: Optional[str] = Field(None, description="썸네일 이미지 S3 키 (thumbnail_s3_url이 없을 경우)")


class ImageGenerationRequest(BaseModel):
    """이미지 생성 요청"""
    story_id: str = Field(..., description="소설 ID (스타일 정보 로드용)")
    user_prompt: str = Field(..., description="사용자가 입력한 이미지 프롬프트")
    context_text: Optional[str] = Field(None, description="추가 컨텍스트 텍스트 (선택사항, 프롬프트 개선에 사용)")
    # S3 업로드 정보 (필수 - 이미지는 S3에만 저장)
    s3_url: Optional[str] = Field(None, description="S3 presigned URL (업로드용)")
    s3_bucket: Optional[str] = Field(None, description="S3 버킷 (s3_url이 없을 경우)")
    s3_key: Optional[str] = Field(None, description="S3 키/경로 (s3_url이 없을 경우)")


class ImageGenerationResponse(BaseModel):
    """이미지 생성 응답"""
    image_url: str = Field(..., description="S3에 업로드된 이미지 URL")
    enhanced_prompt: str = Field(..., description="소설 스타일이 반영된 최종 프롬프트")
    story_id: str
    s3_key: Optional[str] = Field(None, description="S3에 업로드된 파일 키")


class StyleAnalysisResponse(BaseModel):
    """스타일 분석 응답"""
    story_id: str
    style_summary: str = Field(..., description="분석된 스타일 요약")
    atmosphere: str = Field(..., description="분위기 설명")
    visual_style: str = Field(..., description="시각적 스타일 설명")
    created_at: str
    thumbnail_image_url: Optional[str] = Field(None, description="생성된 썸네일 이미지 S3 URL")




# ==================== 유틸리티 함수 ====================

def get_s3_client():
    """S3 클라이언트 생성 및 반환"""
    if not S3_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="S3 기능을 사용할 수 없습니다. boto3가 설치되지 않았습니다."
        )
    
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        raise HTTPException(
            status_code=500,
            detail="AWS 자격 증명이 설정되지 않았습니다. AWS_ACCESS_KEY_ID와 AWS_SECRET_ACCESS_KEY를 설정해주세요."
        )
    
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION
        )
        return s3_client
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"S3 클라이언트 생성 실패: {str(e)}"
        )


async def sanitize_prompt_for_imagen(prompt: str) -> str:
    """
    프롬프트를 Imagen 정책에 맞게 안전하게 변환

    민감하거나 정책 위반 가능성이 있는 표현을 예술적이고 안전한 표현으로 자동 변환합니다.
    Gemini를 사용하여 지능적으로 프롬프트를 재작성합니다.

    Args:
        prompt: 원본 프롬프트

    Returns:
        정제된 안전한 프롬프트
    """
    try:
        model_instance = get_model()

        sanitization_prompt = f"""You are an expert prompt engineer specializing in converting prompts for safe image generation while preserving artistic intent.

ORIGINAL PROMPT: {prompt}

YOUR TASK: Rewrite this prompt to pass through image generation safety filters while maintaining the original artistic vision.

TRANSFORMATION RULES:
1. VIOLENCE/CONFLICT → Artistic alternatives:
   - "battle/fight/combat" → "dramatic confrontation", "intense standoff", "heroic moment"
   - "weapons/swords/guns" → "medieval artifacts", "historical equipment", "ornate objects"
   - "blood/gore/injury" → "dramatic lighting", "red accents", "weathered appearance"
   - "death/killing" → "fallen hero", "dramatic finale", "emotional climax"

2. DARK/HORROR THEMES → Atmospheric alternatives:
   - "scary/terrifying" → "mysterious", "atmospheric", "enigmatic"
   - "monster/demon" → "mythical creature", "fantasy being", "legendary entity"
   - "evil/sinister" → "shadowy", "dramatic", "powerful presence"

3. SENSITIVE CONTENT → Neutral alternatives:
   - Any suggestive content → focus on "elegant", "graceful", "dignified" poses
   - Controversial themes → abstract or symbolic representation

4. STYLE ENHANCEMENT (always add these):
   - Add: "digital art", "concept art", "professional illustration"
   - Add: "highly detailed", "cinematic lighting", "masterpiece quality"
   - Add appropriate art style: "fantasy art style", "dramatic composition"

5. STRUCTURE:
   - Start with the main subject
   - Add environment/setting details
   - Include lighting and mood
   - End with style/quality keywords
   - Keep between 60-120 words

OUTPUT: Write ONLY the transformed English prompt. No explanations, no quotes, no prefixes.

TRANSFORMED PROMPT:"""

        response = model_instance.generate_content(sanitization_prompt)
        sanitized = response.text.strip()

        # 따옴표로 감싸져 있으면 제거
        if sanitized.startswith('"') and sanitized.endswith('"'):
            sanitized = sanitized[1:-1]
        if sanitized.startswith("'") and sanitized.endswith("'"):
            sanitized = sanitized[1:-1]

        # 프롬프트가 너무 짧거나 비어있으면 원본 사용
        if len(sanitized) < 10:
            logger.warning(f"⚠️ 프롬프트 정제 결과가 너무 짧습니다. 원본 사용: {prompt}")
            return prompt

        logger.info("🔄 프롬프트 정제 완료")
        logger.info(f"   원본: {prompt[:100]}...")
        logger.info(f"   정제: {sanitized[:100]}...")

        return sanitized

    except Exception as e:
        logger.warning(f"⚠️ 프롬프트 정제 중 오류 발생: {e}")
        logger.info("   원본 프롬프트를 그대로 사용합니다.")
        return prompt


def _is_imagen_safety_block_error(err: Exception) -> bool:
    """Imagen 안전 필터/정책 차단으로 보이는 에러인지 간단 휴리스틱으로 판별"""
    msg = str(err).upper()
    keywords = [
        "SENSITIVE",
        "SAFETY",
        "BLOCKED",
        "FILTER",
        "VIOLATION",
        "CONTENT",
        "POLICY",
    ]
    return any(k in msg for k in keywords)


async def generate_image_with_api(enhanced_prompt: str) -> bytes:
    """
    이미지 생성 API를 사용하여 이미지 생성

    Args:
        enhanced_prompt: 개선된 프롬프트

    Returns:
        생성된 이미지의 바이너리 데이터 (bytes)
    """
    try:
        logger.info(f"🎨 이미지 생성 시작: {enhanced_prompt[:50]}...")

        # Google Imagen API를 사용한 이미지 생성
        try:
            from vertexai.preview.vision_models import ImageGenerationModel

            # Imagen 모델 초기화
            imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")

            logger.info("🖼️ Imagen API로 이미지 생성 중... (단일 시도)")

            # 이미지 생성 (1024x1024)
            response = imagen_model.generate_images(
                prompt=enhanced_prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_some",
                person_generation="allow_adult",
            )

            # 생성된 이미지(들) 가져오기
            images = None
            if response is None:
                images = []
            elif isinstance(response, (list, tuple)):
                images = list(response)
            elif hasattr(response, "images"):
                # SDK 버전에 따라 Response 객체에 images 필드가 있을 수 있음
                try:
                    images = list(getattr(response, "images"))
                except Exception:
                    images = []
            else:
                # 혹시 iterable이면 리스트로 강제 변환 시도
                try:
                    images = list(response)  # type: ignore[arg-type]
                except Exception:
                    images = []

            if not images:
                # 안전 필터/정책 차단 또는 내부 오류로 0장 반환될 수 있음
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "IMAGEN_BLOCKED",
                        "message": "이미지 생성이 정책(안전 필터)로 차단되었거나 결과가 비어있습니다. 사용자가 직접 이미지를 업로드해주세요.",
                        "action": "UPLOAD_IMAGE",
                        "provider": "imagen",
                    },
                )

            generated_image = images[0]

            # 이미지를 bytes로 변환 (SDK 내부 구현에 따라 속성명이 다를 수 있어 안전하게 처리)
            image_bytes = getattr(generated_image, "_image_bytes", None)
            if image_bytes is None and hasattr(generated_image, "image_bytes"):
                image_bytes = getattr(generated_image, "image_bytes")

            if not isinstance(image_bytes, (bytes, bytearray)):
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "IMAGEN_BAD_RESPONSE",
                        "message": "Imagen 응답에서 이미지 데이터를 추출할 수 없습니다. 사용자가 직접 이미지를 업로드해주세요.",
                        "action": "UPLOAD_IMAGE",
                        "provider": "imagen",
                    },
                )

            logger.info("✅ 이미지 생성 성공")
            logger.info(f"📦 생성된 이미지 데이터 크기: {len(image_bytes)} bytes")
            return bytes(image_bytes)

        except ImportError:
            logger.warning("⚠️ Imagen API를 사용할 수 없습니다.")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "IMAGEN_UNAVAILABLE",
                    "message": "Imagen 서비스를 사용할 수 없습니다. 사용자가 직접 이미지를 업로드해주세요.",
                    "action": "UPLOAD_IMAGE",
                    "provider": "imagen",
                },
            )
        except Exception as e:
            logger.warning(f"⚠️ Imagen API 호출 중 오류: {e}")
            if _is_imagen_safety_block_error(e):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "IMAGEN_BLOCKED",
                        "message": "이미지 생성이 정책(안전 필터)로 차단되었습니다(SENSITIVE). 사용자가 직접 이미지를 업로드해주세요.",
                        "action": "UPLOAD_IMAGE",
                        "provider": "imagen",
                    },
                )
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "IMAGEN_FAILED",
                    "message": "이미지 생성에 실패했습니다. 사용자가 직접 이미지를 업로드해주세요.",
                    "action": "UPLOAD_IMAGE",
                    "provider": "imagen",
                },
            )
    except Exception as e:
        logger.error(f"❌ 이미지 생성 실패: {e}", exc_info=True)
        raise


async def download_text_from_s3(
    s3_url: Optional[str] = None,
    s3_bucket: Optional[str] = None,
    s3_key: Optional[str] = None
) -> str:
    """
    S3에서 텍스트 파일을 다운로드
    
    Args:
        s3_url: S3 presigned URL (다운로드용)
        s3_bucket: S3 버킷 이름 (s3_url이 없을 경우)
        s3_key: S3 키/경로 (s3_url이 없을 경우)
    
    Returns:
        다운로드한 텍스트 내용
    """
    if s3_url:
        # Presigned URL을 사용한 다운로드
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(s3_url, timeout=30.0)
                response.raise_for_status()
                
                # 텍스트 인코딩 처리
                content_type = response.headers.get('content-type', '')
                if 'charset' in content_type:
                    encoding = content_type.split('charset=')[1].split(';')[0].strip()
                    try:
                        text = response.content.decode(encoding)
                    except:
                        # 지정된 인코딩 실패 시 UTF-8 시도
                        text = response.content.decode('utf-8', errors='ignore')
                else:
                    # 기본적으로 UTF-8 시도, 실패하면 cp949 시도
                    try:
                        text = response.content.decode('utf-8')
                    except UnicodeDecodeError:
                        text = response.content.decode('cp949', errors='ignore')
                
                return text
        except Exception as e:
            raise Exception(f"S3 presigned URL 다운로드 실패: {str(e)}")
    
    elif s3_bucket and s3_key:
        # boto3를 사용한 직접 다운로드
        try:
            s3_client = get_s3_client()
            response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
            
            # 텍스트 인코딩 처리
            content = response['Body'].read()
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                text = content.decode('cp949', errors='ignore')
            
            return text
        except Exception as e:
            raise Exception(f"S3 다운로드 실패: {str(e)}")
    
    else:
        raise ValueError("S3 다운로드를 위해 s3_url 또는 (s3_bucket, s3_key)가 필요합니다.")


async def upload_image_to_s3(
    image_data: bytes,
    s3_url: Optional[str] = None,
    s3_bucket: Optional[str] = None,
    s3_key: Optional[str] = None
) -> str:
    """
    이미지를 S3에 업로드
    
    Args:
        image_data: 업로드할 이미지 바이너리 데이터
        s3_url: S3 presigned URL (이 경우 PUT 요청으로 업로드)
        s3_bucket: S3 버킷 이름 (s3_url이 없을 경우)
        s3_key: S3 키/경로 (s3_url이 없을 경우)
    
    Returns:
        업로드된 이미지의 URL
    """
    if s3_url:
        # Presigned URL을 사용한 업로드
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    s3_url,
                    content=image_data,
                    headers={"Content-Type": "image/png"}
                )
                response.raise_for_status()
            
            # Presigned URL에서 실제 URL 추출 (쿼리 파라미터 제거)
            actual_url = s3_url.split('?')[0]
            return actual_url
        except Exception as e:
            raise Exception(f"S3 presigned URL 업로드 실패: {str(e)}")
    
    elif s3_bucket and s3_key:
        # boto3를 사용한 직접 업로드
        try:
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=image_data,
                ContentType='image/png'
            )
            
            # S3 URL 생성
            if s3_key.startswith('https://') or s3_key.startswith('http://'):
                return s3_key
            else:
                return f"https://{s3_bucket}.s3.{config.AWS_REGION}.amazonaws.com/{s3_key}"
        except Exception as e:
            raise Exception(f"S3 업로드 실패: {str(e)}")
    
    elif config.S3_BUCKET_NAME:
        # 기본 버킷 사용 (s3_key가 자동 생성됨)
        if not s3_key:
            # 자동 키 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            s3_key = f"generated-images/{timestamp}_{hash(str(image_data)) % 10000}.png"
        
        return await upload_image_to_s3(image_data, s3_bucket=config.S3_BUCKET_NAME, s3_key=s3_key)
    
    else:
        raise ValueError("S3 업로드를 위해 s3_url 또는 (s3_bucket, s3_key) 또는 S3_BUCKET_NAME 환경 변수가 필요합니다.")


async def upload_image_to_s3_presigned_url(
    image_bytes: bytes,
    presigned_url: str,
    content_type: str = "image/png"
) -> bool:
    """
    S3 presigned URL을 사용하여 이미지를 업로드
    
    Args:
        image_bytes: 업로드할 이미지 바이트 데이터
        presigned_url: S3 presigned URL
        content_type: 이미지 MIME 타입
    
    Returns:
        업로드 성공 여부
    """
    try:
        import httpx
        
        logger.info(f"📤 S3 presigned URL로 이미지 업로드 시작... ({len(image_bytes)} bytes)")
        
        # presigned URL로 PUT 요청
        async with httpx.AsyncClient() as client:
            response = await client.put(
                presigned_url,
                content=image_bytes,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(image_bytes))
                },
                timeout=30.0
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ S3 업로드 성공: {response.status_code}")
                return True
            else:
                logger.error(f"❌ S3 업로드 실패: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"❌ S3 업로드 중 오류 발생: {str(e)}", exc_info=True)
        return False


def get_style_file_path(story_id: str) -> Path:
    """스타일 파일 경로 반환"""
    return config.STYLES_DIR / f"{story_id}.json"


def save_novel_style(story_id: str, style_data: Dict):
    """소설 스타일을 파일로 저장"""
    style_file = get_style_file_path(story_id)
    style_data['story_id'] = story_id
    style_data['updated_at'] = datetime.now().isoformat()
    
    with open(style_file, 'w', encoding='utf-8') as f:
        json.dump(style_data, f, ensure_ascii=False, indent=2)
    
    return style_file


def load_novel_style(story_id: str) -> Optional[Dict]:
    """소설 스타일 로드"""
    style_file = get_style_file_path(story_id)
    if not style_file.exists():
        return None
    
    with open(style_file, 'r', encoding='utf-8') as f:
        return json.load(f)


async def analyze_novel_style(novel_text: str, title: Optional[str] = None) -> Dict:
    """
    Gemini를 사용하여 소설의 스타일과 분위기를 분석

    Returns:
        분석된 스타일 정보 (분위기, 시각적 스타일, 이미지 생성용 키워드 등)
    """
    # 소설 텍스트의 일부만 사용 (너무 길면 토큰 제한)
    text_sample = novel_text[:5000] if len(novel_text) > 5000 else novel_text

    prompt = f"""Analyze the style and atmosphere of the following novel for image generation purposes.

NOVEL TITLE: {title if title else "Untitled"}

NOVEL CONTENT (excerpt):
{text_sample}

Provide a JSON response with the following structure. All values should be optimized for AI image generation:

{{
    "style_summary": "2-3 sentences describing the overall style and tone of the novel",
    "atmosphere": "Atmosphere description in English (e.g., 'dark and mysterious', 'bright and cheerful', 'melancholic and poetic')",
    "visual_style": "Visual art style for image generation (e.g., 'dark fantasy art', 'realistic illustration', 'anime style', 'oil painting style')",
    "key_themes": ["theme1", "theme2", "theme3"],
    "color_palette": "Color palette description (e.g., 'cool blue tones with purple accents', 'warm golden hues', 'high contrast dark and light')",
    "lighting_style": "Lighting style for images (e.g., 'dramatic chiaroscuro', 'soft diffused light', 'moonlit ambiance', 'golden hour warmth')",
    "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}

IMPORTANT for visual_keywords:
- Provide 5-8 English keywords that can be directly used in image generation prompts
- Include: art style, mood, setting type, time of day, weather/atmosphere
- Examples: "fantasy", "medieval", "misty forest", "twilight", "ethereal glow", "gothic architecture"
- These keywords should be safe for image generation (avoid violent or sensitive terms)

Respond ONLY with valid JSON, no additional text or markdown."""

    try:
        # Vertex AI GenerativeModel 사용
        model_instance = get_model()
        response = model_instance.generate_content(prompt)

        # 응답 텍스트 추출
        if hasattr(response, 'text'):
            response_text = response.text.strip()
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            response_text = response.candidates[0].content.parts[0].text.strip()
        else:
            raise ValueError("응답에서 텍스트를 추출할 수 없습니다.")

        # JSON 응답 파싱
        # JSON 코드 블록이 있으면 제거
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        style_data = json.loads(response_text)

        # 필수 필드 확인 및 기본값 설정
        if 'lighting_style' not in style_data:
            style_data['lighting_style'] = 'natural lighting'
        if 'visual_keywords' not in style_data:
            style_data['visual_keywords'] = []

        return style_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {e}")
        logger.debug(f"응답 텍스트: {response_text[:200]}")
        # 기본값 반환
        return {
            "style_summary": "Unable to analyze novel style.",
            "atmosphere": "general",
            "visual_style": "realistic illustration",
            "key_themes": [],
            "color_palette": "natural colors",
            "lighting_style": "natural lighting",
            "visual_keywords": ["illustration", "detailed", "atmospheric"]
        }
    except Exception as e:
        logger.error(f"스타일 분석 오류: {e}", exc_info=True)
        # 기본값 반환
        return {
            "style_summary": "Unable to analyze novel style.",
            "atmosphere": "general",
            "visual_style": "realistic illustration",
            "key_themes": [],
            "color_palette": "natural colors",
            "lighting_style": "natural lighting",
            "visual_keywords": ["illustration", "detailed", "atmospheric"]
        }


async def generate_thumbnail_prompt(
    title: Optional[str],
    novel_style: Dict,
    novel_text_sample: Optional[str] = None
) -> str:
    """
    소설 썸네일 이미지를 위한 프롬프트 생성
    """
    # 시각적 키워드 추출
    visual_keywords = novel_style.get('visual_keywords', [])
    visual_keywords_str = ", ".join(visual_keywords) if visual_keywords else ""

    style_context = f"""
- Atmosphere: {novel_style.get('atmosphere', 'general')}
- Visual Style: {novel_style.get('visual_style', 'realistic style')}
- Color Palette: {novel_style.get('color_palette', 'natural colors')}
- Key Themes: {', '.join(novel_style.get('key_themes', [])[:3])}
- Lighting: {novel_style.get('lighting_style', 'natural lighting')}
- Visual Keywords: {visual_keywords_str}
"""

    text_sample = f"\nNovel excerpt: {novel_text_sample[:300]}" if novel_text_sample else ""

    prompt = f"""You are an expert book cover designer and image prompt engineer.

NOVEL TITLE: {title if title else "Untitled"}

NOVEL STYLE INFORMATION:
{style_context}{text_sample}

CREATE a book cover/thumbnail image prompt that:

1. COMPOSITION:
   - Strong focal point that captures the novel's essence
   - Suitable for vertical format (book cover style)
   - Clear visual hierarchy with a central element
   - Leave space for potential title overlay (but don't include text)

2. VISUAL ELEMENTS:
   - Incorporate symbolic elements from the novel's themes
   - Use the specified color palette and atmosphere
   - Add atmospheric effects (mist, light rays, particles) if appropriate

3. STYLE REQUIREMENTS:
   - Art style matching the novel's genre
   - Professional book cover quality
   - Must include: "book cover art", "professional illustration"
   - Add: "highly detailed", "cinematic composition", "dramatic lighting"

4. SAFETY COMPLIANCE:
   - Use artistic/symbolic representation for any dramatic themes
   - Focus on atmosphere and mood rather than explicit content
   - Transform any potentially sensitive elements into abstract visuals

5. FORMAT:
   - Write in English only
   - Keep between 80-120 words
   - Do NOT include any text/typography in the image description

OUTPUT: Write ONLY the prompt. No explanations, no quotes.

THUMBNAIL PROMPT:"""

    try:
        model_instance = get_model()
        response = model_instance.generate_content(prompt)

        if hasattr(response, 'text'):
            thumbnail_prompt = response.text.strip()
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            thumbnail_prompt = response.candidates[0].content.parts[0].text.strip()
        else:
            raise ValueError("응답에서 텍스트를 추출할 수 없습니다.")

        # 따옴표로 감싸져 있으면 제거
        if thumbnail_prompt.startswith('"') and thumbnail_prompt.endswith('"'):
            thumbnail_prompt = thumbnail_prompt[1:-1]
        if thumbnail_prompt.startswith("'") and thumbnail_prompt.endswith("'"):
            thumbnail_prompt = thumbnail_prompt[1:-1]

        return thumbnail_prompt
    except Exception as e:
        logger.error(f"썸네일 프롬프트 생성 오류: {e}", exc_info=True)
        # 기본 프롬프트 반환
        return f"Book cover illustration for '{title or 'a novel'}', {novel_style.get('visual_style', 'realistic style')}, {novel_style.get('atmosphere', 'atmospheric')} mood, {novel_style.get('color_palette', 'natural colors')}, professional artwork, highly detailed, cinematic lighting, dramatic composition"


async def generate_enhanced_prompt(
    user_prompt: str,
    novel_style: Dict,
    context_text: Optional[str] = None
) -> str:
    """
    사용자 프롬프트와 소설 스타일을 결합하여 최종 이미지 생성 프롬프트 생성
    """
    # 스타일 정보에서 시각적 키워드 추출
    visual_keywords = novel_style.get('visual_keywords', [])
    visual_keywords_str = ", ".join(visual_keywords) if visual_keywords else ""

    style_context = f"""
- Atmosphere: {novel_style.get('atmosphere', 'general')}
- Visual Style: {novel_style.get('visual_style', 'realistic style')}
- Color Palette: {novel_style.get('color_palette', 'natural colors')}
- Lighting: {novel_style.get('lighting_style', 'natural lighting')}
- Visual Keywords: {visual_keywords_str}
"""

    context = f"\nAdditional Context: {context_text[:500]}" if context_text else ""

    prompt = f"""You are an expert image generation prompt engineer. Create a high-quality image generation prompt.

USER'S REQUEST: {user_prompt}

NOVEL STYLE INFORMATION:
{style_context}{context}

REQUIREMENTS:
1. Maintain the user's original intent and subject matter
2. Naturally incorporate the novel's atmosphere and visual style
3. Structure the prompt as follows:
   - Main subject with specific details
   - Environment/background description
   - Lighting and mood (use novel's atmosphere)
   - Art style and quality keywords

4. MUST include these quality enhancers:
   - Art style: "digital painting", "concept art", or "illustration"
   - Quality: "highly detailed", "professional artwork", "masterpiece"
   - Technical: "8k resolution", "sharp focus", "intricate details"

5. Use cinematic/artistic language:
   - Instead of "dark" → "dramatic shadows", "low-key lighting"
   - Instead of "scary" → "mysterious atmosphere", "enigmatic mood"
   - Instead of "fighting" → "dynamic pose", "intense moment"

6. Keep the prompt between 80-150 words
7. Write in English only
8. Do NOT include any negative words or things to avoid

OUTPUT: Write ONLY the enhanced prompt. No explanations, no quotes, no prefixes.

ENHANCED PROMPT:"""

    try:
        # Vertex AI GenerativeModel 사용
        model_instance = get_model()
        response = model_instance.generate_content(prompt)

        # 응답 텍스트 추출
        if hasattr(response, 'text'):
            enhanced_prompt = response.text.strip()
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            enhanced_prompt = response.candidates[0].content.parts[0].text.strip()
        else:
            raise ValueError("응답에서 텍스트를 추출할 수 없습니다.")

        # 따옴표로 감싸져 있으면 제거
        if enhanced_prompt.startswith('"') and enhanced_prompt.endswith('"'):
            enhanced_prompt = enhanced_prompt[1:-1]
        if enhanced_prompt.startswith("'") and enhanced_prompt.endswith("'"):
            enhanced_prompt = enhanced_prompt[1:-1]

        return enhanced_prompt
    except Exception as e:
        logger.error(f"프롬프트 개선 오류: {e}", exc_info=True)
        # 오류 발생 시 사용자 프롬프트 그대로 반환
        return user_prompt


async def generate_and_upload_image(
    enhanced_prompt: str,
    s3_url: Optional[str] = None,
    s3_bucket: Optional[str] = None,
    s3_key: Optional[str] = None
) -> str:
    """
    이미지 생성 후 S3에 업로드

    Args:
        enhanced_prompt: 개선된 이미지 생성 프롬프트
        s3_url: S3 presigned URL (업로드용)
        s3_bucket: S3 버킷 (s3_url이 없을 경우)
        s3_key: S3 키/경로 (s3_url이 없을 경우)

    Returns:
        S3에 업로드된 이미지 URL
    """
    try:
        logger.info(f"🎨 이미지 생성 시작: {enhanced_prompt[:50]}...")

        # 프롬프트 정제 (정책 우회 및 안전성 확보)
        sanitized_prompt = await sanitize_prompt_for_imagen(enhanced_prompt)
        logger.info(f"🔒 정제된 프롬프트로 이미지 생성 시도")

        # 이미지 생성
        image_data = await generate_image_with_api(sanitized_prompt)
        
        logger.info(f"📦 생성된 이미지 데이터 크기: {len(image_data)} bytes")
        
        # S3에 업로드 (필수)
        if not s3_url and not (s3_bucket and s3_key):
            raise ValueError("S3 업로드 정보가 필요합니다. s3_url 또는 (s3_bucket, s3_key)를 제공해주세요.")
        
        logger.info(f"📤 S3 업로드 시작...")
        image_url = await upload_image_to_s3(
            image_data,
            s3_url=s3_url,
            s3_bucket=s3_bucket,
            s3_key=s3_key
        )
        
        logger.info(f"✅ 이미지 생성 및 S3 업로드 완료: {image_url}")
        return image_url
        
    except Exception as e:
        logger.error(f"❌ 이미지 생성/업로드 오류: {e}")
        logger.debug(f"   프롬프트: {enhanced_prompt}")
        raise


# ==================== 중복 요청 방지 ====================

# 진행 중인 요청 추적 (중복 방지용)
# 구조: {request_id: {"task": asyncio.Task, "timestamp": datetime, "s3_key": str}}
_processing_requests: Dict[str, Dict] = {}
# 요청 정리 주기 (초) - 오래된 완료된 요청 자동 정리
CLEANUP_INTERVAL = 300  # 5분

def get_request_id(story_id: str, s3_key: Optional[str] = None, user_prompt: Optional[str] = None) -> str:
    """
    요청 ID 생성 (중복 방지용)
    
    노드별 이미지 생성: 각 노드는 다른 s3_key를 가지므로 다른 request_id 생성됨 (정상)
    썸네일 생성: 같은 story_id + 같은 s3_key로 여러 번 호출되면 같은 request_id (중복 차단)
    """
    # s3_key가 있으면 그것을 기준으로 (가장 정확한 중복 방지)
    if s3_key:
        key = f"{story_id}:{s3_key}"
    elif user_prompt:
        # user_prompt 기반 (같은 프롬프트로 여러 번 호출 방지)
        key = f"{story_id}:{hashlib.md5(user_prompt.encode()).hexdigest()[:8]}"
    else:
        # 타임스탬프 기반 (항상 다른 ID)
        key = f"{story_id}:{datetime.now().isoformat()}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def cleanup_old_requests():
    """완료된 오래된 요청 정리"""
    current_time = datetime.now()
    to_remove = []
    
    for request_id, request_info in _processing_requests.items():
        task = request_info.get("task")
        timestamp = request_info.get("timestamp")
        
        # 완료된 작업이거나 5분 이상 지난 요청 제거
        if task and task.done():
            to_remove.append(request_id)
        elif timestamp and (current_time - timestamp).total_seconds() > CLEANUP_INTERVAL:
            to_remove.append(request_id)
    
    for request_id in to_remove:
        if request_id in _processing_requests:
            del _processing_requests[request_id]
            logger.debug(f"🧹 오래된 요청 정리: Request ID {request_id}")


# ==================== API 엔드포인트 ====================

@app.get("/")
async def root():
    """헬스 체크"""
    return {
        "service": "AI-IMAGE Server",
        "version": "1.0.0",
        "status": "running"
    }


@app.post("/api/v1/learn-style", response_model=StyleAnalysisResponse)
async def learn_novel_style(request: NovelStyleRequest, http_request: Request = None):
    """
    소설 텍스트를 분석하여 스타일을 학습하고 저장
    소설 썸네일 이미지를 생성하여 S3에 업로드
    
    소설 업로드 시 백엔드에서 호출할 엔드포인트
    
    novel_text를 직접 제공하거나, S3에서 다운로드할 수 있습니다:
    - novel_text: 직접 제공
    - novel_s3_url 또는 (novel_s3_bucket, novel_s3_key): S3에서 다운로드
    
    중복 요청 방지: 동일한 story_id로 이미 처리 중이면 거부합니다.
    """
    # 중복 요청 확인 (썸네일 생성 중복 방지)
    learn_request_id = get_request_id(
        story_id=request.story_id,
        s3_key=request.thumbnail_s3_key,
        user_prompt=None
    )
    
    client_ip = http_request.client.host if http_request else "unknown"
    logger.info(f"📥 [요청 수신] POST /api/v1/learn-style")
    logger.info(f"   Request ID: {learn_request_id}")
    logger.info(f"   Client IP: {client_ip}")
    logger.info(f"   Story ID: {request.story_id}")
    
    # 중복 요청 확인
    cleanup_old_requests()
    if learn_request_id in _processing_requests:
        request_info = _processing_requests[learn_request_id]
        existing_task = request_info.get("task")
        
        if existing_task and not existing_task.done():
            logger.warning(f"⚠️ [중복 요청 차단] learn-style Request ID: {learn_request_id}")
            logger.warning(f"   Story ID: {request.story_id} - 이미 처리 중인 요청입니다.")
            raise HTTPException(
                status_code=409,
                detail=f"동일한 스토리의 스타일 학습이 이미 처리 중입니다. Request ID: {learn_request_id}"
            )
    
    thumbnail_url = None
    
    try:
        # 소설 텍스트 가져오기 (직접 제공 또는 S3에서 다운로드)
        novel_text = request.novel_text
        
        # novel_text가 None이거나 빈 문자열인 경우 S3에서 다운로드 시도
        if novel_text is None or (isinstance(novel_text, str) and len(novel_text.strip()) == 0):
            # S3 정보 확인
            has_s3_url = request.novel_s3_url is not None and len(request.novel_s3_url.strip()) > 0
            has_s3_bucket_key = (
                request.novel_s3_bucket is not None and len(request.novel_s3_bucket.strip()) > 0 and
                request.novel_s3_key is not None and len(request.novel_s3_key.strip()) > 0
            )
            
            if has_s3_url or has_s3_bucket_key:
                # S3 모드: S3에서 다운로드
                logger.info(f"📥 S3 모드: 소설 텍스트 다운로드 시작 (story_id={request.story_id})")
                logger.debug(f"   S3 URL: {request.novel_s3_url[:50] if request.novel_s3_url else 'None'}...")
                logger.debug(f"   S3 Bucket/Key: {request.novel_s3_bucket}/{request.novel_s3_key if request.novel_s3_key else 'None'}")
                
                try:
                    novel_text = await download_text_from_s3(
                        s3_url=request.novel_s3_url if has_s3_url else None,
                        s3_bucket=request.novel_s3_bucket if has_s3_bucket_key else None,
                        s3_key=request.novel_s3_key if has_s3_bucket_key else None
                    )
                    logger.info(f"✅ 소설 텍스트 다운로드 완료: {len(novel_text)} 문자")
                except Exception as e:
                    logger.error(f"❌ S3 다운로드 실패: {str(e)}", exc_info=True)
                    raise HTTPException(
                        status_code=400,
                        detail=f"S3에서 소설 텍스트 다운로드 실패: {str(e)}"
                    )
            else:
                # novel_text도 없고 S3 정보도 없는 경우
                raise HTTPException(
                    status_code=400,
                    detail="novel_text 또는 S3 정보가 필요합니다. novel_text를 직접 제공하거나, novel_s3_url 또는 (novel_s3_bucket, novel_s3_key)를 제공해주세요."
                )
        else:
            # 직접 제공 모드: novel_text를 그대로 사용
            logger.info(f"📝 직접 제공 모드: novel_text 사용 (story_id={request.story_id}, 길이={len(novel_text)} 문자)")
        
        # 소설 스타일 분석
        style_data = await analyze_novel_style(novel_text, request.title)
        
        # 스타일 저장
        save_novel_style(request.story_id, style_data)
        
        # 썸네일 이미지 생성 및 S3 업로드 (S3 정보가 제공된 경우)
        if request.thumbnail_s3_url or (request.thumbnail_s3_bucket and request.thumbnail_s3_key):
            try:
                logger.info(f"📸 소설 썸네일 이미지 생성 시작: story_id={request.story_id}")
                
                # 썸네일 프롬프트 생성
                thumbnail_prompt = await generate_thumbnail_prompt(
                    request.title,
                    style_data,
                    request.novel_text[:500] if request.novel_text else None
                )
                
                logger.debug(f"🎨 썸네일 프롬프트: {thumbnail_prompt[:100]}...")

                # 프롬프트 정제 (정책 우회 및 안전성 확보)
                sanitized_thumbnail_prompt = await sanitize_prompt_for_imagen(thumbnail_prompt)
                logger.info(f"🔒 정제된 썸네일 프롬프트로 이미지 생성 시도")

                # 이미지 생성
                image_data = await generate_image_with_api(sanitized_thumbnail_prompt)
                
                # S3에 업로드
                thumbnail_url = await upload_image_to_s3(
                    image_data,
                    s3_url=request.thumbnail_s3_url,
                    s3_bucket=request.thumbnail_s3_bucket,
                    s3_key=request.thumbnail_s3_key or f"thumbnails/{request.story_id}/thumbnail.png"
                )
                
                logger.info(f"✅ 썸네일 이미지 S3 업로드 완료: {thumbnail_url}")
            except Exception as e:
                logger.warning(f"⚠️ 썸네일 이미지 생성/업로드 실패 (스타일 학습은 성공): {str(e)}", exc_info=True)
                # 썸네일 생성 실패해도 스타일 학습은 성공으로 처리
        
        return StyleAnalysisResponse(
            story_id=request.story_id,
            style_summary=style_data.get('style_summary', ''),
            atmosphere=style_data.get('atmosphere', ''),
            visual_style=style_data.get('visual_style', ''),
            created_at=datetime.now().isoformat(),
            thumbnail_image_url=thumbnail_url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스타일 학습 실패: {str(e)}")


@app.get("/api/v1/style/{story_id}", response_model=StyleAnalysisResponse)
async def get_novel_style(story_id: str):
    """저장된 소설 스타일 조회"""
    style_data = load_novel_style(story_id)
    if not style_data:
        raise HTTPException(status_code=404, detail=f"스토리 ID {story_id}의 스타일 정보를 찾을 수 없습니다.")
    
    return StyleAnalysisResponse(
        story_id=story_id,
        style_summary=style_data.get('style_summary', ''),
        atmosphere=style_data.get('atmosphere', ''),
        visual_style=style_data.get('visual_style', ''),
        created_at=style_data.get('updated_at', datetime.now().isoformat())
    )


@app.post("/api/v1/generate-image", response_model=ImageGenerationResponse)
async def generate_image(request: ImageGenerationRequest, http_request: Request = None):
    """
    이미지 생성 및 S3 업로드
    
    사용자가 입력한 프롬프트와 소설 스타일을 결합하여 이미지 생성 후 S3에 업로드합니다.
    노드 정보는 백엔드에서 관리하므로, AI 서버는 이미지 생성과 S3 업로드만 담당합니다.
    
    중복 요청 방지: 동일한 story_id + s3_key 조합의 요청이 이미 처리 중이면 거부합니다.
    """
    # 요청 ID 생성 (중복 방지용)
    request_id = get_request_id(
        story_id=request.story_id,
        s3_key=request.s3_key,
        user_prompt=request.user_prompt
    )
    
    # 클라이언트 IP 및 요청 정보 로깅
    client_ip = http_request.client.host if http_request else "unknown"
    logger.info(f"📥 [요청 수신] POST /api/v1/generate-image")
    logger.info(f"   Request ID: {request_id}")
    logger.info(f"   Client IP: {client_ip}")
    logger.info(f"   Story ID: {request.story_id}")
    logger.info(f"   S3 Key: {request.s3_key}")
    logger.info(f"   User Prompt: {request.user_prompt[:50]}..." if request.user_prompt else "   User Prompt: None")
    
    # 오래된 요청 정리 (주기적으로)
    cleanup_old_requests()
    
    # 중복 요청 확인
    if request_id in _processing_requests:
        request_info = _processing_requests[request_id]
        existing_task = request_info.get("task")
        
        if existing_task and not existing_task.done():
            logger.warning(f"⚠️ [중복 요청 차단] Request ID: {request_id}")
            logger.warning(f"   Story ID: {request.story_id}, S3 Key: {request.s3_key}")
            logger.warning(f"   이미 처리 중인 동일한 요청입니다. (같은 story_id + s3_key 조합)")
            raise HTTPException(
                status_code=409,
                detail=f"동일한 요청이 이미 처리 중입니다. Request ID: {request_id}. "
                       f"노드별 이미지 생성 시에는 각 노드마다 다른 s3_key를 사용해야 합니다."
            )
        else:
            # 완료된 작업이면 제거
            del _processing_requests[request_id]
            logger.debug(f"🧹 완료된 요청 제거: Request ID {request_id}")
    
    async def process_image_generation():
        """실제 이미지 생성 처리"""
        try:
            # 소설 스타일 로드
            novel_style = load_novel_style(request.story_id)
            if not novel_style:
                raise HTTPException(
                    status_code=404,
                    detail=f"스토리 ID {request.story_id}의 스타일 정보가 없습니다. 먼저 스타일을 학습해주세요."
                )
            
            logger.info(f"🎯 [처리 시작] Request ID: {request_id}")
            
            # 프롬프트 개선
            enhanced_prompt = await generate_enhanced_prompt(
                request.user_prompt,
                novel_style,
                request.context_text
            )
            
            logger.debug(f"   개선된 프롬프트: {enhanced_prompt[:100]}...")
            
            # 이미지 생성 및 S3 업로드
            image_url = await generate_and_upload_image(
                enhanced_prompt,
                s3_url=request.s3_url,
                s3_bucket=request.s3_bucket,
                s3_key=request.s3_key
            )
            
            logger.info(f"✅ [처리 완료] Request ID: {request_id} - 이미지 URL: {image_url}")
            
            return ImageGenerationResponse(
                image_url=image_url,
                enhanced_prompt=enhanced_prompt,
                story_id=request.story_id,
                s3_key=request.s3_key
            )
        except HTTPException:
            raise
        except ValueError as e:
            logger.error(f"❌ [처리 실패] Request ID: {request_id} - ValueError: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"❌ [처리 실패] Request ID: {request_id} - Exception: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"이미지 생성 실패: {str(e)}")
        finally:
            # 처리 완료 후 요청 ID 제거 (나중에 정리되도록 남겨둠)
            # cleanup_old_requests()에서 정리됨
            pass
    
    # 비동기 작업 생성 및 추적
    task = asyncio.create_task(process_image_generation())
    _processing_requests[request_id] = {
        "task": task,
        "timestamp": datetime.now(),
        "s3_key": request.s3_key,
        "story_id": request.story_id
    }
    
    try:
        result = await task
        return result
    except Exception as e:
        # 에러 발생 시에도 요청 ID 제거
        if request_id in _processing_requests:
            del _processing_requests[request_id]
        raise


@app.delete("/api/v1/style/{story_id}")
async def delete_novel_style(story_id: str):
    """소설 스타일 삭제"""
    style_file = get_style_file_path(story_id)
    if style_file.exists():
        style_file.unlink()
        return {"message": f"스토리 ID {story_id}의 스타일이 삭제되었습니다."}
    else:
        raise HTTPException(status_code=404, detail=f"스토리 ID {story_id}의 스타일 정보를 찾을 수 없습니다.")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 AI-IMAGE 서버 시작: {config.HOST}:{config.PORT}")
    logger.info(f"📋 설정 정보:\n{config}")
    logger.info(f"📝 로그 레벨: {config.LOG_LEVEL}")
    logger.info(f"📁 로그 파일: logs/ai-image-{datetime.now().strftime('%Y%m%d')}.log")
    uvicorn.run(app, host=config.HOST, port=config.PORT)

