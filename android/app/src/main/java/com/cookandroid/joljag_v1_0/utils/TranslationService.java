package com.cookandroid.joljag_v1_0.utils;

import retrofit2.Call;
import retrofit2.http.Body;
import retrofit2.http.Headers;
import retrofit2.http.POST;
import retrofit2.http.Query;

public interface TranslationService {
    @Headers("Content-Type: application/json")
    @POST("/language/translate/v2")
    Call<TranslationResponse> translateText(
            @Query("key") String apiKey,
            @Body TranslationRequest request
    );
}
