package com.cookandroid.joljag_v1_0;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.annotation.RequiresApi;

public class TaskCheckService extends Service {

    private static final String TAG = "MyServiceTag";
    boolean thread_switch = true;

    public TaskCheckService() {
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "onCreate");
    }

    @RequiresApi(api = Build.VERSION_CODES.O)
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {



        final String CHANNELID = "notification_channel";
        NotificationChannel channel = new NotificationChannel(
                CHANNELID,
                CHANNELID,
                NotificationManager.IMPORTANCE_HIGH);

        getSystemService(NotificationManager.class).createNotificationChannel(channel);
        Notification.Builder notification = new Notification.Builder(this, CHANNELID)
                .setContentTitle("목소리 학습 진행 중..")
                .setContentText("학습 완료 시, 알림으로 알려드리겠습니다! 조금만 기다려주세요:)")
                .setSmallIcon(R.drawable.engineering)
                .setOngoing(true);

        startForeground(1, notification.build());

        new Thread(new Runnable() {
            @Override
            public void run() {
                while (thread_switch) {

                    Log.e("Service", "서비스가 실행 중입니다...");
                    try {
                        Thread.sleep(5000);
                    } catch (Exception e) {
                        e.printStackTrace();
                    }

                }
            }
        }).start();

        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        thread_switch = false;
        Log.d(TAG, "onDestroy");
    }
}