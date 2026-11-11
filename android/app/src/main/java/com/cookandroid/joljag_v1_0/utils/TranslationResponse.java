package com.cookandroid.joljag_v1_0.utils;

import java.util.List;

public class TranslationResponse {
    private Data data;

    public Data getData() {
        return data;
    }

    public class Data {
        private List<Translation> translations;

        public List<Translation> getTranslations() {
            return translations;
        }
    }

    public class Translation {
        private String translatedText;

        public String getTranslatedText() {
            return translatedText;
        }
    }
}
