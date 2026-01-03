"""
API v1 라우터
이미지 생성 및 스타일 학습 관련 엔드포인트
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from config import config
from logger import setup_logger
from models.schemas import (
    NovelStyleRequest,
    ImageGenerationRequest,
    ImageGenerationResponse,
    StyleAnalysisResponse,
)
from services.s3_service import download_text_from_s3, upload_image_to_s3
from services.style_service import (
    save_novel_style,
    load_novel_style,
    analyze_novel_style,
    generate_thumbnail_prompt,
    generate_enhanced_prompt,
    get_style_file_path,
)
from services.image_service import generate_image_with_api, generate_and_upload_image
from services.prompt_service import sanitize_prompt_for_imagen
from utils.request_tracker import (
    get_request_id,
    cleanup_old_requests,
    get_processing_requests,
    register_request,
    unregister_request,
    is_request_processing,
)

logger = setup_logger()

router = APIRouter()


@router.get("/health")
async def health_check():
    """헬스 체크"""
    return {
        "service": "AI-IMAGE Server",
        "version": "1.0.0",
        "status": "running"
    }


@router.post("/learn-style", response_model=StyleAnalysisResponse)
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
    logger.info(f"[요청 수신] POST /api/v1/learn-style")
    logger.info(f"   Request ID: {learn_request_id}")
    logger.info(f"   Client IP: {client_ip}")
    logger.info(f"   Story ID: {request.story_id}")
    logger.info(f"   Title: {request.title}")
    logger.info(f"   novel_text 제공: {'Yes (' + str(len(request.novel_text)) + ' chars)' if request.novel_text else 'No'}")
    logger.info(f"   novel_s3_url: {request.novel_s3_url[:50] + '...' if request.novel_s3_url else 'None'}")
    logger.info(f"   novel_s3_bucket: {request.novel_s3_bucket}")
    logger.info(f"   novel_s3_key: {request.novel_s3_key}")
    logger.info(f"   thumbnail_s3_url: {request.thumbnail_s3_url[:50] + '...' if request.thumbnail_s3_url else 'None'}")
    logger.info(f"   thumbnail_s3_bucket: {request.thumbnail_s3_bucket}")
    logger.info(f"   thumbnail_s3_key: {request.thumbnail_s3_key}")
    logger.info(f"   기본 S3 버킷 (config): {config.S3_BUCKET_NAME}")

    # 중복 요청 확인
    cleanup_old_requests()
    if is_request_processing(learn_request_id):
        logger.warning(f"[중복 요청 차단] learn-style Request ID: {learn_request_id}")
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
                logger.info(f"S3 모드: 소설 텍스트 다운로드 시작 (story_id={request.story_id})")
                logger.debug(f"   S3 URL: {request.novel_s3_url[:50] if request.novel_s3_url else 'None'}...")
                logger.debug(f"   S3 Bucket/Key: {request.novel_s3_bucket}/{request.novel_s3_key if request.novel_s3_key else 'None'}")

                try:
                    novel_text = await download_text_from_s3(
                        s3_url=request.novel_s3_url if has_s3_url else None,
                        s3_bucket=request.novel_s3_bucket if has_s3_bucket_key else None,
                        s3_key=request.novel_s3_key if has_s3_bucket_key else None
                    )
                    logger.info(f"소설 텍스트 다운로드 완료: {len(novel_text)} 문자")
                except Exception as e:
                    logger.error(f"S3 다운로드 실패: {str(e)}", exc_info=True)
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
            logger.info(f"직접 제공 모드: novel_text 사용 (story_id={request.story_id}, 길이={len(novel_text)} 문자)")

        # 소설 스타일 분석
        style_data = await analyze_novel_style(novel_text, request.title)

        # 스타일 저장
        save_novel_style(request.story_id, style_data)

        # 썸네일 이미지 생성 및 S3 업로드
        has_thumbnail_s3_info = request.thumbnail_s3_url or (request.thumbnail_s3_bucket and request.thumbnail_s3_key)
        has_default_bucket = bool(config.S3_BUCKET_NAME)

        if has_thumbnail_s3_info or has_default_bucket:
            try:
                logger.info(f"소설 썸네일 이미지 생성 시작: story_id={request.story_id}")

                # 썸네일 프롬프트 생성
                thumbnail_prompt = await generate_thumbnail_prompt(
                    request.title,
                    style_data,
                    novel_text[:500] if novel_text else None
                )

                logger.debug(f"썸네일 프롬프트: {thumbnail_prompt[:100]}...")

                # 프롬프트 정제 (정책 우회 및 안전성 확보)
                sanitized_thumbnail_prompt = await sanitize_prompt_for_imagen(thumbnail_prompt)
                logger.info("정제된 썸네일 프롬프트로 이미지 생성 시도")

                # 이미지 생성
                image_data = await generate_image_with_api(sanitized_thumbnail_prompt)

                # S3에 업로드 (제공된 정보 또는 기본 버킷 사용)
                thumbnail_s3_bucket = request.thumbnail_s3_bucket or config.S3_BUCKET_NAME
                thumbnail_s3_key = request.thumbnail_s3_key or f"thumbnails/{request.story_id}/thumbnail.png"

                thumbnail_url = await upload_image_to_s3(
                    image_data,
                    s3_url=request.thumbnail_s3_url,
                    s3_bucket=thumbnail_s3_bucket,
                    s3_key=thumbnail_s3_key
                )

                logger.info(f"썸네일 이미지 S3 업로드 완료: {thumbnail_url}")
            except Exception as e:
                logger.warning(f"썸네일 이미지 생성/업로드 실패 (스타일 학습은 성공): {str(e)}", exc_info=True)
                # 썸네일 생성 실패해도 스타일 학습은 성공으로 처리
        else:
            logger.warning("썸네일 S3 정보가 제공되지 않고 기본 버킷도 설정되지 않아 썸네일 생성을 건너뜁니다.")

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


@router.get("/style/{story_id}", response_model=StyleAnalysisResponse)
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


@router.post("/generate-image", response_model=ImageGenerationResponse)
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
    logger.info(f"[요청 수신] POST /api/v1/generate-image")
    logger.info(f"   Request ID: {request_id}")
    logger.info(f"   Client IP: {client_ip}")
    logger.info(f"   Story ID: {request.story_id}")
    logger.info(f"   S3 Key: {request.s3_key}")
    logger.info(f"   User Prompt: {request.user_prompt[:50]}..." if request.user_prompt else "   User Prompt: None")

    # 오래된 요청 정리 (주기적으로)
    cleanup_old_requests()

    # 중복 요청 확인
    if is_request_processing(request_id):
        logger.warning(f"[중복 요청 차단] Request ID: {request_id}")
        logger.warning(f"   Story ID: {request.story_id}, S3 Key: {request.s3_key}")
        logger.warning(f"   이미 처리 중인 동일한 요청입니다. (같은 story_id + s3_key 조합)")
        raise HTTPException(
            status_code=409,
            detail=f"동일한 요청이 이미 처리 중입니다. Request ID: {request_id}. "
                   f"노드별 이미지 생성 시에는 각 노드마다 다른 s3_key를 사용해야 합니다."
        )

    # 완료된 요청이 있으면 제거
    processing_requests = get_processing_requests()
    if request_id in processing_requests:
        del processing_requests[request_id]
        logger.debug(f"완료된 요청 제거: Request ID {request_id}")

    async def process_image_generation():
        """실제 이미지 생성 처리"""
        try:
            # 소설 스타일 로드
            logger.debug(f"[스타일 로드 시도] Story ID: {request.story_id}")
            novel_style = load_novel_style(request.story_id)
            if not novel_style:
                logger.error(f"[스타일 정보 없음] Story ID: {request.story_id} - 먼저 /api/v1/learn-style 호출 필요")
                raise HTTPException(
                    status_code=404,
                    detail=f"스토리 ID {request.story_id}의 스타일 정보가 없습니다. 먼저 스타일을 학습해주세요."
                )

            logger.info(f"[처리 시작] Request ID: {request_id}")
            logger.debug(f"   스타일 정보 로드 완료: atmosphere={novel_style.get('atmosphere')}, visual_style={novel_style.get('visual_style')}")

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

            logger.info(f"[처리 완료] Request ID: {request_id} - 이미지 URL: {image_url}")

            return ImageGenerationResponse(
                image_url=image_url,
                enhanced_prompt=enhanced_prompt,
                story_id=request.story_id,
                s3_key=request.s3_key
            )
        except HTTPException:
            raise
        except ValueError as e:
            logger.error(f"[처리 실패] Request ID: {request_id} - ValueError: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"[처리 실패] Request ID: {request_id} - Exception: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"이미지 생성 실패: {str(e)}")

    # 비동기 작업 생성 및 추적
    task = asyncio.create_task(process_image_generation())
    register_request(request_id, task, request.s3_key, request.story_id)

    try:
        result = await task
        return result
    except Exception as e:
        # 에러 발생 시에도 요청 ID 제거
        unregister_request(request_id)
        raise


@router.delete("/style/{story_id}")
async def delete_novel_style(story_id: str):
    """소설 스타일 삭제"""
    style_file = get_style_file_path(story_id)
    if style_file.exists():
        style_file.unlink()
        return {"message": f"스토리 ID {story_id}의 스타일이 삭제되었습니다."}
    else:
        raise HTTPException(status_code=404, detail=f"스토리 ID {story_id}의 스타일 정보를 찾을 수 없습니다.")
