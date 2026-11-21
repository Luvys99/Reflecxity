package com.cookandroid.joljag_v1_0;

import android.Manifest;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.drawable.Drawable;
import android.media.MediaMetadataRetriever;
import android.media.MediaPlayer;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ImageButton;
import android.widget.ProgressBar;
import android.widget.SeekBar;
import android.widget.TextView;

import androidx.appcompat.app.AlertDialog;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.cookandroid.joljag_v1_0.utils.AudioFilesAdapter;
import com.google.android.material.snackbar.Snackbar;

import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

public class DataLearningActivity extends AppCompatActivity {

    private TextView txt_delete;
    private TextView txt_play;
    private TextView txt_record;
    private TextView txt_send;
    private TextView txt_currentTime;
    private TextView txt_totalTime;
    private ImageButton recording;
    private ImageButton playing;
    private ImageButton delete_selected;
    private ImageButton submit_selected;
    private String from;
    private MediaRecorder recorder;
    private MediaPlayer player;
    private String audioFilePath;
    private boolean isRecording = false;
    private boolean isPlaying = false;
    private ArrayList<File> audioFiles = new ArrayList<>();
    private RecyclerView recyclerView;
    private AudioFilesAdapter adapter;

    private static final int REQUEST_AUDIO_PERMISSION_CODE = 200;

    private static final String MainAPI_URL = BuildConfig.MainAPI_URL;
    private static final String MainAPI_URL_OnlineCheck = MainAPI_URL + "/online/";

    private boolean server_status_main = false;
    private boolean server_status_model = false;

    private SeekBar seekBar;
    private Handler seekBarHandler = new Handler(); // UI 업데이트를 위한 핸들러
    private Runnable updateSeekBar;

    private Handler recordingTimeHandler = new Handler();
    private long recordingStartTime;
    private Runnable updateRecordingTime;
    private TextView txt_recordingTime;

    // 학습에 필요한 녹음 길이 (Main 서버가 아니라 앱이 정한 조건)
    private static final long MIN_TRAINING_MS = 5 * 60 * 1000;
    private View progressCard;
    private View tipsRow;
    private View recordingPanel;
    private TextView txtTotalRecorded;
    private TextView txtProgressMessage;
    private TextView txtListHeader;
    private ProgressBar progressTotal;
    private TextView txtReadText;
    private String[] readTexts;
    private int readTextIndex = -1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_data_learning);

        txt_delete = findViewById(R.id.txt_delete);
        txt_play = findViewById(R.id.txt_play);
        txt_record = findViewById(R.id.txt_record);
        txt_send = findViewById(R.id.txt_send);
        txt_currentTime = findViewById(R.id.txt_currentTime);
        txt_totalTime = findViewById(R.id.txt_totalTime);
        recording = findViewById(R.id.button_recording);
        playing = findViewById(R.id.button_playing);
        delete_selected = findViewById(R.id.button_delete_selected);
        submit_selected = findViewById(R.id.button_submit_selected);
        seekBar = findViewById(R.id.seekBar);

        txt_recordingTime = findViewById(R.id.txt_recordingTime); // 녹음 시간 TextView 초기화

        // 모은 녹음 진행, 녹음 중 읽을 글 (#82)
        progressCard = findViewById(R.id.progress_card);
        tipsRow = findViewById(R.id.tips_row);
        recordingPanel = findViewById(R.id.recording_panel);
        txtTotalRecorded = findViewById(R.id.txt_total_recorded);
        txtProgressMessage = findViewById(R.id.txt_progress_message);
        txtListHeader = findViewById(R.id.txt_list_header);
        progressTotal = findViewById(R.id.progress_total);
        txtReadText = findViewById(R.id.txt_read_text);
        readTexts = getResources().getStringArray(R.array.record_read_texts);
        findViewById(R.id.button_next_text).setOnClickListener(v -> showNextReadText());

        // Toolbar 설정
        Toolbar toolbar = findViewById(R.id.custom_toolbar);
        setSupportActionBar(toolbar);

        // 앱 이름 중앙 정렬
        if (getSupportActionBar() != null) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(true);
            getSupportActionBar().setTitle("");
        }

        Drawable navigationIcon = toolbar.getNavigationIcon();
        if (navigationIcon != null) {
            navigationIcon.setTint(ContextCompat.getColor(this, R.color.ink));
        }

        // Intent로부터 데이터 읽기
        Intent dataLearningIntent = getIntent();

        from = dataLearningIntent.getStringExtra("FROM");
        if ("Terms".equals(from)) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(true);
        } else if ("ReTrain".equals(from)) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(false);
        } else {
            from = "None";
            getSupportActionBar().setDisplayHomeAsUpEnabled(false);
        }

        // SharedPreferences 객체 생성
        SharedPreferences prefs = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        boolean isFirstGuide = prefs.getBoolean("isFirstGuide", true);

        if (isFirstGuide) {
            new MaterialAlertDialogBuilder(DataLearningActivity.this)
                    .setTitle(R.string.record_guide_title)
                    .setMessage(getString(R.string.learning_guideline))
                    .setPositiveButton(R.string.ok, null)
                    .setNeutralButton(R.string.dont_show_again, new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface dialog, int which) {
                            // 다음 번에는 다이얼로그가 표시되지 않도록 isFirstLaunch 값을 false로 변경
                            SharedPreferences.Editor editor = prefs.edit();
                            editor.putBoolean("isFirstGuide", false);
                            editor.apply();

                            dialog.dismiss();
                        }
                    })
                    .show();
        }


        // RecyclerView 설정
        recyclerView = findViewById(R.id.recordings_recycler_view);
        recyclerView.setLayoutManager(new LinearLayoutManager(this));

        // Adapter 설정
        loadAudioFiles();
        adapter = new AudioFilesAdapter(audioFiles, this::updateActionButtonsVisibility);
        recyclerView.setAdapter(adapter);
        updateTotalProgress();

        // 초기에는 버튼을 숨긴 상태로 설정
        playing.setVisibility(View.GONE);
        delete_selected.setVisibility(View.GONE);
        submit_selected.setVisibility(View.GONE);
        recording.setVisibility(View.VISIBLE);
        seekBar.setVisibility(View.GONE);
        txt_play.setVisibility(View.GONE);
        txt_delete.setVisibility(View.GONE);
        txt_send.setVisibility(View.GONE);
        txt_record.setVisibility(View.VISIBLE);
        txt_currentTime.setVisibility(View.GONE);
        txt_totalTime.setVisibility(View.GONE);
        syncButtonContainers();

        // 버튼 클릭 리스너 설정
        playing.setOnClickListener(v -> playSelectedFiles());
        delete_selected.setOnClickListener(v -> confirmDeleteSelectedFiles());
        submit_selected.setOnClickListener(v -> {
            confirmSubmitSelectedFiles();

            // 선택한 파일 경로를 SharedPreferences에 저장
            ArrayList<File> selectedFiles = adapter.getSelectedFiles();
            ArrayList<String> selectedFilePaths = new ArrayList<>();
            for (File file : selectedFiles) {
                selectedFilePaths.add(file.getAbsolutePath());
            }
            saveSelectedFilePaths(selectedFilePaths); // 파일 경로 저장
        });

        recording.setOnClickListener(v -> {
            if (checkPermissions()) {
                if (!isRecording) {
                    startRecording();  // 녹음이 정상적으로 시작된 후에만 텍스트 변경
                } else {
                    stopRecording();
                    loadAudioFiles();
                    adapter.notifyDataSetChanged();
                    updateTotalProgress();
                }
            } else {
                requestPermissions();
            }
        });

        // SeekBar 변경 이벤트 처리
        seekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                if (fromUser && player != null) {
                    player.seekTo(progress);
                }
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) { }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) { }
        });
    }

    private void updateActionButtonsVisibility(int selectedCount) {
        if (selectedCount > 0 || isPlaying) {
            playing.setVisibility(View.VISIBLE);
            delete_selected.setVisibility(View.VISIBLE);
            submit_selected.setVisibility(View.VISIBLE);
            recording.setVisibility(View.GONE);
            txt_play.setVisibility(View.VISIBLE);
            txt_delete.setVisibility(View.VISIBLE);
            txt_send.setVisibility(View.VISIBLE);
            txt_record.setVisibility(View.GONE);
        } else {
            playing.setVisibility(View.GONE);
            delete_selected.setVisibility(View.GONE);
            submit_selected.setVisibility(View.GONE);
            recording.setVisibility(View.VISIBLE);
            txt_play.setVisibility(View.GONE);
            txt_delete.setVisibility(View.GONE);
            txt_send.setVisibility(View.GONE);
            txt_record.setVisibility(View.VISIBLE);
        }
        syncButtonContainers();
    }

    // 버튼을 숨기면 그 칸(버튼 + 아래 글자)도 숨겨서, 녹음하기 버튼 하나일 때 가로를 다 쓰게 한다 (#82)
    private void syncButtonContainers() {
        for (View button : new View[]{playing, delete_selected, submit_selected, recording}) {
            ((View) button.getParent()).setVisibility(button.getVisibility());
        }
    }

    private void playSelectedFiles() {
        ArrayList<File> selectedFiles = adapter.getSelectedFiles();
        if (!isPlaying) {
            if (selectedFiles.size() == 1) {
                playAudio(selectedFiles.get(0));
                txt_play.setText(R.string.record_play_stop);
                playing.setImageDrawable(getDrawable(R.drawable.stop));
            } else if (selectedFiles.size() > 1) {
                Snackbar.make(findViewById(R.id.layout), "한 번에 하나의 파일만 재생할 수 있습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            } else {
                Snackbar.make(findViewById(R.id.layout), "선택된 파일이 없습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            }
        } else {
            stopAudio();
        }
    }

    private void confirmDeleteSelectedFiles() {
        ArrayList<File> selectedFiles = adapter.getSelectedFiles();
        if (!selectedFiles.isEmpty()) {
            new MaterialAlertDialogBuilder(this)
                    .setTitle(R.string.record_delete)
                    .setMessage("녹음 " + selectedFiles.size() + "개를 지울까요?")
                    .setPositiveButton(R.string.record_delete, (dialog, which) -> deleteSelectedFiles())
                    .setNegativeButton(R.string.cancel, null)
                    .show();
        } else {
            Snackbar.make(findViewById(R.id.layout), "선택된 파일이 없습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
        }
    }

    private void deleteSelectedFiles() {
        ArrayList<File> selectedFiles = adapter.getSelectedFiles();
        if (!selectedFiles.isEmpty()) {
            for (File file : selectedFiles) {
                deleteAudioFile(file);
            }
            adapter.clearSelection();
            adapter.notifyDataSetChanged();
            updateActionButtonsVisibility(0);
        }
    }

    private void confirmSubmitSelectedFiles() {
        ArrayList<File> selectedFiles = adapter.getSelectedFiles();
        if (!selectedFiles.isEmpty()) {
            long totalDuration = calculateTotalDuration(selectedFiles);

            if (totalDuration < MIN_TRAINING_MS) {
                Snackbar.make(findViewById(R.id.layout), getString(R.string.record_too_short, formatKoreanDuration(MIN_TRAINING_MS - totalDuration)), Snackbar.LENGTH_LONG).setAction(R.string.ok, v -> {}).show();
                return; // 진행 중지
            }

            String formattedDuration = formatDuration(totalDuration);
            new MaterialAlertDialogBuilder(this)
                    .setTitle(getString(R.string.record_submit_title, selectedFiles.size()))
                    .setMessage(getString(R.string.record_submit_message, formattedDuration, TrainingTime.estimateMinutes(totalDuration)))
                    .setPositiveButton(R.string.record_submit, (dialog, which) -> submitSelectedFiles())
                    .setNegativeButton(R.string.cancel, null)
                    .show();
        } else {
            Snackbar.make(findViewById(R.id.layout), "선택된 파일이 없습니다.", Snackbar.LENGTH_SHORT).setAction("확인",null).show();
        }
    }

    private long calculateTotalDuration(ArrayList<File> selectedFiles) {
        long totalDuration = 0;
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();

        try {
            for (File file : selectedFiles) {
                retriever.setDataSource(file.getAbsolutePath());
                String durationStr = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
                long duration = Long.parseLong(durationStr);
                totalDuration += duration;
            }
        } catch (Exception e) {
            e.printStackTrace(); // 예외 처리: 로그로 출력하거나 사용자에게 알려줄 수 있습니다.
        } finally {
            try {
                retriever.release(); // IOException 예외를 처리합니다.
            } catch (Exception e) {
                e.printStackTrace(); // IOException을 캐치하여 로그로 출력
            }
        }
        return totalDuration;
    }


    private String formatDuration(long durationInMillis) {
        int totalSeconds = (int) (durationInMillis / 1000);
        int minutes = totalSeconds / 60;
        int seconds = totalSeconds % 60;
        return String.format(Locale.getDefault(), "%02d:%02d", minutes, seconds);
    }

    // 모은 녹음 길이를 "모은 녹음" 카드에 보여 준다: 5분까지 얼마나 남았는지 (#82)
    private void updateTotalProgress() {
        long total = calculateTotalDuration(audioFiles);
        txtTotalRecorded.setText(formatShortDuration(total));
        progressTotal.setProgress((int) Math.min(total / 1000, MIN_TRAINING_MS / 1000));
        if (total >= MIN_TRAINING_MS) {
            txtProgressMessage.setText(R.string.record_enough);
        } else {
            txtProgressMessage.setText(getString(R.string.record_need_more, formatKoreanDuration(MIN_TRAINING_MS - total)));
        }
        txtListHeader.setText(getString(R.string.record_list_count, audioFiles.size()));
        txtListHeader.setVisibility(audioFiles.isEmpty() ? View.GONE : View.VISIBLE);
    }

    // 녹음 중에는 진행 카드 대신 읽을 글과 녹음 시간을 보여 준다
    private void showRecordingPanel(boolean isRecordingNow) {
        recordingPanel.setVisibility(isRecordingNow ? View.VISIBLE : View.GONE);
        progressCard.setVisibility(isRecordingNow ? View.GONE : View.VISIBLE);
        tipsRow.setVisibility(isRecordingNow ? View.GONE : View.VISIBLE);
        if (isRecordingNow) {
            showNextReadText();
        }
    }

    private void showNextReadText() {
        readTextIndex = (readTextIndex + 1) % readTexts.length;
        txtReadText.setText(readTexts[readTextIndex]);
    }

    // 3분 12초 → "3:12"
    private String formatShortDuration(long durationInMillis) {
        int totalSeconds = (int) (durationInMillis / 1000);
        return String.format(Locale.getDefault(), "%d:%02d", totalSeconds / 60, totalSeconds % 60);
    }

    // 108초 → "1분 48초"
    private String formatKoreanDuration(long durationInMillis) {
        int totalSeconds = (int) Math.ceil(durationInMillis / 1000.0);
        int minutes = totalSeconds / 60;
        int seconds = totalSeconds % 60;
        if (minutes == 0) {
            return seconds + "초";
        }
        return seconds == 0 ? minutes + "분" : minutes + "분 " + seconds + "초";
    }

    private void saveSelectedFilePaths(ArrayList<String> selectedFilePaths) {
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        SharedPreferences.Editor editor = sharedPreferences.edit();
        editor.putStringSet("selectedFilePaths", new HashSet<>(selectedFilePaths)); // Set으로 변환하여 저장
        editor.apply();
    }

    private void submitSelectedFiles() {
        ArrayList<File> selectedFiles = adapter.getSelectedFiles();
        if (!selectedFiles.isEmpty()) {
            // 파일 경로 리스트로 변환
            ArrayList<String> selectedFilePaths = new ArrayList<>();
            for (File file : selectedFiles) {
                selectedFilePaths.add(file.getAbsolutePath());
            }

            // 선택한 파일 경로를 SharedPreferences에 저장
            saveSelectedFilePaths(selectedFilePaths);

            // 서버 상태를 확인한 후 TaskStatusActivity로 넘어가는 로직 추가
            checkServerStatus(() -> {
                if (server_status_main && server_status_model) {
                    // TaskStatusActivity로 넘어가기
                    Intent serviceIntent = new Intent(DataLearningActivity.this, TaskCheckService.class);
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) { // 현재 안드로이드 버전 점검
                        startForegroundService(serviceIntent);// 서비스 인텐트를 전달한 foregroundService 시작 메서드 실행
                    }else {
                        startService(serviceIntent);// 서비스 인텐트를 전달한 서비스 시작 메서드 실행
                    }
                    Intent taskStatusIntent = new Intent(DataLearningActivity.this, TaskStatusActivity.class);
                    startActivity(taskStatusIntent);
                } else {
                    // 서버 상태가 정상적이지 않으면 사용자에게 알림
                    showErrorSnackbar(findViewById(R.id.layout));
                }
            });
        }
    }

    private void deleteAudioFile(File audioFile) {
        if (audioFile.exists()) {
            if (audioFile.delete()) {
                loadAudioFiles();
                adapter.notifyDataSetChanged();
                updateTotalProgress();
            } else {
                Snackbar.make(findViewById(R.id.layout), "파일 삭제에 실패했습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            }
        }
    }

    private void loadAudioFiles() {
        File dir = getExternalFilesDir(Environment.DIRECTORY_MUSIC);
        if (dir != null && dir.exists()) {
            File[] files = dir.listFiles();
            if (files != null) {
                audioFiles.clear();
                for (File file : files) {
                    if (file.isFile() && file.getName().endsWith(".m4a")) {
                        audioFiles.add(file);
                    }
                }
            }
        }
    }

    private void playAudio(File audioFile) {
        player = new MediaPlayer();
        try {
            player.setDataSource(audioFile.getAbsolutePath());
            player.prepare();
            player.start();
            isPlaying = true;
            seekBar.setMax(player.getDuration());
            txt_totalTime.setText(formatDuration(player.getDuration()));
            updateSeekBar = new Runnable() {
                @Override
                public void run() {
                    if (player != null) {
                        txt_totalTime.setVisibility(View.VISIBLE);
                        txt_currentTime.setVisibility(View.VISIBLE);
                        txt_currentTime.setText(formatDuration(player.getCurrentPosition()));
                        seekBar.setVisibility(View.VISIBLE);
                        seekBar.setProgress(player.getCurrentPosition());
                    }
                    seekBarHandler.postDelayed(this, 100);
                }
            };
            seekBarHandler.post(updateSeekBar);

            player.setOnCompletionListener(mp -> stopAudio());
        } catch (IOException e) {
            e.printStackTrace();
            Snackbar.make(findViewById(R.id.layout), "재생 실패", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            stopAudio();
        }
    }

    private void stopAudio() {
        ArrayList<File> selectedFiles = adapter.getSelectedFiles();
        if (player != null) {
            try {
                if (player.isPlaying()) {
                    player.stop();
                }
            } catch (IllegalStateException e) {
                e.printStackTrace();
            } finally {
                player.release();
                player = null;
                isPlaying = false;
                seekBarHandler.removeCallbacks(updateSeekBar);
                seekBar.setVisibility(View.GONE);
                seekBar.setProgress(0);
                txt_currentTime.setText("00:00");
                txt_currentTime.setVisibility(View.GONE);
                txt_totalTime.setText("00:00");
                txt_totalTime.setVisibility(View.GONE);
                txt_play.setText(R.string.record_play);
                playing.setImageDrawable(getDrawable(R.drawable.play_arrow));
                updateActionButtonsVisibility(selectedFiles.size());
            }
        }
    }

    private static final int MAX_RECORDING_FILES = 10; // 최대 녹음 파일 수

    private boolean canStartRecording() {
        File dir = getExternalFilesDir(Environment.DIRECTORY_MUSIC);
        if (dir != null && dir.exists()) {
            File[] files = dir.listFiles((file, s) -> s.endsWith(".m4a"));
            return files == null || files.length < MAX_RECORDING_FILES;
        }
        return true;
    }

    private void startRecording() {
        if (!canStartRecording()) {
            Snackbar.make(findViewById(R.id.layout), "녹음 파일의 최대 개수를 초과했습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            return;
        }

        // 날짜 포맷 생성 (연_월_일)
        String dateFormat = new SimpleDateFormat("yyyy_MM_dd", Locale.getDefault()).format(new Date());


        // 해당 날짜에 존재하는 파일의 수를 세어 순번 지정
        File dir = getExternalFilesDir(Environment.DIRECTORY_MUSIC);
        int fileCount = 1; // 기본 순번

        if (dir != null && dir.exists()) {
            File[] files = dir.listFiles((file, name) -> name.startsWith(dateFormat) && name.endsWith(".m4a"));
            if (files != null) {
                fileCount = files.length + 1; // 기존 파일 수 + 1로 새로운 순번 설정
            }
        }

        audioFilePath = dir.getAbsolutePath() + "/" + dateFormat + " " + fileCount + "번 녹음.m4a";

        recorder = new MediaRecorder();
        recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
        recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
        recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
        recorder.setAudioEncodingBitRate(96000);
        recorder.setAudioSamplingRate(44100);
        recorder.setOutputFile(audioFilePath);

        try {
            recorder.prepare();
            recorder.start();
            isRecording = true;

            recordingStartTime = System.currentTimeMillis(); // 녹음 시작 시간 기록
            updateRecordingTime = new Runnable() {
                @Override
                public void run() {
                    if (isRecording) {
                        long elapsedTime = System.currentTimeMillis() - recordingStartTime;
                        txt_recordingTime.setText(formatDuration(elapsedTime));
                        recordingTimeHandler.postDelayed(this, 1000); // 1초마다 업데이트
                    }
                }
            };
            recordingTimeHandler.post(updateRecordingTime); // 타이머 시작

            // 녹음이 성공적으로 시작되었을 때만 버튼 텍스트 변경
            txt_record.setText(R.string.record_stop);
            recording.setImageDrawable(getDrawable(R.drawable.stop));
            recording.setBackground(getDrawable(R.drawable.bg_button_recording));
            showRecordingPanel(true);
        } catch (IOException e) {
            e.printStackTrace();
            Snackbar.make(findViewById(R.id.layout), "녹음 시작에 실패했습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            if (recorder != null) {
                recorder.release();
                recorder = null;
            }
        }
    }

    private void stopRecording() {
        if (recorder != null) {
            try {
                recorder.stop();
            } catch (RuntimeException e) {
                e.printStackTrace();
            } finally {
                recorder.release();
                recorder = null;
                isRecording = false;
                recordingTimeHandler.removeCallbacks(updateRecordingTime); // 타이머 중지
                txt_record.setText(R.string.record_start);
                recording.setImageDrawable(getDrawable(R.drawable.record));
                recording.setBackground(getDrawable(R.drawable.bg_button_primary));
                showRecordingPanel(false);
            }
        }
    }

    private boolean checkPermissions() {
        int recordPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            int readAudioPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_AUDIO);
            int readNotificationPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS);
            return recordPermission == PackageManager.PERMISSION_GRANTED && readAudioPermission == PackageManager.PERMISSION_GRANTED && readNotificationPermission == PackageManager.PERMISSION_GRANTED;
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            int writePermission = ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE);
            return recordPermission == PackageManager.PERMISSION_GRANTED && writePermission == PackageManager.PERMISSION_GRANTED;
        } else {
            return recordPermission == PackageManager.PERMISSION_GRANTED;
        }
    }

    private void requestPermissions() {
        List<String> permissionsNeeded = new ArrayList<>();
        permissionsNeeded.add(Manifest.permission.RECORD_AUDIO);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissionsNeeded.add(Manifest.permission.READ_MEDIA_AUDIO);
            permissionsNeeded.add(Manifest.permission.POST_NOTIFICATIONS);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            permissionsNeeded.add(Manifest.permission.WRITE_EXTERNAL_STORAGE);
        }
        ActivityCompat.requestPermissions(this, permissionsNeeded.toArray(new String[0]), REQUEST_AUDIO_PERMISSION_CODE);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_AUDIO_PERMISSION_CODE) {
            Map<String, Integer> perms = new HashMap<>();
            perms.put(Manifest.permission.RECORD_AUDIO, PackageManager.PERMISSION_GRANTED);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                perms.put(Manifest.permission.READ_MEDIA_AUDIO, PackageManager.PERMISSION_GRANTED);
                perms.put(Manifest.permission.POST_NOTIFICATIONS, PackageManager.PERMISSION_GRANTED);
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                perms.put(Manifest.permission.WRITE_EXTERNAL_STORAGE, PackageManager.PERMISSION_GRANTED);
            }
            boolean allPermissionsGranted = true;
            for (int permResult : perms.values()) {
                if (permResult != PackageManager.PERMISSION_GRANTED) {
                    allPermissionsGranted = false;
                    break;
                }
            }
            if (allPermissionsGranted) {
                Snackbar.make(findViewById(R.id.layout), "권한이 허용되었습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            } else {
                Snackbar.make(findViewById(R.id.layout), "권한이 거부되었습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            }
        }
    }

    private void checkServerStatus(Runnable onSuccess) {
        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .writeTimeout(5, TimeUnit.SECONDS)
                .readTimeout(5, TimeUnit.SECONDS)
                .build();

        Request request = new Request.Builder()
                .url(MainAPI_URL_OnlineCheck)
                .get()
                .build();

        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                e.printStackTrace();
                runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if (response.isSuccessful()) {
                    try (ResponseBody responseBody = response.body()) {
                        String responseBodyString = responseBody.string();
                        JSONObject jsonResponse = new JSONObject(responseBodyString);
                        String status = jsonResponse.getString("status");
                        boolean model_server = jsonResponse.getBoolean("model_server");

                        runOnUiThread(() -> {
                            if ("online".equals(status)) {
                                server_status_main = true;
                                server_status_model = model_server;
                            } else {
                                server_status_main = false;
                            }

                            // 서버 상태 확인 후 성공 시 콜백 실행
                            if (server_status_main && server_status_model) {
                                onSuccess.run();
                            } else {
                                showErrorSnackbar(findViewById(R.id.layout));
                            }
                        });
                    } catch (Exception e) {
                        e.printStackTrace();
                        runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
                    }
                } else {
                    runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
                }
                response.close();
            }
        });
    }


    @Override
    protected void onPause() {
        super.onPause();
        stopAudioIfPlaying();
    }

    private void stopAudioIfPlaying() {
        if (isPlaying) {
            stopAudio();
        }
    }

    // 메뉴 생성
    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        getMenuInflater().inflate(R.menu.back_menu, menu);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()){
            case android.R.id.home: //뒤로가기버튼 클릭
                SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                SharedPreferences.Editor editor = sharedPreferences.edit();
                editor.putBoolean("isTermConfirm", false);
                editor.apply();
                finish();
                return true;
            default:
                break;
        }
        if (item.getItemId() == R.id.action_info) {
            new MaterialAlertDialogBuilder(DataLearningActivity.this)
                    .setTitle(R.string.record_guide_title)
                    .setMessage(getString(R.string.learning_guideline))
                    .setPositiveButton(R.string.ok, null)
                    .show();
        }
        return super.onOptionsItemSelected(item);
    }

    private boolean backPressedOnce = false;
    @Override
    public void onBackPressed() {
        if (backPressedOnce) {
            super.onBackPressed();
            finishAffinity();
        } else {
            this.backPressedOnce = true;
            Snackbar.make(findViewById(R.id.layout), "뒤로 가기 버튼을 한 번 더 누르면 앱이 종료됩니다.", Snackbar.LENGTH_SHORT).show();
            new Handler().postDelayed(() -> backPressedOnce = false, 2000);
        }
    }
    // 스낵바 표시 함수
    public static void showErrorSnackbar(View view) {
        Snackbar.make(view, "학습 서버와 통신이 원활하지 않습니다.\n문제가 지속되면 관리자에게 문의바랍니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
    }
}
