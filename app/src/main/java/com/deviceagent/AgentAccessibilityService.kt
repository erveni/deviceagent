package com.deviceagent

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.GestureDescription
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Path
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class AgentAccessibilityService : AccessibilityService() {

    companion object {
        var instance: AgentAccessibilityService? = null
            private set
        var onLog: ((String) -> Unit)? = null
        var httpServer: AgentHttpServer? = null
            private set
        var mqttManager: MqttManager? = null
            private set
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        // Ensure Enhanced Web Accessibility is ON — required for React SPAs like ChatGPT
        val info = serviceInfo
        info.flags = info.flags or AccessibilityServiceInfo.FLAG_REQUEST_ENHANCED_WEB_ACCESSIBILITY
        serviceInfo = info
        log("Service connected")

        // Start HTTP API server for automated execution
        httpServer = AgentHttpServer(FlowEngine(this))
        httpServer?.start()
        log("HTTP API ready on port ${AgentHttpServer.PORT}")

        // Start MQTT for heartbeat + command subscription
        startMqttIfConfigured()
    }

    fun startMqttIfConfiguredPublic() { startMqttIfConfigured() }
    private fun startMqttIfConfigured() {
        val prefs = getSharedPreferences("mqtt", MODE_PRIVATE)
        val brokerUrl = prefs.getString("broker_url", null) ?: return
        val username = prefs.getString("username", "")
        val password = prefs.getString("password", "")
        val heartbeatTopic = prefs.getString("heartbeat_topic", "device/heartbeat") ?: "device/heartbeat"
        val commandTopic = prefs.getString("command_topic", "device/command") ?: "device/command"
        val deviceId = android.provider.Settings.Secure.getString(
            contentResolver,
            android.provider.Settings.Secure.ANDROID_ID
        )

        mqttManager = MqttManager(this, brokerUrl, username!!, password!!, heartbeatTopic, commandTopic, deviceId)
        mqttManager?.onCommand { json ->
            val type = json.optString("type", "")
            if (type == "session") {
                val platform = json.optString("platform", "gemini")
                val prompt = json.optString("prompt", "")
                val followUp = json.optString("followUp", "").let { if (it.isBlank()) null else it }
                val backlinkDomain = json.optString("backlinkDomain", "").let { if (it.isBlank()) null else it }
                if (prompt.isNotBlank()) {
                    log("MQTT job: $platform prompt=${prompt.take(50)}...")
                    Thread {
                        val flowEngine = FlowEngine(this@AgentAccessibilityService)
                        val result = AgentHttpServer.SessionResult(platform = platform, status = "running", prompt = prompt, backlinkDomain = backlinkDomain)
                        AgentHttpServer.lastResult.set(result)
                        AgentHttpServer.executeSessionStatic(result, flowEngine, platform, prompt, followUp, backlinkDomain)
                        // Publish result back
                        val resultJson = org.json.JSONObject().apply {
                            put("status", result.status)
                            put("platform", result.platform)
                            put("backlink_clicked", result.backlinkClicked)
                            put("backlink_domain", result.backlinkDomain ?: "")
                            put("error", result.error ?: "")
                            put("steps", result.steps.size)
                        }
                        mqttManager?.publishResult(resultJson)
                    }.start()
                }
            }
        }
        mqttManager?.start()
        log("MQTT connected to $brokerUrl heartbeat=$heartbeatTopic cmd=$commandTopic id=$deviceId")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {}

    override fun onDestroy() {
        super.onDestroy()
        httpServer?.stop()
        httpServer = null
        mqttManager?.stop()
        mqttManager = null
        instance = null
    }

    override fun onUnbind(intent: Intent?): Boolean {
        httpServer?.stop()
        httpServer = null
        mqttManager?.stop()
        mqttManager = null
        instance = null
        return super.onUnbind(intent)
    }

    // ── core primitives ──

    /** Two-pass search: prefers interactive nodes (clickable/focusable/editable), falls back to any match */
    fun findNode(
        text: String? = null,
        contentDesc: String? = null,
        resourceId: String? = null,
        className: String? = null,
        timeoutMs: Long = 3000
    ): AccessibilityNodeInfo? {
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            val root = rootInActiveWindow ?: run {
                Thread.sleep(200)
                continue
            }
            // pass 1: prefer interactive nodes
            val found = findNodeRecursive(root, text, contentDesc, resourceId, className, requireInteractive = true)
                ?: findNodeRecursive(root, text, contentDesc, resourceId, className, requireInteractive = false)
            root.recycle()
            if (found != null) return found
            Thread.sleep(200)
        }
        return null
    }

    private fun matches(
        node: AccessibilityNodeInfo,
        text: String?,
        contentDesc: String?,
        resourceId: String?,
        className: String?
    ): Boolean {
        if (text != null && node.text?.toString()?.contains(text, ignoreCase = true) != true) return false
        if (contentDesc != null && node.contentDescription?.toString()?.contains(contentDesc, ignoreCase = true) != true) return false
        if (resourceId != null && node.viewIdResourceName?.contains(resourceId) != true) return false
        if (className != null && node.className?.toString()?.contains(className, ignoreCase = true) != true) return false
        return true
    }

    private fun isInteractive(node: AccessibilityNodeInfo): Boolean =
        node.isClickable || node.isFocusable || node.isEditable

    private fun findNodeRecursive(
        node: AccessibilityNodeInfo,
        text: String?,
        contentDesc: String?,
        resourceId: String?,
        className: String?,
        requireInteractive: Boolean
    ): AccessibilityNodeInfo? {
        if (matches(node, text, contentDesc, resourceId, className)) {
            if (!requireInteractive || isInteractive(node)) return node
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findNodeRecursive(child, text, contentDesc, resourceId, className, requireInteractive)
            if (result != null) return result
        }
        return null
    }

    /** Find an EditText by placeholder hint text or className */
    fun findInputField(hintText: String? = null, timeoutMs: Long = 3000): AccessibilityNodeInfo? {
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            val root = rootInActiveWindow ?: run {
                Thread.sleep(200)
                continue
            }
            val found = findEditTextRecursive(root, hintText)
            root.recycle()
            if (found != null) return found
            Thread.sleep(200)
        }
        return null
    }

    private fun findEditTextRecursive(node: AccessibilityNodeInfo, hintText: String?): AccessibilityNodeInfo? {
        val isEdit = node.className?.toString()?.contains("EditText") == true
        if (isEdit && node.isFocusable) {
            if (hintText == null || node.text?.toString()?.contains(hintText, ignoreCase = true) == true) {
                // Skip Chrome URL bar (at top of screen, y < 200)
                val rect = android.graphics.Rect()
                node.getBoundsInScreen(rect)
                if (rect.top > 200) {
                    return node
                }
            }
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findEditTextRecursive(child, hintText)
            if (result != null) return result
        }
        return null
    }

    /** Set text on an EditText node using ACTION_SET_TEXT */
    fun setTextOnNode(node: AccessibilityNodeInfo, text: String): Boolean {
        val args = Bundle()
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        val ok = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        log(if (ok) "ACTION_SET_TEXT succeeded" else "ACTION_SET_TEXT failed")
        return ok
    }

    fun clickNode(node: AccessibilityNodeInfo): Boolean {
        if (node.isClickable) {
            return node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        }
        var p = node.parent
        while (p != null) {
            if (p.isClickable) {
                val ok = p.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                p.recycle()
                return ok
            }
            val next = p.parent
            p.recycle()
            p = next
        }
        return false
    }

    fun scrollForward(): Boolean {
        val root = rootInActiveWindow ?: return false
        val scrollable = findScrollableRecursive(root)
        root.recycle()
        return scrollable?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) == true
    }

    private fun findScrollableRecursive(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isScrollable && node.actionList?.any { it.id == AccessibilityNodeInfo.ACTION_SCROLL_FORWARD } == true) {
            return node
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findScrollableRecursive(child)
            if (result != null) return result
        }
        return null
    }

    fun gestureSwipe(startX: Float, startY: Float, endX: Float, endY: Float, durationMs: Long = 400): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false
        val path = Path().apply {
            moveTo(startX, startY)
            lineTo(endX, endY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
            .build()
        dispatchGesture(gesture, null, null)
        Thread.sleep(durationMs + 100)
        return true
    }

    fun gestureLongPress(x: Float, y: Float, durationMs: Long = 600): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false
        val path = Path().apply {
            moveTo(x, y)
            lineTo(x + 1, y + 1)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
            .build()
        dispatchGesture(gesture, null, null)
        Thread.sleep(durationMs + 200)
        return true
    }

    fun gestureTap(x: Float, y: Float): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false
        val path = Path().apply {
            moveTo(x, y)
            lineTo(x + 1, y)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 80))
            .build()
        dispatchGesture(gesture, null, null)
        Thread.sleep(150)
        return true
    }

    /** Copy text to clipboard */
    fun setClipboard(text: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("agent", text))
        log("Clipboard set: \"${text.take(40)}...\"")
    }

    /** Paste from clipboard via long-press + paste button */
    fun pasteAt(x: Float, y: Float): Boolean {
        log("pasteAt: long-press at ($x, $y)")
        gestureLongPress(x, y, 500)
        Thread.sleep(600)
        var paste = findInAllWindows(text = "Paste", timeoutMs = 1500)
            ?: findInAllWindows(contentDesc = "Paste", timeoutMs = 1000)
            ?: findInAllWindows(text = "Clipboard", timeoutMs = 800)
        if (paste != null) {
            log("pasteAt: found '${paste.text ?: paste.contentDescription}' — clicking")
            clickNode(paste)
            log("Pasted via context menu")
            return true
        }
        // 2nd attempt
        gestureTap(x, y)
        Thread.sleep(200)
        gestureLongPress(x, y, 500)
        Thread.sleep(600)
        paste = findInAllWindows(text = "Paste", timeoutMs = 1500)
            ?: findInAllWindows(contentDesc = "Paste", timeoutMs = 1000)
        if (paste != null) {
            clickNode(paste)
            log("Pasted via context menu (2nd)")
            return true
        }
        log("pasteAt: Paste button not found")
        return false
    }

    /** Search for a node across ALL accessibility windows, not just active */
    private fun findInAllWindows(
        text: String? = null,
        contentDesc: String? = null,
        timeoutMs: Long = 2000
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            val allWindows = windows ?: run { Thread.sleep(200); continue }
            for (window in allWindows) {
                val root = window.root ?: continue
                val found = findNodeRecursive(root, text, contentDesc, null, null, false)
                root.recycle()
                if (found != null) return found
            }
            Thread.sleep(200)
        }
        return null
    }

    // open URL in Chrome
    fun navigateToUrl(url: String) {
        val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)).apply {
            setPackage("com.android.chrome")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        startActivity(intent)
        log("Navigating to $url")
    }

    // get screen dimensions
    fun screenWidth(): Int = resources.displayMetrics.widthPixels
    fun screenHeight(): Int = resources.displayMetrics.heightPixels

    // dump the current screen tree
    fun dumpTree(maxDepth: Int = 8): String {
        val sb = StringBuilder()
        val root = rootInActiveWindow ?: return "(no root)"
        dumpNode(root, 0, maxDepth, sb)
        root.recycle()
        return sb.toString()
    }

    private fun dumpNode(node: AccessibilityNodeInfo, depth: Int, maxDepth: Int, sb: StringBuilder) {
        if (depth > maxDepth) return
        val indent = "  ".repeat(depth)
        val text = node.text?.toString()?.take(60) ?: ""
        val cd = node.contentDescription?.toString()?.take(40) ?: ""
        val rid = node.viewIdResourceName ?: ""
        val cls = node.className?.toString()?.split(".")?.lastOrNull() ?: ""
        val flags = buildString {
            if (node.isClickable) append("[C]")
            if (node.isFocusable) append("[F]")
            if (node.isEditable) append("[E]")
            if (node.isScrollable) append("[S]")
        }
        sb.appendLine("$indent$cls$flags text=\"$text\" cd=\"$cd\" id=\"$rid\"")
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { dumpNode(it, depth + 1, maxDepth, sb) }
        }
    }

    /** Take screenshot via AccessibilityService.takeScreenshot (API 34+) */
    fun captureScreen(): Bitmap? {
        if (Build.VERSION.SDK_INT < 34) {
            log("takeScreenshot requires API 34+")
            return null
        }
        try {
            val latch = java.util.concurrent.CountDownLatch(1)
            var result: Bitmap? = null
            takeScreenshot(
                0, // DEFAULT_DISPLAY
                mainExecutor,
                object : TakeScreenshotCallback {
                    override fun onSuccess(screenshot: ScreenshotResult) {
                        result = Bitmap.wrapHardwareBuffer(screenshot.hardwareBuffer, screenshot.colorSpace)
                        screenshot.hardwareBuffer.close()
                        latch.countDown()
                    }
                    override fun onFailure(errorCode: Int) {
                        log("Screenshot failed, code=$errorCode")
                        latch.countDown()
                    }
                }
            )
            latch.await(5, java.util.concurrent.TimeUnit.SECONDS)
            return result
        } catch (e: Exception) {
            log("Screenshot error: ${e.message}")
            return null
        }
    }

    /** Save screenshot to app's external files dir (no permission needed). Returns file path. */
    fun saveScreenshot(name: String): String? {
        val bitmap = captureScreen() ?: return null
        try {
            val dir = java.io.File(getExternalFilesDir(null), "screenshots")
            dir.mkdirs()
            val file = java.io.File(dir, "$name.png")
            java.io.FileOutputStream(file).use { out ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 90, out)
            }
            bitmap.recycle()
            val path = file.absolutePath
            log("Screenshot saved: $path")
            return path
        } catch (e: Exception) {
            log("Screenshot save error: ${e.message}")
            return null
        }
    }

    fun log(msg: String) {
        android.util.Log.d("DeviceAgent", msg)
        onLog?.invoke(msg)
        // Also write to file so we can pull logs via ADB
        try {
            val dir = java.io.File(getExternalFilesDir(null), "logs")
            dir.mkdirs()
            val file = java.io.File(dir, "agent.log")
            val ts = java.text.SimpleDateFormat("HH:mm:ss.SSS", java.util.Locale.getDefault())
                .format(java.util.Date())
            file.appendText("[$ts] $msg\n")
        } catch (_: Exception) {}
    }
}
