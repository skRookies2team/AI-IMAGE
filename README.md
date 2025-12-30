# AI-IMAGE Server

GCP Vertex AI의 Gemini 2.5 Flash를 사용하여 소설 스타일을 학습하고 노드별 이미지를 생성하는 서버입니다.

## 기능

1. **소설 스타일 학습**: 소설 텍스트를 분석하여 분위기, 시각적 스타일 등을 추출하여 저장
2. **이미지 프롬프트 개선**: 사용자가 입력한 프롬프트를 소설의 스타일에 맞게 개선
3. **이미지 생성**: Google Imagen API를 사용한 고품질 이미지 생성
4. **프롬프트 정제 (Prompt Sanitization)**: Gemini를 사용하여 민감한 표현을 안전하게 변환
5. **자동 재시도**: 안전 필터에 차단된 경우 프롬프트를 자동으로 재작성하여 재시도
6. **S3 스토리지 통합**: 생성된 이미지를 AWS S3에 저장

## 설치

```bash
# Python 3.10 이상 필요
pip install -r requirements.txt
```

## GCP 설정

### 1. GCP 프로젝트 생성 및 Vertex AI 활성화

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. **Vertex AI API** 활성화:
   ```bash
   gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
   ```

### 2. 인증 설정

#### 옵션 A: 서비스 계정 키 파일 사용 (로컬 개발 권장)

1. 서비스 계정 생성:
   ```bash
   gcloud iam service-accounts create ai-image-server \
     --display-name="AI Image Server Service Account"
   ```

2. 권한 부여:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:ai-image-server@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```

3. 서비스 계정 키 파일 다운로드:
   ```bash
   gcloud iam service-accounts keys create key.json \
     --iam-account=ai-image-server@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

#### 옵션 B: Application Default Credentials (GCP 환경)

GCP 환경 (Cloud Run, GCE, GKE 등)에서는 ADC가 자동으로 사용됩니다.

로컬에서 ADC 사용:
```bash
gcloud auth application-default login
```

## 환경 변수 설정

`.env` 파일을 생성하고 다음 내용을 추가하세요:

```env
# 필수
GCP_PROJECT_ID=your-gcp-project-id

# 선택 (기본값 제공)
GCP_LOCATION=us-central1
GEMINI_MODEL_NAME=gemini-2.0-flash-exp

# 로컬 개발 시에만 필요 (서비스 계정 키 파일 경로)
GCP_SERVICE_ACCOUNT_KEY_PATH=/path/to/key.json
```

### 환경 변수 설명

- **GCP_PROJECT_ID** (필수): GCP 프로젝트 ID
- **GCP_LOCATION** (선택): Vertex AI 리전 (기본값: `us-central1`)
  - 사용 가능: `us-central1`, `us-east1`, `us-west1`, `asia-northeast1`, `europe-west1` 등
- **GEMINI_MODEL_NAME** (선택): 사용할 Gemini 모델 (기본값: `gemini-2.0-flash-exp`)
  - 사용 가능: `gemini-2.0-flash-exp`, `gemini-1.5-flash`, `gemini-1.5-pro` 등
- **GCP_SERVICE_ACCOUNT_KEY_PATH** (선택): 서비스 계정 키 파일 경로
  - 설정하지 않으면 ADC 사용

## 실행

```bash
python main.py
```

또는 uvicorn으로:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

환경 변수가 올바르게 설정되어 있는지 확인하세요.

## API 엔드포인트

### 1. 헬스 체크
```
GET /
```

### 2. 소설 스타일 학습
```
POST /api/v1/learn-style
Body:
{
  "story_id": "story_123",
  "novel_text": "소설 전체 텍스트...",
  "title": "소설 제목" (선택사항)
}
```

### 3. 소설 스타일 조회
```
GET /api/v1/style/{story_id}
```

### 4. 이미지 생성
```
POST /api/v1/generate-image
Body:
{
  "story_id": "story_123",
  "node_id": "node_456",
  "user_prompt": "사용자가 입력한 이미지 프롬프트",
  "node_text": "노드 텍스트" (선택사항, 컨텍스트용)
}
```

### 5. 소설 스타일 삭제
```
DELETE /api/v1/style/{story_id}
```

## 주의사항

- 소설 스타일은 `styles/` 디렉토리에 JSON 파일로 저장됩니다.
- 이미지 생성 시 Google Imagen의 안전 필터가 적용됩니다:
  - **안전 필터 레벨**: `block_only_high` (가장 느슨한 설정)
  - **차단 카테고리**: Violence (폭력), Sexual (성적), Derogatory (비하), Toxic (유해)
  - 차단된 경우 자동으로 프롬프트를 정제하여 최대 2회 재시도합니다.
- AWS S3 설정이 필요합니다 (환경 변수 참조)

## 프롬프트 정제 기능

민감하거나 정책 위반 가능성이 있는 프롬프트는 자동으로 안전하고 정책 준수적인 표현으로 변환됩니다:

1. **자동 정제**: Gemini가 프롬프트를 분석하여 안전하게 재작성
2. **의도 보존**: 원본의 핵심 의도와 시각적 요소는 최대한 유지
3. **재시도 로직**: 차단된 경우 정제된 프롬프트로 자동 재시도 (최대 2회)

### 예시

- 원본: `"A dramatic battle scene with weapons"`
- 정제: `"An artistic depiction of a historical confrontation scene with period-appropriate elements"`

## 테스트

일반 이미지 생성 테스트:
```bash
python test_image_gen.py
```

민감한 프롬프트로 정제 기능 테스트:
```bash
python test_image_gen.py --sensitive
```

## 향후 개선 사항

1. 이미지 캐싱 기능으로 반복 생성 방지
2. 프롬프트 정제 품질 향상 (더 다양한 패턴 학습)
3. 안전 필터 차단 이유 상세 분석 기능
4. 백엔드 릴레이 서버와의 통합
5. 이미지 생성 진행 상황 실시간 업데이트

