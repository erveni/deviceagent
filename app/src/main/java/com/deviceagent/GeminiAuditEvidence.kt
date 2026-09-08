package com.deviceagent

/** Audit-only evidence checks. Prompt examples and loading text are never answers. */
object GeminiAuditEvidence {
    fun normalized(text: String) = text.replace(Regex("\\s+"), " ").trim()

    fun promptMatches(actual: String, expected: String): Boolean =
        expected.isNotBlank() && normalized(actual) == normalized(expected)

    fun answer(page: String): String? {
        val boundary = Regex("(?m)^\\s*Gemini said\\s*$").findAll(page).toList()
        if (boundary.size != 1) return null
        var answer = page.substring(boundary.single().range.last + 1).trim()
        val footer = Regex("(?m)^\\s*(?:Gemini is AI and can make mistakes\\.|Ask Gemini|Upload & tools)\\s*$").find(answer)
        if (footer != null) answer = answer.substring(0, footer.range.first).trim()
        if (answer.contains("Connecting to Google", ignoreCase = true) ||
            answer.contains("You said", ignoreCase = true)) return null
        val ranks = Regex("\\[RANK:\\s*(\\d+)\\s*/\\s*(\\d+)\\]", RegexOption.IGNORE_CASE).findAll(answer).toList()
        if (ranks.size != 1) return null
        val rank = ranks.single()
        val position = rank.groupValues[1].toIntOrNull() ?: return null
        val total = rank.groupValues[2].toIntOrNull() ?: return null
        if (position < 1 || total < position || answer.substring(rank.range.last + 1).isNotBlank()) return null
        // A completed top-three response must contain the actual numbered list.
        if (!(1..3).all { Regex("(?m)^\\s*$it[.)]\\s*\\S").containsMatchIn(answer) }) return null
        return answer
    }
}
