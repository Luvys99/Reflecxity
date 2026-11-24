package com.log.reflecxity;

import android.app.Application;

import androidx.appcompat.app.AppCompatDelegate;

// 앱 전체 설정. 새 디자인(시안 C)은 밝은 화면 하나만 있어서, 기기가 다크 모드여도 밝은 화면으로 연다 (#78)
// 화면들이 다크 모드일 때 흰 로고로 바꾸는 코드가 있어서, 여기서 끄지 않으면 모래색 배경에 흰 로고가 나온다
public class ReflecxityApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_NO);
    }
}
