package com.cookandroid.joljag_v1_0;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;

import androidx.appcompat.app.AppCompatActivity;
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

        // 설명 페이지들 리스트 설정
        List<Integer> pages = new ArrayList<>();
        pages.add(R.layout.page_intro_1);
        pages.add(R.layout.page_intro_2);
        pages.add(R.layout.page_intro_3); // 설명 페이지 3개라고 가정

        pagerAdapter = new IntroPagerAdapter(pages, this);
        viewPager.setAdapter(pagerAdapter);

        // 아래 점과 버튼 글자를 지금 페이지에 맞춘다: 마지막 장만 "시작하기" (#80)
        LinearLayout pageDots = findViewById(R.id.page_dots);
        viewPager.registerOnPageChangeCallback(new ViewPager2.OnPageChangeCallback() {
            @Override
            public void onPageSelected(int position) {
                super.onPageSelected(position);
                for (int i = 0; i < pageDots.getChildCount(); i++) {
                    pageDots.getChildAt(i).setSelected(i == position);
                }
                pageDots.requestLayout(); // 지금 페이지 점은 길어져서 크기를 다시 잰다
                boolean isLastPage = position == pages.size() - 1;
                buttonConfirm.setText(isLastPage ? R.string.intro_start : R.string.intro_next);
            }
        });

        buttonConfirm.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                // 마지막 장이 아니면 다음 장으로
                if (viewPager.getCurrentItem() < pages.size() - 1) {
                    viewPager.setCurrentItem(viewPager.getCurrentItem() + 1);
                    return;
                }
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
