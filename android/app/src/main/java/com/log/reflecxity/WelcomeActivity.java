package com.log.reflecxity;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.view.View;
import android.widget.ImageView;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.snackbar.Snackbar;

public class WelcomeActivity extends AppCompatActivity {

    ImageView appLogo;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_welcome);

        appLogo = findViewById(R.id.app_logo);

        findViewById(R.id.newUser).setOnClickListener(v -> {
            Intent newUserIntent = new Intent(WelcomeActivity.this, TermsActivity.class);
            startActivity(newUserIntent);
        });

        findViewById(R.id.readQR).setOnClickListener(v -> {
            Intent qrIntent = new Intent(WelcomeActivity.this, QRScanActivity.class);
            startActivity(qrIntent);
        });

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
