package com.deviceagent

import android.content.Context
import android.os.BatteryManager
import android.net.wifi.WifiManager
import android.provider.Settings
import org.eclipse.paho.client.mqttv3.*
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject

/**
 * MQTT manager for heartbeat publishing and command subscription.
 * Connects to Solace MQTT broker (compatible with the orchestrator's Pub/Sub).
 *
 * Heartbeat: published to {heartbeatTopic}/{deviceId}
 * Command:   subscribed to {commandTopic}/{deviceId}
 */
class MqttManager(
    private val context: Context,
    private val brokerUrl: String,       // e.g. "tcp://192.168.0.100:1883"
    private val username: String,
    private val password: String,
    private val heartbeatTopic: String,  // e.g. "device/heartbeat"
    private val commandTopic: String,    // e.g. "device/command"
    private val deviceId: String         // unique device identifier
) {
    companion object {
        private const val TAG = "DeviceAgent-MQTT"
        private const val HEARTBEAT_INTERVAL_MS = 30_000L  // 30 seconds
        private const val QOS = 1
    }

    private var client: MqttAsyncClient? = null
    private var running = false
    private var heartbeatThread: Thread? = null
    private var onCommand: ((JSONObject) -> Unit)? = null

    /** Set callback for incoming commands */
    fun onCommand(callback: (JSONObject) -> Unit) {
        onCommand = callback
    }

    fun start() {
        running = true
        val clientId = "${deviceId}-agent"
        client = MqttAsyncClient(brokerUrl, clientId, MemoryPersistence()).apply {
            setCallback(object : MqttCallback {
                override fun connectionLost(cause: Throwable?) {
                    android.util.Log.w(TAG, "Connection lost: ${cause?.message}")
                    if (running) reconnect()
                }
                override fun messageArrived(topic: String?, message: MqttMessage?) {
                    if (topic == null || message == null) return
                    try {
                        val json = JSONObject(String(message.payload))
                        android.util.Log.d(TAG, "Command received: $json")
                        onCommand?.invoke(json)
                    } catch (e: Exception) {
                        android.util.Log.e(TAG, "Invalid command: ${e.message}")
                    }
                }
                override fun deliveryComplete(token: IMqttDeliveryToken?) {}
            })
        }
        connect()
    }

    private fun connect() {
        try {
            val opts = MqttConnectOptions().apply {
                userName = this@MqttManager.username
                password = this@MqttManager.password.toCharArray()
                isCleanSession = true
                connectionTimeout = 10
                keepAliveInterval = 60
                isAutomaticReconnect = true
            }
            client?.connect(opts)?.waitForCompletion(10_000)

            // Subscribe to command topic
            val cmdTopic = "$commandTopic/$deviceId"
            client?.subscribe(cmdTopic, QOS)
            android.util.Log.d(TAG, "Connected. Subscribed to: $cmdTopic")

            // Start heartbeat thread
            startHeartbeat()
        } catch (e: Exception) {
            android.util.Log.e(TAG, "Connect failed: ${e.message}")
            if (running) {
                android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({ connect() }, 10_000)
            }
        }
    }

    private fun reconnect() {
        try { client?.disconnect() } catch (_: Exception) {}
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            if (running) connect()
        }, 5_000)
    }

    private fun startHeartbeat() {
        heartbeatThread = Thread {
            while (running) {
                try {
                    publishHeartbeat()
                    Thread.sleep(HEARTBEAT_INTERVAL_MS)
                } catch (_: InterruptedException) { break
                } catch (e: Exception) {
                    android.util.Log.e(TAG, "Heartbeat error: ${e.message}")
                    Thread.sleep(HEARTBEAT_INTERVAL_MS)
                }
            }
        }.apply {
            name = "mqtt-heartbeat"
            isDaemon = true
            start()
        }
    }

    private fun publishHeartbeat() {
        val battery = getBatteryLevel()
        val rssi = getWifiRssi()
        val ts = System.currentTimeMillis() / 1000

        val payload = JSONObject().apply {
            put("id", deviceId)
            put("bat", battery)
            put("rssi", rssi)
            put("ts", ts)
        }.toString()

        val topic = "$heartbeatTopic/$deviceId"
        client?.publish(topic, MqttMessage(payload.toByteArray()).apply { qos = QOS })
    }

    fun stop() {
        running = false
        heartbeatThread?.interrupt()
        try { client?.disconnect() } catch (_: Exception) {}
        try { client?.close() } catch (_: Exception) {}
    }

    /** Publish a result back after executing a session */
    fun publishResult(result: JSONObject) {
        val topic = "$commandTopic/${deviceId}/result"
        try {
            client?.publish(topic, MqttMessage(result.toString().toByteArray()).apply { qos = QOS })
        } catch (e: Exception) {
            android.util.Log.e(TAG, "Publish result error: ${e.message}")
        }
    }

    private fun getBatteryLevel(): Int {
        val intent = context.registerReceiver(null, android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED))
        val level = intent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = intent?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        return if (scale > 0) (level * 100 / scale) else -1
    }

    private fun getWifiRssi(): Int {
        return try {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            wifi?.connectionInfo?.rssi ?: 0
        } catch (e: Exception) { 0 }
    }
}
