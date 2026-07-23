from __future__ import annotations

import re
from collections import Counter
from typing import Any


LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "English": ("english",),
    "Chinese": ("chinese", "mandarin", "中文", "汉语", "漢語", "普通话", "普通話"),
    "Japanese": ("japanese", "日本語"),
    "Korean": ("korean", "한국어", "조선말"),
    "Spanish": ("spanish", "español", "castilian"),
    "French": ("french", "français", "francais"),
    "German": ("german", "deutsch"),
    "Portuguese": ("portuguese", "português", "portugues"),
    "Italian": ("italian", "italiano"),
    "Russian": ("russian", "русский"),
    "Ukrainian": ("ukrainian", "українська", "украинский"),
    "Arabic": ("arabic", "العربية"),
    "Persian": ("persian", "farsi", "فارسی"),
    "Hebrew": ("hebrew", "עברית"),
    "Hindi": ("hindi", "हिन्दी", "हिंदी"),
    "Bengali": ("bengali", "bangla", "বাংলা"),
    "Thai": ("thai", "ภาษาไทย"),
    "Vietnamese": ("vietnamese", "tiếng việt", "tieng viet"),
    "Turkish": ("turkish", "türkçe", "turkce"),
    "Dutch": ("dutch", "nederlands"),
    "Polish": ("polish", "polski"),
    "Indonesian": ("indonesian", "bahasa indonesia"),
    "Malay": ("malay", "bahasa melayu"),
    "Swahili": ("swahili", "kiswahili"),
}


def _alias_pattern(aliases: tuple[str, ...]) -> str:
    return "(?:" + "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True)) + ")"


def detect_explicit_language_request(content: str) -> str | None:
    """Return a requested output language only when the text contains a language-control instruction."""
    text = content.strip()
    if not text:
        return None
    native_chinese = re.search(
        r"(?:请|請)?(?:全程)?(?:用|使用|改用)(?:简体|簡體|繁体|繁體)?中文(?:回答|讨论|討論|交流|输出|輸出|对话|對話)?",
        text,
    )
    if native_chinese:
        return "Chinese"
    for language, aliases in LANGUAGE_ALIASES.items():
        alias = _alias_pattern(aliases)
        patterns = (
            rf"\b(?:please\s+)?(?:use|speak|talk|discuss|respond|answer|write|continue|output)\s+(?:in\s+|using\s+)?{alias}(?:\s+language)?\b",
            rf"\b(?:switch|change)\s+(?:the\s+)?(?:conversation|discussion|roundtable|output)?(?:\s+language)?\s*(?:to|into)\s+{alias}(?:\s+language)?\b",
            rf"\b(?:conversation|discussion|roundtable|responses?|answers?|output)\s+(?:should\s+be\s+|must\s+be\s+|in\s+|using\s+){alias}(?:\s+language)?\b",
            rf"\b(?:conduct|hold)\s+(?:the\s+)?(?:conversation|discussion|roundtable)\s+in\s+{alias}(?:\s+language)?\b",
            rf"\b{alias}(?:\s+language)?\s+(?:conversation|discussion|roundtable|responses?|answers?|output)\b",
        )
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
            return language
    return None


LATIN_LANGUAGE_MARKERS: dict[str, set[str]] = {
    "Spanish": {"el", "la", "los", "las", "que", "para", "con", "una", "del", "estudio", "resultados", "salud"},
    "French": {"le", "la", "les", "des", "que", "pour", "avec", "une", "dans", "étude", "résultats", "santé"},
    "German": {"der", "die", "das", "und", "für", "mit", "eine", "einer", "studie", "ergebnisse", "gesundheit"},
    "Portuguese": {"o", "a", "os", "as", "que", "para", "com", "uma", "dos", "estudo", "resultados", "saúde"},
    "Italian": {"il", "la", "gli", "che", "per", "con", "una", "della", "studio", "risultati", "salute"},
}

# Common articles and prepositions are useful only after the text supplies
# language-specific evidence. Without this guard, English academic PDFs can be
# mistaken for Portuguese because isolated tokens such as "a", "as", and "o"
# occur in references, table labels, and extracted formulas.
LATIN_LANGUAGE_DISTINCTIVE_MARKERS: dict[str, set[str]] = {
    "Spanish": {"estudio", "estudios", "resultados", "salud", "muestra", "muestras", "hallazgos", "fueron"},
    "French": {"\u00e9tude", "\u00e9tudes", "r\u00e9sultats", "sant\u00e9", "\u00e9chantillon", "\u00e9chantillons", "selon", "\u00e9taient"},
    "German": {"studie", "studien", "ergebnisse", "gesundheit", "stichprobe", "stichproben", "wurden", "zwischen"},
    "Portuguese": {"estudo", "estudos", "resultados", "sa\u00fade", "amostra", "amostras", "achados", "foram"},
    "Italian": {"studio", "studi", "risultati", "salute", "campione", "campioni", "secondo", "erano"},
}


def detect_document_language(text: str) -> str:
    """Detect only clear non-English evidence; ambiguous source text defaults to English."""
    sample = text[:250_000]
    if not sample.strip():
        return "English"
    counts = {
        "han": len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", sample)),
        "kana": len(re.findall(r"[\u3040-\u30ff]", sample)),
        "hangul": len(re.findall(r"[\uac00-\ud7af]", sample)),
        "arabic": len(re.findall(r"[\u0600-\u06ff]", sample)),
        "cyrillic": len(re.findall(r"[\u0400-\u04ff]", sample)),
        "hebrew": len(re.findall(r"[\u0590-\u05ff]", sample)),
        "devanagari": len(re.findall(r"[\u0900-\u097f]", sample)),
        "bengali": len(re.findall(r"[\u0980-\u09ff]", sample)),
        "thai": len(re.findall(r"[\u0e00-\u0e7f]", sample)),
        "latin": len(re.findall(r"[A-Za-zÀ-ÿ]", sample)),
    }
    if counts["kana"] >= 20 and counts["kana"] + counts["han"] >= counts["latin"] * 0.15:
        return "Japanese"
    if counts["hangul"] >= 30 and counts["hangul"] >= counts["latin"] * 0.15:
        return "Korean"
    if counts["han"] >= 50 and counts["han"] >= counts["latin"] * 0.15:
        return "Chinese"
    for key, language in (
        ("arabic", "Arabic"),
        ("cyrillic", "Russian"),
        ("hebrew", "Hebrew"),
        ("devanagari", "Hindi"),
        ("bengali", "Bengali"),
        ("thai", "Thai"),
    ):
        if counts[key] >= 50 and counts[key] >= counts["latin"] * 0.15:
            return language
    words = re.findall(r"[a-zà-ÿ]+", sample.lower())
    frequencies = Counter(words)
    scores = {
        language: sum(frequencies[word] for word in markers)
        for language, markers in LATIN_LANGUAGE_MARKERS.items()
    }
    distinctive_scores = {
        language: sum(frequencies[word] for word in markers)
        for language, markers in LATIN_LANGUAGE_DISTINCTIVE_MARKERS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if ranked and ranked[0][1] >= max(6, len(words) * 0.015):
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        candidate = ranked[0][0]
        if distinctive_scores[candidate] >= 3 and ranked[0][1] >= runner_up + 2:
            return ranked[0][0]
    return "English"


def output_language_instruction(session: dict[str, Any]) -> str:
    language = str(session.get("conversation_language") or "English").strip() or "English"
    return (
        f'<output_language name="{language}">\n'
        f"Required output language: {language}. Write all visible prose for Momo, Bobby, Sam-facing recaps, "
        f"document digests, topic/conversation digests, and closing summaries in {language}. Understand source "
        "material in its original language and translate concepts accurately when needed. Preserve proper nouns, "
        "formulas, numerical values, citations, and short verbatim quotations in their source form when translation "
        "would reduce accuracy. Translate visible provenance labels such as Background knowledge, Inference, and "
        "Speculation into the required output language while preserving their meaning. For structured JSON, keep "
        "the required schema keys exactly as specified while "
        f"writing every human-readable string value in {language}. Do not discuss this language directive.\n"
        "</output_language>"
    )


GREETING_MESSAGES: dict[str, tuple[str, str]] = {
    "English": (
        "Hello, Sam—I'm Momo. I'm glad to join you and Bobby for this discussion.",
        "Hello, Sam—I'm Bobby. I'm ready when you are; you can set our first scientific direction.",
    ),
    "Chinese": (
        "你好，Sam——我是 Momo。很高兴和你及 Bobby 一起参加这场讨论。",
        "你好，Sam——我是 Bobby。我已经准备好了，请你提出第一个科学讨论方向。",
    ),
    "Japanese": ("こんにちは、Sam。Momoです。Bobbyと一緒に議論できることを楽しみにしています。", "こんにちは、Sam。Bobbyです。最初の科学的な方向を示してください。"),
    "Korean": ("안녕하세요, Sam. 저는 Momo입니다. Bobby와 함께 토론하게 되어 반갑습니다.", "안녕하세요, Sam. 저는 Bobby입니다. 첫 번째 과학적 논의 방향을 정해 주세요."),
    "Spanish": ("Hola, Sam. Soy Momo; me alegra participar en esta discusión contigo y con Bobby.", "Hola, Sam. Soy Bobby. Estoy listo; puedes marcar la primera dirección científica."),
    "French": ("Bonjour, Sam. Je suis Momo, ravie de participer à cette discussion avec Bobby et vous.", "Bonjour, Sam. Je suis Bobby. Je suis prêt; indiquez-nous la première direction scientifique."),
    "German": ("Hallo, Sam. Ich bin Momo und freue mich auf die Diskussion mit dir und Bobby.", "Hallo, Sam. Ich bin Bobby. Ich bin bereit; gib bitte die erste wissenschaftliche Richtung vor."),
    "Portuguese": ("Olá, Sam. Sou Momo e fico contente em participar desta discussão com você e Bobby.", "Olá, Sam. Sou Bobby. Estou pronto; indique a primeira direção científica."),
    "Italian": ("Ciao, Sam. Sono Momo e sono lieta di partecipare a questa discussione con te e Bobby.", "Ciao, Sam. Sono Bobby. Sono pronto; indica la prima direzione scientifica."),
    "Russian": ("Здравствуйте, Sam. Я Momo и рада участвовать в обсуждении вместе с вами и Bobby.", "Здравствуйте, Sam. Я Bobby. Я готов; задайте первое научное направление."),
    "Arabic": ("مرحبًا Sam، أنا Momo. يسعدني أن أشارك في هذا النقاش معك ومع Bobby.", "مرحبًا Sam، أنا Bobby. أنا مستعد؛ حدّد لنا الاتجاه العلمي الأول."),
    "Hindi": ("नमस्ते Sam, मैं Momo हूँ। आपके और Bobby के साथ इस चर्चा में शामिल होकर खुशी हुई।", "नमस्ते Sam, मैं Bobby हूँ। मैं तैयार हूँ; कृपया पहला वैज्ञानिक विषय तय करें।"),
}


def localized_greetings(language: str) -> tuple[str, str]:
    return GREETING_MESSAGES.get(language, GREETING_MESSAGES["English"])


CLOSING_MESSAGES = {
    "English": "Thank you, Sam—this was a thoughtful conversation. Let's finish here.",
    "Chinese": "谢谢你，Sam——这是一场很有深度的讨论。我们就此结束吧。",
    "Japanese": "Sam、ありがとうございました。とても有意義な議論でした。ここで終わりにしましょう。",
    "Korean": "Sam, 감사합니다. 매우 의미 있는 토론이었습니다. 여기서 마치겠습니다.",
    "Spanish": "Gracias, Sam. Ha sido una conversación muy reflexiva. Terminemos aquí.",
    "French": "Merci, Sam. Cette conversation a été très enrichissante. Terminons ici.",
    "German": "Danke, Sam. Das war ein sehr gehaltvolles Gespräch. Beenden wir es hier.",
}


def localized_closing(language: str) -> str:
    return CLOSING_MESSAGES.get(language, CLOSING_MESSAGES["English"])
