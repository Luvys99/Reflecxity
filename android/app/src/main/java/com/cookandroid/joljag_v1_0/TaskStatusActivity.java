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
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import com.google.android.material.snackbar.Snackbar;

import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.net.URLConnection;
import java.util.ArrayList;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import okhttp3.*;

public class TaskStatusActivity extends AppCompatActivity {

    private TextView info_title;
    private TextView info_txt;
    private TextView userCreationStatus;
    private TextView fileUploadStatus;
    private TextView modelCreationRequest;
    private TextView modelCreationStatus;
    private Button homeButton;
    private Button nextButton;
    private ProgressBar progressBar_creationStatus;
    private ProgressBar progressBar_uploadStatus;
    private ProgressBar progressBar_modelRequest;
    private ProgressBar progressBar_modelStatus;
    private ImageView status_icon;
    private ImageView imageView_creationStatus;
    private ImageView imageView_uploadStatus;
    private ImageView imageView_modelRequest;
    private ImageView imageView_modelStatus;

    String uuid;
    private boolean isUserCreated;
    private boolean isFilesUploaded;
    private boolean isModelRequest;
    private boolean isModelCreated;
    private boolean isPushCreated;
    private boolean isMainEntryTime;
    private boolean server_status_main = false;
    private boolean server_status_model = false;

    private static final String MainAPI_URL = BuildConfig.MainAPI_URL;
    private static final String MainAPI_URL_OnlineCheck = MainAPI_URL + "/online/";
    private static final String MainAPI_URL_USER = BuildConfig.MainAPI_URL_USER;
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

        info_title = findViewById(R.id.info_title);
        info_txt = findViewById(R.id.info_txt);
        userCreationStatus = findViewById(R.id.user_creation_status);
        fileUploadStatus = findViewById(R.id.file_upload_status);
        modelCreationRequest = findViewById(R.id.model_creation_request);
        modelCreationStatus = findViewById(R.id.model_creation_status);
        homeButton = findViewById(R.id.home_button);
        nextButton = findViewById(R.id.next_button);
        progressBar_creationStatus = findViewById(R.id.progressBar_creationStatus);
        progressBar_uploadStatus = findViewById(R.id.progressBar_uploadStatus);
        progressBar_modelRequest = findViewById(R.id.progressBar_modelRequest);
        progressBar_modelStatus = findViewById(R.id.progressBar_modelStatus);
        status_icon = findViewById(R.id.status_icon);
        imageView_creationStatus = findViewById(R.id.imageView_creationStatus);
        imageView_uploadStatus = findViewById(R.id.imageView_uploadStatus);
        imageView_modelRequest = findViewById(R.id.imageView_modelRequest);
        imageView_modelStatus = findViewById(R.id.imageView_modelStatus);

        homeButton.setVisibility(View.GONE);
        nextButton.setVisibility(View.GONE);
        progressBar_creationStatus.setVisibility(View.VISIBLE);
        imageView_creationStatus.setVisibility(View.GONE);
        progressBar_uploadStatus.setVisibility(View.VISIBLE);
        imageView_uploadStatus.setVisibility(View.GONE);
        progressBar_modelRequest.setVisibility(View.VISIBLE);
        imageView_modelRequest.setVisibility(View.GONE);
        progressBar_modelStatus.setVisibility(View.VISIBLE);
        imageView_modelStatus.setVisibility(View.GONE);

        // StatusBar, NavigationBar 색상 변경
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background)); // 원하는 색상으로 변경
        window.setNavigationBarColor(ContextCompat.getColor(this, R.color.background));

        // 시스템 다크 모드 설정 확인
        int currentNightMode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        switch (currentNightMode) {
            case Configuration.UI_MODE_NIGHT_YES:
                // 다크모드
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
            case Configuration.UI_MODE_NIGHT_NO:
                // 라이트모드
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
            case Configuration.UI_MODE_NIGHT_UNDEFINED:
                // 시스템 설정을 알 수 없을 때 (기본 모드 적용)
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
        }

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
                if (server_status_main && server_status_model) {
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
        nextButton.setTextColor(getResources().getColor(R.color.grey200));
        nextButton.setBackgroundColor(getResources().getColor(R.color.grey500));

        checkUser();
        // Task 시작
        startTasks();
    }

    private void checkUser() {
        if (isUserCreated) {
            runOnUiThread(() -> {
                userCreationStatus.setText("사용자 생성 상태: 완료");
                progressBar_creationStatus.setVisibility(View.GONE);
                imageView_creationStatus.setVisibility(View.VISIBLE);
            });
        }
        if (isFilesUploaded) {
            runOnUiThread(() -> {
                fileUploadStatus.setText("파일 업로드 상태: 완료");
                progressBar_uploadStatus.setVisibility(View.GONE);
                imageView_uploadStatus.setVisibility(View.VISIBLE);
            });
        }
        if (isModelRequest) {
            runOnUiThread(() -> {
                modelCreationRequest.setText("모델 생성 요청: 완료");
                progressBar_modelRequest.setVisibility(View.GONE);
                imageView_modelRequest.setVisibility(View.VISIBLE);
            });
        }
        if (isModelCreated) {
            runOnUiThread(() -> {
                modelCreationStatus.setText("모델 생성 상태: 완료");
                progressBar_modelStatus.setVisibility(View.GONE);
                imageView_modelStatus.setVisibility(View.VISIBLE);
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
                .url(MainAPI_URL_USER)
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
                            userCreationStatus.setText("사용자 생성 상태: 완료");
                            progressBar_creationStatus.setVisibility(View.GONE);
                            imageView_creationStatus.setVisibility(View.VISIBLE);
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
                .url(MainAPI_URL_USER + userUUID)
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
                        Boolean model_server = jsonResponse.getBoolean("model_server");

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

                runOnUiThread(() -> fileUploadStatus.setText("파일 업로드 상태: 완료"));
                progressBar_uploadStatus.setVisibility(View.GONE);
                imageView_uploadStatus.setVisibility(View.VISIBLE);
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
                .url(MainAPI_URL_USER + userUuid + "/upload")
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




    private void createModel(String userUuid) {
        OkHttpClient client = new OkHttpClient();
        JSONObject jsonBody = new JSONObject();
        try {
            jsonBody.put("user_uuid", userUuid);
            jsonBody.put("sample_rate", 40000);
            jsonBody.put("cpu_cores", 4);
        } catch (Exception e) {
            e.printStackTrace();
            return;
        }

        RequestBody requestBody = RequestBody.create(MediaType.parse("application/json; charset=utf-8"), jsonBody.toString());
        Request request = new Request.Builder()
                .url(MainAPI_URL_USER + userUuid + "/models")
                .post(requestBody)
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
                            modelCreationRequest.setText("모델 생성 요청: 완료");
                            progressBar_modelRequest.setVisibility(View.GONE);
                            imageView_modelRequest.setVisibility(View.VISIBLE);
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


    // 사용자 대기열 정보 조회 메서드
    private void checkUserQueueStatus(String userUuid) {
        OkHttpClient client = new OkHttpClient();
        // 요청 생성
        Request request = new Request.Builder()
                .url(MainAPI_URL_USER + userUuid + "/queue")
                .get()
                .build();

        // 비동기 요청 실행
        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                // 실패 처리
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
                        int position = jsonResponse.getInt("position");

                        runOnUiThread(() -> {
                            // 대기열 상태 로그
                            Log.d("Queue Status", "상태: " + status + ", 위치: " + position);

                            if (position == 1) {
                                // 대기열 1번 -> 모델 생성 시작
                                runOnUiThread(() -> modelCreationStatus.setText("모델 생성 상태: 생성 중"));

                            } else if (position >= 2) {
                                // 대기열에 있음
                                runOnUiThread(() -> modelCreationStatus.setText("모델 생성 상태: 대기 순번 - " + (position - 1) + "번"));
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


    private void checkModelPeriodically(String userUuid) {
        Handler handler = new Handler();
        handler.postDelayed(() -> checkModel(userUuid), 30000); // (delay/1000) 초마다 모델 상태를 다시 확인
    }

    private void checkModel(String userUuid) {
        OkHttpClient client = new OkHttpClient();

        Request request = new Request.Builder()
                .url(MainAPI_URL_USER + userUuid + "/modelcheck")
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
                        String message = jsonResponse.getString("message");

                        if ("모델 파일 존재".equals(message)) {
                            runOnUiThread(() -> {
                                isModelCreated = true;

                                SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                                SharedPreferences.Editor editor = sharedPreferences.edit();
                                editor.putBoolean("isModelCreated", isModelCreated);
                                editor.apply();

                                saveMainEntryTime(); // 진입 시간 저장

                                runOnUiThread(() -> {
                                    modelCreationStatus.setText("모델 생성 상태: 완료");
                                    progressBar_modelStatus.setVisibility(View.GONE);
                                    imageView_modelStatus.setVisibility(View.VISIBLE);
                                });
                                checkIfAllTasksCompleted(userUuid);
                            });
                        } else {
                            runOnUiThread(() -> {
                                checkUserQueueStatus(userUuid);

                                checkModelPeriodically(userUuid); // 모델 생성 중일 때 다시 확인
                            });
                        }
                    } catch (Exception e) {
                        e.printStackTrace();
                        runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
                    }
                } else if (response.code() == 500) {
                    runOnUiThread(() -> {
                        status_icon.setImageDrawable(getResources().getDrawable(R.drawable.cloud_alert));
                        info_title.setText("학습 오류 발생");
                        info_txt.setText(getString(R.string.learning_error));
                        modelCreationStatus.setText("모델 생성 상태: 오류");
                        progressBar_modelStatus.setVisibility(View.GONE);
                        homeButton.setVisibility(View.VISIBLE);
                        nextButton.setVisibility(View.GONE);

                        imageView_modelStatus.setVisibility(View.VISIBLE);
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
                    });
                } else {
                    runOnUiThread(() -> showErrorSnackbar(findViewById(R.id.layout)));
                }
                response.close();
            }
        });
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
                status_icon.setImageDrawable(getResources().getDrawable(R.drawable.cloud_done));
                info_title.setText("준비 완료!");
                info_txt.setText("이제 서비스를 이용할 준비가 되었어요.\n아래의 다음 버튼을 눌러 메인 화면으로 이동해주세요.");
                homeButton.setVisibility(View.GONE);
                nextButton.setVisibility(View.VISIBLE);
                nextButton.setTextColor(getResources().getColor(R.color.grey900));
                nextButton.setBackgroundColor(getResources().getColor(R.color.btn_green));

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
            createModel(userUuid);
        } else if (isModelRequest && !isModelCreated) {
            checkModel(userUuid);
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