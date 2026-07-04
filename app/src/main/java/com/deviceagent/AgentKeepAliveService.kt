package com.deviceagent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.util.Log

/**
 * Foreground keep-alive service — the survival layer under the self-heal watchdog.
 *
 * The 2026-07-04 incident: an OEM battery-killer took the whole app process down
 * with the wireless-debug listener, leaving a phone with NO listening service and
 * no inbound path — unrecoverable remotely. This service makes that death much
 * less likely and recovery automatic:
 *  - startForeground + persistent notification: exempts the process from most
 *    OEM background killers (HiOS/One UI treat FGS apps as user-visible).
 *  - START_STICKY: if the process is killed anyway, Android re-spawns it, which
 *    also restarts the self-heal watchdog (via accessibility service rebind).
 *  - WifiLock (FULL_HIGH_PERF): WiFi never sleeps, attacking the root cause of
 *    the listener drops in the first place.
 * Started from MainActivity, AgentAccessibilityService.onServiceConnected, and
 * BootReceiver, so every entry point re-arms it.
 */
class AgentKeepAliveService : Service() {

    companion object {
        const val CHANNEL_ID = "deviceagent_keepalive"
        const val NOTIFICATION_ID = 1001

        fun ensureRunning(context: Context) {
            try {
                val intent = Intent(context, AgentKeepAliveService::class.java)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            } catch (e: Exception) {
                Log.e("DeviceAgent", "keep-alive start failed: ${e.message}")
            }
        }
    }

    private var wifiLock: WifiManager.WifiLock? = null

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "DeviceAgent keep-alive",
                    NotificationManager.IMPORTANCE_LOW).apply {
                    description = "Keeps the fleet agent alive so remote recovery always works"
                    setShowBadge(false)
                })
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification: Notification = (
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                Notification.Builder(this, CHANNEL_ID)
            else @Suppress("DEPRECATION") Notification.Builder(this)
        )
            .setContentTitle("DeviceAgent active")
            .setContentText("Fleet agent running — do not dismiss")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .build()
        // CRITICAL: startForeground must NEVER crash the app — a FGS-type/permission
        // failure here would defeat the whole purpose (keeping the agent alive). Try
        // the typed FGS, fall back to untyped, and if even that fails just log and
        // keep running as a background service (HTTP server + self-heal still work).
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notification,
                    android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (e: Exception) {
            Log.e("DeviceAgent", "startForeground(typed) failed: ${e.message} — retrying untyped")
            try { startForeground(NOTIFICATION_ID, notification) }
            catch (e2: Exception) { Log.e("DeviceAgent", "startForeground failed entirely: ${e2.message}") }
        }

        if (wifiLock == null) {
            try {
                val wm = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
                @Suppress("DEPRECATION")
                wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "DeviceAgent:keepalive")
                    .apply { setReferenceCounted(false); acquire() }
                Log.d("DeviceAgent", "keep-alive: foreground + WifiLock acquired")
            } catch (e: Exception) {
                Log.e("DeviceAgent", "WifiLock failed: ${e.message}")
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        try { wifiLock?.release() } catch (_: Exception) {}
        wifiLock = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
