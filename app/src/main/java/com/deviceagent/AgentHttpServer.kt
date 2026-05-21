package com.deviceagent

import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.io.OutputStream
import java.io.OutputStreamWriter
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicReference

class AgentHttpServer(private val flowEngine: FlowEngine) {

    companion object {
        const val PORT = 8765
        // Kept in sync with app/build.gradle.kts. Reported by /health so the
        // Mac-side dispatcher can detect a fleet running mixed APK versions.
        const val APP_VERSION_NAME = "0.7.1-b64"
        const val APP_VERSION_CODE = 9
        val lastResult = AtomicReference<SessionResult?>(null)
        // Approximation of app startup time — initialized when the class is first
        // referenced (which happens at HTTP server start, very early in the
        // process lifecycle). Used for /health uptime reporting.
        val PROCESS_START_MS = System.currentTimeMillis()

        private const val AUDIT_PROMPT_TEMPLATE = (
            "Top 3 businesses for {keyword} in {city}, {state}. " +
            "Format: numbered list, each entry: name, 2-3 sentence description of why they stand out, " +
            "and whether they appear on Google Maps (yes/no). " +
            "Do not include any maps, images, or embedded content — text only. " +
            "After the list, rank {biz_name} ({biz_url}) among all businesses in this space. " +
            "You MUST include this exact line on its own: [RANK: X/Y] " +
            "where X is the position and Y is total businesses (e.g., [RANK: 7/25]). " +
            "Then one sentence explaining why. " +
            "Keep entire response under 200 words."
        )

        fun buildAuditPrompt(bizName: String, bizUrl: String, city: String, state: String, keyword: String): String {
            return AUDIT_PROMPT_TEMPLATE
                .replace("{keyword}", keyword)
                .replace("{city}", city)
                .replace("{state}", state)
                .replace("{biz_name}", bizName)
                .replace("{biz_url}", bizUrl)
        }

        /** Execute a session from anywhere (HTTP or MQTT). Updates result in-place. */
        fun executeSessionStatic(
            result: SessionResult,
            flowEngine: FlowEngine,
            platform: String,
            prompt: String,
            followUp: String?,
            backlinkDomain: String?
        ) {
            fun step(name: String, block: () -> Boolean): Boolean {
                result.steps.add("$name...")
                val ok = try { block() } catch (e: Exception) {
                    result.steps.add("$name: ERROR - ${e.message}")
                    false
                }
                result.steps.add("$name: ${if (ok) "OK" else "FAILED"}")
                return ok
            }
            try {
                if (!step("reset_chrome") { flowEngine.resetChrome() }) {
                    result.status = "error"; result.error = "reset_chrome failed"; return
                }
                Thread.sleep(500)
                if (!step("navigate") { flowEngine.navigateTo(platform) }) {
                    result.status = "error"; result.error = "navigate failed"; return
                }
                Thread.sleep(if (platform == "chatgpt") 6000L else 3000L)
                step("dismiss_popups") { flowEngine.dismissPlatformPopups(platform); true }
                Thread.sleep(500)
                if (!step("input") { flowEngine.inputText(prompt) }) {
                    result.status = "error"; result.error = "input failed"; return
                }
                Thread.sleep(300)
                step("submit") { flowEngine.submit() }
                Thread.sleep(2000)
                if (!step("wait_generation") { flowEngine.waitForGeneration(timeoutSec = 120) }) {
                    result.status = "error"; result.error = "generation timeout"; return
                }
                // ChatGPT: click backlink BEFORE scroll (links at top of response).
                // Wait a moment for response to fully render before searching.
                if (!backlinkDomain.isNullOrBlank() && platform.lowercase() == "chatgpt") {
                    Thread.sleep(3000)
                    val clicked = step("backlink") { flowEngine.clickBacklink(backlinkDomain, platform) }
                    result.backlinkClicked = clicked
                }
                step("scroll") { flowEngine.scrollResponse(12) }
                if (!followUp.isNullOrBlank()) {
                    step("follow_up") { flowEngine.sendFollowUp(followUp) }
                }
                // Other platforms: click backlink AFTER scroll
                if (!backlinkDomain.isNullOrBlank() && platform.lowercase() != "chatgpt") {
                    val clicked = step("backlink") { flowEngine.clickBacklink(backlinkDomain, platform) }
                    result.backlinkClicked = clicked
                }
                result.status = "completed"
            } catch (e: Exception) {
                result.status = "error"
                result.error = e.message
                Log.e("DeviceAgent", "Session error: ${e.stackTraceToString()}")
            }
        }

        /** Execute an audit session — runs specified platforms. If platforms is empty, runs all 3. */
        fun executeAuditSessionStatic(
            result: SessionResult,
            flowEngine: FlowEngine,
            bizName: String,
            bizUrl: String,
            city: String,
            state: String,
            keyword: String,
            platformsFilter: String? = null
        ) {
            val prompt = buildAuditPrompt(bizName, bizUrl, city, state, keyword)
            result.prompt = prompt
            result.type = "audit"

            val platformsOrder = if (platformsFilter.isNullOrBlank()) {
                listOf("gemini", "chatgpt", "perplexity")
            } else {
                listOf(platformsFilter.lowercase())
            }

            // No preflight. Audit must mirror daily exactly — daily has near-100%
            // success without any preflight call. Adding a navigateToUrl before
            // resetChrome caused subsequent jobs on the same phone to fail
            // (Chrome state mismatch after the extra nav). The audit flow body
            // below is now structurally identical to executeSessionStatic
            // (the daily flow), one platform at a time.

            for (platform in platformsOrder) {
                val pr = PlatformResult(status = "running")
                result.platforms[platform] = pr

                val stepBase = System.currentTimeMillis()
                fun step(name: String, block: () -> Boolean): Boolean {
                    val t0 = System.currentTimeMillis()
                    val ok = try { block() } catch (e: Exception) {
                        result.steps.add("[$platform] $name FAILED ${(System.currentTimeMillis()-t0)/1000}s - ${e.message}")
                        false
                    }
                    val dt = (System.currentTimeMillis() - t0) / 1000
                    val total = (System.currentTimeMillis() - stepBase) / 1000
                    result.steps.add("[$platform] $name ${if (ok) "OK" else "FAILED"} ${dt}s (total ${total}s)")
                    return ok
                }

                try {
                    // Audit flow MATCHES daily exactly. Steps below are identical to
                    // executeSessionStatic — no audit-only guards, no platform-specific
                    // branches. If daily reliability holds, audit reliability holds.
                    if (!step("reset_chrome") { flowEngine.resetChrome() }) {
                        pr.status = "error"; pr.error = "reset_chrome failed"; continue
                    }
                    Thread.sleep(500)
                    if (!step("navigate") { flowEngine.navigateTo(platform) }) {
                        pr.status = "error"; pr.error = "navigate failed"; continue
                    }
                    Thread.sleep(if (platform == "chatgpt") 6000L else 3000L)
                    step("dismiss_popups") { flowEngine.dismissPlatformPopups(platform); true }
                    Thread.sleep(500)
                    if (!step("input") { flowEngine.inputText(prompt) }) {
                        pr.status = "error"; pr.error = "input failed"; continue
                    }
                    Thread.sleep(300)
                    step("submit") { flowEngine.submit() }
                    Thread.sleep(2000)
                    if (!step("wait_generation") { flowEngine.waitForGeneration(timeoutSec = 120) }) {
                        pr.status = "error"; pr.error = "generation timeout"; continue
                    }
                    // 200-word capped response — 6 scrolls covers the full response
                    // and lands on the [RANK: X/Y] line near the end. Saves ~17s vs 12.
                    step("scroll") { flowEngine.scrollResponse(6) }
                    Thread.sleep(1000)
                    // Capture full LLM response text once; reuse for rank scan + audit log.
                    val responseText = flowEngine.getResponseText()
                    val (pos, total) = flowEngine.extractRankingFromText(responseText)
                    pr.rankingPosition = pos
                    pr.rankingTotal = total
                    pr.responseText = responseText

                    // Capture screenshot — saved to phone-side scoped dir and
                    // ALSO base64-encoded inline so the Mac dispatcher can write
                    // the file locally without an `adb pull` round-trip. Falls
                    // back to the path-only behaviour when the file can't be
                    // read back (caller will adb-pull as before).
                    val ssName = "audit_${platform}_${System.currentTimeMillis()}"
                    val ssPath = try { flowEngine.saveScreenshot(ssName) } catch (e: Exception) { null }
                    pr.screenshotPath = ssPath
                    if (!ssPath.isNullOrBlank()) {
                        pr.screenshotB64 = try {
                            val bytes = File(ssPath).readBytes()
                            android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
                        } catch (e: Exception) {
                            Log.w("DeviceAgent", "screenshot b64 encode failed for $ssPath: ${e.message}")
                            null
                        }
                    }

                    pr.status = "completed"
                    result.steps.add("[$platform] ranking: $pos / $total  ss=$ssPath")
                } catch (e: Exception) {
                    pr.status = "error"
                    pr.error = e.message
                    Log.e("DeviceAgent", "Audit $platform error: ${e.stackTraceToString()}")
                }
            }

            // Set overall ranking from first platform that has one
            for (platform in platformsOrder) {
                val pr = result.platforms[platform] ?: continue
                if (pr.rankingPosition != null) {
                    result.rankingPosition = pr.rankingPosition
                    result.rankingTotal = pr.rankingTotal
                    break
                }
            }

            val hasError = result.platforms.values.any { it.status == "error" }
            result.status = if (hasError && result.platforms.values.all { it.status == "error" }) "error" else "completed"
        }
    }

    private var serverThread: Thread? = null
    private var serverSocket: java.net.ServerSocket? = null
    private var running = false

    data class PlatformResult(
        var status: String = "idle",
        var rankingPosition: Int? = null,
        var rankingTotal: String? = null,
        var screenshotPath: String? = null,
        // Base64-encoded PNG bytes. Inlined in the audit response so the Mac
        // dispatcher can write the file locally without `adb pull` — works
        // during active VPN since the response travels over the existing
        // adb-forward HTTP tunnel.
        var screenshotB64: String? = null,
        var responseText: String? = null,
        var error: String? = null
    )

    data class SessionResult(
        val platform: String = "",
        var status: String = "idle",       // idle | running | completed | error
        val steps: MutableList<String> = mutableListOf(),
        var backlinkClicked: Boolean = false,
        var backlinkDomain: String? = null,
        var error: String? = null,
        var prompt: String = "",
        var type: String = "daily",
        var rankingPosition: Int? = null,
        var rankingTotal: String? = null,
        var proxyIp: String? = null,
        val platforms: MutableMap<String, PlatformResult> = mutableMapOf()
    )

    fun start() {
        running = true
        serverThread = Thread {
            try {
                val server = ServerSocket().apply {
                    reuseAddress = true
                    bind(java.net.InetSocketAddress(PORT))
                }
                serverSocket = server
                Log.d("DeviceAgent", "HTTP API listening on port $PORT")
                while (running) {
                    try {
                        val client = server.accept()
                        Thread { handleClient(client) }.start()
                    } catch (e: Exception) {
                        if (running) Log.e("DeviceAgent", "Accept error: ${e.message}")
                    }
                }
                server.close()
            } catch (e: Exception) {
                Log.e("DeviceAgent", "Server error: ${e.message}")
            }
        }.apply {
            name = "agent-http"
            isDaemon = true
            start()
        }
    }

    fun stop() {
        running = false
        try { serverSocket?.close() } catch (_: Exception) {}
        serverSocket = null
        serverThread?.interrupt()
    }

    private fun handleClient(socket: Socket) {
        try {
            val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
            val writer = OutputStreamWriter(socket.outputStream)

            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return
            val method = parts[0]
            val path = parts[1]

            var contentLength = 0
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isBlank()) break
                if (line.startsWith("Content-Length:", ignoreCase = true)) {
                    contentLength = line.substringAfter(":").trim().toIntOrNull() ?: 0
                }
            }

            val body = if (contentLength > 0) {
                val buf = CharArray(contentLength)
                reader.read(buf, 0, contentLength)
                String(buf)
            } else ""

            Log.d("DeviceAgent", "HTTP $method $path")

            when {
                path == "/ping" || path == "/ping/" -> {
                    respond(writer, 200, """{"pong":true}""")
                }
                path == "/status" || path == "/status/" -> {
                    handleStatus(writer)
                }
                path == "/health" || path == "/health/" -> {
                    handleHealth(writer)
                }
                path.startsWith("/screenshot") -> {
                    handleScreenshot(socket.outputStream, writer, path)
                }
                path == "/session" || path == "/session/" -> {
                    if (method == "POST") {
                        handleSession(writer, body)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                path == "/mqtt/config" || path == "/mqtt/config/" -> {
                    if (method == "POST") {
                        handleMqttConfig(writer, body)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                else -> {
                    respond(writer, 404, """{"error":"not found"}""")
                }
            }

            writer.flush()
        } catch (e: Exception) {
            Log.e("DeviceAgent", "Client error: ${e.message}")
        } finally {
            try { socket.close() } catch (_: Exception) {}
        }
    }

    private fun handleSession(writer: OutputStreamWriter, body: String) {
        try {
            val json = JSONObject(body)
            val sessionType = json.optString("type", "daily")

            if (sessionType == "audit") {
                handleAuditSession(writer, json)
            } else {
                handleDailySession(writer, json)
            }
        } catch (e: Exception) {
            Log.e("DeviceAgent", "Session error: ${e.message}")
            respond(writer, 400, """{"error":"${e.message?.replace("\"", "'")}"}""")
        }
    }

    private fun handleDailySession(writer: OutputStreamWriter, json: JSONObject) {
        val platform = json.optString("platform", "gemini")
        val prompt = json.optString("prompt", "").let { if (it == "null") "" else it }
        val followUp = json.optString("followUp", "").let { if (it.isBlank() || it == "null") null else it }
        val backlinkDomain = json.optString("backlinkDomain", "").let { if (it.isBlank()) null else it }

        if (prompt.isBlank()) {
            respond(writer, 400, """{"error":"prompt is required"}""")
            return
        }

        Log.d("DeviceAgent", "Daily: $platform prompt=${prompt.take(50)}... backlink=$backlinkDomain")

        val result = SessionResult(
            platform = platform,
            status = "running",
            prompt = prompt,
            backlinkDomain = backlinkDomain,
            type = "daily"
        )
        lastResult.set(result)

        executeSession(result, platform, prompt, followUp, backlinkDomain)

        val response = JSONObject().apply {
            put("status", result.status)
            put("type", "daily")
            put("platform", result.platform)
            put("backlink_clicked", result.backlinkClicked)
            put("backlink_domain", result.backlinkDomain ?: "")
            put("error", result.error ?: "")
            put("steps", result.steps.size)
            put("step_log", org.json.JSONArray(result.steps))
        }
        // Always 200 — caller inspects per-platform status in the JSON body.
        // Returning 500 made urllib.urlopen raise and discard the body.
        respond(writer, 200, response.toString())
    }

    private fun handleAuditSession(writer: OutputStreamWriter, json: JSONObject) {
        val bizName = json.optString("bizName", "")
        val bizUrl = json.optString("bizUrl", "")
        val city = json.optString("city", "")
        val state = json.optString("state", "")
        val keyword = json.optString("keyword", "")

        if (bizName.isBlank() || bizUrl.isBlank() || city.isBlank() || state.isBlank() || keyword.isBlank()) {
            respond(writer, 400, """{"error":"bizName, bizUrl, city, state, keyword are required for audit"}""")
            return
        }

        Log.d("DeviceAgent", "Audit: $bizName ($bizUrl) | $keyword in $city, $state")

        val result = SessionResult(
            platform = "all",
            status = "running",
            type = "audit"
        )
        lastResult.set(result)

        val platformFilter = json.optString("platform", "").let { if (it.isBlank()) null else it }
        executeAuditSession(result, bizName, bizUrl, city, state, keyword, platformFilter)

        val response = JSONObject().apply {
            put("status", result.status)
            put("type", "audit")
            put("prompt", result.prompt)
            put("ranking_position", result.rankingPosition ?: 0)
            put("ranking_total", result.rankingTotal ?: "")
            put("error", result.error ?: "")
            put("proxy_ip", result.proxyIp ?: "")
            put("steps", result.steps.size)
            put("step_log", org.json.JSONArray(result.steps))
            val platformsJson = JSONObject()
            for ((name, pr) in result.platforms) {
                val pj = JSONObject().apply {
                    put("status", pr.status)
                    put("ranking_position", pr.rankingPosition ?: 0)
                    put("ranking_total", pr.rankingTotal ?: "")
                    put("screenshot_path", pr.screenshotPath ?: "")
                    // Base64 PNG bytes — Mac decodes + writes locally; saves an adb pull.
                    put("screenshot_b64", pr.screenshotB64 ?: "")
                    put("response_text", pr.responseText ?: "")
                    put("error", pr.error ?: "")
                }
                platformsJson.put(name, pj)
            }
            put("platforms", platformsJson)
        }
        // Always 200 — caller inspects per-platform status in the JSON body.
        // Returning 500 made urllib.urlopen raise and discard the body.
        respond(writer, 200, response.toString())
    }

    fun executeSession(
        result: SessionResult,
        platform: String,
        prompt: String,
        followUp: String?,
        backlinkDomain: String?
    ) {
        executeSessionStatic(result, flowEngine, platform, prompt, followUp, backlinkDomain)
    }

    fun executeAuditSession(
        result: SessionResult,
        bizName: String,
        bizUrl: String,
        city: String,
        state: String,
        keyword: String,
        platformFilter: String? = null
    ) {
        executeAuditSessionStatic(result, flowEngine, bizName, bizUrl, city, state, keyword, platformFilter)
    }

    private fun handleMqttConfig(writer: OutputStreamWriter, body: String) {
        try {
            val json = JSONObject(body)
            val brokerUrl = json.optString("broker_url", "")
            val username = json.optString("username", "")
            val password = json.optString("password", "")
            val heartbeatTopic = json.optString("heartbeat_topic", "device/heartbeat")
            val commandTopic = json.optString("command_topic", "device/command")

            if (brokerUrl.isBlank()) {
                respond(writer, 400, """{"error":"broker_url is required"}""")
                return
            }

            // Save to SharedPreferences via the accessibility service
            val svc = AgentAccessibilityService.instance
            if (svc != null) {
                val prefs = svc.getSharedPreferences("mqtt", android.content.Context.MODE_PRIVATE)
                prefs.edit()
                    .putString("broker_url", brokerUrl)
                    .putString("username", username)
                    .putString("password", password)
                    .putString("heartbeat_topic", heartbeatTopic)
                    .putString("command_topic", commandTopic)
                    .apply()

                // Restart MQTT
                AgentAccessibilityService.mqttManager?.stop()
                svc.startMqttIfConfiguredPublic()

                respond(writer, 200, """{"status":"ok","message":"MQTT configured and connecting"}""")
            } else {
                respond(writer, 503, """{"error":"accessibility service not running"}""")
            }
        } catch (e: Exception) {
            respond(writer, 400, """{"error":"${e.message?.replace("\"", "'")}"}""")
        }
    }

    private fun handleStatus(writer: OutputStreamWriter) {
        val result = lastResult.get()
        if (result == null) {
            respond(writer, 200, """{"status":"idle"}""")
            return
        }
        val json = JSONObject().apply {
            put("status", result.status)
            put("type", result.type)
            put("platform", result.platform)
            put("backlink_clicked", result.backlinkClicked)
            put("backlink_domain", result.backlinkDomain ?: "")
            put("error", result.error ?: "")
            put("steps", result.steps.joinToString(" | "))
            if (result.type == "audit") {
                put("ranking_position", result.rankingPosition ?: 0)
                put("ranking_total", result.rankingTotal ?: "")
                val platformsJson = JSONObject()
                for ((name, pr) in result.platforms) {
                    val pj = JSONObject().apply {
                        put("status", pr.status)
                        put("ranking_position", pr.rankingPosition ?: 0)
                        put("ranking_total", pr.rankingTotal ?: "")
                        put("error", pr.error ?: "")
                    }
                    platformsJson.put(name, pj)
                }
                put("platforms", platformsJson)
            }
        }
        respond(writer, 200, json.toString())
    }

    private fun handleHealth(writer: OutputStreamWriter) {
        // Phase 1 endpoint: report enough state for the Mac to decide whether to
        // dispatch to this phone without falling back to `adb devices` / `adb shell`.
        val wifiIp = currentWifiIp() ?: ""
        val tun = readTunInterface()
        val accessibilityActive = AgentAccessibilityService.instance != null
        val lastStatus = lastResult.get()?.status ?: "idle"

        val json = JSONObject().apply {
            put("ok", true)
            put("version", APP_VERSION_NAME)
            put("versionCode", APP_VERSION_CODE)
            put("wifiIp", wifiIp)
            put("accessibility", accessibilityActive)
            put("lastJobStatus", lastStatus)
            put("uptimeMs", System.currentTimeMillis() - PROCESS_START_MS)
            put("tun0", JSONObject().apply {
                put("up", tun.first)
                put("addr", tun.second ?: "")
            })
        }
        respond(writer, 200, json.toString())
    }

    private fun handleScreenshot(rawOut: OutputStream, writer: OutputStreamWriter, fullPath: String) {
        // GET /screenshot?path=<URL-encoded absolute path on phone>
        // Replaces `adb pull` for the Mac-side consumer when running in direct-WiFi mode.
        val qIdx = fullPath.indexOf('?')
        if (qIdx < 0) { respond(writer, 400, """{"error":"path query param required"}"""); return }
        val query = fullPath.substring(qIdx + 1)
        val pathParam = query.split("&")
            .map { it.split("=", limit = 2) }
            .firstOrNull { it.size == 2 && it[0] == "path" }
            ?.let { java.net.URLDecoder.decode(it[1], "UTF-8") }

        if (pathParam.isNullOrBlank()) {
            respond(writer, 400, """{"error":"path query param required"}""")
            return
        }
        // Path-traversal + allow-list guard. Screenshots live under /sdcard, /storage, or /data/local/tmp.
        if (pathParam.contains("..") ||
            !(pathParam.startsWith("/sdcard/") ||
              pathParam.startsWith("/storage/") ||
              pathParam.startsWith("/data/local/tmp/"))) {
            respond(writer, 403, """{"error":"path not allowed"}""")
            return
        }
        val file = File(pathParam)
        if (!file.exists() || !file.isFile) {
            respond(writer, 404, """{"error":"file not found"}""")
            return
        }
        try {
            val bytes = file.readBytes()
            val header = buildString {
                append("HTTP/1.1 200 OK\r\n")
                append("Content-Type: image/png\r\n")
                append("Content-Length: ${bytes.size}\r\n")
                append("Connection: close\r\n")
                append("\r\n")
            }
            rawOut.write(header.toByteArray(Charsets.UTF_8))
            rawOut.write(bytes)
            rawOut.flush()
        } catch (e: Exception) {
            respond(writer, 500, """{"error":"read failed: ${e.message?.replace("\"", "'")}"}""")
        }
    }

    private fun currentWifiIp(): String? {
        // Prefer wlan0; fall back to first non-loopback IPv4 on a UP interface.
        return try {
            val ifaces = NetworkInterface.getNetworkInterfaces() ?: return null
            var fallback: String? = null
            for (iface in ifaces) {
                if (!iface.isUp || iface.isLoopback) continue
                for (addr in iface.inetAddresses) {
                    if (addr.isLoopbackAddress) continue
                    val host = addr.hostAddress ?: continue
                    if (host.contains(":")) continue  // skip IPv6
                    if (iface.name == "wlan0") return host
                    if (fallback == null) fallback = host
                }
            }
            fallback
        } catch (_: Exception) {
            null
        }
    }

    private fun readTunInterface(): Pair<Boolean, String?> {
        // /proc/net/dev tells us tun0 exists but not its IPv4 — Android blocks
        // ifconfig from non-root. Fall back to NetworkInterface API.
        return try {
            val ifaces = NetworkInterface.getNetworkInterfaces() ?: return false to null
            for (iface in ifaces) {
                if (iface.name != "tun0") continue
                if (!iface.isUp) return false to null
                val addr = iface.inetAddresses.toList()
                    .firstOrNull { !it.isLoopbackAddress && !(it.hostAddress?.contains(":") ?: false) }
                    ?.hostAddress
                return true to addr
            }
            false to null
        } catch (_: Exception) {
            false to null
        }
    }

    private fun respond(writer: OutputStreamWriter, code: Int, body: String) {
        val status = when (code) {
            200 -> "200 OK"
            400 -> "400 Bad Request"
            404 -> "404 Not Found"
            405 -> "405 Method Not Allowed"
            500 -> "500 Internal Server Error"
            else -> "$code"
        }
        val bodyBytes = body.toByteArray(Charsets.UTF_8)
        writer.write("HTTP/1.1 $status\r\n")
        writer.write("Content-Type: application/json; charset=utf-8\r\n")
        writer.write("Content-Length: ${bodyBytes.size}\r\n")
        writer.write("Connection: close\r\n")
        writer.write("\r\n")
        writer.write(body)
    }
}
