from app.services.nlp.analyzer import (
    extract_sentiment,
    extract_tickers,
    extract_market_signals,
    extract_key_phrases,
    extract_named_entities,
    calculate_market_impact,
    analyze_article,
)


def test_sentiment_positive():
    result = extract_sentiment("The market is booming with incredible growth and profits.")
    assert result["sentiment_label"] == "positive"
    assert result["sentiment_score"] > 0


def test_sentiment_negative():
    result = extract_sentiment("Stocks crashed amid terrible losses and fear.")
    assert result["sentiment_label"] == "negative"
    assert result["sentiment_score"] < 0


def test_sentiment_neutral():
    result = extract_sentiment("The company announced a meeting on Tuesday.")
    assert result["sentiment_label"] == "neutral"


def test_sentiment_empty():
    result = extract_sentiment("")
    assert result["sentiment_label"] == "neutral"
    assert result["sentiment_score"] == 0.0


def test_tickers_stock():
    result = extract_tickers("AAPL and MSFT shares rose, while TSLA fell 5% today")
    assert "AAPL" in result
    assert "MSFT" in result
    assert "TSLA" in result


def test_tickers_crypto():
    result = extract_tickers("BTC surged past $60k while ETH followed. SOL and BNB also gained.")
    assert "BTC" in result
    assert "ETH" in result
    assert "SOL" in result


def test_tickers_unknown_filtered():
    """Unknown uppercase words should not be matched as tickers."""
    result = extract_tickers("The QWERTY company and ZZZZZ stock moved today")
    assert "QWERTY" not in result
    assert "ZZZZZ" not in result


def test_tickers_empty():
    result = extract_tickers("")
    assert result == []


def test_market_signals_bull():
    result = extract_market_signals("Stocks rally to all-time high with strong breakout momentum")
    assert "bull_run" in result


def test_market_signals_crash():
    result = extract_market_signals("Market crash fears grow amid recession and correction")
    assert "crash_risk" in result


def test_market_signals_defi():
    result = extract_market_signals("DeFi yield farming and staking protocols see record liquidity")
    assert "defi" in result


def test_market_signals_multiple():
    result = extract_market_signals(
        "Fed raises interest rate causing inflation concerns; "
        "stocks rally despite recession signals"
    )
    assert "macro" in result
    assert "crash_risk" in result
    assert "bull_run" in result


def test_market_signals_empty():
    result = extract_market_signals("")
    assert result == []


def test_key_phrases_nontrivial():
    result = extract_key_phrases(
        "The Federal Reserve announced interest rate hikes "
        "affecting corporate bond yields and market liquidity"
    )
    assert len(result) > 0


def test_key_phrases_empty():
    result = extract_key_phrases("")
    assert result == []


def test_named_entities():
    result = extract_named_entities("Goldman Sachs and Federal Reserve met at Wall Street")
    assert len(result) > 0


def test_named_entities_empty():
    result = extract_named_entities("")
    assert result == []


def test_market_impact_extreme_negative():
    score = calculate_market_impact(
        sentiment_score=-0.9, signal_count=5, ticker_count=4, source_trust=1
    )
    assert score > 0.5


def test_market_impact_neutral():
    score = calculate_market_impact(
        sentiment_score=0.0, signal_count=0, ticker_count=0, source_trust=1
    )
    assert score == 0.0


def test_market_impact_bounds():
    """Impact score should always be between 0 and 1."""
    score = calculate_market_impact(1.0, 10, 20, 1)
    assert 0 <= score <= 1


def test_analyze_article_full():
    result = analyze_article(
        title="Breaking: Fed Raises Rates, Stocks Crash Amid Bear Market Fears",
        content=(
            "The Federal Reserve announced an emergency rate hike today. "
            "BTC and ETH prices plummeted. Goldman Sachs warned of recession risks. "
            "AAPL, MSFT, and NVDA shares down 10%. This could be the biggest crash in years."
        ),
        source_trust=1,
    )
    assert result["sentiment_label"] == "negative" or result["sentiment_label"] == "neutral"
    assert result["sentiment_score"] is not None
    assert isinstance(result["market_signals"], str)
    assert "crash_risk" in result["market_signals"]
    assert result["mentioned_tickers"] is not None
    assert "BTC" in result["mentioned_tickers"]
    assert result["market_impact_score"] > 0
    assert result["model_version"] == "v1"


def test_analyze_article_empty_content():
    """Article with only a title should still produce analysis."""
    result = analyze_article(title="Market Update", content="")
    assert result["sentiment_score"] is not None
    assert result["market_impact_score"] is not None


def test_analyze_article_none_content():
    result = analyze_article(title="Market Update", content=None)
    assert result["sentiment_score"] is not None
