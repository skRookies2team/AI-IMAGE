# AI-IMAGE 서버 설정 가이드

GCP Vertex AI Gemini 2.5 Flash를 사용한 AI 이미지 서버 설정 가이드입니다.

## 1. 사전 준비

### GCP 프로젝트 생성
1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. 프로젝트 ID 확인

### Vertex AI API 활성화
```bash
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

## 2. 인증 설정

### 옵션 A: 서비스 계정 키 파일 (로컬 개발)

1. 서비스 계정 생성:
```bash
gcloud iam service-accounts create ai-image-server \
  --display-name="AI Image Server Service Account" \
  --project=YOUR_PROJECT_ID
```

2. 권한 부여:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:ai-image-server@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

3. 키 파일 다운로드:
```bash
gcloud iam service-accounts keys create key.json \
  --iam-account=ai-image-server@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

4. `.env` 파일에 경로 설정:
```env
GCP_SERVICE_ACCOUNT_KEY_PATH=/path/to/key.json
```

### 옵션 B: Application Default Credentials (GCP 환경 또는 로컬)

#### GCP 환경 (Cloud Run, GCE, GKE 등)
ADC가 자동으로 사용됩니다. 추가 설정 불필요.

#### 로컬 개발
```bash
gcloud auth application-default login
```

`.env` 파일에서 `GCP_SERVICE_ACCOUNT_KEY_PATH`는 설정하지 않습니다.

## 3. 환경 변수 설정

`.env` 파일 생성:

```env
# 필수
GCP_PROJECT_ID=your-gcp-project-id

# 선택 (기본값 제공)
GCP_LOCATION=us-central1
GEMINI_MODEL_NAME=gemini-2.0-flash-exp

# 서비스 계정 키 (로컬 개발 시 필요)
GCP_SERVICE_ACCOUNT_KEY_PATH=/path/to/key.json

# 서버 설정
PORT=8001
```

## 4. 설치 및 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행
python main.py
```

## 5. 테스트

### 헬스 체크
```bash
curl http://localhost:8001/
```

### 소설 스타일 학습
```bash
curl -X POST http://localhost:8001/api/v1/learn-style \
  -H "Content-Type: application/json" \
  -d '{
    "story_id": "test_story_1",
    "novel_text": "소설 내용...",
    "title": "테스트 소설"
  }'
```

### 이미지 생성
```bash
curl -X POST http://localhost:8001/api/v1/generate-image \
  -H "Content-Type: application/json" \
  -d '{
    "story_id": "test_story_1",
    "node_id": "node_1",
    "user_prompt": "어둡고 신비로운 숲",
    "node_text": "노드 텍스트..."
  }'
```

## 문제 해결

### 인증 오류
- 서비스 계정 키 파일 경로 확인
- 또는 `gcloud auth application-default login` 실행

### Vertex AI API 활성화 오류
- GCP 콘솔에서 Vertex AI API 활성화 확인
- 프로젝트 ID 확인

### 모델 이름 오류
- 사용 가능한 모델 확인: `gemini-2.0-flash-exp`, `gemini-1.5-flash` 등
- `.env` 파일의 `GEMINI_MODEL_NAME` 확인


