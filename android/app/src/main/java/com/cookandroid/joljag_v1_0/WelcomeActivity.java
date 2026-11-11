package com.cookandroid.joljag_v1_0;

import android.content.Intent;
import android.content.res.Configuration;
import android.os.Bundle;
import android.os.Handler;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ImageView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.google.android.material.snackbar.Snackbar;

public class WelcomeActivity extends AppCompatActivity {

    ImageView app_logo;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_welcome);

        app_logo = findViewById(R.id.app_logo);

        findViewById(R.id.newUser).setOnClickListener(v -> {
            Intent newUserIntent = new Intent(WelcomeActivity.this, TermsActivity.class);
            startActivity(newUserIntent);
        });

        findViewById(R.id.readQR).setOnClickListener(v -> {
            Intent qrIntent = new Intent(WelcomeActivity.this, QRScanActivity.class);
            startActivity(qrIntent);
        });

        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.status_green)); // 원하는 색상으로 변경
        window.setNavigationBarColor(ContextCompat.getColor(this, R.color.background));

        // 시스템 다크 모드 설정 확인
        int currentNightMode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        switch (currentNightMode) {
            case Configuration.UI_MODE_NIGHT_YES:
                // 다크모드
                app_logo.setImageDrawable(getResources().getDrawable(R.drawable.reflecxity_logo_white));
                break;
            case Configuration.UI_MODE_NIGHT_NO:
                // 라이트모드
                app_logo.setImageDrawable(getResources().getDrawable(R.drawable.reflecxity_logo));
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
            case Configuration.UI_MODE_NIGHT_UNDEFINED:
                // 시스템 설정을 알 수 없을 때 (기본 모드 적용)
                app_logo.setImageDrawable(getResources().getDrawable(R.drawable.reflecxity_logo));
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
        }
    }

    private boolean backPressedOnce = false;
    @Override
    public void onBackPressed() {
        if (backPressedOnce) {
            super.onBackPressed();
            finishAffinity();
        } else {
            this.backPressedOnce = true;
            Snackbar.make(findViewById(R.id.full), "뒤로 가기 버튼을 한 번 더 누르면 앱이 종료됩니다.", Snackbar.LENGTH_SHORT).show();
            new Handler().postDelayed(() -> backPressedOnce = false, 2000);
        }
    }

}
