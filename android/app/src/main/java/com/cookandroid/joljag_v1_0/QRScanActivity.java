package com.cookandroid.joljag_v1_0;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Base64;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;

import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

public class QRScanActivity extends AppCompatActivity {

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        startQRScanner();
    }

    private void startQRScanner() {
        IntentIntegrator integrator = new IntentIntegrator(this);
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE);
        integrator.setPrompt("QR 코드를 스캔하세요");
        integrator.setCameraId(0);  // 후면 카메라 사용
        integrator.setBeepEnabled(false);
        integrator.setBarcodeImageEnabled(false);
        integrator.setOrientationLocked(false); // 가로, 세로 모드 자동으로 변경
        integrator.initiateScan();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        IntentResult result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data);
        if (result != null) {
            if (result.getContents() != null && result.getContents().startsWith("AVCSIA-")) {
                // 스캔된 데이터가 있을 경우 (암호화된 UUID를 해독)
                String scannedData = result.getContents().substring("AVCSIA-".length());
                String decodedUUID = decryptUUID(scannedData);
                saveUUID(decodedUUID);
                Toast.makeText(this, "사용자 정보가 저장되었습니다.", Toast.LENGTH_SHORT).show();

                SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
                SharedPreferences.Editor editor = sharedPreferences.edit();
                editor.putBoolean("isFirstRun", false);
                editor.apply();

                Intent intent = new Intent(QRScanActivity.this, MainActivity.class);
                startActivity(intent);
                finish();
            } else if (result.getContents() == null) {
                Toast.makeText(this, "QR 코드 스캔이 취소되었습니다.", Toast.LENGTH_SHORT).show();
                finish();
            } else {
                Toast.makeText(this, "사용자 정보가 유효하지 않습니다.", Toast.LENGTH_SHORT).show();
                finish();
            }
        }

    }

    private void saveUUID(String uuid) {
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        SharedPreferences.Editor editor = sharedPreferences.edit();
        editor.putString("UUID", uuid);
        editor.putBoolean("isUserCreated", true);
        editor.putBoolean("isFilesUploaded", true);
        editor.putBoolean("isModelRequest", true);
        editor.putBoolean("isModelCreated", true);
        editor.apply();
    }

    private String decryptUUID(String encodedUUID) {
        // Base64 디코딩을 사용하여 암호화된 UUID를 해독
        byte[] decodedBytes = Base64.decode(encodedUUID, Base64.DEFAULT);
        return new String(decodedBytes);
    }
}