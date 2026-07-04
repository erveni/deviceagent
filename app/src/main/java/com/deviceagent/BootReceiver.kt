package com.deviceagent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/** Restart the keep-alive service after a reboot so a power-cycled phone rejoins
 *  the fleet with no hands (accessibility rebinds on its own; this brings back
 *  the foreground service + WifiLock + notification). */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.d("DeviceAgent", "boot completed — starting keep-alive service")
            AgentKeepAliveService.ensureRunning(context)
        }
    }
}
