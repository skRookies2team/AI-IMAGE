"""
S3 서비스 모듈
AWS S3 파일 업로드/다운로드 기능
"""

from typing import Optional
from datetime import datetime

from fastapi import HTTPException
import httpx

from config import config
from logger import setup_logger

logger = setup_logger()

# boto3 import
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    logger.warning("boto3가 설치되지 않았습니다. S3 기능을 사용할 수 없습니다.")


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
        logger.info(f"S3 presigned URL로 이미지 업로드 시작... ({len(image_bytes)} bytes)")

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
                logger.info(f"S3 업로드 성공: {response.status_code}")
                return True
            else:
                logger.error(f"S3 업로드 실패: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"S3 업로드 중 오류 발생: {str(e)}", exc_info=True)
        return False
