"""
이미지 서비스 모듈
이미지 생성 및 처리 관련 기능
"""

from typing import Optional

from fastapi import HTTPException

from config import config
from logger import setup_logger
from services.prompt_service import sanitize_prompt_for_imagen
from services.s3_service import upload_image_to_s3
from utils.sensitive_filter import is_imagen_safety_block_error

logger = setup_logger()

# PIL import (이미지 리사이즈용)
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def resize_image_to_target(image_bytes: bytes, target_width: int, target_height: int) -> bytes:
    """
    이미지를 목표 해상도로 리사이즈

    Args:
        image_bytes: 원본 이미지 바이너리 데이터
        target_width: 목표 너비 (기본값: config.IMAGE_WIDTH)
        target_height: 목표 높이 (기본값: config.IMAGE_HEIGHT)

    Returns:
        리사이즈된 이미지의 바이너리 데이터 (PNG)
    """
    if not PIL_AVAILABLE:
        logger.warning("PIL이 설치되지 않아 리사이즈를 건너뜁니다.")
        return image_bytes

    try:
        # 바이트 데이터를 이미지로 변환
        img = Image.open(io.BytesIO(image_bytes))
        original_size = img.size

        # 목표 크기로 리사이즈 (고품질 리샘플링)
        img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # PNG 형식으로 바이트 변환
        output_buffer = io.BytesIO()
        img_resized.save(output_buffer, format='PNG', optimize=True)
        resized_bytes = output_buffer.getvalue()

        logger.info(f"이미지 리사이즈 완료: {original_size} -> ({target_width}, {target_height})")
        logger.info(f"   용량 변화: {len(image_bytes):,} bytes -> {len(resized_bytes):,} bytes")

        return resized_bytes
    except Exception as e:
        logger.warning(f"이미지 리사이즈 실패: {e}")
        return image_bytes


async def generate_image_with_api(enhanced_prompt: str) -> bytes:
    """
    이미지 생성 API를 사용하여 이미지 생성

    Args:
        enhanced_prompt: 개선된 프롬프트

    Returns:
        생성된 이미지의 바이너리 데이터 (bytes)
    """
    try:
        logger.info(f"이미지 생성 시작: {enhanced_prompt[:50]}...")

        # Google Imagen API를 사용한 이미지 생성
        try:
            from vertexai.preview.vision_models import ImageGenerationModel

            # Imagen 4 Fast 모델 초기화 (더 빠른 생성 속도)
            imagen_model = ImageGenerationModel.from_pretrained("imagen-4.0-fast-generate-001")

            logger.info("Imagen 4 Fast API로 이미지 생성 중...")

            # 이미지 생성 (16:9 비율로 720p에 적합)
            logger.debug(f"Imagen API 호출 파라미터: aspect_ratio=16:9, safety_filter=block_some, person_generation=allow_adult")
            response = imagen_model.generate_images(
                prompt=enhanced_prompt,
                number_of_images=1,
                aspect_ratio="16:9",
                safety_filter_level="block_some",
                person_generation="allow_adult",
            )

            # 생성된 이미지(들) 가져오기
            logger.debug(f"Imagen API 응답 타입: {type(response)}")
            logger.debug(f"Imagen API 응답 속성: {dir(response) if response else 'None'}")

            images = None
            if response is None:
                logger.warning("Imagen API 응답이 None입니다")
                images = []
            elif isinstance(response, (list, tuple)):
                logger.debug(f"응답이 리스트/튜플 형태: {len(response)}개 항목")
                images = list(response)
            elif hasattr(response, "images"):
                try:
                    images = list(getattr(response, "images"))
                    logger.debug(f"response.images에서 {len(images)}개 이미지 추출")
                except Exception as e:
                    logger.warning(f"response.images 접근 실패: {e}")
                    images = []
            else:
                try:
                    images = list(response)
                    logger.debug(f"응답을 리스트로 변환: {len(images)}개 항목")
                except Exception as e:
                    logger.warning(f"응답을 리스트로 변환 실패: {e}")
                    images = []

            if not images:
                logger.error(f"Imagen API 응답이 비어있음 - response 타입: {type(response)}, 프롬프트: {enhanced_prompt[:100]}")
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
            logger.debug(f"생성된 이미지 객체 타입: {type(generated_image)}")
            logger.debug(f"생성된 이미지 객체 속성: {dir(generated_image)}")

            # 이미지를 bytes로 변환
            image_bytes = getattr(generated_image, "_image_bytes", None)
            if image_bytes is None and hasattr(generated_image, "image_bytes"):
                image_bytes = getattr(generated_image, "image_bytes")

            logger.debug(f"이미지 바이트 추출 결과: type={type(image_bytes)}, is_bytes={isinstance(image_bytes, (bytes, bytearray))}")

            if not isinstance(image_bytes, (bytes, bytearray)):
                logger.error(f"이미지 바이트 변환 실패 - image_bytes 타입: {type(image_bytes)}, 값: {str(image_bytes)[:200] if image_bytes else 'None'}")
                logger.error(f"generated_image 속성: {[attr for attr in dir(generated_image) if not attr.startswith('_')]}")
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "IMAGEN_BAD_RESPONSE",
                        "message": "Imagen 응답에서 이미지 데이터를 추출할 수 없습니다. 사용자가 직접 이미지를 업로드해주세요.",
                        "action": "UPLOAD_IMAGE",
                        "provider": "imagen",
                    },
                )

            logger.info("이미지 생성 성공")
            logger.info(f"원본 이미지 데이터 크기: {len(image_bytes)} bytes")

            # 720p로 리사이즈 (config에서 설정값 사용)
            resized_image_bytes = resize_image_to_target(
                bytes(image_bytes),
                config.IMAGE_WIDTH,
                config.IMAGE_HEIGHT
            )

            return resized_image_bytes

        except ImportError:
            logger.warning("Imagen API를 사용할 수 없습니다.")
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
            logger.error(f"Imagen API 호출 중 오류 발생")
            logger.error(f"   예외 타입: {type(e).__name__}")
            logger.error(f"   예외 메시지: {str(e)}")
            logger.error(f"   프롬프트: {enhanced_prompt[:200]}")
            logger.error(f"   요청 파라미터: aspect_ratio=16:9, safety_filter=block_some, person_generation=allow_adult")

            if is_imagen_safety_block_error(e):
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
        logger.error(f"이미지 생성 실패: {e}", exc_info=True)
        raise


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
        logger.info(f"이미지 생성 시작: {enhanced_prompt[:50]}...")

        # 프롬프트 정제 (정책 우회 및 안전성 확보)
        sanitized_prompt = await sanitize_prompt_for_imagen(enhanced_prompt)
        logger.info("정제된 프롬프트로 이미지 생성 시도")

        # 이미지 생성
        image_data = await generate_image_with_api(sanitized_prompt)

        logger.info(f"생성된 이미지 데이터 크기: {len(image_data)} bytes")

        # S3에 업로드 (필수)
        if not s3_url and not (s3_bucket and s3_key):
            raise ValueError("S3 업로드 정보가 필요합니다. s3_url 또는 (s3_bucket, s3_key)를 제공해주세요.")

        logger.info("S3 업로드 시작...")
        image_url = await upload_image_to_s3(
            image_data,
            s3_url=s3_url,
            s3_bucket=s3_bucket,
            s3_key=s3_key
        )

        logger.info(f"이미지 생성 및 S3 업로드 완료: {image_url}")
        return image_url

    except Exception as e:
        logger.error(f"이미지 생성/업로드 오류: {e}")
        logger.debug(f"   프롬프트: {enhanced_prompt}")
        raise
