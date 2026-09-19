package com.deviceagent

/** Audit-only evidence checks. Prompt examples and loading text are never answers. */
object GeminiAuditEvidence {
    fun normalized(text: String) = text.replace(Regex("\\s+"), " ").trim()

    fun promptMatches(actual: String, expected: String): Boolean =
        expected.isNotBlank() && normalized(actual) == normalized(expected)

    fun answer(page: String): String? {
        val boundary = Regex("(?m)^\\s*Gemini said\\s*$").findAll(page).toList()
        var answer = if (boundary.size == 1) {
            page.substring(boundary.single().range.last + 1).trim()
        } else {
            // Some Chrome/WebView accessibility trees omit the "Gemini said"
            // landmark even though the rendered answer is complete.  Recover the
            // answer from its first numbered result instead of timing out a visible
            // response.
            val firstResult = Regex("(?m)^\\s*1[.)]\\s+\\S").find(page) ?: return null
            page.substring(firstResult.range.first).trim()
        }
        val footer = Regex("(?m)^\\s*(?:Gemini is AI and can make mistakes\\.|Ask Gemini|Upload & tools)\\s*$").find(answer)
        if (footer != null) answer = answer.substring(0, footer.range.first).trim()
        if (answer.contains("Connecting to Google", ignoreCase = true) ||
            answer.contains("You said", ignoreCase = true)) return null
        val ranks = Regex("\\[RANK:\\s*(\\d+)\\s*/\\s*(\\d+)\\]", RegexOption.IGNORE_CASE).findAll(answer).toList()
        if (ranks.size != 1) return null
        val rank = ranks.single()
        val position = rank.groupValues[1].toIntOrNull() ?: return null
        val total = rank.groupValues[2].toIntOrNull() ?: return null
        if (position < 1 || total < position) return null
        // The production ranking prompt places a brief summary after the numeric
        // marker.  The marker remains authoritative; trailing prose is valid answer
        // content and must not turn a rendered answer into a generation timeout.
        // A completed top-three response must contain the actual numbered list.
        if (!(1..3).all { Regex("(?m)^\\s*$it[.)]\\s*\\S").containsMatchIn(answer) }) return null
        return answer
    }
}
