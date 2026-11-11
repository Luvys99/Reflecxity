package com.cookandroid.joljag_v1_0;

import android.Manifest;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.media.MediaPlayer;
import android.os.*;
import android.speech.RecognitionListener;
import android.text.Editable;
import android.text.Html;
import android.text.TextWatcher;
import android.util.Log;
import android.view.*;
import android.view.animation.Animation;
import android.view.animation.AnimationUtils;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.*;
import android.speech.SpeechRecognizer;
import android.speech.RecognizerIntent;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.cookandroid.joljag_v1_0.utils.*;
import com.google.android.material.snackbar.Snackbar;

import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class MainActivity extends AppCompatActivity {

    private EditText inputText;
    private TextView translatedText;
    private TextView selectTv;
    private TextView selectTv2;
    private TextView targetTv;
    private TextView targetTv2;
    private TextView ttsstart_guide;
    private Button recognizeButton;
    private ImageButton tts;
    private ImageButton switchLanguage;
    private SpeechRecognizer speechRecognizer;
    private Intent speechRecognizerIntent;
    private final Handler debounceHandler = new Handler(Looper.getMainLooper());
    private Runnable debounceRunnable;

    private ProgressBar progressBar_ttsloading;

    private boolean isKoreanToEnglish = true; // 한국어 -> 영어 여부 상태
    private boolean isListening = false;  // 음성 인식 중인지 여부

    private File cachedTtsFile; // 캐시된 TTS 파일을 저장할 변수
    private String targetLanguage = "en"; // 영어
    private String previousTtsText = ""; // 이전 TTS 텍스트를 저장할 변수
    private String tts_text;
    private String uuid;
    private String cache_text_translated;
    private int tts_pitch;
    private int previousPitch = 0;
    private boolean isFirst_tts;

    private MediaPlayer mediaPlayer;

    private static final String GoogleAPI_KEY = BuildConfig.GoogleAPI_KEY;
    private static final String MainAPI_URL_USER = BuildConfig.MainAPI_URL_USER;
    private static final int REQUEST_AUDIO_PERMISSION_CODE = 200;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 앱의 첫 실행 여부를 SharedPreferences로 확인
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        boolean isFirstRun = sharedPreferences.getBoolean("isFirstRun", true);
        boolean isUserCreated = sharedPreferences.getBoolean("isUserCreated", false);
        boolean isTermConfirm = sharedPreferences.getBoolean("isTermConfirm", false);

        isFirst_tts = sharedPreferences.getBoolean("isFirst_tts", true);

        if (isFirstRun && !isUserCreated && !isTermConfirm) {
            // 앱이 처음 실행된 적이 없고, UUID가 없는 경우 IntroActivity로 이동
            Intent introIntent = new Intent(MainActivity.this, IntroActivity.class);
            startActivity(introIntent);
            finish();
            Log.d("MainActivity", "Intro 진입");
        } else if (!isFirstRun && !isUserCreated && !isTermConfirm) {
            // 앱이 처음 실행된 적이 있고, UUID가 없으면서 약관 컨펌한 경우 WelcomeActivity로 이동
            Intent welcomeIntent = new Intent(MainActivity.this, WelcomeActivity.class);
            startActivity(welcomeIntent);
            finish();
            Log.d("MainActivity", "Welcome 진입");
        } else if (!isFirstRun && !isUserCreated && isTermConfirm) {
            // 앱이 처음 실행된 적이 있고, UUID가 없으면서 약관 컨펌 한 경우 DataLearningActivity로 이동
            Intent dataLearningIntent = new Intent(MainActivity.this, DataLearningActivity.class);
            startActivity(dataLearningIntent);
            finish();
        } else {
            // 앱이 처음 실행된 적이 있고, UUID가 존재하는 경우 메인 화면을 보여줍니다
            setContentView(R.layout.activity_main);
            Log.d("MainActivity", "Main 진입");
        }

        // Toolbar 설정
        Toolbar toolbar = findViewById(R.id.custom_toolbar);
        ImageView toolbar_title = findViewById(R.id.toolbar_title);
        setSupportActionBar(toolbar);

        // 앱 이름 중앙 정렬
        if (getSupportActionBar() != null) {
            getSupportActionBar().setDisplayShowTitleEnabled(true);
            getSupportActionBar().setTitle("");
        }

        // StatusBar, NavigationBar 색상 변경
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background)); // 원하는 색상으로 변경
        window.setNavigationBarColor(ContextCompat.getColor(this, R.color.background));

        // 시스템 다크 모드 설정 확인
        int currentNightMode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        switch (currentNightMode) {
            case Configuration.UI_MODE_NIGHT_YES:
                // 다크모드
                toolbar_title.setImageDrawable(getDrawable(R.drawable.reflecxity_logo_white_small));
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
            case Configuration.UI_MODE_NIGHT_NO:
                // 라이트모드
                toolbar_title.setImageDrawable(getDrawable(R.drawable.reflecxity_logo_small));
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
            case Configuration.UI_MODE_NIGHT_UNDEFINED:
                // 시스템 설정을 알 수 없을 때 (기본 모드 적용)
                toolbar_title.setImageDrawable(getDrawable(R.drawable.reflecxity_logo_small));
                window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                break;
        }

        inputText = findViewById(R.id.inputText);
        translatedText = findViewById(R.id.translatedText);
        selectTv = findViewById(R.id.selectTv1);
        selectTv2 = findViewById(R.id.selectTv2);
        targetTv = findViewById(R.id.targetTv1);
        targetTv2 = findViewById(R.id.targetTv2);
        ttsstart_guide = findViewById(R.id.ttsstart_guide);
        tts = findViewById(R.id.tts);
        progressBar_ttsloading = findViewById(R.id.progressBar_ttsloading);
        recognizeButton = findViewById(R.id.recognizeButton);
        switchLanguage = findViewById(R.id.switchLanguage);

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this);
        speechRecognizerIntent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR"); // STT 기본값으로 한국어 설정

        Animation switch_anim = AnimationUtils.loadAnimation(getApplicationContext(),R.anim.switch_anim);

        if (!isFirst_tts) {
            ttsstart_guide.setVisibility(View.GONE);
        }

        // 버튼 클릭 시 음성 인식 시작
        recognizeButton.setOnClickListener(v -> {
            if (isListening) {
                stopListening();
                Log.d("GoogleSTT Module", "stopListening");
            } else {
                startListening();
                Log.d("GoogleSTT Module", "startListening");
            }
        });

        // tts 버튼 클릭 시 tts 출력
        tts.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                uuid = sharedPreferences.getString("UUID", null);
                tts_text = translatedText.getText().toString();
                tts_pitch = sharedPreferences.getInt("tts_pitch", 0);

                if (tts_text != null && !tts_text.trim().isEmpty()) {
                    if (tts_text.equals(previousTtsText) && cachedTtsFile != null && cachedTtsFile.exists() && tts_pitch == previousPitch) {
                        // 텍스트가 이전과 같고 캐시된 파일이 있다면 재생
                        playTTS(cachedTtsFile);
                        Log.d("TTS Module", "Play Cached TTS");
                    } else {
                        // 텍스트가 변경되었거나 캐시된 파일이 없으면 새로 요청
                        previousTtsText = tts_text; // 이전 텍스트 업데이트
                        previousPitch = tts_pitch;
                        tts.setVisibility(View.GONE); // 버튼 비활성화
                        progressBar_ttsloading.setVisibility(View.VISIBLE);
                        requestTTS(uuid, tts_text, tts_pitch);
                        Log.d("TTS Module", "request TTS");
                    }
                } else {
                    Snackbar.make(findViewById(R.id.full), "먼저 번역하실 문구를 입력해주세요.", Snackbar.LENGTH_SHORT).setAction("확인", new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
                }
            }
        });

        // 번역 언어 전환 버튼 클릭 리스너
        switchLanguage.setOnClickListener(v -> {
            switchLanguage.startAnimation(switch_anim);
            inputText.setText(cache_text_translated);
            if (isKoreanToEnglish) {
                targetLanguage = "ko"; // 한국어로 번역
                selectTv.setText(R.string.eng);
                selectTv2.setText(R.string.eng);
                targetTv.setText(R.string.kor);
                targetTv2.setText(R.string.kor);
                tts.setVisibility(View.INVISIBLE);
                speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR");  // 한국어
                speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ko-KR");
                speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_ONLY_RETURN_LANGUAGE_PREFERENCE, true);
                Log.d("Translation Activity", "STT Language : ko-KR");
            } else {
                targetLanguage = "en"; // 영어로 번역
                selectTv.setText(R.string.kor);
                selectTv2.setText(R.string.kor);
                targetTv.setText(R.string.eng);
                targetTv2.setText(R.string.eng);
                tts.setVisibility(View.VISIBLE);
                speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US");  // 영어
                speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "en-US");
                speechRecognizerIntent.putExtra(RecognizerIntent.EXTRA_ONLY_RETURN_LANGUAGE_PREFERENCE, true);
                Log.d("Translation Activity", "STT Language : en-US");
            }
            isKoreanToEnglish = !isKoreanToEnglish; // 상태 변경

            // 텍스트 다시 번역
            translateText(inputText.getText().toString());
        });

        inputText.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_DONE || actionId == EditorInfo.IME_ACTION_GO || (event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER)) {
                InputMethodManager imm = (InputMethodManager)getSystemService(INPUT_METHOD_SERVICE);
                imm.hideSoftInputFromWindow(this.getCurrentFocus().getWindowToken(),0);  // 키보드를 내리는 메서드 호출
                inputText.clearFocus();  // 입력 후 EditText에서 포커스를 제거
                return true;
            }
            return false;
        });

        inputText.addTextChangedListener(new TextWatcher() {
        @Override
        public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            // 텍스트가 변경되기 전 동작
        }

        @Override
        public void onTextChanged(CharSequence s, int start, int before, int count) {
            // 텍스트가 변경될 때마다 호출됨
            if (debounceRunnable != null) {
                // 이전 요청이 있다면 취소
                debounceHandler.removeCallbacks(debounceRunnable);
            }

            // 일정 시간 후(500ms) 번역 요청을 보냄 (debouncing)
            debounceRunnable = new Runnable() {
                @Override
                public void run() {
                    translateText(s.toString());
                }
            };
            debounceHandler.postDelayed(debounceRunnable, 250);  // 500ms 대기 후 실행
        }

        @Override
        public void afterTextChanged(Editable s) {
            // 텍스트 변경 후 동작
        }

    });

    speechRecognizer.setRecognitionListener(new RecognitionListener() {
        @Override
        public void onReadyForSpeech(Bundle params) { recognizeButton.setText("음성인식 중지"); }

        @Override
        public void onBeginningOfSpeech() {}

        @Override
        public void onRmsChanged(float rmsdB) {}

        @Override
        public void onBufferReceived(byte[] buffer) {}

        @Override
        public void onEndOfSpeech() { recognizeButton.setText("음성인식"); }

        @Override
        public void onError(int error) {
            recognizeButton.setText("음성인식");

            String message;

            switch (error) {
                case SpeechRecognizer.ERROR_AUDIO:
                    message = "음성 오류";
                    break;
                case SpeechRecognizer.ERROR_CLIENT:
                    message = "클라이언트 오류 (너무 빠르게 요청하고 있지않나요?)";
                    break;
                case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS:
                    message = "마이크 권한 거부됨";
                    break;
                case SpeechRecognizer.ERROR_NETWORK:
                    message = "인터넷 오류";
                    break;
                case SpeechRecognizer.ERROR_NETWORK_TIMEOUT:
                    message = "연결 타임아웃";
                    break;
                case SpeechRecognizer.ERROR_NO_MATCH:
                    message = "단어를 찾을 수 없음";
                    break;
                case SpeechRecognizer.ERROR_RECOGNIZER_BUSY:
                    message = "음성인식이 바쁨";
                    break;
                case SpeechRecognizer.ERROR_SERVER:
                    message = "서버 오류";
                    break;
                case SpeechRecognizer.ERROR_SPEECH_TIMEOUT:
                    message = "서버 타임아웃";
                    break;
                default:
                    message = "알 수 없는 오류";
                    break;
            }
            Snackbar.make(findViewById(R.id.full), "오류: " + message, Snackbar.LENGTH_SHORT).setAction("확인", new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            Log.e("GoogleSTT Module", "Error : " + message);
        }

        @Override
        public void onResults(Bundle results) {
            recognizeButton.setText("음성인식");

            ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
            if (matches != null) {
                // STT로 변환된 텍스트 표시
                inputText.setText(matches.get(0));
            }
        }

        @Override
        public void onPartialResults(Bundle partialResults) {}

        @Override
        public void onEvent(int eventType, Bundle params) {}

    });
}

private void startListening() {
    if (checkPermissions()) {
        speechRecognizer.startListening(speechRecognizerIntent);
        isListening = true;
    } else {
        requestPermissions();
    }

}

private void stopListening() {
    // 음성 인식 중지 및 상태 업데이트
    speechRecognizer.stopListening();
    isListening = false;
}


private void translateText(String originalText) {
    OkHttpClient client = new OkHttpClient.Builder().build();

    Retrofit retrofit = new Retrofit.Builder()
        .baseUrl("https://translation.googleapis.com")
        .client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build();

    TranslationService service = retrofit.create(TranslationService.class);
    TranslationRequest request = new TranslationRequest(Collections.singletonList(originalText), targetLanguage);

    Call<TranslationResponse> call = service.translateText(GoogleAPI_KEY, request);
    call.enqueue(new Callback<TranslationResponse>() {
        @Override
        public void onResponse(Call<TranslationResponse> call, Response<TranslationResponse> response) {
            if (response.isSuccessful() && response.body() != null) {
                String translated = response.body().getData().getTranslations().get(0).getTranslatedText();
                translated = Html.fromHtml(translated).toString();
                translatedText.setText(translated);
                cache_text_translated = translated;
            } else {
                Log.e("TranslateError", "Translation failed: " + response.message());
            }
        }

        @Override
        public void onFailure(Call<TranslationResponse> call, Throwable t) {
            Log.e("TranslateError", "API call failed", t);
        }
    });
}

    // 메뉴 생성
    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        getMenuInflater().inflate(R.menu.main_menu, menu);
        return true;
    }

    // 메뉴 아이템 클릭 리스너
    @Override
    public boolean onOptionsItemSelected(@NonNull MenuItem item) {
        if (item.getItemId() == R.id.action_settings) {
            // 환경설정 액티비티로 이동
            Intent intent = new Intent(MainActivity.this, SettingsActivity.class);

            startActivity(intent);
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    protected void onResume() {
        super.onResume();
        checkUser();
    }

    private boolean checkPermissions() {
        int recordPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            int readAudioPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_AUDIO);
            int readNotificationPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS);
            return recordPermission == PackageManager.PERMISSION_GRANTED && readAudioPermission == PackageManager.PERMISSION_GRANTED && readNotificationPermission == PackageManager.PERMISSION_GRANTED;
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            int writePermission = ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE);
            return recordPermission == PackageManager.PERMISSION_GRANTED && writePermission == PackageManager.PERMISSION_GRANTED;
        } else {
            return recordPermission == PackageManager.PERMISSION_GRANTED;
        }
    }

    private void requestPermissions() {
        List<String> permissionsNeeded = new ArrayList<>();
        permissionsNeeded.add(Manifest.permission.RECORD_AUDIO);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissionsNeeded.add(Manifest.permission.READ_MEDIA_AUDIO);
            permissionsNeeded.add(Manifest.permission.POST_NOTIFICATIONS);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            permissionsNeeded.add(Manifest.permission.WRITE_EXTERNAL_STORAGE);
        }
        ActivityCompat.requestPermissions(this, permissionsNeeded.toArray(new String[0]), REQUEST_AUDIO_PERMISSION_CODE);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_AUDIO_PERMISSION_CODE) {
            Map<String, Integer> perms = new HashMap<>();
            perms.put(Manifest.permission.RECORD_AUDIO, PackageManager.PERMISSION_GRANTED);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                perms.put(Manifest.permission.READ_MEDIA_AUDIO, PackageManager.PERMISSION_GRANTED);
                perms.put(Manifest.permission.POST_NOTIFICATIONS, PackageManager.PERMISSION_GRANTED);
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                perms.put(Manifest.permission.WRITE_EXTERNAL_STORAGE, PackageManager.PERMISSION_GRANTED);
            }
            boolean allPermissionsGranted = true;
            for (int permResult : perms.values()) {
                if (permResult != PackageManager.PERMISSION_GRANTED) {
                    allPermissionsGranted = false;
                    break;
                }
            }
            if (allPermissionsGranted) {
                Snackbar.make(findViewById(R.id.full), "권한이 허용되었습니다.", Snackbar.LENGTH_SHORT).setAction("확인", new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            } else {
                Snackbar.make(findViewById(R.id.full), "권한이 거부되었습니다.", Snackbar.LENGTH_SHORT).setAction("확인", new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            }
        }
    }

    private void checkUser() {
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);
        String uuid = sharedPreferences.getString("UUID", null);
        boolean isModelCreated = sharedPreferences.getBoolean("isModelCreated", false);

        if (uuid == null || uuid.isEmpty()) {
            // UUID가 없는 경우 DataLearningActivity로 이동
            Intent dataLearningIntent = new Intent(MainActivity.this, DataLearningActivity.class);
            startActivity(dataLearningIntent);
            Log.d("CheckUser Module", "DataLearning 진입");
            finish();
        } else if ((uuid != null || !uuid.isEmpty()) && (isModelCreated == false || !isModelCreated)) {
            // Model이 없는 경우 TaskStatusActivity로 이동
            Intent taskStatusIntent = new Intent(MainActivity.this, TaskStatusActivity.class);
            startActivity(taskStatusIntent);
            Log.d("CheckUser Module", "TaskStatus 진입");
            finish();
        }
    }

    private void requestTTS(String userUuid, String tts_text, int tts_pitch) {
        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build();

        // FormBody를 사용하여 데이터를 보내기 위한 준비
        RequestBody requestBody = new FormBody.Builder()
                .add("tts_text", tts_text)
                .add("pitch", String.valueOf(tts_pitch))
                .build();

        // 요청 생성
        Request request = new Request.Builder()
                .url(MainAPI_URL_USER + userUuid + "/tts")
                .post(requestBody) // JSON 대신 Form 데이터 전송
                .build();

        client.newCall(request).enqueue(new okhttp3.Callback() {
            @Override
            public void onFailure(okhttp3.Call call, IOException e) {
                e.printStackTrace();
                runOnUiThread(() -> {
                    tts.setVisibility(View.VISIBLE); // 버튼 활성화
                    progressBar_ttsloading.setVisibility(View.GONE);
                    showErrorSnackbar(findViewById(R.id.full));
                    Log.e("TTS Module", "1번 오류");
                });
            }

            @Override
            public void onResponse(okhttp3.Call call, okhttp3.Response response) throws IOException {
                if (!response.isSuccessful()) {
                    String errorMessage = response.body().string();
                    runOnUiThread(() -> {
                        tts.setVisibility(View.VISIBLE); // 버튼 활성화
                        progressBar_ttsloading.setVisibility(View.GONE);
                        showErrorSnackbar(findViewById(R.id.full));
                        Log.e("TTS Module", "2번 오류");
                    });
                } else {
                    // wav 파일로 응답 받음
                    byte[] wavData = response.body().bytes();

                    // 파일 저장 경로 설정
                    File outputDir = MainActivity.this.getCacheDir(); // 임시 파일 저장 디렉토리
                    File outputFile = new File(outputDir, "output_tts.wav"); // 확장자를 wav로 변경
                    cachedTtsFile = new File(outputDir, "output_tts.wav"); // 캐시 파일로 저장

                    // 파일에 데이터 쓰기
                    try (FileOutputStream fos = new FileOutputStream(outputFile)) {
                        fos.write(wavData);
                        runOnUiThread(() -> {
                            playTTS(outputFile);
                            tts.setVisibility(View.VISIBLE); // 버튼 활성화
                            progressBar_ttsloading.setVisibility(View.GONE);
                        });
                    } catch (IOException e) {
                        e.printStackTrace();
                        runOnUiThread(() -> {
                            tts.setVisibility(View.VISIBLE); // 버튼 활성화
                            progressBar_ttsloading.setVisibility(View.GONE);
                            showErrorSnackbar(findViewById(R.id.full));
                            Log.e("TTS Module", "3번 오류");
                        });
                    }
                }
                response.close();
            }
        });
    }

    private void playTTS(File wavFile) {
        SharedPreferences sharedPreferences = getSharedPreferences("AppPreferences", MODE_PRIVATE);

        if (mediaPlayer != null) {
            mediaPlayer.release(); // 기존의 MediaPlayer 해제
        }
        mediaPlayer = new MediaPlayer();

        try {
            // wav 파일을 설정
            mediaPlayer.setDataSource(wavFile.getAbsolutePath());

            mediaPlayer.prepareAsync();
            mediaPlayer.setOnPreparedListener(mp -> mediaPlayer.start());

            mediaPlayer.setOnCompletionListener(mp -> {
                mp.release();
                mediaPlayer = null; // 해제 후 null로 설정
                if(isFirst_tts){
                    ttsstart_guide.setVisibility(View.GONE);
                    SettingsActivity.showPitchDialog(this, sharedPreferences);
                    isFirst_tts = false;

                    SharedPreferences.Editor editor = sharedPreferences.edit();
                    editor.putBoolean("isFirst_tts", isFirst_tts);
                    editor.apply();
                }
            });

        } catch (IOException e) {
            e.printStackTrace();
            Snackbar.make(findViewById(R.id.full), "오디오 파일 재생 중 오류 발생", Snackbar.LENGTH_SHORT).setAction("확인", new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
            Log.e("TTS Module", "4번 오류");
        }
    }

    private void cleanupResources() {
        // 임시 파일이 존재하는지 확인 후 삭제
        if (cachedTtsFile != null && cachedTtsFile.exists()) {
            cachedTtsFile.delete();
            cachedTtsFile = null;
        }

        // MediaPlayer 해제
        if (mediaPlayer != null) {
            mediaPlayer.release();
            mediaPlayer = null;
        }
    }

    // 스낵바 표시 함수
    public static void showErrorSnackbar(View view) {
        Snackbar.make(view, "서버 통신이 원활하지 않습니다.\n문제가 지속되면 관리자에게 문의바랍니다.", Snackbar.LENGTH_SHORT).setAction("확인",new View.OnClickListener() { @Override public void onClick(View v) {}}).show();
    }

    private boolean backPressedOnce = false;
    @Override
    public void onBackPressed() {
        // 뒤로가기 버튼을 두번 누르면 앱 종료
        if (backPressedOnce) {
            finishAffinity(); // 모든 Activity를 종료하여 앱을 완전히 종료
            return;
        }

        this.backPressedOnce = true;
        Snackbar.make(findViewById(R.id.full), "뒤로 가기 버튼을 한 번 더 누르면 앱이 종료됩니다.", Snackbar.LENGTH_SHORT).show();

        // 2초 후에 backPressedOnce를 false로 설정하여 다시 누를 수 있도록 함
        new android.os.Handler().postDelayed(() -> backPressedOnce = false, 2000);
    }

    @Override
    public void onPause() {
        super.onPause();
        cleanupResources();  // 리소스 정리
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        cleanupResources();  // 리소스 정리
    }
}
