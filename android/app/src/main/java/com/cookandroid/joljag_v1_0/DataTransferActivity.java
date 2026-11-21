package com.cookandroid.joljag_v1_0;

import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.os.Bundle;
import android.os.CountDownTimer;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.google.zxing.BarcodeFormat;
import com.google.zxing.EncodeHintType;
import com.google.zxing.MultiFormatWriter;
import com.google.zxing.WriterException;
import com.google.zxing.common.BitMatrix;
import com.journeyapps.barcodescanner.BarcodeEncoder;

import java.util.HashMap;
import java.util.Map;

public class DataTransferActivity extends AppCompatActivity {

    private View qrCodeBackground;
    private ImageView qrCodeImageView;
    private TextView buttonQRTimer;
    private Button buttonQR;
    private static final int QR_DISPLAY_TIME = 15000; // 15초

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_data_transfer);


        qrCodeImageView = findViewById(R.id.qrCodeImageView);
        qrCodeBackground = findViewById(R.id.qrCodeBackground);
        buttonQRTimer = findViewById(R.id.button_qr_timer);
        buttonQR = findViewById(R.id.button_qr);

        // UUID 가져오기
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        String uuid = sharedPreferences.getString("UUID", null);

        if (uuid != null) {
            // UUID 암호화
            String encryptedUUID = encryptUUID(uuid);
            String QRUUID = "AVCSIA-" + encryptedUUID;

            // QR 보이기 버튼 클릭 시 QR 코드를 15초 동안 표시
            buttonQR.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    generateQRCode(QRUUID);

                    qrCodeImageView.setVisibility(View.VISIBLE);
                    qrCodeBackground.setVisibility(View.GONE);
                    buttonQRTimer.setVisibility(View.VISIBLE);

                    buttonQR.setEnabled(false);

                    startCountDownTimer();

                    // 15초 후 QR 코드를 숨김
                    qrCodeImageView.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            qrCodeImageView.setVisibility(View.GONE);
                            qrCodeBackground.setVisibility(View.VISIBLE);
                            buttonQRTimer.setText(R.string.transfer_hidden);
                            buttonQR.setEnabled(true);
                        }
                    }, QR_DISPLAY_TIME);
                }
            });
        }
    }

    private String encryptUUID(String uuid) {
        // 단순한 Base64 인코딩을 예로 사용 (암호화 알고리즘 변경 가능)
        return Base64.encodeToString(uuid.getBytes(), Base64.DEFAULT);
    }

    private void generateQRCode(String data) {
        // 디스플레이의 가로 너비를 가져옵니다.
        DisplayMetrics displayMetrics = new DisplayMetrics();
        getWindowManager().getDefaultDisplay().getMetrics(displayMetrics);
        int screenWidth = displayMetrics.widthPixels;

        // QR 코드의 크기를 화면 너비의 80%로 설정합니다.
        int qrCodeSize = (int) (screenWidth * 0.8);
        int qrMargin = 2; // 여백 설정

        MultiFormatWriter multiFormatWriter = new MultiFormatWriter();
        try {
            // QR 코드 생성을 위한 힌트 설정
            Map<EncodeHintType, Object> hints = new HashMap<>();
            hints.put(EncodeHintType.MARGIN, qrMargin); // 여백을 설정

            BitMatrix bitMatrix = multiFormatWriter.encode(data, BarcodeFormat.QR_CODE, qrCodeSize, qrCodeSize, hints);
            BarcodeEncoder barcodeEncoder = new BarcodeEncoder();
            qrCodeImageView.setImageBitmap(barcodeEncoder.createBitmap(bitMatrix));
        } catch (WriterException e) {
            e.printStackTrace();
        }
    }

    private void startCountDownTimer() {
        new CountDownTimer(QR_DISPLAY_TIME, 1000) {
            @Override
            public void onTick(long millisUntilFinished) {
                buttonQRTimer.setText(getString(R.string.transfer_remaining, (int) (millisUntilFinished / 1000)));
            }

            @Override
            public void onFinish() {
                buttonQRTimer.setText(R.string.transfer_hidden);
            }
        }.start();
    }
}