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

## Model Server 실행 (Windows + NVIDIA GPU)

원본과 같은 환경(Windows + CUDA)입니다. 원래 팀의 설치 스크립트를 그대로 쓰고, 지금 다시 설치하면 깨지는 부분만 고쳤습니다 ([#8](../../issues/8)).

### 확인한 환경

| 항목 | 버전 |
| --- | --- |
| OS | Windows |
| GPU | NVIDIA GeForce RTX 3060 (드라이버의 CUDA 13.3) |
| Python | 3.9 (`install.bat`이 Miniconda로 설치) |
| torch | 2.3.1+cu121 |

### 1. 설치

Git이 필요합니다. 경로에 한글이나 띄어쓰기가 없는 곳에 받습니다.

```powershell
mkdir C:\dev
cd C:\dev
git clone https://github.com/Luvys99/Reflecxity.git
cd Reflecxity\backend\ModelServer
.\install.bat
```

`install.bat`은 `%UserProfile%\Miniconda3`에 Miniconda를 설치하고, `ModelServer\env`에 Python 3.9 환경을 만든 뒤 패키지와 CUDA 12.1용 torch를 설치합니다. 시스템에 Python을 등록하지는 않습니다.

GPU가 잡히는지 확인합니다. `True`가 나와야 합니다.

```powershell
env\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### 2. 사전 학습 모델 받기

Windows에서는 `ffmpeg.exe`, `ffprobe.exe`도 같이 받습니다 (`--exe` 기본값).

```powershell
env\python.exe rvc_cli.py prerequisites
```

### 3. 서버 실행

```powershell
.\start.bat
```

- 다른 컴퓨터(Main Server)에서 접속하려면 Windows 방화벽에서 48000 포트를 허용해야 합니다. 처음 실행할 때 뜨는 허용 창에서 허용합니다.
- 동작 확인은 macOS와 같습니다. `localhost` 대신 `127.0.0.1`을 씁니다 (Windows에서 `localhost`가 IPv6로 먼저 연결되면 접속되지 않을 수 있음).

10분 10초짜리 녹음(m4a, 앱과 같은 형식) 기준 걸린 시간입니다 (Main Server가 있는 Mac에서 와이파이로 요청, 2 epoch).

| 단계 | 시간 |
| --- | --- |
| UVR 모델 다운로드 (첫 학습 때 한 번만, 와이파이) | 약 9분 |
| UVR (잡음 제거) | 약 2분 |
| 자르기 → 특징 추출 | 약 42초 |
| 학습 (2 epoch) | 약 75초 |
| index 저장, pitch 찾기 | 약 12초 |
| **합계 (다운로드 제외)** | **약 4분 10초** |

TTS 변환은 짧은 문장 약 10초, 긴 문장(결과 10.5초) 11 ~ 31초 걸렸습니다. 기계 음성을 인터넷(edge-tts)에서 받아 와서 네트워크 상태에 따라 달라집니다.

`raw/`에 `.ogg` 파일이 이미 있으면 UVR을 이미 마친 것으로 보고 건너뜁니다.

### 원래 스크립트에서 고친 것

- **`install.bat`**: `pip install --upgrade setuptools`가 최신 setuptools를 설치하는데, 최신 버전에는 `pkg_resources`가 없어 librosa를 불러올 때 `ModuleNotFoundError`가 납니다. `setuptools<70`으로 고정했습니다.
- **`start.bat`**: 원래 팀 컴퓨터의 경로(`C:\Users\user\rvc-cli`)가 고정돼 있어서, 파일이 있는 폴더 기준으로 실행하게 바꿨습니다.

## Main Server 실행 (macOS)

Main Server는 사용자(UUID)를 MariaDB에 저장하고, 녹음 업로드·학습·TTS 요청을 Model Server로 전달합니다. Model Server가 다른 컴퓨터(예: Windows GPU 컴퓨터)에 있어도 됩니다 ([#2](../../issues/2)).

### 1. 설정 (`.env`)

DB 계정과 Model Server 주소처럼 컴퓨터마다 다른 값은 `backend/MainServer/.env`에 둡니다 (git에 올리지 않음). 환경 변수가 있으면 `config.ini` 값보다 우선합니다.

```bash
cd backend/MainServer
cp .env.example .env
# .env를 열어 DB_USER, DB_PASSWORD를 채우고,
# Model Server가 다른 컴퓨터면 MODEL_SERVER_URL=http://<그 컴퓨터 IP>:48000
```

### 2. MariaDB (Docker)

`.env`의 계정으로 DB를 만듭니다. 처음 실행할 때 `reflecxity` DB와 계정이 만들어지고, 테이블은 Main Server가 시작할 때 `db_schema.sql`로 만듭니다.

```bash
set -a; . ./.env; set +a
docker run -d --name reflecxity-db -p 3306:3306 \
  -e MARIADB_ROOT_PASSWORD="$DB_ROOT_PASSWORD" \
  -e MARIADB_DATABASE=reflecxity \
  -e MARIADB_USER="$DB_USER" -e MARIADB_PASSWORD="$DB_PASSWORD" \
  -v reflecxity-db:/var/lib/mysql \
  mariadb:11
```

`DB_ROOT_PASSWORD`는 DB 관리용이라 `.env`에 따로 적어 둡니다 (Main Server는 쓰지 않음).

### 3. Python 가상 환경과 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

- 주소: `http://localhost:28300`, API 문서: `http://localhost:28300/docs`
- 로그에 `테이블 생성 완료`가 나와야 합니다
- `mysql-connector-python`은 8.x로 고정했습니다. 9.x에서는 `cursor.execute(..., multi=True)`가 없어져 테이블 생성이 실패합니다

### 4. 동작 확인 (Main → Model)

```bash
# 1) 사용자 생성 → {"uuid": ...}
curl -X POST localhost:28300/user

# 2) 녹음 업로드 (m4a / ogg)
curl -F "file=@voice.m4a" localhost:28300/user/<uuid>/upload

# 3) 학습 요청 (대기열에 들어감) → 완료 확인
curl -X POST localhost:28300/user/<uuid>/models
curl localhost:28300/user/<uuid>/modelcheck

# 4) TTS (결과 음성 파일을 바로 받음)
curl -X POST localhost:28300/user/<uuid>/tts -F "tts_text=Hello, this is my voice." -o result.wav
```

Mac(Main, MariaDB) + Windows RTX 3060(Model)에서 10분 녹음 기준 학습 요청부터 Main이 완료를 확인하기까지 4분 20초, TTS는 약 20초 걸렸습니다. TTS는 edge-tts 응답에 따라 가끔 실패하니 다시 요청해 봅니다.

## 개선 작업

개선은 이슈 → 브랜치 → PR로 하나씩 진행합니다. 진행 상황은 [Issues](../../issues)에서 볼 수 있습니다.
