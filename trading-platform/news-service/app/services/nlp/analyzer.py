"""NLP analysis pipeline for news articles.

Extracts market-moving signals: sentiment, tickers, keywords, market signals.
Falls back to rule-based analysis when heavy ML models aren't available.
"""

import re
import json
import logging
from datetime import datetime
from textblob import TextBlob

logger = logging.getLogger(__name__)

# Common market-moving signal keywords by category
MARKET_SIGNALS = {
    "regulation": ["regulation", "sec", "cftc", "compliance", "fraud", "investigation", "sanction"],
    "bull_run": ["rally", "bull market", "breakout", "all-time high", "surge", "momentum"],
    "crash_risk": ["crash", "recession", "bear market", "sell-off", "decline", "correction"],
    "earnings": ["earnings", "revenue", "guidance", "eps", "beats estimates", "misses", "forecast"],
    "macro": ["fed", "interest rate", "inflation", "cpi", "gdp", "unemployment", "quantitative easing"],
    "defi": ["defi", "yield farm", "liquidity", "amm", "staking", "governance", "dao"],
    "partnership": ["partnership", "collaboration", "integration", "acquired", "merger"],
    "security": ["hack", "exploit", "vulnerability", "breach", "stolen", "compromised"],
}

# Common ticker regex patterns
TICKER_PATTERN = re.compile(r'\b([A-Z]{1,5})\b')

# Stop words for keyword extraction
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "this", "that", "it", "its", "i", "you", "he", "she", "we", "they",
    "not", "no", "do", "does", "did", "have", "has", "had", "will", "would",
    "can", "could", "may", "might", "must", "should", "what", "which",
    "who", "whom", "when", "where", "why", "how", "all", "each", "every",
    "both", "few", "many", "much", "some", "any", "more", "most", "other",
    "said", "says", "according", "also", "about", "up", "out", "into",
}

# Known stock/crypto tickers to validate against (subset)
KNOWN_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", "BAC",
    "WMT", "V", "MA", "DIS", "NFLX", "CRM", "ORCL", "INTC", "AMD", "QCOM",
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LINK", "UNI", "ATOM", "LTC", "BCH", "FIL", "NEAR", "FTT", "SHIB",
    "SPY", "QQQ", "DIA", "IWM", "TLT", "GLD", "SLV", "USO",
}


def extract_sentiment(text: str) -> dict:
    """Analyze sentiment using TextBlob.
    
    Returns sentiment_score (-1.0 to 1.0), label, and confidence.
    """
    if not text or not text.strip():
        return {
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
            "sentiment_confidence": 0.0,
        }
    
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity  # -1.0 to 1.0
    subjectivity = blob.sentiment.subjectivity  # 0.0 to 1.0
    
    # Determine label
    if polarity > 0.15:
        label = "positive"
    elif polarity < -0.15:
        label = "negative"
    else:
        label = "neutral"
    
    return {
        "sentiment_score": round(polarity, 4),
        "sentiment_label": label,
        "sentiment_confidence": round(subjectivity, 4),
    }


def extract_tickers(text: str) -> list[str]:
    """Extract stock and crypto tickers from text.
    
    Validates against known ticker symbols to reduce false positives.
    """
    if not text:
        return []
    
    # Find all potential tickers (1-5 uppercase letters)
    candidates = set(TICKER_PATTERN.findall(text))
    
    # Filter to known tickers only
    found = [t for t in candidates if t in KNOWN_TICKERS]
    
    return sorted(found)


def extract_market_signals(text: str) -> list[str]:
    """Identify market-moving signal categories from article text."""
    if not text:
        return []
    
    text_lower = text.lower()
    signals = []
    
    for signal_category, keywords in MARKET_SIGNALS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                if signal_category not in signals:
                    signals.append(signal_category)
                break
    
    return signals


def extract_key_phrases(text: str, max_phrases: int = 10) -> list[str]:
    """Extract key phrases/nouns from text using simple NLP."""
    if not text:
        return []
    
    blob = TextBlob(text)
    phrases = []
    
    for np in blob.noun_phrases:
        words = np.split()
        # Filter out stop words and very short phrases
        meaningful = [w for w in words if w.lower() not in STOP_WORDS and len(w) > 2]
        if meaningful:
            phrases.append(np)
    
    return phrases[:max_phrases]


def extract_named_entities(text: str) -> list[str]:
    """Simple named entity extraction (company/org patterns)."""
    if not text:
        return []
    
    entities = []
    
    # Pattern: proper noun sequences (e.g., "Goldman Sachs", "Federal Reserve")
    for match in re.finditer(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text):
        candidate = match.group(0)
        # Filter common false positives
        if candidate.lower().split()[0] not in STOP_WORDS and len(candidate) > 4:
            entities.append(candidate)
    
    return list(dict.fromkeys(entities))[:15]  # Deduplicate, limit


def calculate_market_impact(
    sentiment_score: float,
    signal_count: int,
    ticker_count: int,
    source_trust: int = 1,
) -> float:
    """Calculate market impact score (0.0 to 1.0).
    
    Higher score = more likely to move markets.
    Factors: sentiment extremity, number of signals, ticker density.
    """
    # Sentiment magnitude contribution (0-0.3)
    sentiment_magnitude = abs(sentiment_score) * 0.3
    
    # Signal density contribution (0-0.4)
    signal_contribution = min(signal_count * 0.1, 0.4)
    
    # Ticker relevance (0-0.2)
    ticker_contribution = min(ticker_count * 0.05, 0.2)
    
    # Source trust multiplier (0.5-1.0)
    trust_multipliers = {1: 1.0, 2: 0.9, 3: 0.7}
    trust_multiplier = trust_multipliers.get(source_trust, 0.5)
    
    raw = (sentiment_magnitude + signal_contribution + ticker_contribution) * trust_multiplier
    return round(min(max(raw, 0.0), 1.0), 4)


def analyze_article(
    title: str,
    content: str = "",
    source_trust: int = 1,
    model_version: str = "v1",
) -> dict:
    """Full NLP analysis pipeline for a single article.
    
    Returns a dict matching SignalAnalysis schema fields.
    """
    combined_text = f"{title}. {content}" if content else title
    
    # Sentiment analysis
    sentiment = extract_sentiment(combined_text)
    
    # Ticker extraction
    tickers = extract_tickers(combined_text)
    
    # Market signals
    signals = extract_market_signals(combined_text)
    
    # Key phrases
    phrases = extract_key_phrases(combined_text)
    
    # Named entities
    entities = extract_named_entities(combined_text)
    
    # Market impact
    impact = calculate_market_impact(
        sentiment["sentiment_score"],
        len(signals),
        len(tickers),
        source_trust,
    )
    
    return {
        **sentiment,
        "market_signals": ",".join(signals) if signals else None,
        "market_impact_score": impact,
        "mentioned_tickers": ",".join(tickers) if tickers else None,
        "key_phrases": json.dumps(phrases) if phrases else None,
        "named_entities": json.dumps(entities) if entities else None,
        "model_version": model_version,
    }
