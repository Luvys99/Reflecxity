package com.cookandroid.joljag_v1_0.utils;

import android.media.MediaPlayer;
import android.util.Log;
import android.util.SparseBooleanArray;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.RecyclerView;

import com.cookandroid.joljag_v1_0.R;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Locale;

public class AudioFilesAdapter extends RecyclerView.Adapter<AudioFilesAdapter.AudioFileViewHolder> {

    private ArrayList<File> audioFiles;
    private SparseBooleanArray selectedItems = new SparseBooleanArray(); // 선택 상태 저장
    private OnItemSelectedListener itemSelectedListener; // 선택 상태 변경 리스너

    public interface OnItemSelectedListener {
        void onItemSelectionChanged(int selectedCount);
    }

    public AudioFilesAdapter(ArrayList<File> audioFiles, OnItemSelectedListener listener) {
        this.audioFiles = audioFiles;
        this.itemSelectedListener = listener;
    }

    @NonNull
    @Override
    public AudioFileViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.learning_item_audio_file, parent, false);
        return new AudioFileViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull AudioFileViewHolder holder, int position) {
        File audioFile = audioFiles.get(position);
        holder.fileNameTextView.setText(audioFile.getName());

        // MediaPlayer로 파일 길이 가져오기
        MediaPlayer mediaPlayer = new MediaPlayer();
        try {
            mediaPlayer.setDataSource(audioFile.getAbsolutePath());
            mediaPlayer.prepare();
            long durationInMillis = mediaPlayer.getDuration();  // 파일 길이(밀리초)
            String formattedDuration = formatDuration(durationInMillis);  // 파일 길이를 분:초 형식으로 변환
            holder.fileDurationTextView.setText(formattedDuration);  // 파일 길이를 TextView에 설정
        } catch (IOException e) {
            e.printStackTrace();
            Log.e("MediaPlayer Error", "파일 길이 가져오기 실패: " + e.getMessage());
            holder.fileDurationTextView.setText("길이 가져오기 실패");
        } finally {
            mediaPlayer.release();
        }

        // 선택 상태에 따른 배경색 설정
        if (selectedItems.get(position, false)) {
            holder.itemView.setBackgroundColor(ContextCompat.getColor(holder.itemView.getContext(), R.color.grey300));
        } else {
            holder.itemView.setBackgroundColor(ContextCompat.getColor(holder.itemView.getContext(), android.R.color.transparent));
        }

        // 항목 클릭 시 선택 상태 토글
        holder.itemView.setOnClickListener(v -> {
            if (selectedItems.get(position, false)) {
                selectedItems.delete(position);
            } else {
                selectedItems.put(position, true);
            }

            // 선택 상태 변경에 따라 배경색 갱신
            notifyItemChanged(position);

            // 선택된 항목 수 전달
            if (itemSelectedListener != null) {
                itemSelectedListener.onItemSelectionChanged(selectedItems.size());
            }
        });
    }

    // 밀리초를 분:초 형식으로 변환하는 메서드
    private String formatDuration(long durationInMillis) {
        int totalSeconds = (int) (durationInMillis / 1000);
        int minutes = totalSeconds / 60;
        int seconds = totalSeconds % 60;
        return String.format(Locale.getDefault(), "%02d:%02d", minutes, seconds);
    }

    @Override
    public int getItemCount() {
        return audioFiles.size();
    }

    // 선택 상태 초기화 메서드
    public void clearSelection() {
        selectedItems.clear(); // 선택 상태 초기화
        notifyDataSetChanged(); // RecyclerView 갱신
    }

    // 선택된 파일 반환
    public ArrayList<File> getSelectedFiles() {
        ArrayList<File> selectedFiles = new ArrayList<>();
        for (int i = 0; i < selectedItems.size(); i++) {
            int position = selectedItems.keyAt(i);
            if (selectedItems.valueAt(i)) {
                selectedFiles.add(audioFiles.get(position));
            }
        }
        return selectedFiles;
    }

    public static class AudioFileViewHolder extends RecyclerView.ViewHolder {
        TextView fileNameTextView;
        TextView fileDurationTextView;  // 파일 길이를 표시할 TextView

        public AudioFileViewHolder(@NonNull View itemView) {
            super(itemView);
            fileNameTextView = itemView.findViewById(R.id.audio_file_name);
            fileDurationTextView = itemView.findViewById(R.id.audio_file_duration);  // 파일 길이 TextView 참조
        }
    }
}