package com.cookandroid.joljag_v1_0.utils;

import java.util.List;

public class TranslationRequest {
    private List<String> q;
    private String target;

    public TranslationRequest(List<String> q, String target) {
        this.q = q;
        this.target = target;
    }
}
