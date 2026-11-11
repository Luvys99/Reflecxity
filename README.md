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

## 개선 작업

개선은 이슈 → 브랜치 → PR로 하나씩 진행합니다. 진행 상황은 [Issues](../../issues)에서 볼 수 있습니다.
