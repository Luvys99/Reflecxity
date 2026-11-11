package com.cookandroid.joljag_v1_0;

import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Base64;
import android.view.LayoutInflater;
import android.view.View;
import android.view.Window;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.snackbar.Snackbar;

public class SettingsActivity extends AppCompatActivity {

    public ImageButton button_retrain;
    public ImageButton button_data_transfer;
    public ImageButton device_erase;
    public ImageButton pitch_setting;
    public static boolean isFirst_tts;
    public static boolean isFirst_dialog;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        supportRequestWindowFeature(Window.FEATURE_NO_TITLE);
        setContentView(R.layout.activity_settings);

        button_retrain = findViewById(R.id.button_retrain);
        button_data_transfer = findViewById(R.id.button_data_transfer);
        device_erase = findViewById(R.id.device_erase);
        pitch_setting = findViewById(R.id.pitch_setting);

        button_retrain.setOnClickListener(v -> {
            Intent intent = new Intent(SettingsActivity.this, RetrainActivity.class);
            startActivity(intent);
        });

        button_data_transfer.setOnClickListener(v -> {
            Intent intent = new Intent(SettingsActivity.this, DataTransferActivity.class);
            startActivity(intent);
        });

        // UUID 가져오기
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        String uuid = sharedPreferences.getString("UUID", null);
        isFirst_tts = sharedPreferences.getBoolean("isFirst_tts", true);
        isFirst_dialog = sharedPreferences.getBoolean("isFirst_dialog", true);

        if (uuid != null) {
            // UUID 암호화
            String encryptedUUID = encryptUUID(uuid);
            String QRUUID = "AVCSIA-" + encryptedUUID;

            device_erase.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    if (uuid == null) {
                        Snackbar.make(findViewById(R.id.layout), "사용자 정보를 확인할 수 없습니다. 문제가 계속되면 재설치 해주세요.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
                        return;
                    }

                    // 초기화 여부를 묻는 팝업 표시
                    new AlertDialog.Builder(SettingsActivity.this)
                            .setTitle("초기화 확인")
                            .setMessage("본 기능은 QR을 통한 다른 기기로 데이터 이전 후, 서버에는 데이터를 남기고 기존 기기에서만 데이터를 지우시고 싶으신 경우에 사용할 수 있는 기능입니다. \n\n완전 데이터 삭제를 원하실 경우, 데이터 재학습 기능을 사용해주세요. \n\n 정말로 기기에서 사용자 정보를 삭제하시겠습니까?")
                            .setPositiveButton("삭제", new DialogInterface.OnClickListener() {
                                @Override
                                public void onClick(DialogInterface dialog, int which) {
                                    // SharedPreferences에서 UUID 삭제
                                    SharedPreferences.Editor editor = sharedPreferences.edit();
                                    editor.remove("UUID");
                                    editor.remove("isUserCreated");
                                    editor.remove("isFilesUploaded");
                                    editor.remove("isModelRequest");
                                    editor.remove("isModelCreated");
                                    editor.apply();

                                    // UUID 삭제 후 WelcomeActivity로 이동
                                    Intent welcomeIntent = new Intent(SettingsActivity.this, WelcomeActivity.class);
                                    Intent dataLearningIntent = new Intent(SettingsActivity.this, DataLearningActivity.class);
                                    dataLearningIntent.putExtra("FROM", "ReTrain");
                                    startActivity(welcomeIntent);
                                    finish(); // 현재 Activity 종료
                                }
                            })
                            .setNegativeButton("취소", null) // 취소 버튼을 누르면 팝업만 닫힘
                            .show();
                }
            });
        }

        pitch_setting.setOnClickListener(v -> {
            // showPitchDialog() 메서드 호출로 변경
            showPitchDialog(SettingsActivity.this, sharedPreferences);
        });
    }

    public static void showPitchDialog(Context context, SharedPreferences sharedPreferences) {
        // 피치 값을 가져오고 초기 설정 여부 확인
        int tts_pitch = sharedPreferences.getInt("tts_pitch", Integer.MIN_VALUE); // 기본값을 Integer.MIN_VALUE로 설정

        if (tts_pitch == Integer.MIN_VALUE) {
            // 피치 값이 설정된 적이 없는 경우 초기값을 0으로 표시
            tts_pitch = 0;
        }

        SharedPreferences.Editor editor = sharedPreferences.edit();

        // 커스텀 뷰를 설정
        View customView = LayoutInflater.from(context).inflate(R.layout.pitch_dialog_custom_view, null);
        TextView pitchTextView = customView.findViewById(R.id.pitch);
        SeekBar seekBar = customView.findViewById(R.id.seek_bar);
        LinearLayout FirstRun = customView.findViewById(R.id.FirstRun);

        if (isFirst_dialog) {
            FirstRun.setVisibility(View.VISIBLE);
            editor.putBoolean("isFirst_dialog", false);
            editor.apply();
        } else {
            FirstRun.setVisibility(View.GONE);
        }

        // 시크바 초기화 (0부터 48까지 설정)
        seekBar.setMax(48);
        seekBar.setProgress(tts_pitch + 24); // 초기값을 -24에서 24의 중간인 0으로 설정
        pitchTextView.setText(String.valueOf(tts_pitch));

        // 시크바의 변경 이벤트 리스너 설정
        seekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                int displayedValue = progress - 24; // 실제 표시할 값 (범위: -24 ~ 24)
                pitchTextView.setText(String.valueOf(displayedValue)); // TextView에 표시
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
                // 사용자가 시크바를 터치할 때 호출됨
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
                // 사용자가 시크바의 터치를 멈출 때 호출됨
            }
        });

        // AlertDialog 설정
        new AlertDialog.Builder(context)
                .setView(customView) // 커스텀 뷰를 설정
                .setPositiveButton("저장", (dialog, which) -> {
                    // 다이얼로그 확인 버튼 클릭 시, 현재 시크바 값을 저장
                    int displayedValue = seekBar.getProgress() - 24;
                    editor.putInt("tts_pitch", displayedValue);
                    editor.apply();
                })
                .setNegativeButton("취소", null)
                .show();
    }

    private String encryptUUID(String uuid) {
        // 단순한 Base64 인코딩을 예로 사용 (암호화 알고리즘 변경 가능)
        return Base64.encodeToString(uuid.getBytes(), Base64.DEFAULT);
    }
}
