package com.deviceagent

import android.graphics.Bitmap
import android.util.Base64
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

object DeepSeekVision {
    // Set your API key here or via environment
    var apiKey = ""

    private const val API_URL = "https://api.deepseek.com/v1/chat/completions"

    data class FindResult(val found: Boolean, val x: Int = 0, val y: Int = 0)

    fun findText(bitmap: Bitmap, searchText: String): FindResult {
        if (apiKey.isBlank()) {
            Log.e("DeviceAgent", "DeepSeek API key not set")
            return FindResult(false)
        }

        try {
            val base64 = bitmapToBase64(bitmap)
            val prompt = """
You are a screen reader. Find the text "$searchText" on this mobile screenshot.
It could be a link, button, or text label.
Return ONLY valid JSON, no other text:
{"found":true,"x":<center_x_pixel>,"y":<center_y_pixel>}
or
{"found":false}
The coordinates must be the CENTER pixel of the element containing "$searchText".
""".trimIndent()

            val requestBody = JSONObject().apply {
                put("model", "deepseek-chat")
                put("max_tokens", 100)
                put("temperature", 0.0)
                put("messages", JSONArray().apply {
                    put(JSONObject().apply {
                        put("role", "user")
                        put("content", JSONArray().apply {
                            put(JSONObject().apply {
                                put("type", "image_url")
                                put("image_url", JSONObject().apply {
                                    put("url", "data:image/jpeg;base64,$base64")
                                })
                            })
                            put(JSONObject().apply {
                                put("type", "text")
                                put("text", prompt)
                            })
                        })
                    })
                })
            }

            val conn = URL(API_URL).openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Authorization", "Bearer $apiKey")
            conn.doOutput = true
            conn.connectTimeout = 15000
            conn.readTimeout = 15000

            conn.outputStream.use { it.write(requestBody.toString().toByteArray()) }
            val code = conn.responseCode
            val response = if (code in 200..299) {
                conn.inputStream.bufferedReader().readText()
            } else {
                val errBody = conn.errorStream?.bufferedReader()?.readText() ?: ""
                Log.e("DeviceAgent", "DeepSeek HTTP $code: $errBody")
                conn.disconnect()
                return FindResult(false)
            }
            conn.disconnect()

            Log.d("DeviceAgent", "DeepSeek response: ${response.take(200)}")
            val json = JSONObject(response)
            val content = json.getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .getString("content")
                .trim()

            // Parse JSON from response (strip markdown if present)
            val cleanContent = content
                .replace("```json", "")
                .replace("```", "")
                .trim()

            val result = JSONObject(cleanContent)
            return if (result.optBoolean("found", false)) {
                FindResult(true, result.getInt("x"), result.getInt("y"))
            } else {
                FindResult(false)
            }
        } catch (e: Exception) {
            Log.e("DeviceAgent", "DeepSeek vision error: ${e.message}")
            return FindResult(false)
        }
    }

    private fun bitmapToBase64(bitmap: Bitmap): String {
        val stream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 70, stream)
        return Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP)
    }
}
