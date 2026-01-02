"""
Pydantic 스키마 모델
API 요청/응답에 사용되는 데이터 모델 정의
"""

from typing import Optional
from pydantic import BaseModel, Field


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
