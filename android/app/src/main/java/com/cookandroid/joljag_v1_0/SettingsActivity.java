package com.cookandroid.joljag_v1_0;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Base64;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.SeekBar;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;

import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.snackbar.Snackbar;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

// 설정 (#87): 목소리 높이, 다시 학습, 다른 기기로 옮기기, 이 기기에서 지우기
public class SettingsActivity extends AppCompatActivity {
    // 사용자가 피치를 저장한 적 없음. 이때 TTS 요청에 피치를 보내지 않아 서버가 학습 때 잰 자동 피치를 쓴다 (#72)
    public static final int PITCH_NOT_SET = Integer.MIN_VALUE;
    // 서버가 자동 피치를 −12 ~ +12로 제한한다 (#59). 직접 조절도 같은 범위
    private static final int MAX_PITCH = 12;

    public View buttonRetrain;
    public View buttonDataTransfer;
    public View deviceErase;
    public View pitchSetting;
    private TextView txtPitchValue;
    private SharedPreferences sharedPreferences;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        Toolbar toolbar = findViewById(R.id.settings_toolbar);
        toolbar.setNavigationOnClickListener(v -> finish());

        buttonRetrain = findViewById(R.id.button_retrain);
        buttonDataTransfer = findViewById(R.id.button_data_transfer);
        deviceErase = findViewById(R.id.device_erase);
        pitchSetting = findViewById(R.id.pitch_setting);
        txtPitchValue = findViewById(R.id.txt_pitch_value);

        ((TextView) findViewById(R.id.txt_version)).setText(getString(R.string.settings_version, BuildConfig.VERSION_NAME));
        findViewById(R.id.button_terms).setOnClickListener(v -> showTerms());

        buttonRetrain.setOnClickListener(v -> {
            Intent intent = new Intent(SettingsActivity.this, RetrainActivity.class);
            startActivity(intent);
        });

        buttonDataTransfer.setOnClickListener(v -> {
            Intent intent = new Intent(SettingsActivity.this, DataTransferActivity.class);
            startActivity(intent);
        });

        sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        String uuid = sharedPreferences.getString("UUID", null);

        deviceErase.setOnClickListener(v -> {
            if (uuid == null) {
                Snackbar.make(findViewById(R.id.layout), R.string.settings_no_user, Snackbar.LENGTH_SHORT).setAction(R.string.ok, view -> {}).show();
                return;
            }

            // 지울지 묻고, 지우면 이 기기의 사용자 정보만 지운 뒤 시작 화면으로 (서버 데이터는 남는다)
            new MaterialAlertDialogBuilder(SettingsActivity.this)
                    .setTitle(R.string.settings_erase_title)
                    .setMessage(R.string.settings_erase_message)
                    .setPositiveButton(R.string.record_delete, (dialog, which) -> {
                        SharedPreferences.Editor editor = sharedPreferences.edit();
                        editor.remove("UUID");
                        editor.remove("isUserCreated");
                        editor.remove("isFilesUploaded");
                        editor.remove("isModelRequest");
                        editor.remove("isModelCreated");
                        editor.apply();

                        Intent welcomeIntent = new Intent(SettingsActivity.this, WelcomeActivity.class);
                        startActivity(welcomeIntent);
                        finish();
                    })
                    .setNegativeButton(R.string.cancel, null)
                    .show();
        });

        pitchSetting.setOnClickListener(v -> showPitchDialog(this, sharedPreferences, this::showPitchValue));
        showPitchValue();
    }

    // 목록에 지금 목소리 높이를 보여 준다: 저장한 적 없으면 "자동"
    private void showPitchValue() {
        int pitch = sharedPreferences.getInt("tts_pitch", PITCH_NOT_SET);
        txtPitchValue.setText(pitch == PITCH_NOT_SET ? getString(R.string.settings_pitch_auto) : formatPitch(pitch));
    }

    private static String formatPitch(int pitch) {
        return pitch > 0 ? "+" + pitch : String.valueOf(pitch);
    }

    // 목소리 높이 창. 저장하면 그 값을 쓰고, 자동을 누르면 저장한 값을 지워 서버의 자동 피치를 쓴다 (#72, #87)
    public static void showPitchDialog(Context context, SharedPreferences sharedPreferences, Runnable onChanged) {
        int savedPitch = sharedPreferences.getInt("tts_pitch", PITCH_NOT_SET);
        boolean isAuto = savedPitch == PITCH_NOT_SET;
        int startPitch = isAuto ? 0 : Math.max(-MAX_PITCH, Math.min(MAX_PITCH, savedPitch));

        View customView = LayoutInflater.from(context).inflate(R.layout.pitch_dialog_custom_view, null);
        TextView pitchTextView = customView.findViewById(R.id.pitch);
        SeekBar seekBar = customView.findViewById(R.id.seek_bar);

        seekBar.setMax(MAX_PITCH * 2);
        seekBar.setProgress(startPitch + MAX_PITCH);
        pitchTextView.setText(isAuto ? context.getString(R.string.pitch_current_auto) : formatPitch(startPitch));

        seekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                if (fromUser) {
                    pitchTextView.setText(formatPitch(progress - MAX_PITCH));
                }
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) { }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) { }
        });

        SharedPreferences.Editor editor = sharedPreferences.edit();
        new MaterialAlertDialogBuilder(context)
                .setTitle(R.string.pitch_title)
                .setView(customView)
                .setPositiveButton(R.string.save, (dialog, which) -> {
                    editor.putInt("tts_pitch", seekBar.getProgress() - MAX_PITCH);
                    editor.apply();
                    onChanged.run();
                })
                .setNeutralButton(R.string.settings_pitch_auto, (dialog, which) -> {
                    editor.remove("tts_pitch");
                    editor.apply();
                    onChanged.run();
                })
                .setNegativeButton(R.string.cancel, null)
                .show();
    }

    private void showTerms() {
        StringBuilder terms = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(getAssets().open("terms.txt")))) {
            String line;
            while ((line = reader.readLine()) != null) {
                terms.append(line).append('\n');
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
        new MaterialAlertDialogBuilder(this)
                .setTitle(R.string.terms_full)
                .setMessage(terms.toString())
                .setPositiveButton(R.string.close, null)
                .show();
    }

    private String encryptUUID(String uuid) {
        // 단순한 Base64 인코딩을 예로 사용 (암호화 알고리즘 변경 가능)
        return Base64.encodeToString(uuid.getBytes(), Base64.DEFAULT);
    }
}
