package com.luvys99.olog;

import android.media.MediaMetadataRetriever;

import java.util.Collection;

// 학습 시간 계산을 한곳에 모은다 (#82, #93). 녹음 화면(예상 시간)과 학습 중 화면(남은 시간)이 같이 쓴다
public final class TrainingTime {
    private TrainingTime() { }

    // 예상 학습 시간(초): 녹음 2분 → 3분 22초, 5분 → 5분 7초, 6분 → 6분 8초 측정값(10 epoch, Windows RTX 3060, #65)에 맞춘 직선
    // 2분 + 녹음 길이 × 0.7. 학습 워커가 다른 사람 학습 중이면 더 걸린다
    public static long estimateSeconds(long recordingMs) {
        return Math.round(120 + 0.7 * recordingMs / 1000.0);
    }

    public static int estimateMinutes(long recordingMs) {
        return (int) Math.round(estimateSeconds(recordingMs) / 60.0);
    }

    // 녹음 파일들의 길이 합 (밀리초). 읽지 못한 파일은 건너뛴다
    public static long totalDurationMs(Collection<String> filePaths) {
        long total = 0;
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try {
            for (String path : filePaths) {
                try {
                    retriever.setDataSource(path);
                    String duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
                    total += Long.parseLong(duration);
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
        } finally {
            try {
                retriever.release();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
        return total;
    }
}
