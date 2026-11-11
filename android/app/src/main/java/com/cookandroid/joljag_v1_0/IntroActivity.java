package com.cookandroid.joljag_v1_0;

import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;
import androidx.viewpager2.widget.ViewPager2;
import java.util.ArrayList;
import java.util.List;

public class IntroActivity extends AppCompatActivity {

    private ViewPager2 viewPager;
    private Button buttonConfirm;
    private IntroPagerAdapter pagerAdapter;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_intro);

        viewPager = findViewById(R.id.viewPager);
        buttonConfirm = findViewById(R.id.button_confirm);

        // StatusBar, NavigationBar 색상 변경
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.btn_green)); // 원하는 색상으로 변경
        window.setNavigationBarColor(ContextCompat.getColor(this, R.color.btn_green));

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

        // 설명 페이지들 리스트 설정
        List<Integer> pages = new ArrayList<>();
        pages.add(R.layout.page_intro_1);
        pages.add(R.layout.page_intro_2);
        pages.add(R.layout.page_intro_3); // 설명 페이지 3개라고 가정

        pagerAdapter = new IntroPagerAdapter(pages, this);
        viewPager.setAdapter(pagerAdapter);

        viewPager.registerOnPageChangeCallback(new ViewPager2.OnPageChangeCallback() {
            @Override
            public void onPageSelected(int position) {
                super.onPageSelected(position);
                // 마지막 페이지에서만 버튼 보이기
                if (position == pages.size() - 3) {
                    buttonConfirm.setVisibility(View.GONE);
                    //Toast.makeText(IntroActivity.this, "1번", Toast.LENGTH_SHORT).show();
                } else if (position == pages.size() - 2) {
                    buttonConfirm.setVisibility(View.GONE);
                    //Toast.makeText(IntroActivity.this, "2번", Toast.LENGTH_SHORT).show();
                } else {
                    buttonConfirm.setVisibility(View.VISIBLE);
                }
            }
        });

        buttonConfirm.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                SharedPreferences.Editor editor = sharedPreferences.edit();
                editor.putBoolean("isFirstRun", false);
                editor.apply();

                Intent welcomeIntent = new Intent(IntroActivity.this, WelcomeActivity.class);
                startActivity(welcomeIntent);
            }
        });
    }
}
