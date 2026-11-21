package com.cookandroid.joljag_v1_0;

import okhttp3.OkHttpClient;
import okhttp3.Request;

// Main 서버로 보내는 요청에 앱 전용 문구(X-App-Key)를 붙인다 (#103)
// 앱을 풀면 보이는 값이라 자물쇠가 아니라, 주소를 찔러 보는 봇을 막는 용도다
public final class MainApi {
    private MainApi() { }

    public static OkHttpClient.Builder newClientBuilder() {
        return new OkHttpClient.Builder().addInterceptor(chain -> {
            Request.Builder request = chain.request().newBuilder();
            if (!BuildConfig.APP_KEY.isEmpty()) {
                request.header("X-App-Key", BuildConfig.APP_KEY);
            }
            return chain.proceed(request.build());
        });
    }

    public static OkHttpClient newClient() {
        return newClientBuilder().build();
    }
}
