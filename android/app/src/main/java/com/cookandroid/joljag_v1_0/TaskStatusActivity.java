package com.cookandroid.joljag_v1_0;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.util.Log;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.progressindicator.CircularProgressIndicator;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import com.google.android.material.snackbar.Snackbar;

import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.net.URLConnection;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import okhttp3.*;

public class TaskStatusActivity extends AppCompatActivity {

    private TextView infoTitle;
    private TextView infoText;
    private TextView userCreationStatus;
    private TextView fileUploadStatus;
    private TextView modelCreationRequest;
    private TextView modelCreationStatus;
    private Button homeButton;
    private Button nextButton;
    private ProgressBar progressBarCreationStatus;
    private ProgressBar progressBarUploadStatus;
    private ProgressBar progressBarModelRequest;
    private ProgressBar progressBarModelStatus;
    private ImageView statusIcon;
    private ImageView imageViewCreationStatus;
    private ImageView imageViewUploadStatus;
    private ImageView imageViewModelRequest;
    private ImageView imageViewModelStatus;

    String uuid;
    private boolean isUserCreated;
    private boolean isFilesUploaded;
    private boolean isModelRequest;
    private boolean isModelCreated;
    private boolean isPushCreated;
    private boolean isMainEntryTime;
    private boolean isMainServerOnline = false;

    // 남은 시간 (#93)
    private CircularProgressIndicator progressRing;
    private View etaBox;
    private View tipsBox;
    private TextView txtEta;
    private TextView txtEtaLabel;
    private long estimatedSeconds;
    private long elapsedBaseSeconds = -1;
    private long elapsedBaseAt;
    private boolean isWaiting;
    private int jobsAhead;
    private final Handler etaHandler = new Handler();
    private Runnable etaTicker;
    private boolean isModelServerOnline = false;

    private static final String MAIN_API_URL = BuildConfig.MAIN_API_URL;
    private static final String ONLINE_CHECK_URL = MAIN_API_URL + "/online";
    private static final String USERS_URL = BuildConfig.MAIN_API_URL + "/users/";
    private static final String CHANNEL_ID = "notification_channel";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_task_status);

        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        uuid = sharedPreferences.getString("UUID", null);
        isUserCreated = sharedPreferences.getBoolean("isUserCreated", false);
        isFilesUploaded = sharedPreferences.getBoolean("isFilesUploaded", false);
        isModelRequest = sharedPreferences.getBoolean("isModelRequest", false);
        isModelCreated = sharedPreferences.getBoolean("isModelCreated", false);
        isPushCreated = sharedPreferences.getBoolean("isPushCreated", false);

        infoTitle = findViewById(R.id.info_title);
        infoText = findViewById(R.id.info_txt);
        userCreationStatus = findViewById(R.id.user_creation_status);
        fileUploadStatus = findViewById(R.id.file_upload_status);
        modelCreationRequest = findViewById(R.id.model_creation_request);
        modelCreationStatus = findViewById(R.id.model_creation_status);
        homeButton = findViewById(R.id.home_button);
        nextButton = findViewById(R.id.next_button);
        progressBarCreationStatus = findViewById(R.id.progressBar_creationStatus);
        progressBarUploadStatus = findViewById(R.id.progressBar_uploadStatus);
        progressBarModelRequest = findViewById(R.id.progressBar_modelRequest);
        progressBarModelStatus = findViewById(R.id.progressBar_modelStatus);
        statusIcon = findViewById(R.id.status_icon);
        imageViewCreationStatus = findViewById(R.id.imageView_creationStatus);
        imageViewUploadStatus = findViewById(R.id.imageView_uploadStatus);
        imageViewModelRequest = findViewById(R.id.imageView_modelRequest);
        imageViewModelStatus = findViewById(R.id.imageView_modelStatus);

        homeButton.setVisibility(View.GONE);
        nextButton.setVisibility(View.GONE);
        progressBarCreationStatus.setVisibility(View.VISIBLE);
        imageViewCreationStatus.setVisibility(View.GONE);
        progressBarUploadStatus.setVisibility(View.VISIBLE);
        imageViewUploadStatus.setVisibility(View.GONE);
        progressBarModelRequest.setVisibility(View.VISIBLE);
        imageViewModelRequest.setVisibility(View.GONE);
        progressBarModelStatus.setVisibility(View.VISIBLE);
        imageViewModelStatus.setVisibility(View.GONE);

        // 남은 시간: 녹음 길이로 예상 학습 시간을 구해 둔다 (#93)
        progressRing = findViewById(R.id.progress_ring);
        etaBox = findViewById(R.id.eta_box);
        txtEta = findViewById(R.id.txt_eta);
        txtEtaLabel = findViewById(R.id.txt_eta_label);
        tipsBox = findViewById(R.id.tips_box);
        Set<String> selectedFilePaths = sharedPreferences.getStringSet("selectedFilePaths", new HashSet<>());
        estimatedSeconds = TrainingTime.estimateSeconds(TrainingTime.totalDurationMs(selectedFilePaths));

        homeButton.setOnClickListener(v -> {
            final String userUUID = sharedPreferences.getString("UUID", null);
            SharedPreferences.Editor editor = sharedPreferences.edit();
            editor.putBoolean("isPushCreated", false);
            editor.apply();

            if (userUUID == null) {
                Snackbar.make(findViewById(R.id.layout), "사용자 정보를 확인할 수 없습니다. 문제가 계속되면 재설치 해주세요.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
                return;
            }
            finish();

            checkServerStatus(() -> {
                if (isMainServerOnline && isModelServerOnline) {
                    // 서버에서 사용자 삭제 요청
                    deleteUserFromServer(userUUID);

                    // SharedPreferences에서 UUID 삭제
                    editor.remove("UUID");
                    editor.remove("isUserCreated");
                    editor.remove("isFilesUploaded");
                    editor.remove("isModelRequest");
                    editor.remove("isModelCreated");
                    editor.remove("isPushCreated");
                    editor.apply();

                    // UUID 삭제 후 WelcomeActivity로 이동
                    Intent welcomeIntent = new Intent(TaskStatusActivity.this, WelcomeActivity.class);
                    Intent dataLearningIntent = new Intent(TaskStatusActivity.this, DataLearningActivity.class);
                    dataLearningIntent.putExtra("FROM", "ReTrain");
                    startActivity(welcomeIntent);
                    finish(); // 현재 Activity 종료
                } else {
                    // 서버 상태가 정상적이지 않으면 사용자에게 알림
                    showErrorSnackbar(findViewById(R.id.layout));
                    Log.e("Remove User", "Server Fail 1");
                }
            });


        });

        nextButton.setOnClickListener(v -> {
            if (isMainEntryTime == false){
                saveMainEntryTime();
            }
            SharedPreferences.Editor editor = sharedPreferences.edit();
            editor.putBoolean("isPushCreated", false);
            editor.apply();

            Intent mainIntent = new Intent(TaskStatusActivity.this, MainActivity.class);
            startActivity(mainIntent);
            finish();
        });

        checkUser();
        // Task 시작
        startTasks();
    }

    private void checkUser() {
        if (isUserCreated) {
            runOnUiThread(() -> {
                userCreationStatus.setText(R.string.step_prepare);
                progressBarCreationStatus.setVisibility(View.GONE);
                imageViewCreationStatus.setVisibility(View.VISIBLE);
            });
        }
        if (isFilesUploaded) {
            runOnUiThread(() -> {
                fileUploadStatus.setText(R.string.step_upload);
                progressBarUploadStatus.setVisibility(View.GONE);
                imageViewUploadStatus.setVisibility(View.VISIBLE);
            });
        }
        if (isModelRequest) {
            runOnUiThread(() -> {
                modelCreationRequest.setText(R.string.step_request);
                progressBarModelRequest.setVisibility(View.GONE);
                imageViewModelRequest.setVisibility(View.VISIBLE);
            });
        }
        if (isModelCreated) {
            runOnUiThread(() -> {
                modelCreationStatus.setText(R.string.step_train);
                progressBarModelStatus.setVisibility(View.GONE);
                imageViewModelStatus.setVisibility(View.VISIBLE);
            });
        }
    }

    private void startTasks() {
        // UUID와 사용자 생성 상태 확인
        if (uuid == null || uuid.isEmpty()) {
            createUser(UserUuid -> {
            });
        } else {
            checkIfAllTasksCompleted(uuid);
        }
    }

    private void createUser(TaskStatusActivity.OnUserCreatedListener listener) {
        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .writeTimeout(10, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build();

        Request request = new Request.Builder()
                .url(MAIN_API_URL + "/users")
                .post(RequestBody.create("", null)) // 빈 POST 요청
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
                        String userUuid = jsonResponse.getString("uuid");

                        isUserCreated = true;

                        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                        SharedPreferences.Editor editor = sharedPreferences.edit();
                        editor.putString("UUID", userUuid);
                        editor.putBoolean("isUserCreated", isUserCreated);
                        editor.apply();

                        runOnUiThread(() -> {
                            userCreationStatus.setText(R.string.step_prepare);
                            progressBarCreationStatus.setVisibility(View.GONE);
                            imageViewCreationStatus.setVisibility(View.VISIBLE);
                            listener.onUserCreated(userUuid);
                        });

                        checkIfAllTasksCompleted(userUuid);

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

    // OkHttp를 사용해 서버에 사용자 삭제 요청을 보내는 메서드
    private void deleteUserFromServer(String userUUID) {
        OkHttpClient client = new OkHttpClient();

        // 요청 생성 (DELETE 요청)
        Request request = new Request.Builder()
                .url(USERS_URL + userUUID)
                .delete()
                .build();

        // 비동기 요청 실행
        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                // 서버 요청 실패 시 처리
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        showErrorSnackbar(findViewById(R.id.layout));
                        Log.e("Remove User", "Server Fail 2");
                    }
                });
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                // 서버 요청 성공 시 처리
                if (response.isSuccessful()) {
                    // 응답 성공
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Snackbar.make(findViewById(R.id.layout), "사용자 정보가 성공적으로 삭제되었습니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
                        }
                    });
                } else {
                    // 응답 실패
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            showErrorSnackbar(findViewById(R.id.layout));
                            Log.e("Remove User", "Server Fail 3");
                        }
                    });
                }
            }
        });
    }

    private void checkServerStatus(Runnable onSuccess) {
        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .writeTimeout(5, TimeUnit.SECONDS)
                .readTimeout(5, TimeUnit.SECONDS)
                .build();

        Request request = new Request.Builder()
                .url(ONLINE_CHECK_URL)
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
                        Boolean modelServer = jsonResponse.getBoolean("model_server");

                        runOnUiThread(() -> {
                            if ("online".equals(status)) {
                                isMainServerOnline = true;
                                isModelServerOnline = modelServer;
                            } else {
                                isMainServerOnline = false;
                            }

                            // 서버 상태 확인 후 성공 시 콜백 실행
                            if (isMainServerOnline && isModelServerOnline) {
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


    private ArrayList<String> loadSelectedFilePaths() {
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        Set<String> selectedFilePathsSet = sharedPreferences.getStringSet("selectedFilePaths", null);
        return selectedFilePathsSet == null ? new ArrayList<>() : new ArrayList<>(selectedFilePathsSet);
    }

    private void uploadFiles(String userUuid) {
        // 기존에는 Intent에서 받았던 파일 경로를 SharedPreferences에서 불러옴
        ArrayList<String> selectedFilePaths = loadSelectedFilePaths();

        if (selectedFilePaths != null && !selectedFilePaths.isEmpty()) {
            ArrayList<File> selectedFiles = new ArrayList<>();
            for (String path : selectedFilePaths) {
                selectedFiles.add(new File(path));
            }

            // 파일 업로드 로직을 사용하여 파일 업로드 진행
            uploadSelectedFiles(userUuid, selectedFiles, () -> {
                isFilesUploaded = true;
                SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                SharedPreferences.Editor editor = sharedPreferences.edit();
                editor.putBoolean("isFilesUploaded", isFilesUploaded);
                editor.apply();

                runOnUiThread(() -> fileUploadStatus.setText(R.string.step_upload));
                progressBarUploadStatus.setVisibility(View.GONE);
                imageViewUploadStatus.setVisibility(View.VISIBLE);
                checkIfAllTasksCompleted(userUuid);
            });
        }
    }

    private void uploadSelectedFiles(String userUuid, ArrayList<File> selectedFiles, TaskStatusActivity.OnFilesUploadedListener listener) {
        OkHttpClient client = new OkHttpClient();

        uploadFileRecursively(userUuid, selectedFiles, 0, client, listener);
    }

    private void uploadFileRecursively(String userUuid, ArrayList<File> selectedFiles, int index, OkHttpClient client, TaskStatusActivity.OnFilesUploadedListener listener) {
        // 모든 파일 업로드가 완료되면 리스너 호출
        if (index >= selectedFiles.size()) {
            runOnUiThread(() -> listener.onFilesUploaded());
            return;
        }

        File file = selectedFiles.get(index);
        String mimeType = URLConnection.guessContentTypeFromName(file.getName());

        if (mimeType == null || mimeType.equals("audio/mpeg")) {
            if (file.getName().endsWith(".m4a")) {
                mimeType = "audio/mp4"; // 수동으로 m4a MIME 타입 설정
            } else if (file.getName().endsWith(".ogg")) {
                mimeType = "audio/ogg";
            }
        }

        // 지원되는 파일 형식 확인
        if (!mimeType.equals("audio/m4a") && !mimeType.equals("audio/mp4") && !mimeType.equals("audio/ogg")) {
            runOnUiThread(() -> Snackbar.make(findViewById(R.id.layout), "허용되지 않는 파일 형식입니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show());
            return;
        }

        // 파일 업로드 요청 생성
        RequestBody fileBody = RequestBody.create(MediaType.parse(mimeType), file);
        MultipartBody requestBody = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", file.getName(), fileBody)
                .build();

        Request request = new Request.Builder()
                .url(USERS_URL + userUuid + "/recordings")
                .post(requestBody)
                .build();

        // 파일 업로드 요청
        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                e.printStackTrace();
                runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
                // 다음 파일 업로드 시도
                uploadFileRecursively(userUuid, selectedFiles, index + 1, client, listener);
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if (response.isSuccessful()) {
                } else {
                    runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
                }
                response.close();

                // 다음 파일 업로드 시도
                uploadFileRecursively(userUuid, selectedFiles, index + 1, client, listener);
            }
        });
    }




    private void requestTraining(String userUuid) {
        OkHttpClient client = new OkHttpClient();
        Request request = new Request.Builder()
                .url(USERS_URL + userUuid + "/training")
                .post(RequestBody.create("", null)) // 빈 POST 요청
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
                    runOnUiThread(() -> {
                        isModelRequest = true;

                        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                        SharedPreferences.Editor editor = sharedPreferences.edit();
                        editor.putBoolean("isModelRequest", isModelRequest);
                        editor.apply();

                        runOnUiThread(() -> {
                            modelCreationRequest.setText(R.string.step_request);
                            progressBarModelRequest.setVisibility(View.GONE);
                            imageViewModelRequest.setVisibility(View.VISIBLE);
                        });
                        checkIfAllTasksCompleted(userUuid);
                    });
                } else {
                    runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
                }
                response.close();
            }
        });
    }


    // 학습 중: 남은 시간 = 예상 학습 시간 - 지난 시간. 서버가 지난 시간을 주면 그 값으로 맞추고, 사이에는 1초마다 앱이 센다 (#93)
    private void showTraining(int elapsedFromServer) {
        isWaiting = false;
        long now = System.currentTimeMillis();
        if (elapsedFromServer >= 0) {
            elapsedBaseSeconds = elapsedFromServer;
            elapsedBaseAt = now;
        } else if (elapsedBaseSeconds < 0) {
            elapsedBaseSeconds = 0; // 서버가 안 주면 학습 중을 처음 본 때부터 센다
            elapsedBaseAt = now;
        }
        startEtaTicker();
    }

    private void showWaiting(int jobsAhead) {
        isWaiting = true;
        this.jobsAhead = jobsAhead;
        startEtaTicker();
    }

    private void startEtaTicker() {
        if (etaTicker != null) {
            updateEta();
            return;
        }
        etaTicker = new Runnable() {
            @Override
            public void run() {
                updateEta();
                etaHandler.postDelayed(this, 1000);
            }
        };
        etaHandler.post(etaTicker);
    }

    private void updateEta() {
        if (isWaiting) {
            txtEtaLabel.setText(getString(R.string.training_waiting_ahead, jobsAhead));
            txtEta.setText(R.string.training_waiting);
            return;
        }
        long elapsed = elapsedBaseSeconds + (System.currentTimeMillis() - elapsedBaseAt) / 1000;
        long remaining = estimatedSeconds - elapsed;
        txtEtaLabel.setText(R.string.training_remaining_label);
        txtEta.setText(remaining <= 30 ? getString(R.string.training_almost) : getString(R.string.training_remaining, (int) Math.ceil(remaining / 60.0)));
        if (progressRing.isIndeterminate()) {
            // 보이는 동안에는 바꿀 수 없어서 잠깐 숨긴다
            progressRing.setVisibility(View.INVISIBLE);
            progressRing.setIndeterminate(false);
            progressRing.setVisibility(View.VISIBLE);
        }
        progressRing.setProgressCompat((int) Math.min(99, elapsed * 100 / Math.max(1, estimatedSeconds)), true);
    }

    // 끝(완료·실패): 남은 시간 대신 아이콘, 기다리는 동안 안내는 숨긴다
    private void showFinished(int iconRes, int tintRes) {
        if (etaTicker != null) {
            etaHandler.removeCallbacks(etaTicker);
        }
        progressRing.setVisibility(View.GONE);
        etaBox.setVisibility(View.GONE);
        tipsBox.setVisibility(View.GONE);
        statusIcon.setImageResource(iconRes);
        statusIcon.setColorFilter(ContextCompat.getColor(this, tintRes));
        statusIcon.setVisibility(View.VISIBLE);
    }

    private void checkTrainingLater(String userUuid) {
        Handler handler = new Handler();
        handler.postDelayed(() -> checkTraining(userUuid), 10000); // 10초마다 모델 상태를 다시 확인 (학습이 약 5분이라 30초는 늦었다, #93)
    }

    // 학습 상태를 한 번에 묻는다 (#63): status 값으로 대기·학습 중·완료·실패를 나눈다
    private void checkTraining(String userUuid) {
        OkHttpClient client = new OkHttpClient();

        Request request = new Request.Builder()
                .url(USERS_URL + userUuid + "/training")
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
                        int position = jsonResponse.optInt("position", 0);
                        // 학습 중이면 서버가 학습을 시작한 뒤 지난 초를 준다 (#89). 없으면 -1
                        int elapsedSeconds = jsonResponse.optInt("elapsed_seconds", -1);
                        Log.d("Training Status", "상태: " + status + ", 위치: " + position);

                        if ("success".equals(status)) {
                            runOnUiThread(() -> {
                                isModelCreated = true;

                                SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                                SharedPreferences.Editor editor = sharedPreferences.edit();
                                editor.putBoolean("isModelCreated", isModelCreated);
                                editor.apply();

                                saveMainEntryTime(); // 진입 시간 저장

                                modelCreationStatus.setText(R.string.step_train);
                                progressBarModelStatus.setVisibility(View.GONE);
                                imageViewModelStatus.setVisibility(View.VISIBLE);
                                checkIfAllTasksCompleted(userUuid);
                            });
                        } else if ("queued".equals(status) || "progress".equals(status)) {
                            runOnUiThread(() -> {
                                if ("progress".equals(status)) {
                                    modelCreationStatus.setText(R.string.step_train_now);
                                    showTraining(elapsedSeconds);
                                } else {
                                    // 내 앞에 position - 1개
                                    modelCreationStatus.setText(getString(R.string.step_train_wait, position - 1));
                                    showWaiting(position - 1);
                                }
                                checkTrainingLater(userUuid); // 끝날 때까지 다시 확인
                            });
                        } else {
                            // fail, 또는 학습 요청이 사라짐(none): 처음부터 다시 해야 한다
                            Log.e("Training Status", "학습 실패: " + jsonResponse.optString("error", status));
                            runOnUiThread(() -> showTrainingFailed());
                        }
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

    private void showTrainingFailed() {
        showFinished(R.drawable.cloud_alert, R.color.danger);
        infoTitle.setText(R.string.training_fail_title);
        infoText.setText(getString(R.string.learning_error));
        modelCreationStatus.setText(R.string.step_train_fail);
        progressBarModelStatus.setVisibility(View.GONE);
        homeButton.setVisibility(View.VISIBLE);
        nextButton.setVisibility(View.GONE);

        imageViewModelStatus.setVisibility(View.VISIBLE);
        showModelErrorSnackbar(findViewById(R.id.layout));

        Intent serviceIntent = new Intent(TaskStatusActivity.this, TaskCheckService.class);
        stopService(serviceIntent);

        if(isPushCreated) {

        } else {
            createNotificationChannel();
            sendErrorPushNotification();

            SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
            SharedPreferences.Editor editor = sharedPreferences.edit();
            editor.putBoolean("isPushCreated", true);
            editor.apply();
        }
    }

    private void sendSuccessPushNotification() {
        Intent notificationIntent = new Intent(this, TaskStatusActivity.class);
        notificationIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);

        // PendingIntent 생성, FLAG_IMMUTABLE 추가 (Android 12 이상 필수)
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                0,
                notificationIntent,
                PendingIntent.FLAG_IMMUTABLE
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.cloud_done)
                .setContentTitle("목소리 학습 완료!")
                .setContentText("자세한 내용은 앱을 통해 확인해주세요.")
                .setContentIntent(pendingIntent)
                .setPriority(NotificationCompat.PRIORITY_HIGH);

        NotificationManager notificationManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        notificationManager.notify(1, builder.build());
    }

    private void sendErrorPushNotification() {
        Intent notificationIntent = new Intent(this, TaskStatusActivity.class);
        notificationIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);

        // PendingIntent 생성, FLAG_IMMUTABLE 추가 (Android 12 이상 필수)
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                0,
                notificationIntent,
                PendingIntent.FLAG_IMMUTABLE
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.cloud_alert)
                .setContentTitle("목소리 학습 오류 발생")
                .setContentText("자세한 내용은 앱을 통해 확인해주세요.")
                .setContentIntent(pendingIntent)
                .setPriority(NotificationCompat.PRIORITY_HIGH);

        NotificationManager notificationManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        notificationManager.notify(1, builder.build());
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            CharSequence name = "Notification Channel";
            String description = "Channel for push notifications";
            int importance = NotificationManager.IMPORTANCE_HIGH;
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, name, importance);
            channel.setDescription(description);

            NotificationManager notificationManager = getSystemService(NotificationManager.class);
            notificationManager.createNotificationChannel(channel);
        }
    }

    private void checkIfAllTasksCompleted(String userUuid) {
        if (isUserCreated && isFilesUploaded && isModelRequest && isModelCreated) {
            runOnUiThread(() -> {
                showFinished(R.drawable.check_circle, R.color.success);
                infoTitle.setText(R.string.training_done_title);
                infoText.setText(R.string.training_done_body);
                homeButton.setVisibility(View.GONE);
                nextButton.setVisibility(View.VISIBLE);

                Intent serviceIntent = new Intent(TaskStatusActivity.this, TaskCheckService.class);
                stopService(serviceIntent);

                if(isPushCreated) {

                } else {
                    createNotificationChannel();
                    sendSuccessPushNotification();

                    SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                    SharedPreferences.Editor editor = sharedPreferences.edit();
                    editor.putBoolean("isPushCreated", true);
                    editor.apply();
                }
            });
        }  else if (isUserCreated && !isFilesUploaded) {
            uploadFiles(userUuid);
        } else if (isFilesUploaded && !isModelRequest) {
            requestTraining(userUuid);
        } else if (isModelRequest && !isModelCreated) {
            checkTraining(userUuid);
        }
    }

    interface OnUserCreatedListener {
        void onUserCreated(String userUuid);
    }

    interface OnFilesUploadedListener {
        void onFilesUploaded();
    }

    private void saveMainEntryTime() {
        isMainEntryTime = true;
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        SharedPreferences.Editor editor = sharedPreferences.edit();
        editor.putLong("mainEntryTime", System.currentTimeMillis());
        editor.apply();
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
        Snackbar.make(view, "학습 서버 통신이 원활하지 않습니다.\n문제가 지속되면 관리자에게 문의바랍니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
    }

    public static void showModelErrorSnackbar(View view) {
        Snackbar.make(view, "모델 생성에 문제가 발생하였습니다.\n학습을 처음부터 다시 시도해주세요.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
    }

}