package com.cookandroid.joljag_v1_0;

import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.os.Bundle;
import android.os.Handler;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.TextView;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.google.android.material.snackbar.Snackbar;

import org.json.JSONObject;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

public class RetrainActivity extends AppCompatActivity {

    private static final String MainAPI_URL = BuildConfig.MainAPI_URL;
    private static final String MainAPI_URL_OnlineCheck = MainAPI_URL + "/online/";
    private static final String MainAPI_URL_USER = BuildConfig.MainAPI_URL_USER;

    private TextView remainingTimeText;
    private Handler handler = new Handler();
    private Runnable updateTimeRunnable;

    private boolean server_status_main = false;
    private boolean server_status_model = false;

    private static final int timelimit = 300000; //시간 제한 (밀리초)

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_retrain);

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

        Button resetButton = findViewById(R.id.button_reset);
        remainingTimeText = findViewById(R.id.remaining_time_text);

        // SharedPreferences에서 메인 화면에 진입한 시간 가져오기
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        long mainEntryTime = sharedPreferences.getLong("mainEntryTime", 0);
        long currentTime = System.currentTimeMillis();

        // 5분(300,000 밀리초)이 지나지 않았으면 버튼 비활성화
        if (currentTime - mainEntryTime < timelimit) {
            remainingTimeText.setVisibility(View.VISIBLE);
            resetButton.setEnabled(false); // 버튼 비활성화
            long remainingTime = timelimit - (currentTime - mainEntryTime); // 남은 시간 계산

            // 1초마다 남은 시간을 업데이트하는 Runnable
            updateTimeRunnable = new Runnable() {
                @Override
                public void run() {
                    long currentTime = System.currentTimeMillis();
                    long timePassed = currentTime - mainEntryTime;
                    long timeLeft = timelimit - timePassed; // 남은 시간 계산

                    if (timeLeft > 0) {
                        int secondsLeft = (int) (timeLeft / 1000) % 60;
                        int minutesLeft = (int) (timeLeft / 1000) / 60;

                        // 남은 시간 업데이트
                        remainingTimeText.setText(String.format("%02d분 %02d초 이후에 초기화 버튼을 사용할 수 있습니다.", minutesLeft, secondsLeft));
                        handler.postDelayed(this, 1000); // 1초마다 반복 실행
                    } else {
                        // 5분이 지나면 버튼 활성화 및 시간 표시 업데이트 중지
                        resetButton.setEnabled(true);
                        remainingTimeText.setVisibility(View.GONE);
                        handler.removeCallbacks(updateTimeRunnable); // 더 이상 반복하지 않도록 콜백 제거
                    }
                }
            };

            handler.post(updateTimeRunnable); // Runnable 실행 시작

        } else {
            remainingTimeText.setVisibility(View.GONE);
        }

        resetButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                // SharedPreferences에서 UUID 가져오기
                SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                final String userUUID = sharedPreferences.getString("UUID", null);

                if (userUUID == null) {
                    Snackbar.make(findViewById(R.id.layout), "사용자 정보를 확인할 수 없습니다. 문제가 계속되면 재설치 해주세요.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
                    return;
                }

                // 초기화 여부를 묻는 팝업 표시
                new AlertDialog.Builder(RetrainActivity.this)
                        .setTitle("초기화 확인")
                        .setMessage("사용자 정보를 정말로 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.")
                        .setPositiveButton("삭제", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface dialog, int which) {
                                // 서버 상태를 확인한 후 TaskStatusActivity로 넘어가는 로직 추가
                                checkServerStatus(() -> {
                                    if (server_status_main && server_status_model) {
                                        // 서버에서 사용자 삭제 요청
                                        deleteUserFromServer(userUUID);

                                        // SharedPreferences에서 UUID 삭제
                                        SharedPreferences.Editor editor = sharedPreferences.edit();
                                        editor.remove("UUID");
                                        editor.remove("isUserCreated");
                                        editor.remove("isFilesUploaded");
                                        editor.remove("isModelRequest");
                                        editor.remove("isModelCreated");
                                        editor.remove("isPushCreated");
                                        editor.apply();

                                        // UUID 삭제 후 WelcomeActivity로 이동
                                        Intent welcomeIntent = new Intent(RetrainActivity.this, WelcomeActivity.class);
                                        Intent dataLearningIntent = new Intent(RetrainActivity.this, DataLearningActivity.class);
                                        dataLearningIntent.putExtra("FROM", "ReTrain");
                                        startActivity(welcomeIntent);
                                        finish(); // 현재 Activity 종료
                                    } else {
                                        // 서버 상태가 정상적이지 않으면 사용자에게 알림
                                        showErrorSnackbar(findViewById(R.id.layout));
                                    }
                                });
                            }
                        })
                        .setNegativeButton("취소", null) // 취소 버튼을 누르면 팝업만 닫힘
                        .show();
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

    // 스낵바 표시 함수
    public static void showErrorSnackbar(View view) {
        Snackbar.make(view, "서버 통신이 원활하지 않습니다.\n문제가 지속되면 관리자에게 문의바랍니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        handler.removeCallbacks(updateTimeRunnable); // 액티비티가 파괴되면 핸들러의 콜백 제거
    }
}
