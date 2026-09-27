import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# Page configuration for mobile viewports
st.set_page_config(page_title="Spready", page_icon="📈", layout="centered")

st.title("📈 Spready")
st.caption("ROIC - WACC Spread Screener")

@st.cache_data(ttl=3600)
def fetch_risk_free_rate():
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1]) / 100
    except Exception:
        pass
    return 0.045  # Standard fallback

@st.cache_data(ttl=1800)
def calculate_metrics(ticker_symbol, rf_rate, market_return=0.10):
    stock = yf.Ticker(ticker_symbol.strip())
    info = stock.info
    financials = stock.financials
    balance_sheet = stock.balance_sheet

    if financials.empty or balance_sheet.empty:
        raise ValueError("Missing statements")

    # --- ROIC Calculation ---
    ebit = financials.loc['EBIT'].iloc[0]
    try:
        pretax = financials.loc['Pretax Income'].iloc[0]
        tax_prov = financials.loc['Tax Provision'].iloc[0]
        tax_rate = tax_prov / pretax if pretax > 0 else 0.21
    except Exception:
        tax_rate = 0.21

    nopat = ebit * (1 - tax_rate)

    total_debt = balance_sheet.loc['Total Debt'].iloc[0] if 'Total Debt' in balance_sheet.index else 0
    equity = balance_sheet.loc['Stockholders Equity'].iloc[0]
    cash = balance_sheet.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in balance_sheet.index else 0

    invested_capital = total_debt + equity - cash
    if invested_capital <= 0:
        return None

    roic = nopat / invested_capital

    # --- WACC Calculation ---
    beta = info.get('beta')
    beta = float(beta) if beta is not None else 1.0
    cost_of_equity = rf_rate + beta * (market_return - rf_rate)

    interest = financials.loc['Interest Expense'].iloc[0] if 'Interest Expense' in financials.index else 0
    cost_of_debt = (interest / total_debt) if total_debt > 0 else 0.0

    market_cap = info.get('marketCap', equity)
    total_capital = market_cap + total_debt

    weight_eq = market_cap / total_capital if total_capital > 0 else 1.0
    weight_dt = total_debt / total_capital if total_capital > 0 else 0.0

    wacc = (weight_eq * cost_of_equity) + (weight_dt * cost_of_debt * (1 - tax_rate))
    spread = roic - wacc

    return {
        "Ticker": ticker_symbol.strip().upper(),
        "ROIC (%)": round(roic * 100, 2),
        "WACC (%)": round(wacc * 100, 2),
        "Spread (%)": round(spread * 100, 2)
    }

# Input Form
with st.form("screener_form"):
    ticker_input = st.text_input(
        "Enter US Tickers (comma or space separated):",
        value="FAST, WSO, ENSG, APH, MSFT"
    )
    submitted = st.form_submit_button("Calculate Spreads", use_container_width=True)

if submitted or ticker_input:
    # Clean and split tickers
    raw_tickers = ticker_input.replace(",", " ").split()
    tickers = [t.upper().strip() for t in raw_tickers if t.strip()]

    if tickers:
        with st.spinner("Pulling filings and yields..."):
            rf_rate = fetch_risk_free_rate()
            results = []
            failed = []

            for sym in tickers:
                try:
                    res = calculate_metrics(sym, rf_rate)
                    if res:
                        results.append(res)
                    else:
                        failed.append(sym)
                except Exception:
                    failed.append(sym)

        if results:
            df = pd.DataFrame(results).sort_values(by="Spread (%)", ascending=False).reset_index(drop=True)

            # Mobile-optimized table styling
            st.dataframe(
                df.style.map(
                    lambda v: "color: #00c853; font-weight: bold;" if v > 0 else "color: #d50000; font-weight: bold;",
                    subset=["Spread (%)"]
                ),
                use_container_width=True,
                hide_index=True
            )

        if failed:
            st.caption(f"Could not compute data for: {', '.join(failed)}")
    else:
        st.warning("Please enter at least one ticker.")
