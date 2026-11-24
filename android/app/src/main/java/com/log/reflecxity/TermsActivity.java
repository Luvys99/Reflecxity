package com.log.reflecxity;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.widget.CheckBox;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.dialog.MaterialAlertDialogBuilder;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

public class TermsActivity extends AppCompatActivity {

    String readStr = "";
    private boolean isTermConfirm;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_terms);

        isTermConfirm = false;

        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        SharedPreferences.Editor editor = sharedPreferences.edit();
        editor.putBoolean("isTermConfirm", isTermConfirm);
        editor.apply();

        // 약관 전문은 assets/terms.txt를 읽어 "약관 전문 보기" 창으로 보여 준다 (#80)
        try (BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(getAssets().open("terms.txt")))) {
            String str;
            while ((str = bufferedReader.readLine()) != null) {
                readStr += str + "\n";
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
        findViewById(R.id.button_full_terms).setOnClickListener(v ->
                new MaterialAlertDialogBuilder(this)
                        .setTitle(R.string.terms_full)
                        .setMessage(readStr)
                        .setPositiveButton(R.string.close, null)
                        .show());

        // 동의 체크를 해야 다음으로 갈 수 있다
        View confirmButton = findViewById(R.id.button_confirm);
        CheckBox agreeCheck = findViewById(R.id.check_agree);
        agreeCheck.setOnCheckedChangeListener((buttonView, isChecked) -> confirmButton.setEnabled(isChecked));

        findViewById(R.id.button_confirm).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Intent intent = new Intent(TermsActivity.this, DataLearningActivity.class);
                intent.putExtra("FROM", "Terms");
                editor.putBoolean("isTermConfirm", true);
                editor.apply();
                startActivity(intent);
            }
        });

        findViewById(R.id.button_back).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                finish();
            }
        });
    }
}
