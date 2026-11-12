# Reflecxity

녹음한 **내 목소리**로 번역된 문장을 읽어 주는 AI 음성 통역 앱입니다.
졸업 작품(2024)의 원본 코드를 가져와서, **Model Server를 분석하고 개선하는 개인 저장소**입니다.

## 원본과 역할

| 구분 | 내용 |
| --- | --- |
| 원본 백엔드 | [Reflecxity/Reflecxity-Back-End-Project](https://github.com/Reflecxity/Reflecxity-Back-End-Project) |
| 원본 Android 앱 | [Reflecxity/Reflecxity-Project](https://github.com/Reflecxity/Reflecxity-Project) |
| 원본 개발 | 졸업 작품 팀 (코드는 팀원이 작성, 저는 보고서와 발표 담당) |
| 이 저장소 | 원본을 가져온 뒤 제가 진행한 **분석과 개선 작업** |

- 첫 커밋(`졸업 작품 원본 코드 가져옴`)은 원본 커밋의 파일을 **수정 없이** 옮긴 것입니다.
- 그 이후의 커밋이 이 저장소에서 진행한 개선 작업입니다.

## 구조

```
Reflecxity/
├── backend/
│   ├── MainServer/    사용자(UUID) 관리, 요청 중계, 학습 대기열 (FastAPI + MariaDB)
│   └── ModelServer/   녹음 저장, UVR 전처리, RVC 학습, TTS + RVC 변환 (FastAPI)
└── android/           녹음, STT, 번역, 재생 (Android)
```

```
번역된 텍스트 → [TTS] → 기계 음성 → [RVC + 내 목소리 모델] → 내 목소리 음성
```

## Model Server 실행 (macOS)

원본은 Windows + NVIDIA GPU(CUDA) 기준으로 만들어져 있어서, Mac에서 녹음 업로드 → 학습 → TTS 변환까지 돌아가도록 고쳤습니다 ([#1](../../issues/1)).

### 확인한 환경

| 항목 | 버전 |
| --- | --- |
| OS | macOS (Apple M4, 메모리 16GB) |
| Python | 3.9.6 |
| 학습 장치 | Mac GPU(MPS). 특징 추출(extract) 단계만 CPU |

### 1. ffmpeg 설치

UVR 결과를 OGG로 저장하려면 **libvorbis 인코더가 들어 있는 ffmpeg**이 필요합니다.
Homebrew 기본 ffmpeg(`brew install ffmpeg`)에는 libvorbis가 없어서 학습이 UVR 단계에서 실패합니다.

```bash
brew tap homebrew-ffmpeg/ffmpeg
brew trust --formula homebrew-ffmpeg/ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg

ffmpeg -hide_banner -encoders | grep vorbis   # libvorbis가 보이면 성공
```

기본 ffmpeg이 이미 설치돼 있으면 먼저 `brew uninstall ffmpeg`로 지웁니다.

### 2. Python 가상 환경과 패키지

```bash
cd backend/ModelServer
python3 -m venv .venv
.venv/bin/pip install "pip<24.1"
.venv/bin/pip install -r requirements.txt
```

### 3. 사전 학습 모델 받기

RVC 사전 학습 모델(v2), 음색 추출 모델(contentvec), 음높이 추출 모델(rmvpe)을 받습니다 (약 1.2GB).

```bash
.venv/bin/python rvc_cli.py prerequisites --exe False
```

UVR(잡음 제거) 모델(약 1GB)은 **첫 학습 때 `uvrmodel/` 폴더로 자동으로** 받습니다.
모델 파일은 용량이 커서 저장소에 넣지 않습니다 (`.gitignore`).

### 4. 서버 실행

```bash
.venv/bin/python main.py
```

- 주소: `http://localhost:48000`
- API 문서(Swagger): `http://localhost:48000/docs`

### 5. 동작 확인 (업로드 → 학습 → TTS)

`test-user`는 예시 사용자 ID이고, `voice.wav`는 1분 이상 말한 녹음 파일입니다.

```bash
# 1) 녹음 업로드 → user/test-user/raw/
curl -F "file=@voice.wav" localhost:48000/user/test-user/upload

# 2) 학습 요청 (백그라운드에서 실행)
curl -X POST localhost:48000/models -H "Content-Type: application/json" \
  -d '{"user_uuid":"test-user"}'

# 3) 학습 완료 확인 → {"message":"모델 파일 존재"}가 나오면 완료
curl localhost:48000/user/test-user/modelcheck

# 4) TTS 변환 → user/test-user/convert.wav
curl -X POST localhost:48000/tts -H "Content-Type: application/json" \
  -d '{"user_uuid":"test-user","tts_text":"Hello, this is my voice.","pitch":0}'
curl localhost:48000/user/test-user/status   # {"tts":"success"}가 나오면 완료
```

1분 48초짜리 녹음 기준으로 UVR을 뺀 학습(자르기 → 특징 추출 → 2 epoch 학습)은 약 3분 30초, TTS 변환은 15초 정도 걸렸습니다.
진행 단계는 `logs/test-user/`에 생기는 파일로도 확인할 수 있습니다 (마지막에 `pitch.txt`가 생기면 완료, `fail`이 생기면 실패).

### 참고

- **녹음 길이**: 녹음을 잘랐을 때 조각이 10개 이하이면 학습이 실패로 처리됩니다. 1분 이상 녹음을 권장합니다.
- **TTS는 인터넷이 필요합니다**: 기계 음성은 `edge-tts`로 Microsoft 음성 서버에서 받아 옵니다. 서버 응답에 따라 가끔 실패할 수 있으니 다시 요청해 봅니다.
- **실행하면 설정 파일이 바뀝니다**: CUDA가 없는 환경에서 실행하면 RVC가 `rvc/configs/v1|v2/*.json`의 `fp16_run`을 `false`로 바꿔 저장합니다. 이 변경은 커밋하지 않습니다.

## 개선 작업

개선은 이슈 → 브랜치 → PR로 하나씩 진행합니다. 진행 상황은 [Issues](../../issues)에서 볼 수 있습니다.
